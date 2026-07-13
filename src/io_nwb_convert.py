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
"""
from __future__ import annotations

from pathlib import Path

import h5py
import numpy as np
from pynwb import NWBHDF5IO


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
