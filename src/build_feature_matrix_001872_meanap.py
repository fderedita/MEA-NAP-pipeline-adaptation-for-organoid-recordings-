"""Stage 2 orchestrator for DANDI:001872 — MEA-NAP threshold spike source.

SUPERSEDED as the primary Stage 2 path (2026-07-13, second pivot same day):
see src/run_meanap_pipeline.py, which runs MEA-NAP's own run_pipeline()
end-to-end (Steps 1-4, including modularity/node-cartography/small-
worldness/etc. that this module's piecemeal features/network.py calls
never wired in) instead of calling individual MEA-NAP functions. Kept for
the comparison output already on disk (feature_matrix_001872_meanap.parquet
where a run got that far), not re-run -- see outputs/reports/
stage1_validation.md's "Third addendum" for the full reasoning.

Original docstring, for the historical record: 2026-07-13 policy pivot
(config/params.yaml `spike_detection`) made MEA-NAP threshold detection the
uniform default for every recording with raw available, so 001603 (HO1-HO4)
and 001872 are measured the SAME way instead of mixing deposited Units /
curated-sorter output across datasets. This module ran independently of,
and in parallel with, build_feature_matrix_001872.py's self-derived-sorting
(`lupin`) run -- separate checkpoint and output files, so neither run
interfered with the other. Both results were kept for comparison, not one
replacing the other.
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from src.build_feature_matrix import compute_spectral_features_for_recording
from src.build_feature_matrix_001872 import _RAW_FILES, _parse_filename
from src.config import load_config
from src.features.complexity import compute_complexity_features
from src.features.network import compute_network_features
from src.features.spike_train import (
    aggregate_spike_train_features,
    compute_spike_train_features,
    detect_bursts_meanap_isin_batch,
)
from src.validate_pipeline import detect_spikes_full_recording

DATA_RAW = Path(__file__).resolve().parent.parent / "data" / "raw"
FEATURES_DIR = Path(__file__).resolve().parent.parent / "outputs" / "features"


def process_meanap_recording(raw_path: str, config: dict) -> dict:
    meta = _parse_filename(Path(raw_path).name)

    detected = detect_spikes_full_recording(raw_path, config)
    spike_times_dict = detected["spike_times"]
    duration_s = detected["duration_s"]

    burst_info_by_ch = detect_bursts_meanap_isin_batch(
        spike_times_dict, detected["n_channels"], detected["fs"], duration_s, config
    )
    per_unit_features = [
        compute_spike_train_features(st, duration_s, config, burst_info=burst_info_by_ch.get(ch))
        for ch, st in spike_times_dict.items()
    ]
    spike_train_agg = aggregate_spike_train_features(per_unit_features)

    network_feats = compute_network_features(
        spike_times_dict, detected["n_channels"], detected["fs"], duration_s, config
    )
    spectral_feats = compute_spectral_features_for_recording(raw_path, config)
    complexity_feats = compute_complexity_features(spike_times_dict, duration_s, config)

    row = {
        "dataset_id": "001872",
        "recording_path": raw_path,
        "spike_source": "mea_nap_threshold",
        "duration_s": duration_s,
        "n_channels": detected["n_channels"],
        **meta,
    }
    row.update({f"spike_train__{k}": v for k, v in spike_train_agg.items()})
    row.update(network_feats)
    row.update(spectral_feats)
    row.update({f"complexity__{k}": v for k, v in complexity_feats.items()})
    return row


def main():
    config = load_config()
    FEATURES_DIR.mkdir(parents=True, exist_ok=True)

    checkpoint_path = FEATURES_DIR / "_checkpoint_001872_meanap.json"
    rows_by_key: dict[str, dict] = {}
    if checkpoint_path.exists():
        rows_by_key = json.loads(checkpoint_path.read_text(encoding="utf-8"))
        print(f"Resuming: already have {len(rows_by_key)} recordings", flush=True)

    for fname in _RAW_FILES:
        if fname in rows_by_key:
            print(f"=== {fname} === (skipping, already done)", flush=True)
            continue
        print(f"=== {fname} ===", flush=True)
        raw_path = str(DATA_RAW / fname)
        row = process_meanap_recording(raw_path, config)
        rows_by_key[fname] = row
        checkpoint_path.write_text(json.dumps(rows_by_key, indent=2, default=float), encoding="utf-8")
        print(f"  (saved checkpoint, {len(rows_by_key)}/{len(_RAW_FILES)} recordings done)", flush=True)

    df = pd.DataFrame(list(rows_by_key.values()))
    out_path = FEATURES_DIR / "feature_matrix_001872_meanap.parquet"
    df.to_parquet(out_path, index=False)
    print(f"\nWrote {out_path} ({len(df)} rows, {len(df.columns)} columns)", flush=True)


if __name__ == "__main__":
    main()
