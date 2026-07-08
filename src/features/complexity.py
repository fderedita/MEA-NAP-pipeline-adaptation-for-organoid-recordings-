"""Stage 2.4 — complexity / criticality features.

Neuronal-avalanche detection on binned population activity; avalanche
size/duration distributions, power-law exponents + goodness (with cutoffs),
branching ratio; sample entropy and Lempel-Ziv complexity (antropy) on
population rate.

Not yet implemented — gated behind Stage 1 validation (Checkpoint C).
"""
from __future__ import annotations


def detect_avalanches(population_rate, config: dict) -> dict:
    raise NotImplementedError


def compute_branching_ratio(avalanches, config: dict) -> float:
    raise NotImplementedError


def compute_entropy_complexity(population_rate, config: dict) -> dict:
    raise NotImplementedError
