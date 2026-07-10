"""Stage 2.1 — single-unit / spike-train features.

MFR, ISI mean/CV/skew, % spikes in bursts, intra-burst frequency, burst
rate/duration/spikes-per-burst (Max-Interval method), local variation Lv
(Elephant). Aggregated per recording (mean + dispersion across units).

Spike source (deposited Kilosort2 Units vs self-derived curated `lupin`
sorting) is a per-recording upstream decision -- see
config/params.yaml `spike_detection` and
outputs/reports/stage1_validation.md "Closing decision". This module only
consumes spike times; it doesn't care where they came from, but callers
must carry the `spike_source` label through to the feature matrix.
"""
from __future__ import annotations

import numpy as np
from elephant.statistics import lv as elephant_lv
from scipy.stats import skew

from src.config import require


def _detect_bursts_max_interval(spike_times_s: np.ndarray, config: dict) -> list[tuple[int, int]]:
    """Max-Interval burst detection on a single unit's spike train.

    Returns a list of (start_index, end_index) inclusive index pairs into
    spike_times_s, one per detected burst.

    Algorithm (standard NeuroExplorer/Axion "Max Interval" method, see
    config/params.yaml burst_detection comment for the literature source):
    1. Find "core" runs of consecutive spikes with ISI <= max_isi_start_ms.
    2. Extend each core backward/forward while the next ISI <= max_isi_end_ms
       (a looser threshold, so a burst can survive one slightly larger gap).
    3. Keep only cores meeting min_spikes_per_burst and min_burst_duration_ms.
    """
    max_isi_start_s = require(config, "burst_detection.max_isi_start_ms") / 1000.0
    max_isi_end_s = require(config, "burst_detection.max_isi_end_ms") / 1000.0
    min_spikes = require(config, "burst_detection.min_spikes_per_burst")
    min_duration_s = require(config, "burst_detection.min_burst_duration_ms") / 1000.0

    n = len(spike_times_s)
    if n < 2:
        return []

    isis = np.diff(spike_times_s)

    # Step 1: core runs where consecutive ISI <= max_isi_start_s
    cores: list[tuple[int, int]] = []
    i = 0
    while i < len(isis):
        if isis[i] <= max_isi_start_s:
            start = i
            while i < len(isis) and isis[i] <= max_isi_start_s:
                i += 1
            cores.append((start, i))  # spike indices [start, i] form the core
        else:
            i += 1

    # Step 2: extend each core using the looser end threshold
    bursts = []
    for start, end in cores:
        while start > 0 and isis[start - 1] <= max_isi_end_s:
            start -= 1
        while end < len(isis) and isis[end] <= max_isi_end_s:
            end += 1
        bursts.append((start, end))

    # Merge any now-overlapping bursts (extension can make adjacent cores collide)
    bursts.sort()
    merged: list[list[int]] = []
    for s, e in bursts:
        if merged and s <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], e)
        else:
            merged.append([s, e])

    # Step 3: filter by min spikes / duration
    result = []
    for s, e in merged:
        n_spikes_in_burst = e - s + 1
        duration = spike_times_s[e] - spike_times_s[s]
        if n_spikes_in_burst >= min_spikes and duration >= min_duration_s:
            result.append((s, e))
    return result


def compute_spike_train_features(spike_times_s, duration_s: float, config: dict) -> dict:
    """Single-unit spike-train features. `spike_times_s` in seconds.

    Returns a dict of scalar features for this one unit. Use
    aggregate_spike_train_features() to combine many units into a
    recording-level summary (mean + dispersion).
    """
    spike_times_s = np.asarray(spike_times_s, dtype=float)
    n_spikes = len(spike_times_s)

    mfr_hz = n_spikes / duration_s if duration_s > 0 else np.nan

    if n_spikes >= 2:
        isis = np.diff(spike_times_s)
        isi_mean_s = float(np.mean(isis))
        isi_std_s = float(np.std(isis, ddof=1)) if n_spikes >= 3 else np.nan
        isi_cv = isi_std_s / isi_mean_s if (isi_mean_s > 0 and not np.isnan(isi_std_s)) else np.nan
        isi_skew = float(skew(isis)) if n_spikes >= 3 else np.nan
        local_variation = float(elephant_lv(isis)) if n_spikes >= 3 else np.nan
    else:
        isi_mean_s = isi_cv = isi_skew = local_variation = np.nan

    bursts = _detect_bursts_max_interval(spike_times_s, config)
    n_bursts = len(bursts)
    burst_rate_hz = n_bursts / duration_s if duration_s > 0 else np.nan

    if n_bursts > 0:
        burst_durations_s = np.array([spike_times_s[e] - spike_times_s[s] for s, e in bursts])
        spikes_per_burst = np.array([e - s + 1 for s, e in bursts])
        n_spikes_in_bursts = int(np.sum(spikes_per_burst))
        pct_spikes_in_bursts = 100.0 * n_spikes_in_bursts / n_spikes if n_spikes > 0 else np.nan
        # intra-burst frequency: (spikes-1)/duration for each burst, averaged
        with np.errstate(divide="ignore", invalid="ignore"):
            intra_burst_freqs = np.where(
                burst_durations_s > 0, (spikes_per_burst - 1) / burst_durations_s, np.nan
            )
        intra_burst_freq_hz = float(np.nanmean(intra_burst_freqs))
        mean_burst_duration_s = float(np.mean(burst_durations_s))
        mean_spikes_per_burst = float(np.mean(spikes_per_burst))
    else:
        pct_spikes_in_bursts = 0.0
        intra_burst_freq_hz = np.nan
        mean_burst_duration_s = np.nan
        mean_spikes_per_burst = np.nan

    return {
        "n_spikes": n_spikes,
        "mfr_hz": mfr_hz,
        "isi_mean_s": isi_mean_s,
        "isi_cv": isi_cv,
        "isi_skew": isi_skew,
        "local_variation": local_variation,
        "pct_spikes_in_bursts": pct_spikes_in_bursts,
        "intra_burst_freq_hz": intra_burst_freq_hz,
        "burst_rate_hz": burst_rate_hz,
        "mean_burst_duration_s": mean_burst_duration_s,
        "mean_spikes_per_burst": mean_spikes_per_burst,
        "n_bursts": n_bursts,
    }


_SCALAR_FEATURE_KEYS = [
    "mfr_hz", "isi_mean_s", "isi_cv", "isi_skew", "local_variation",
    "pct_spikes_in_bursts", "intra_burst_freq_hz", "burst_rate_hz",
    "mean_burst_duration_s", "mean_spikes_per_burst",
]


def aggregate_spike_train_features(per_unit_features: list[dict]) -> dict:
    """Recording-level summary: mean + dispersion (std) across units for each
    scalar feature, plus a few recording-level totals. NaN policy: units
    with too few spikes to compute a given feature (e.g. ISI CV needs >=3
    spikes) contribute NaN for that feature only, excluded via nanmean/nanstd
    -- not dropped from the recording entirely (documented per the handoff's
    "handle NaNs explicitly" requirement).
    """
    result: dict = {
        "n_units": len(per_unit_features),
        "total_spikes": int(sum(f["n_spikes"] for f in per_unit_features)),
    }
    for key in _SCALAR_FEATURE_KEYS:
        values = np.array([f[key] for f in per_unit_features], dtype=float)
        result[f"{key}_mean"] = float(np.nanmean(values)) if len(values) else np.nan
        result[f"{key}_std"] = float(np.nanstd(values, ddof=1)) if np.sum(~np.isnan(values)) >= 2 else np.nan
    return result
