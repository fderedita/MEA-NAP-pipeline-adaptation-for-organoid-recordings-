"""Stage 2 orchestrator — assembles outputs/features/feature_matrix.parquet.

One row per recording, columns = features from spike_train/network/spectral/
complexity + metadata: dataset(lab/platform), organoid_id, DIV, well_id,
spike_source in {deposited, self-derived}, raw_provenance. Applies the same
active-electrode criterion to both datasets (from Stage 0 Task 0.4). NaN
policy must be explicit and documented, never a silent drop.

Not yet implemented — gated behind Stage 1 validation (Checkpoint C).
"""
from __future__ import annotations


def build_feature_matrix(manifest, config: dict):
    raise NotImplementedError
