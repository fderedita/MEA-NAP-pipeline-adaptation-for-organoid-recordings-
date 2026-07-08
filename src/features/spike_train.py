"""Stage 2.1 — single-unit / spike-train features.

MFR, ISI mean/CV/skew, % spikes in bursts, intra-burst frequency, burst
rate/duration/spikes-per-burst (Max-Interval method), local variation Lv
(Elephant). Aggregated per recording (mean + dispersion across units).

Not yet implemented — gated behind Stage 1 validation (Checkpoint C).
"""
from __future__ import annotations


def compute_spike_train_features(spike_times, config: dict) -> dict:
    raise NotImplementedError
