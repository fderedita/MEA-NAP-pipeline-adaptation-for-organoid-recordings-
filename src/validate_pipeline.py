"""Stage 1 — pipeline validation against deposited ground truth (001603).

Loads raw recordings via spikeinterface, preprocesses per config, detects
spikes, and compares to deposited Units against the acceptance criteria in
config/params.yaml (validation.min_firing_rate_spearman_rho,
validation.max_network_burst_rate_pct_diff). If met, freezes preprocessing/
detection parameters as canonical; if not, stops for review.

Not yet implemented — gated behind Stage 0 (Checkpoint B).
"""
from __future__ import annotations


def load_raw_recording(asset_path: str):
    raise NotImplementedError


def preprocess(recording, config: dict):
    raise NotImplementedError


def detect_spikes(recording, config: dict):
    raise NotImplementedError


def compare_to_deposited_units(detected, deposited_units, config: dict):
    raise NotImplementedError
