"""Minimal unit tests for feature functions on synthetic spike trains with
known ground-truth statistics (MFR/ISI), to catch silent numeric errors.

Currently placeholders (xfail) since src/features/spike_train.py is not
implemented yet — un-skip as each function lands.
"""
import numpy as np
import pytest


def test_synthetic_regular_spike_train_mfr():
    """A perfectly regular 10 Hz spike train over 10s should have MFR == 10 Hz."""
    spike_times = np.arange(0, 10, 0.1)  # 100 spikes over 10s = 10 Hz
    pytest.xfail("compute_spike_train_features not yet implemented (Stage 2)")

    from src.features.spike_train import compute_spike_train_features

    features = compute_spike_train_features(spike_times, config={})
    assert features["mfr_hz"] == pytest.approx(10.0, rel=1e-6)
    assert features["isi_cv"] == pytest.approx(0.0, abs=1e-6)
