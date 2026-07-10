"""Stage 2.2 — network features.

Population network-burst rate/duration/participation (MEA-NAP's Bakkum
ISI_N detector, same as used in Stage 1); pairwise STTC connectivity and
probabilistic-thresholded functional-connectivity graph (MEA-NAP's own
validated implementations, reused directly rather than reimplemented --
see meanap.pipeline.sttc / probabilistic_threshold, both already checked
against MATLAB reference output per external/MEA-NAP's own test suite);
graph metrics (degree, strength, density, clustering coefficient,
characteristic path length, global/local efficiency) on the thresholded
graph, computed at each of config's `network.sttc_lag_ms` lags.

Modularity (Louvain) and small-worldness are available in MEA-NAP's own
network_metrics.py/modularity.py but not yet wired in here -- deterministic
metrics first, per the project's staged build-out (see commit history).
"""
from __future__ import annotations

import numpy as np

from meanap.pipeline.firing_rates import firing_rates_bursts
from meanap.pipeline.network_metrics import (
    charpath,
    clustering_coef_wu,
    density_und,
    distance_wei,
    efficiency_wei_global,
    efficiency_wei_local,
    find_node_deg_edge_weight,
    strengths_und,
    weight_conversion_lengths,
)
from meanap.pipeline.probabilistic_threshold import adjm_thr
from meanap.params import Params

from src.config import require


def compute_network_bursts(spike_times_dict: dict[int, np.ndarray], n_units: int, fs: float, duration_s: float) -> dict:
    """Population-level network burst stats via MEA-NAP's Bakkum ISI_N detector."""
    p = Params(fs=fs)
    ephys = firing_rates_bursts(spike_times_dict, n_units, fs, duration_s, p)
    return {
        "network_burst_rate_per_min": ephys.get("NBurstRate"),
        "network_burst_count": ephys.get("numNbursts"),
        "mean_network_burst_duration_s": ephys.get("meanNBstLengthS"),
        "mean_units_per_network_burst": ephys.get("meanNumChansInvolvedInNbursts"),
        "frac_spikes_in_network_bursts": ephys.get("fracInNburst"),
    }


def compute_sttc_matrix(
    spike_times_dict: dict[int, np.ndarray], n_units: int, lag_ms: float, config: dict, fs: float, duration_s: float,
    rng: np.random.Generator | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    """Raw + probabilistically-thresholded STTC adjacency matrix at one lag."""
    tail = require(config, "network.surrogate_control.tail")
    n_surrogates = require(config, "network.surrogate_control.n_surrogates")
    adj_raw, adj_thr = adjm_thr(spike_times_dict, n_units, lag_ms, tail, fs, duration_s, n_surrogates, rng)
    return adj_raw, adj_thr


def compute_graph_metrics(adj_thr: np.ndarray) -> dict:
    """Deterministic graph metrics on an already-thresholded adjacency matrix."""
    n = adj_thr.shape[0]
    if n < 2 or not np.any(adj_thr > 0):
        return {
            "mean_degree": np.nan, "mean_strength": np.nan, "density": np.nan,
            "mean_clustering_coef": np.nan, "char_path_length": np.nan,
            "global_efficiency": np.nan, "mean_local_efficiency": np.nan,
        }
    nd, _mew = find_node_deg_edge_weight(adj_thr)
    ns = strengths_und(adj_thr)
    density = density_und(adj_thr)
    cc = clustering_coef_wu(adj_thr)
    length_mat = weight_conversion_lengths(adj_thr)
    dist = distance_wei(length_mat)
    pl, _ecc = charpath(dist)
    global_eff = efficiency_wei_global(adj_thr)
    local_eff = efficiency_wei_local(adj_thr)
    return {
        "mean_degree": float(np.mean(nd)),
        "mean_strength": float(np.mean(ns)),
        "density": float(density),
        "mean_clustering_coef": float(np.nanmean(cc)),
        "char_path_length": float(pl),
        "global_efficiency": float(global_eff),
        "mean_local_efficiency": float(np.nanmean(local_eff)),
    }


def compute_network_features(
    spike_times_dict: dict[int, np.ndarray], n_units: int, fs: float, duration_s: float, config: dict,
    rng: np.random.Generator | None = None,
) -> dict:
    """Full network feature block for one recording: population bursts +
    STTC-graph metrics at every configured lag (key suffix `_{lag}ms`)."""
    if rng is None:
        seed = require(config, "reproducibility.random_seed")
        rng = np.random.default_rng(seed)

    result = {f"network__{k}": v for k, v in compute_network_bursts(spike_times_dict, n_units, fs, duration_s).items()}

    lags = require(config, "network.sttc_lag_ms")
    for lag_ms in lags:
        _adj_raw, adj_thr = compute_sttc_matrix(spike_times_dict, n_units, lag_ms, config, fs, duration_s, rng)
        metrics = compute_graph_metrics(adj_thr)
        result.update({f"network__{k}_{lag_ms}ms": v for k, v in metrics.items()})
    return result
