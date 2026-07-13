"""Converter: DANDI NWB raw recordings -> the .mat format MEA-NAP's own
pipeline expects (meanap.pipeline.io.load_raw_recording): a plain HDF5 file
with `dat` (n_channels, n_samples), `channels` (channel IDs), `fs` (sampling
rate scalar).

Mirrors io_brainwave.py's export_to_meanap_mat (same target format, same
on-disk transpose convention), for DANDI:001603/001872's NWB files instead
of the lab's 3Brain .brw files. Built as part of the 2026-07-13 "unicamente
MEA-NAP" pivot (see config/params.yaml `spike_detection`): running MEA-NAP's
own run_pipeline() end-to-end on DANDI data requires converting NWB to this
format first, since MEA-NAP's own I/O layer only reads Axion/Multichannel-
Systems .mat files (verified in meanap.pipeline.io's docstring), not NWB.

Everything conversion-related lives here, separate from
src/run_meanap_pipeline.py (which only builds the spreadsheet/Params MEA-NAP
itself requires and calls run_pipeline() -- no conversion logic there).
"""
from __future__ import annotations

import re
from pathlib import Path

import h5py
import numpy as np
from pynwb import NWBHDF5IO

DATA_RAW = Path(__file__).resolve().parent.parent / "data" / "raw"
DATA_MEANAP_MAT = Path(__file__).resolve().parent.parent / "data" / "meanap_mat"

_AGE_RE = re.compile(r"P(\d+)M")


def nwb_to_meanap_mat(nwb_path: str | Path, out_mat_path: str | Path) -> None:
    """Convert one NWB raw recording (acquisition/ElectricalSeries) to a
    MEA-NAP-readable .mat file.

    Streams the raw trace in chunks (matching validate_pipeline.py's
    per-channel-batch pattern) rather than holding the full
    (n_samples, n_channels) array in memory at once -- this machine is
    RAM-constrained and DANDI:001872 recordings run up to 1020 channels x
    600s at 10kHz (~2.4GB per full array).
    """
    out_mat_path = Path(out_mat_path)
    out_mat_path.parent.mkdir(parents=True, exist_ok=True)

    io = NWBHDF5IO(str(nwb_path), mode="r")
    try:
        nwbfile = io.read()
        ts = nwbfile.acquisition["ElectricalSeries"]
        fs = float(ts.rate)
        n_samples, n_channels = ts.data.shape

        # meanap.pipeline.io.load_raw_recording reads f["dat"][()].T expecting
        # the on-disk shape to be (n_channels, n_samples) so the transpose
        # lands on (n_samples, n_channels) -- write it pre-transposed to match
        # (same convention as io_brainwave.py's export_to_meanap_mat).
        channel_ids = np.arange(1, n_channels + 1)  # 1-based

        with h5py.File(out_mat_path, "w") as f:
            dat_ds = f.create_dataset("dat", shape=(n_channels, n_samples), dtype="float32")
            chunk_frames = 200_000
            for start in range(0, n_samples, chunk_frames):
                end = min(start + chunk_frames, n_samples)
                traces = np.asarray(ts.data[start:end, :], dtype="float32")  # (frames, channels)
                dat_ds[:, start:end] = traces.T
            f.create_dataset("channels", data=channel_ids)
            f.create_dataset("fs", data=np.array([fs]))
    finally:
        io.close()


def _div_from_age(age: str | None) -> float:
    """Extract a numeric DIV-like proxy from an age tag like 'P7M' (7).
    Not literal DIV (days in vitro) -- 001603's metadata gives postnatal
    age tags, not culture DIV -- but numeric and monotonic, which is all
    the spreadsheet's `DIV` column needs (a descriptive/grouping label
    written into output CSVs, not consumed by any algorithm -- confirmed
    via meanap.pipeline.step2.py/step4.py, which only read
    filename/group/div positionally and pass div straight through to
    output columns)."""
    if not age:
        return 0.0
    m = _AGE_RE.search(age)
    return float(m.group(1)) if m else 0.0


def convert_all_recordings(config: dict) -> list[dict]:
    """Convert every raw recording in scope (001603 HO1-HO4, all 001872) to
    MEA-NAP .mat format, skipping ones already converted. Returns a list of
    recording specs: filename (bare stem), group, div, dataset_id.
    """
    from src.build_feature_matrix import _MEA_NAP_RAW_FILES, _units_metadata
    from src.build_feature_matrix_001872 import _RAW_FILES as _RAW_FILES_001872

    DATA_MEANAP_MAT.mkdir(parents=True, exist_ok=True)
    recordings: list[dict] = []

    for subject_id, filenames in _MEA_NAP_RAW_FILES.items():
        for fname in filenames:
            raw_path = DATA_RAW / fname
            if not raw_path.exists():
                continue
            stem = Path(fname).stem
            mat_path = DATA_MEANAP_MAT / f"{stem}.mat"
            if not mat_path.exists():
                print(f"  converting {fname} -> {mat_path.name} ...", flush=True)
                nwb_to_meanap_mat(raw_path, mat_path)
            meta = _units_metadata(str(raw_path))
            recordings.append({
                "filename": stem, "group": subject_id, "div": _div_from_age(meta.get("age")),
                "dataset_id": "001603",
            })

    for fname in _RAW_FILES_001872:
        raw_path = DATA_RAW / fname
        if not raw_path.exists():
            continue
        stem = Path(fname).stem
        mat_path = DATA_MEANAP_MAT / f"{stem}.mat"
        if not mat_path.exists():
            print(f"  converting {fname} -> {mat_path.name} ...", flush=True)
            nwb_to_meanap_mat(raw_path, mat_path)
        m = re.match(r"sub-(sample2?)-(well\d+)_ses-(\d+T\d+)", fname)
        batch = m.group(1) if m else "unknown"
        recordings.append({
            # No DIV/age metadata exists for 001872 (self-derived dataset,
            # verified in Stage 0's inventory -- flagged, not assumed).
            "filename": stem, "group": f"001872_{batch}", "div": 0.0, "dataset_id": "001872",
        })

    return recordings
