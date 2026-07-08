"""Stage 5 — canonical cortical reference signature + manifold.

On robust features only: canonical human cortical-organoid phenotype with
cross-lab confidence intervals as a function of DIV. Unsupervised UMAP
embedding (optionally CEBRA with DIV as auxiliary) -> reference manifold of
cortical maturation; save the fitted transform for projecting future
datasets. Stretch (001603 only): protosequence structure.

Not yet implemented — gated behind Stage 4.
"""
from __future__ import annotations


def compute_reference_signature(harmonized_matrix, robust_features, config: dict):
    raise NotImplementedError


def fit_reference_manifold(harmonized_matrix, robust_features, config: dict):
    raise NotImplementedError
