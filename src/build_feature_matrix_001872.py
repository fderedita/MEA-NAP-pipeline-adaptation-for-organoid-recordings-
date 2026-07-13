"""Stage 2 orchestrator for DANDI:001872 — self-derived spike source (no
deposited Units exist for this dataset). Mirrors build_feature_matrix.py's
structure but every recording goes through curated `lupin` sorting
(src.self_derived_sorting.run_curated_sorting) first.

Massively more expensive than the 001603 (deposited-Units) path: full-scale
sorting alone is estimated at 30+ hours total across all 15 mirrored
recordings (some are 1020 channels x 600s, 3.3x HO1's duration -- see
conversation log / commit history for the per-file estimate this is based
on). Checkpointed at two levels: the sorter's own output folder (skips
re-sorting on restart) and a JSON checkpoint after every recording's full
feature set is computed (skips re-deriving features on restart). Expected
to run over multiple sessions/days, not one sitting.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pandas as pd

from src.build_feature_matrix import compute_spectral_features_for_recording
from src.config import load_config
from src.features.complexity import compute_complexity_features
from src.features.network import compute_network_features
from src.features.spike_train import aggregate_spike_train_features, compute_spike_train_features
from src.self_derived_sorting import run_curated_sorting

DATA_RAW = Path(__file__).resolve().parent.parent / "data" / "raw"
FEATURES_DIR = Path(__file__).resolve().parent.parent / "outputs" / "features"

_RAW_FILES = [
    "sub-sample-well000_ses-20260622T175109_ecephys.nwb",
    "sub-sample-well000_ses-20260622T195034_ecephys.nwb",
    "sub-sample-well000_ses-20260622T215252_ecephys.nwb",
    "sub-sample-well000_ses-20260622T233922_ecephys.nwb",
    "sub-sample-well008_ses-20260622T182607_ecephys.nwb",
    "sub-sample-well008_ses-20260622T202514_ecephys.nwb",
    "sub-sample-well008_ses-20260622T222259_ecephys.nwb",
    "sub-sample-well008_ses-20260623T000326_ecephys.nwb",
    "sub-sample-well016_ses-20260622T185903_ecephys.nwb",
    "sub-sample-well016_ses-20260622T210111_ecephys.nwb",
    "sub-sample-well016_ses-20260622T225444_ecephys.nwb",
    "sub-sample-well016_ses-20260623T003647_ecephys.nwb",
    "sub-sample2-well000_ses-20260623T155950_ecephys.nwb",
    "sub-sample2-well008_ses-20260623T183144_ecephys.nwb",
    "sub-sample2-well016_ses-20260623T183945_ecephys.nwb",
]

_NAME_RE = re.compile(r"sub-(sample2?)-(well\d+)_ses-(\d+T\d+)")


def _parse_filename(fname: str) -> dict:
    m = _NAME_RE.match(fname)
    if not m:
        raise ValueError(f"Unexpected 001872 filename format: {fname}")
    batch, well_id, session_id = m.groups()
    return {"batch": batch, "well_id": well_id, "session_id": session_id, "organoid_id": f"{batch}_{well_id}"}


def process_self_derived_recording(raw_path: str, sorter_folder: str, config: dict) -> dict:
    meta = _parse_filename(Path(raw_path).name)

    sorted_data = run_curated_sorting(raw_path, sorter_folder, config)
    spike_times_dict = sorted_data["spike_times"]
    n_units = sorted_data["n_units"]
    duration_s = sorted_data["duration_s"]
    fs = sorted_data["fs"]

    per_unit_features = [
        compute_spike_train_features(st, duration_s, config) for st in spike_times_dict.values()
    ]
    spike_train_agg = aggregate_spike_train_features(per_unit_features)

    network_feats = compute_network_features(spike_times_dict, n_units, fs, duration_s, config)
    spectral_feats = compute_spectral_features_for_recording(raw_path, config)
    complexity_feats = compute_complexity_features(spike_times_dict, duration_s, config)

    row = {
        "dataset_id": "001872",
        "recording_path": raw_path,
        "spike_source": "self_derived_lupin_curated",
        "duration_s": duration_s,
        "n_channels": sorted_data["n_channels"],
        "n_units_total_uncurated": sorted_data["n_units_total"],
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

    checkpoint_path = FEATURES_DIR / "_checkpoint_001872.json"
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
        sorter_folder = str(DATA_RAW / f"_sorter_lupin_{Path(fname).stem}")
        row = process_self_derived_recording(raw_path, sorter_folder, config)
        rows_by_key[fname] = row
        checkpoint_path.write_text(json.dumps(rows_by_key, indent=2, default=float), encoding="utf-8")
        print(f"  (saved checkpoint, {len(rows_by_key)}/{len(_RAW_FILES)} recordings done)", flush=True)

    df = pd.DataFrame(list(rows_by_key.values()))
    out_path = FEATURES_DIR / "feature_matrix_001872.parquet"
    df.to_parquet(out_path, index=False)
    print(f"\nWrote {out_path} ({len(df)} rows, {len(df.columns)} columns)", flush=True)


if __name__ == "__main__":
    main()
