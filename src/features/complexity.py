"""Stage 2.4 — complexity / criticality features.

Neuronal-avalanche detection on binned population activity (adaptive
mean-inter-event-interval binning, the standard convention since Beggs &
Plenz 2003); avalanche size/duration distributions with power-law exponent
+ goodness-of-fit (via the `powerlaw` package's Clauset-Shalizi-Newman
method); branching ratio; sample entropy and Lempel-Ziv complexity
(`antropy`) on the binned population-rate signal.
"""
from __future__ import annotations

import antropy as ant
import numpy as np
import powerlaw

from src.config import require


def bin_population_activity(spike_times_dict: dict, duration_s: float, config: dict) -> tuple[np.ndarray, float]:
    """Pool all units/channels' spike times and bin at an adaptive width
    (mean inter-event interval of the pooled train). Returns (counts, bin_width_s).
    """
    method = require(config, "complexity.avalanche_bin_method")
    if method != "mean_iei":
        raise ValueError(f"Unsupported complexity.avalanche_bin_method: {method!r}")

    non_empty = [np.asarray(st) for st in spike_times_dict.values() if len(st) > 0]
    if not non_empty:
        # No units at all, or every unit had zero spikes (e.g. nothing survived
        # curation for this recording) -- a real, expected scenario for
        # low-activity 001872 recordings, not an error to crash on.
        return np.array([]), np.nan

    all_spikes = np.sort(np.concatenate(non_empty))
    if len(all_spikes) < 2:
        return np.array([]), np.nan

    bin_s = float(np.mean(np.diff(all_spikes)))
    if bin_s <= 0 or not np.isfinite(bin_s):
        return np.array([]), np.nan

    n_bins = max(1, int(np.ceil(duration_s / bin_s)))
    edges = np.arange(n_bins + 1) * bin_s
    counts, _ = np.histogram(all_spikes, bins=edges)
    return counts, bin_s


def detect_avalanches(binned_counts: np.ndarray, config: dict) -> dict:
    """Avalanches = maximal runs of consecutive non-empty bins, bounded by
    empty bins on both sides (Beggs & Plenz 2003 definition)."""
    min_size = require(config, "complexity.avalanche_min_size")
    is_active = binned_counts > 0

    sizes, durations = [], []
    i, n = 0, len(binned_counts)
    while i < n:
        if is_active[i]:
            start = i
            while i < n and is_active[i]:
                i += 1
            size = int(np.sum(binned_counts[start:i]))
            duration = i - start
            if size >= min_size:
                sizes.append(size)
                durations.append(duration)
        else:
            i += 1

    return {"sizes": np.array(sizes, dtype=int), "durations": np.array(durations, dtype=int), "n_avalanches": len(sizes)}


def _fit_powerlaw(values: np.ndarray) -> dict:
    """Power-law exponent + Kolmogorov-Smirnov goodness-of-fit via the
    `powerlaw` package (Clauset, Shalizi & Newman 2009 method: xmin chosen
    to minimize KS distance between data and fitted model)."""
    if len(values) < 10 or len(np.unique(values)) < 3:
        return {"exponent": np.nan, "xmin": np.nan, "ks_distance": np.nan}
    try:
        fit = powerlaw.Fit(values, discrete=True, verbose=False)
        return {"exponent": float(fit.alpha), "xmin": float(fit.xmin), "ks_distance": float(fit.power_law.D)}
    except Exception:
        # powerlaw can raise on degenerate distributions (e.g. all-identical
        # values) -- treat as "couldn't fit", not a pipeline crash.
        return {"exponent": np.nan, "xmin": np.nan, "ks_distance": np.nan}


def compute_branching_ratio(binned_counts: np.ndarray, config: dict) -> float:
    """Classic Beggs & Plenz branching ratio: mean of (descendant/ancestor)
    activity ratio over every pair of consecutive non-empty bins."""
    method = require(config, "complexity.branching_ratio_method")
    if method != "ratio_of_consecutive_bins":
        raise ValueError(f"Unsupported complexity.branching_ratio_method: {method!r}")

    if len(binned_counts) < 2:
        return np.nan
    ancestors = binned_counts[:-1]
    descendants = binned_counts[1:]
    mask = ancestors > 0
    if not np.any(mask):
        return np.nan
    ratios = descendants[mask] / ancestors[mask]
    return float(np.mean(ratios))


def compute_entropy_complexity(population_rate: np.ndarray, config: dict) -> dict:
    """Sample entropy + Lempel-Ziv complexity on the binned population-rate signal."""
    m = require(config, "complexity.entropy.sample_entropy_m")
    r_frac = require(config, "complexity.entropy.sample_entropy_r")
    binarization = require(config, "complexity.lempel_ziv.binarization_method")

    population_rate = np.asarray(population_rate, dtype=float)
    std = np.std(population_rate)
    if len(population_rate) > (m + 10) and std > 0:
        samp_en = float(ant.sample_entropy(population_rate, order=m, tolerance=r_frac * std))
    else:
        samp_en = np.nan

    if binarization != "median_split":
        raise ValueError(f"Unsupported complexity.lempel_ziv.binarization_method: {binarization!r}")
    if len(population_rate) > 0 and std > 0:
        binary_seq = (population_rate > np.median(population_rate)).astype(int)
        lz = float(ant.lziv_complexity(binary_seq, normalize=True))
    else:
        lz = np.nan

    return {"sample_entropy": samp_en, "lempel_ziv_complexity": lz}


def compute_complexity_features(spike_times_dict: dict, duration_s: float, config: dict) -> dict:
    """Full complexity/criticality feature block for one recording."""
    binned_counts, bin_width_s = bin_population_activity(spike_times_dict, duration_s, config)
    if len(binned_counts) == 0:
        return {
            "bin_width_s": np.nan, "n_avalanches": 0,
            "avalanche_size_exponent": np.nan, "avalanche_size_xmin": np.nan, "avalanche_size_ks_distance": np.nan,
            "avalanche_duration_exponent": np.nan, "avalanche_duration_xmin": np.nan, "avalanche_duration_ks_distance": np.nan,
            "branching_ratio": np.nan, "sample_entropy": np.nan, "lempel_ziv_complexity": np.nan,
        }

    avalanches = detect_avalanches(binned_counts, config)
    size_fit = _fit_powerlaw(avalanches["sizes"])
    duration_fit = _fit_powerlaw(avalanches["durations"])
    branching = compute_branching_ratio(binned_counts, config)
    entropy_feats = compute_entropy_complexity(binned_counts.astype(float), config)

    return {
        "bin_width_s": bin_width_s,
        "n_avalanches": avalanches["n_avalanches"],
        "avalanche_size_exponent": size_fit["exponent"],
        "avalanche_size_xmin": size_fit["xmin"],
        "avalanche_size_ks_distance": size_fit["ks_distance"],
        "avalanche_duration_exponent": duration_fit["exponent"],
        "avalanche_duration_xmin": duration_fit["xmin"],
        "avalanche_duration_ks_distance": duration_fit["ks_distance"],
        "branching_ratio": branching,
        **entropy_feats,
    }
