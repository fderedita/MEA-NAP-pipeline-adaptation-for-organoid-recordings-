"""Stage 2.2 — network features.

Population network-burst rate/duration/amplitude/participation; pairwise
STTC (elephant.spike_train_correlation.spike_time_tiling_coefficient);
functional-connectivity graph via STTC thresholding (threshold + surrogate
control in config); graph metrics via networkx/bctpy: mean degree, density,
clustering coefficient, characteristic path length, global efficiency,
modularity (Louvain), small-worldness sigma.

Not yet implemented — gated behind Stage 1 validation (Checkpoint C).
"""
from __future__ import annotations


def compute_network_bursts(population_spike_times, config: dict) -> dict:
    raise NotImplementedError


def compute_sttc_matrix(spike_trains, config: dict):
    raise NotImplementedError


def build_connectivity_graph(sttc_matrix, config: dict):
    raise NotImplementedError


def compute_graph_metrics(graph) -> dict:
    raise NotImplementedError
