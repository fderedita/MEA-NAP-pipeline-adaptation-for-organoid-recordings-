"""Stage 2 orchestrator — assembles outputs/features/feature_matrix.parquet.

SUPERSEDED as the primary Stage 2 path: see src/run_meanap_pipeline.py,
which runs MEA-NAP's own run_pipeline()
end-to-end instead of calling features/*.py piecemeal. This module is now
used ONLY for HO5-HO8's forced `deposited` exception (001603 "sourced"
subjects with no raw on DANDI at all -- MEA-NAP cannot run without raw) --
process_deposited_recording() is still the active code path for those 4
subjects. Everything else in this file (the mea_nap_threshold path,
process_meanap_recording(), discover_001603_recordings()) is historical,
kept for the comparison output already on disk
(feature_matrix_001603.parquet), not re-run.

One row per recording, columns = features from spike_train/network/spectral/
complexity + metadata: dataset (lab/platform), organoid_id, DIV/age, well_id,
spike_source in {deposited, mea_nap_threshold, self_derived_lupin_curated},
raw_provenance.

Spike-source policy is frozen in config/params.yaml `spike_detection`. The
earlier deposited-Units-everywhere-available run is preserved as
`feature_matrix_001603_deposited_only.parquet`, not deleted -- see
outputs/reports/stage1_validation.md's "Second"/"Third addendum" for the
full pivot history.

Saves incrementally (one JSON checkpoint written after every recording, not
just at the end) -- network features in particular are slow enough
(O(n_units^2) pairwise STTC, up to ~1hr total across all 14 recordings)
that losing all progress to an interruption would be costly, per the
lesson learned in Stage 1 (see notebooks/run_stage1_validation.py).
"""
from __future__ import annotations

import json
import os
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import numpy as np
import pandas as pd

from src.config import load_config, require
from src.features.complexity import compute_complexity_features
from src.features.network import compute_network_features
from src.features.spectral import aggregate_spectral_features, compute_spectral_features_for_channel
from src.features.spike_train import (
    aggregate_spike_train_features,
    compute_spike_train_features,
    detect_bursts_meanap_isin_batch,
)
from src.validate_pipeline import detect_spikes_full_recording, load_deposited_units

DATA_RAW = Path(__file__).resolve().parent.parent / "data" / "raw"
FEATURES_DIR = Path(__file__).resolve().parent.parent / "outputs" / "features"

# Age-matched raw file for each locally-mirrored units file among 001603's
# "recorded" human subjects (HO1-HO4) -- NOT the same recording session
# (matched only by nominal `age` tag; confirmed gap is ~57min for HO1/HO4
# vs ~4 days for HO2/HO3, which tracks their firing-rate Spearman rho --
# see stage1_validation.md, "Most likely explanation" addendum).
# HO5-8 ("sourced" subjects) have no raw at all -- absent from this dict.
_RAW_FILE_FOR_UNITS = {
    "sub-HO1_ses-20250924T002125.nwb": "sub-HO1_ses-20250924T011900_ecephys.nwb",
    "sub-HO2_ses-20250916T190936.nwb": "sub-HO2_ses-20250912T144835_obj-9jlzq1_ecephys.nwb",  # P6M
    "sub-HO2_ses-20250916T190927_obj-1s1jcwl.nwb": "sub-HO2_ses-20250912T144839_ecephys.nwb",  # P7M
    "sub-HO2_ses-20250916T190928_obj-86y47o.nwb": "sub-HO2_ses-20250912T144837_ecephys.nwb",  # P8M
    "sub-HO2_ses-20250916T190927_obj-vm83mt.nwb": "sub-HO2_ses-20250912T144835_obj-77d92a_ecephys.nwb",  # P8MT4H
    "sub-HO3_ses-20250916T190937.nwb": "sub-HO3_ses-20250912T144841_ecephys.nwb",  # P6M
    "sub-HO3_ses-20250916T190930_obj-2sqh9d.nwb": "sub-HO3_ses-20250912T150817_ecephys.nwb",  # P7M
    "sub-HO3_ses-20250916T190930_obj-ikzmsj.nwb": "sub-HO3_ses-20250912T144835_obj-1hc8buj_ecephys.nwb",  # P8M
    "sub-HO3_ses-20250916T190928.nwb": "sub-HO3_ses-20250912T144846_ecephys.nwb",  # P8MT4H
    "sub-HO4_ses-20250924T002126.nwb": "sub-HO4_ses-20250924T011900_ecephys.nwb",
}

# HO1-HO4's raw files, grouped by subject (derived from _RAW_FILE_FOR_UNITS'
# values, one source of truth) -- these are the recordings MEA-NAP threshold
# detection runs on directly, per the uniform-spike-source policy.
_MEA_NAP_RAW_FILES: dict[str, list[str]] = {}
for _raw_fname in _RAW_FILE_FOR_UNITS.values():
    _subject_id = _raw_fname.split("_")[0].replace("sub-", "")
    _MEA_NAP_RAW_FILES.setdefault(_subject_id, []).append(_raw_fname)


def _process_spectral_channel_batch(raw_path: str, ch_indices: list[int], config: dict) -> dict[int, dict]:
    """Worker (own process): opens its own NWB handle, computes spectral
    features for a batch of channels. Mirrors validate_pipeline.py's
    per-channel parallelization pattern."""
    from pynwb import NWBHDF5IO

    io = NWBHDF5IO(raw_path, mode="r")
    try:
        nwbfile = io.read()
        ts = nwbfile.acquisition["ElectricalSeries"]
        fs = float(ts.rate)
        results = {}
        for ch_idx in ch_indices:
            trace = ts.data[:, ch_idx].astype(float)
            results[ch_idx] = compute_spectral_features_for_channel(trace, fs, config)
        return results
    finally:
        io.close()


def compute_spectral_features_for_recording(raw_path: str, config: dict, n_workers: int | None = None) -> dict:
    """Spectral feature block for a full recording, parallelized across channels."""
    from pynwb import NWBHDF5IO

    io = NWBHDF5IO(raw_path, mode="r")
    try:
        nwbfile = io.read()
        n_channels = nwbfile.acquisition["ElectricalSeries"].data.shape[1]
    finally:
        io.close()

    if n_workers is None:
        n_workers = min(6, max(1, (os.cpu_count() or 4) - 2))

    chunks = [c.tolist() for c in np.array_split(np.arange(n_channels), n_workers) if len(c) > 0]
    per_channel: dict[int, dict] = {}
    with ProcessPoolExecutor(max_workers=n_workers) as executor:
        futures = [executor.submit(_process_spectral_channel_batch, raw_path, chunk, config) for chunk in chunks]
        for future in as_completed(futures):
            per_channel.update(future.result())

    ordered = [per_channel[i] for i in sorted(per_channel)]
    return {f"spectral__{k}": v for k, v in aggregate_spectral_features(ordered).items()}

# DANDI:001603's human subjects all use MaxWell MaxOne at a fixed 20kHz
# sampling rate (confirmed in Stage 0's settings audit,
# outputs/reports/stage0_inventory.md) -- the deposited-Units-only NWB
# files (no raw ElectricalSeries) don't carry their own fs, so this is
# supplied from that audit rather than read per-file.
MAXONE_FS_HZ = 20000.0

# Locally-mirrored deposited-Units files for DANDI:001603's human subjects
# (HO1-HO8). HO2/HO3 have more sessions on DANDI than are mirrored here --
# these are the ones prioritised in Stage 0.5 (one pair per distinct `age`
# tag, see outputs/reports/stage0_5_mirror.log), not the full set.
_HO_UNITS_FILES = {
    "HO1": ["sub-HO1_ses-20250924T002125.nwb"],
    "HO2": [
        "sub-HO2_ses-20250916T190936.nwb",
        "sub-HO2_ses-20250916T190927_obj-1s1jcwl.nwb",
        "sub-HO2_ses-20250916T190928_obj-86y47o.nwb",
        "sub-HO2_ses-20250916T190927_obj-vm83mt.nwb",
    ],
    "HO3": [
        "sub-HO3_ses-20250916T190937.nwb",
        "sub-HO3_ses-20250916T190930_obj-2sqh9d.nwb",
        "sub-HO3_ses-20250916T190930_obj-ikzmsj.nwb",
        "sub-HO3_ses-20250916T190928.nwb",
    ],
    "HO4": ["sub-HO4_ses-20250924T002126.nwb"],
    "HO5": ["sub-HO5_ses-20250924T002125.nwb"],
    "HO6": ["sub-HO6_ses-20250924T002106.nwb"],
    "HO7": ["sub-HO7_ses-20250924T002328.nwb"],
    "HO8": ["sub-HO8_ses-20250924T002134.nwb"],
}


def discover_001603_recordings() -> list[dict]:
    """List recording specs for 001603's human subjects, per the uniform
    spike-source policy: HO1-HO4 (raw available) get a `raw_path` spec (MEA-NAP
    threshold detection); HO5-HO8 (no raw on DANDI) keep a `units_path`
    spec (deposited Units, forced exception)."""
    recordings = []
    for subject_id, filenames in _MEA_NAP_RAW_FILES.items():
        for fname in filenames:
            path = DATA_RAW / fname
            if path.exists():
                recordings.append({"subject_id": subject_id, "raw_path": str(path), "dataset_id": "001603"})
    for subject_id in ("HO5", "HO6", "HO7", "HO8"):
        for fname in _HO_UNITS_FILES.get(subject_id, []):
            path = DATA_RAW / fname
            if path.exists():
                recordings.append({"subject_id": subject_id, "units_path": str(path), "dataset_id": "001603"})
    return recordings


def _units_metadata(units_path: str) -> dict:
    """Pull session_id/age/species straight from the NWB file (not the
    manifest CSV) so this module has no hidden dependency on Stage 0 having
    been re-run recently."""
    from pynwb import NWBHDF5IO

    io = NWBHDF5IO(units_path, mode="r")
    try:
        nwbfile = io.read()
        return {
            "age": nwbfile.subject.age if nwbfile.subject else None,
            "species": nwbfile.subject.species if nwbfile.subject else None,
            "session_start_time": str(nwbfile.session_start_time),
        }
    finally:
        io.close()


def process_deposited_recording(subject_id: str, units_path: str, config: dict) -> dict:
    """One feature-matrix row for a recording using deposited Units directly."""
    deposited = load_deposited_units(units_path)
    meta = _units_metadata(units_path)
    spike_times_dict = {i: st for i, st in enumerate(deposited["spike_times"].values())}

    per_unit_features = [
        compute_spike_train_features(st, deposited["duration_s"], config)
        for st in deposited["spike_times"].values()
    ]
    agg = aggregate_spike_train_features(per_unit_features)

    network_feats = compute_network_features(
        spike_times_dict, deposited["n_units"], MAXONE_FS_HZ, deposited["duration_s"], config
    )

    row = {
        "dataset_id": "001603",
        "organoid_id": subject_id,
        "recording_path": units_path,
        "spike_source": "deposited",
        "duration_s": deposited["duration_s"],
        **meta,
    }
    row.update({f"spike_train__{k}": v for k, v in agg.items()})
    row.update(network_feats)
    return row


def process_meanap_recording(subject_id: str, raw_path: str, config: dict) -> dict:
    """One feature-matrix row using MEA-NAP threshold detection directly on
    the raw ElectricalSeries -- the default for any recording with raw
    available (HO1-HO4 here). MUA-level, not SUA: spike_times
    are per-channel, not per-curated-unit."""
    meta = _units_metadata(raw_path)
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
    agg = aggregate_spike_train_features(per_unit_features)

    network_feats = compute_network_features(
        spike_times_dict, detected["n_channels"], detected["fs"], duration_s, config
    )
    spectral_feats = compute_spectral_features_for_recording(raw_path, config)
    complexity_feats = compute_complexity_features(spike_times_dict, duration_s, config)

    row = {
        "dataset_id": "001603",
        "organoid_id": subject_id,
        "recording_path": raw_path,
        "spike_source": "mea_nap_threshold",
        "duration_s": duration_s,
        "n_channels": detected["n_channels"],
        **meta,
    }
    row.update({f"spike_train__{k}": v for k, v in agg.items()})
    row.update(network_feats)
    row.update(spectral_feats)
    row.update({f"complexity__{k}": v for k, v in complexity_feats.items()})
    return row


def _row_key(rec: dict) -> str:
    path = rec.get("raw_path") or rec["units_path"]
    return f"{rec['subject_id']}::{Path(path).name}"


def build_feature_matrix(
    recordings: list[dict], config: dict, checkpoint_path: Path | None = None
) -> pd.DataFrame:
    """Build the feature matrix for a list of recording specs, saving a JSON
    checkpoint after every recording so a long run can resume.

    Each spec must have at minimum `subject_id`, `dataset_id`, and either
    `raw_path` (MEA-NAP threshold detection) or `units_path` (deposited
    Units, forced exception for HO5-HO8).
    """
    rows_by_key: dict[str, dict] = {}
    if checkpoint_path and checkpoint_path.exists():
        rows_by_key = json.loads(checkpoint_path.read_text(encoding="utf-8"))
        print(f"Resuming: already have {len(rows_by_key)} recordings", flush=True)

    for rec in recordings:
        key = _row_key(rec)
        if key in rows_by_key:
            print(f"  {key} (skipping, already done)", flush=True)
            continue
        print(f"  {key} ...", flush=True)
        if "raw_path" in rec:
            row = process_meanap_recording(rec["subject_id"], rec["raw_path"], config)
        elif "units_path" in rec:
            row = process_deposited_recording(rec["subject_id"], rec["units_path"], config)
        else:
            raise NotImplementedError(f"Recording spec has neither raw_path nor units_path: {rec}")
        rows_by_key[key] = row
        if checkpoint_path:
            checkpoint_path.write_text(json.dumps(rows_by_key, indent=2, default=float), encoding="utf-8")
            print(f"    (saved checkpoint, {len(rows_by_key)} recordings done)", flush=True)

    return pd.DataFrame(list(rows_by_key.values()))


def add_spectral_features(checkpoint_path: Path, config: dict) -> None:
    """Enrich the existing checkpoint's rows with spectral features, for
    recordings that have an age-matched raw file (_RAW_FILE_FOR_UNITS).
    Does NOT recompute spike_train/network (already cached) -- reads the
    checkpoint, adds spectral__* keys to applicable rows, re-saves after
    every recording (spectral is ~40min/recording at full scale, parallelized
    down from that -- still long enough to want incremental saving).
    """
    rows_by_key = json.loads(checkpoint_path.read_text(encoding="utf-8"))
    for key, row in rows_by_key.items():
        if any(k.startswith("spectral__") for k in row):
            print(f"  {key} (spectral already done, skipping)", flush=True)
            continue
        units_fname = Path(row["recording_path"]).name
        raw_fname = _RAW_FILE_FOR_UNITS.get(units_fname)
        if raw_fname is None:
            print(f"  {key} (no raw available, no spectral features -- expected for sourced subjects)", flush=True)
            continue
        raw_path = str(DATA_RAW / raw_fname)
        print(f"  {key} <- {raw_fname} ...", flush=True)
        spectral_feats = compute_spectral_features_for_recording(raw_path, config)
        row.update(spectral_feats)
        checkpoint_path.write_text(json.dumps(rows_by_key, indent=2, default=float), encoding="utf-8")
        print(f"    (saved checkpoint)", flush=True)


def add_complexity_features(checkpoint_path: Path, config: dict) -> None:
    """Enrich the existing checkpoint's rows with complexity features.
    Unlike spectral, this only needs spike times (already available from
    the deposited Units, reloaded here) -- computable for ALL recordings
    including HO5-8 (no raw needed), and cheap (no O(n^2) or per-channel
    raw streaming), so no parallelization/long-run concerns here.
    """
    rows_by_key = json.loads(checkpoint_path.read_text(encoding="utf-8"))
    for key, row in rows_by_key.items():
        if any(k.startswith("complexity__") for k in row):
            print(f"  {key} (complexity already done, skipping)", flush=True)
            continue
        print(f"  {key} ...", flush=True)
        deposited = load_deposited_units(row["recording_path"])
        spike_times_dict = {i: st for i, st in enumerate(deposited["spike_times"].values())}
        complexity_feats = compute_complexity_features(spike_times_dict, deposited["duration_s"], config)
        row.update({f"complexity__{k}": v for k, v in complexity_feats.items()})
        checkpoint_path.write_text(json.dumps(rows_by_key, indent=2, default=float), encoding="utf-8")
    print(f"  done, saved checkpoint", flush=True)


def main():
    config = load_config()
    FEATURES_DIR.mkdir(parents=True, exist_ok=True)

    recordings = discover_001603_recordings()
    print(f"Found {len(recordings)} locally-mirrored recordings in 001603 "
          f"({sum('raw_path' in r for r in recordings)} MEA-NAP, "
          f"{sum('units_path' in r for r in recordings)} deposited-only)", flush=True)

    checkpoint_path = FEATURES_DIR / "_checkpoint_001603.json"
    df = build_feature_matrix(recordings, config, checkpoint_path=checkpoint_path)

    print("\nAdding spectral features where a raw file is available...", flush=True)
    add_spectral_features(checkpoint_path, config)

    print("\nAdding complexity features (all recordings)...", flush=True)
    add_complexity_features(checkpoint_path, config)

    df = pd.DataFrame(list(json.loads(checkpoint_path.read_text(encoding="utf-8")).values()))

    out_path = FEATURES_DIR / "feature_matrix_001603.parquet"
    df.to_parquet(out_path, index=False)
    print(f"\nWrote {out_path} ({len(df)} rows, {len(df.columns)} columns)", flush=True)
    print(df[["organoid_id", "age", "duration_s", "spike_train__n_units", "spike_train__mfr_hz_mean",
              "network__mean_degree_15ms"]], flush=True)


if __name__ == "__main__":
    main()
