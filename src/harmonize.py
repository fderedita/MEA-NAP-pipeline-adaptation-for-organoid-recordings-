"""Stage 4 — harmonization test (ComBat).

Apply ComBat (neuroCombat) with batch=dataset, DIV as covariate; compare to
within-lab z-scoring baseline. Key metric: train a classifier to predict
`dataset` from features, before vs after harmonization, under
organoid-grouped CV. Success = AUC drops from ~1.0 toward ~0.5. Confirm DIV
remains predictable after harmonization (biological signal preserved).

Not yet implemented — gated behind Stage 3.
"""
from __future__ import annotations


def apply_combat(feature_matrix, config: dict):
    raise NotImplementedError


def dataset_classifier_auc(feature_matrix, config: dict) -> float:
    raise NotImplementedError
