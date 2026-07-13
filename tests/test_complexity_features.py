"""Unit tests for complexity.py on hand-constructed / synthetic data with
known ground-truth properties, to catch silent numeric errors.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
import pytest

from src.features.complexity import (
    bin_population_activity,
    compute_branching_ratio,
    compute_entropy_complexity,
    detect_avalanches,
)

CONFIG = {
    "complexity": {
        "avalanche_bin_method": "mean_iei",
        "avalanche_min_size": 1,
        "branching_ratio_method": "ratio_of_consecutive_bins",
        "entropy": {"sample_entropy_m": 2, "sample_entropy_r": 0.2},
        "lempel_ziv": {"binarization_method": "median_split"},
    }
}


def test_detect_avalanches_hand_constructed():
    """[0,2,3,0,0,1,0,5,5,5,0] -> two avalanches: sizes [5,15], durations [2,3]."""
    counts = np.array([0, 2, 3, 0, 0, 1, 0, 5, 5, 5, 0])
    result = detect_avalanches(counts, CONFIG)
    assert result["n_avalanches"] == 3
    assert list(result["sizes"]) == [5, 1, 15]
    assert list(result["durations"]) == [2, 1, 3]


def test_detect_avalanches_all_zero_gives_none():
    counts = np.zeros(10, dtype=int)
    result = detect_avalanches(counts, CONFIG)
    assert result["n_avalanches"] == 0
    assert len(result["sizes"]) == 0


def test_detect_avalanches_min_size_filter():
    """min_size=3 should drop the size-1 avalanche but keep size-5 and size-15."""
    config = {"complexity": {**CONFIG["complexity"], "avalanche_min_size": 3}}
    counts = np.array([0, 2, 3, 0, 0, 1, 0, 5, 5, 5, 0])
    result = detect_avalanches(counts, config)
    assert result["n_avalanches"] == 2
    assert list(result["sizes"]) == [5, 15]


def test_branching_ratio_known_value():
    """counts=[2,4,1,1]: every consecutive pair with a non-zero ancestor
    contributes descendant/ancestor: (2->4)=2.0, (4->1)=0.25, (1->1)=1.0.
    Mean of all three = 1.0833..."""
    counts = np.array([2, 4, 1, 1])
    ratio = compute_branching_ratio(counts, CONFIG)
    assert ratio == pytest.approx((2.0 + 0.25 + 1.0) / 3)


def test_branching_ratio_activity_dying_out():
    """counts=[1,0,1,0,1]: ancestors are bins 0 and 2 (both =1, non-zero);
    their descendants (bins 1 and 3) are both 0 -- activity died out both
    times. Ratio is well-defined (0/1=0) in both cases, not NaN -- a
    descendant of zero is a legitimate "activity died" signal, not an
    undefined case (only a zero ANCESTOR, i.e. dividing by zero, would be)."""
    counts = np.array([1, 0, 1, 0, 1])
    ratio = compute_branching_ratio(counts, CONFIG)
    assert ratio == pytest.approx(0.0)


def test_branching_ratio_undefined_when_no_nonzero_ancestor():
    """All-zero signal: no non-zero ancestor bin exists at all -> NaN (truly undefined)."""
    counts = np.zeros(5)
    ratio = compute_branching_ratio(counts, CONFIG)
    assert np.isnan(ratio)


def test_bin_population_activity_pools_across_units():
    """Two units with regular 10Hz and 5Hz firing, pooled -> bin width should
    reflect the pooled mean ISI (finer than either unit alone)."""
    spike_times_dict = {
        0: np.arange(0, 10, 0.1),   # 10Hz
        1: np.arange(0, 10, 0.2),   # 5Hz
    }
    counts, bin_s = bin_population_activity(spike_times_dict, duration_s=10.0, config=CONFIG)
    assert bin_s > 0
    assert len(counts) > 0
    assert counts.sum() == 100 + 50  # all spikes accounted for


def test_entropy_low_for_constant_signal_high_for_noise():
    """A perfectly regular alternating signal should have near-zero sample
    entropy; random noise should have higher entropy."""
    regular = np.tile([0.0, 1.0], 50)
    rng = np.random.default_rng(0)
    noisy = rng.standard_normal(100)

    regular_result = compute_entropy_complexity(regular, CONFIG)
    noisy_result = compute_entropy_complexity(noisy, CONFIG)

    assert noisy_result["sample_entropy"] > regular_result["sample_entropy"]
