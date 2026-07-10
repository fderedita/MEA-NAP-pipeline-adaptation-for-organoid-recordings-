"""Stage 1 — pipeline validation against deposited ground truth (001603).

Spike detection track: MEA-NAP's Python port (threshold method), replacing
the originally-planned custom "pragmatic" CPU threshold track per the
2026-07-09 decision (see conversation log / commit history) -- MEA-NAP's
detection + burst analysis, cross-checked against MATLAB, is used directly
rather than reimplementing the same thing from scratch.

Streams the raw ElectricalSeries one channel at a time (bandpass filter +
threshold detection) rather than loading the full (n_samples, n_channels)
array into memory -- this machine is RAM-constrained and a full recording
at (3.6M samples x 1020 channels x 2 bytes) would be several GB.

Compares per-electrode firing rate and network-burst rate against the
deposited Units (spatially matched to raw electrodes via nearest-neighbor on
x_pos/y_pos, since the Units table has no explicit electrode-ID column) per
the acceptance criteria in config/params.yaml
(validation.min_firing_rate_spearman_rho, validation.max_network_burst_rate_pct_diff).
"""
from __future__ import annotations

import os
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import numpy as np
from pynwb import NWBHDF5IO
from scipy.spatial import cKDTree
from scipy.stats import spearmanr

from meanap.pipeline.spike_detection import bandpass_filter, detect_spikes_threshold, detect_spikes_wavelet
from meanap.pipeline.firing_rates import firing_rates_bursts
from meanap.params import Params

from src.config import load_config, require


def _method_kwargs_from_config(config: dict, method: str) -> dict:
    if method == "mea_nap_threshold":
        return {
            "multiplier": require(config, "spike_detection.threshold_mad_multiplier"),
            "ref_period_ms": require(config, "spike_detection.ref_period_ms"),
        }
    if method == "mea_nap_wavelet":
        return {
            "wname": require(config, "spike_detection.wavelet.name"),
            "wid_ms": tuple(require(config, "spike_detection.wavelet.wid_ms")),
            "n_scales": require(config, "spike_detection.wavelet.n_scales"),
            "cost_factor": require(config, "spike_detection.wavelet.cost_factor"),
            "option": require(config, "spike_detection.wavelet.option"),
        }
    raise ValueError(f"Unknown spike_detection.method: {method!r}")


def _process_channel_batch(
    raw_path: str, ch_indices: list[int], low: float, high: float, method: str, method_kwargs: dict
) -> dict[int, np.ndarray]:
    """Worker (runs in its own process): opens its own NWB handle, processes a batch of channels.

    HDF5 file handles aren't safely shared across process boundaries, so each
    worker opens the file independently rather than receiving an open handle.
    """
    io = NWBHDF5IO(raw_path, mode="r")
    try:
        nwbfile = io.read()
        ts = nwbfile.acquisition["ElectricalSeries"]
        fs = float(ts.rate)
        results: dict[int, np.ndarray] = {}
        for ch_idx in ch_indices:
            trace = ts.data[:, ch_idx].astype(float)
            filtered = bandpass_filter(trace, fs, low, high)
            if method == "mea_nap_threshold":
                frames, _threshold = detect_spikes_threshold(
                    filtered, method_kwargs["multiplier"], method_kwargs["ref_period_ms"], fs, filter_flag=False
                )
            else:
                frames = detect_spikes_wavelet(
                    filtered, fs, wid_ms=method_kwargs["wid_ms"], ns=method_kwargs["n_scales"],
                    option=method_kwargs["option"], L=method_kwargs["cost_factor"], wname=method_kwargs["wname"],
                )
            results[ch_idx] = frames.astype(float) / fs  # seconds
        return results
    finally:
        io.close()


def detect_spikes_full_recording(raw_path: str | Path, config: dict, n_workers: int | None = None) -> dict:
    """Per-channel spike detection over the full recording, parallelized across processes.

    Method is selected by config `spike_detection.method`
    ({mea_nap_threshold, mea_nap_wavelet}). Channels are independent, so work
    is split into `n_workers` batches, each a separate process that opens its
    own read-only NWB handle and streams its channels one at a time
    (memory-safe: no process ever holds the full (n_samples, n_channels)
    array -- this machine is RAM-constrained).

    Returns dict with: spike_times (dict[ch_idx -> np.ndarray seconds]),
    coords ((n_channels, 2) rel_x/rel_y), fs, duration_s, n_channels.
    """
    low, high = require(config, "preprocessing.bandpass_hz")
    method = require(config, "spike_detection.method")
    method_kwargs = _method_kwargs_from_config(config, method)

    if n_workers is None:
        # Conservative: each worker can transiently hold ~150-200MB (CWT
        # coefficient arrays scale with ns x n_samples for the wavelet
        # method), and this machine has been RAM-constrained (~2GB free
        # observed earlier) -- err toward fewer workers, not maximum
        # parallelism.
        n_workers = min(6, max(1, (os.cpu_count() or 4) - 2))

    io = NWBHDF5IO(str(raw_path), mode="r")
    try:
        nwbfile = io.read()
        ts = nwbfile.acquisition["ElectricalSeries"]
        fs = float(ts.rate)
        n_samples, n_channels = ts.data.shape
        duration_s = n_samples / fs

        electrodes = nwbfile.electrodes
        rel_x = np.asarray(electrodes["rel_x"][:], dtype=float)
        rel_y = np.asarray(electrodes["rel_y"][:], dtype=float)
        coords = np.column_stack([rel_x, rel_y])
    finally:
        io.close()

    chunks = [c.tolist() for c in np.array_split(np.arange(n_channels), n_workers) if len(c) > 0]

    spike_times: dict[int, np.ndarray] = {}
    with ProcessPoolExecutor(max_workers=n_workers) as executor:
        futures = [
            executor.submit(_process_channel_batch, str(raw_path), chunk, low, high, method, method_kwargs)
            for chunk in chunks
        ]
        for future in as_completed(futures):
            spike_times.update(future.result())

    return {
        "spike_times": spike_times,
        "coords": coords,
        "fs": fs,
        "duration_s": duration_s,
        "n_channels": n_channels,
    }


def load_deposited_units(units_path: str | Path) -> dict:
    """Load deposited spike-sorted Units: per-unit spike times + position + duration."""
    io = NWBHDF5IO(str(units_path), mode="r")
    try:
        nwbfile = io.read()
        units = nwbfile.units
        spike_times = list(units["spike_times"][:])
        x_pos = np.asarray(units["x_pos"][:], dtype=float)
        y_pos = np.asarray(units["y_pos"][:], dtype=float)

        duration_s = None
        if "curated_binning" in nwbfile.processing:
            t_spk_mat = nwbfile.processing["curated_binning"]["t_spk_mat"]
            if t_spk_mat.rate:
                duration_s = t_spk_mat.data.shape[0] / t_spk_mat.rate
        if duration_s is None:
            duration_s = max((st.max() for st in spike_times if len(st) > 0), default=0.0)
    finally:
        io.close()

    return {
        "spike_times": {i: st for i, st in enumerate(spike_times)},
        "coords": np.column_stack([x_pos, y_pos]),
        "duration_s": duration_s,
        "n_units": len(spike_times),
    }


def match_units_to_electrodes(unit_coords: np.ndarray, electrode_coords: np.ndarray) -> np.ndarray:
    """Nearest-neighbor spatial match: for each unit, the index of its closest electrode."""
    tree = cKDTree(electrode_coords)
    _dist, idx = tree.query(unit_coords, k=1)
    return idx


def aggregate_deposited_rate_per_electrode(
    deposited: dict, unit_to_electrode: np.ndarray, n_electrodes: int
) -> np.ndarray:
    """Sum matched units' spike counts per electrode, divide by duration -> firing rate array."""
    counts = np.zeros(n_electrodes)
    for unit_idx, st in deposited["spike_times"].items():
        counts[unit_to_electrode[unit_idx]] += len(st)
    return counts / deposited["duration_s"]


def self_derived_rate_per_electrode(detected: dict) -> np.ndarray:
    n = detected["n_channels"]
    rates = np.zeros(n)
    for ch_idx, st in detected["spike_times"].items():
        rates[ch_idx] = len(st) / detected["duration_s"]
    return rates


def network_burst_rate(spike_times: dict, n_units: int, fs: float, duration_s: float) -> float:
    """Network burst rate (bursts/min) via MEA-NAP's own Bakkum ISI_N detector."""
    p = Params(fs=fs)
    ephys = firing_rates_bursts(spike_times, n_units, fs, duration_s, p)
    return float(ephys.get("NBurstRate", 0.0))


def compare_to_deposited_units(raw_path: str | Path, units_path: str | Path, config: dict) -> dict:
    """Full per-subject comparison: self-derived (MEA-NAP threshold) vs deposited Units."""
    detected = detect_spikes_full_recording(raw_path, config)
    deposited = load_deposited_units(units_path)

    unit_to_electrode = match_units_to_electrodes(deposited["coords"], detected["coords"])
    deposited_rate = aggregate_deposited_rate_per_electrode(
        deposited, unit_to_electrode, detected["n_channels"]
    )
    self_rate = self_derived_rate_per_electrode(detected)

    rho, pval = spearmanr(self_rate, deposited_rate)

    self_burst_rate = network_burst_rate(
        detected["spike_times"], detected["n_channels"], detected["fs"], detected["duration_s"]
    )
    deposited_burst_rate = network_burst_rate(
        deposited["spike_times"], deposited["n_units"], detected["fs"], deposited["duration_s"]
    )
    if deposited_burst_rate > 0:
        burst_pct_diff = 100.0 * abs(self_burst_rate - deposited_burst_rate) / deposited_burst_rate
    else:
        burst_pct_diff = float("inf") if self_burst_rate > 0 else 0.0

    return {
        "raw_path": str(raw_path),
        "units_path": str(units_path),
        "n_electrodes": detected["n_channels"],
        "n_units": deposited["n_units"],
        "self_rate_mean_hz": float(np.mean(self_rate)),
        "deposited_rate_mean_hz": float(np.mean(deposited_rate)),
        "firing_rate_spearman_rho": float(rho),
        "firing_rate_spearman_pval": float(pval),
        "self_network_burst_rate_per_min": self_burst_rate,
        "deposited_network_burst_rate_per_min": deposited_burst_rate,
        "network_burst_rate_pct_diff": burst_pct_diff,
    }
