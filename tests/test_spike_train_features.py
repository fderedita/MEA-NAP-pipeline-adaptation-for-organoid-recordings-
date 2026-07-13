"""Minimal unit tests for feature functions on synthetic spike trains with
known ground-truth statistics (MFR/ISI), to catch silent numeric errors.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
import pytest

from src.features.spike_train import (
    aggregate_spike_train_features,
    compute_spike_train_features,
    detect_bursts_meanap_isin_batch,
)

CONFIG = {
    "burst_detection": {
        "method": "max_interval",
        "max_isi_start_ms": 100,
        "max_isi_end_ms": 200,
        "min_spikes_per_burst": 5,
        "min_burst_duration_ms": 50,
    }
}

# meanap_isi_n is the production default since the 2026-07-13 "unicamente
# MEA-NAP" pivot (config/params.yaml). Fixed (non-"automatic") isi_threshold
# here for deterministic tests, independent of get_isin_threshold's
# peak-finding heuristic.
CONFIG_MEANAP = {
    "burst_detection": {
        "method": "meanap_isi_n",
        "meanap_isi_n": {"min_spikes": 5, "isi_threshold": 0.1},
    }
}


def test_regular_spike_train_mfr_and_isi_cv():
    """A perfectly regular 10 Hz spike train over 10s: MFR==10Hz, ISI CV==0 (no variability)."""
    spike_times = np.arange(0, 10, 0.1)  # 100 spikes over 10s = 10 Hz, ISI = 0.1s always
    features = compute_spike_train_features(spike_times, duration_s=10.0, config=CONFIG)
    assert features["mfr_hz"] == pytest.approx(10.0, rel=1e-6)
    assert features["isi_mean_s"] == pytest.approx(0.1, rel=1e-6)
    assert features["isi_cv"] == pytest.approx(0.0, abs=1e-6)
    assert features["n_spikes"] == 100


def test_empty_spike_train():
    """No spikes: MFR is 0, ISI stats are NaN (undefined, not silently 0), no bursts."""
    features = compute_spike_train_features(np.array([]), duration_s=10.0, config=CONFIG)
    assert features["mfr_hz"] == 0.0
    assert np.isnan(features["isi_mean_s"])
    assert features["n_bursts"] == 0
    assert features["pct_spikes_in_bursts"] == 0.0


def test_single_synthetic_burst_detected():
    """5 spikes 20ms apart (well within max_isi_start), then a long silent
    gap, then 5 more spikes 20ms apart -- exactly 2 bursts of 5 spikes each,
    100% of spikes in bursts.
    """
    burst1 = np.arange(0, 5) * 0.02          # 0, 0.02, 0.04, 0.06, 0.08
    burst2 = burst1 + 5.0                     # same shape, 5s later (way past max_isi_end)
    spike_times = np.concatenate([burst1, burst2])
    features = compute_spike_train_features(spike_times, duration_s=10.0, config=CONFIG)
    assert features["n_bursts"] == 2
    assert features["mean_spikes_per_burst"] == pytest.approx(5.0)
    assert features["pct_spikes_in_bursts"] == pytest.approx(100.0)
    # burst duration = time from 1st to 5th spike = 0.08s
    assert features["mean_burst_duration_s"] == pytest.approx(0.08, rel=1e-6)


def test_no_bursts_when_isis_too_large():
    """Spikes spaced 500ms apart (well beyond max_isi_end=200ms) -> no bursts at all."""
    spike_times = np.arange(0, 5, 0.5)
    features = compute_spike_train_features(spike_times, duration_s=5.0, config=CONFIG)
    assert features["n_bursts"] == 0
    assert features["pct_spikes_in_bursts"] == 0.0


def test_meanap_isin_two_well_separated_bursts_detected():
    """Two well-separated 8-spike groups (20ms apart within a group, 5s gap
    between groups) via the meanap_isi_n backend (production default since
    2026-07-13, see config/params.yaml burst_detection). Uses 8 spikes/group
    (not 5, the min_spikes floor) because the ISI_N sliding-window algorithm
    needs headroom above min_spikes for its burst-length counter to reach
    min_spikes before the boundary crossing, or it fails to split -- an
    inherent property of Bakkum's algorithm (verified empirically against
    meanap.pipeline.burst_detection.burst_detect_isin directly), not a
    concern with exactly-min_spikes-sized bursts in real recordings. Exact
    per-burst spike counts are asymmetric (5 + 7, not 8 + 8) because the
    algorithm assigns the boundary-ambiguous first spike of the second
    group to whichever burst reaches min_spikes first -- expected behavior
    of this method, not asserted as a fixed split point since it's an
    algorithm-internal detail, not a semantic guarantee."""
    burst1 = np.arange(0, 8) * 0.02
    burst2 = burst1 + 5.0
    spike_times = np.concatenate([burst1, burst2])
    features = compute_spike_train_features(spike_times, duration_s=10.0, config=CONFIG_MEANAP)
    assert features["n_bursts"] == 2
    assert features["pct_spikes_in_bursts"] == pytest.approx(75.0)


def test_meanap_isin_no_bursts_when_isis_too_large():
    """Spikes spaced 500ms apart, well beyond the 0.1s isi_threshold -> no bursts."""
    spike_times = np.arange(0, 5, 0.5)
    features = compute_spike_train_features(spike_times, duration_s=5.0, config=CONFIG_MEANAP)
    assert features["n_bursts"] == 0
    assert features["pct_spikes_in_bursts"] == 0.0


def test_meanap_isin_batch_matches_standalone_per_channel():
    """detect_bursts_meanap_isin_batch (the primary path, called once per
    recording by the build_feature_matrix* orchestrators) must give the
    same per-channel result as the standalone single-unit fallback --
    both ultimately call the same MEA-NAP function
    (single_channel_burst_detection / burst_detect_isin), just batched vs.
    per-unit, so results should be identical, not just similar."""
    ch0 = np.arange(0, 8) * 0.02
    ch1 = np.arange(0, 5) * 0.5  # too sparse to burst under this threshold
    spike_times_dict = {0: ch0, 1: ch1}

    batch = detect_bursts_meanap_isin_batch(spike_times_dict, n_channels=2, fs=20000.0, duration_s=10.0, config=CONFIG_MEANAP)

    feats_ch0_batch = compute_spike_train_features(ch0, duration_s=10.0, config=CONFIG_MEANAP, burst_info=batch[0])
    feats_ch0_standalone = compute_spike_train_features(ch0, duration_s=10.0, config=CONFIG_MEANAP)
    assert feats_ch0_batch["n_bursts"] == feats_ch0_standalone["n_bursts"]
    assert feats_ch0_batch["pct_spikes_in_bursts"] == pytest.approx(feats_ch0_standalone["pct_spikes_in_bursts"])

    feats_ch1_batch = compute_spike_train_features(ch1, duration_s=10.0, config=CONFIG_MEANAP, burst_info=batch[1])
    assert feats_ch1_batch["n_bursts"] == 0


def test_aggregate_across_units_mean_and_nan_handling():
    """Aggregation takes mean/std across units and doesn't let NaN (e.g. from
    a unit with too few spikes for ISI CV) poison the whole recording.
    """
    unit_a = compute_spike_train_features(np.arange(0, 10, 0.1), duration_s=10.0, config=CONFIG)  # 10Hz regular
    unit_b = compute_spike_train_features(np.array([1.0]), duration_s=10.0, config=CONFIG)  # single spike, NaN ISI stats
    agg = aggregate_spike_train_features([unit_a, unit_b])
    assert agg["n_units"] == 2
    # unit_b contributes 0.1 Hz MFR (1 spike / 10s); mean of [10.0, 0.1]
    assert agg["mfr_hz_mean"] == pytest.approx((10.0 + 0.1) / 2, rel=1e-6)
    # isi_cv is NaN for unit_b (needs >=3 spikes) -- mean should just be unit_a's value, not NaN
    assert agg["isi_cv_mean"] == pytest.approx(0.0, abs=1e-6)
