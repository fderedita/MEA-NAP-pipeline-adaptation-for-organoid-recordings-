"""Builds the "spreadsheet" CSV that MEA-NAP's own pipeline requires before
it can run at all (meanap.pipeline.spreadsheet.read_recording_csv(), called
by meanap.pipeline.runner.run_pipeline()) -- every MEA-NAP user prepares one
of these by hand before pressing run, per MEA-NAP's own README ("How to use
the pipeline": "you have created a spreadsheet (csv file) with the names of
your mat files for each recording and their group and ages to guide the
batch analysis"). This is that step, done programmatically instead of by
hand since we have dozens of recordings.

Columns are read positionally by read_recording_csv() (Recording Filename,
DIV group, Genotype, [Ground]) -- header text isn't enforced by that
function, but written here with MEA-NAP's own header names for readability.
`filename` must be the bare stem (no extension) of the .mat file produced by
src/io_nwb_convert.py -- MEA-NAP looks it up as
f"{params.raw_data}/{filename}.mat".
"""
from __future__ import annotations

import csv
from pathlib import Path


def build_spreadsheet(recordings: list[dict], out_csv_path: str | Path) -> None:
    """`recordings`: list of {"filename": ..., "div": ..., "group": ...} dicts,
    e.g. from src.io_nwb_convert.convert_all_recordings()."""
    out_csv_path = Path(out_csv_path)
    out_csv_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["Recording Filename", "DIV group", "Genotype"])
        for rec in recordings:
            writer.writerow([rec["filename"], rec["div"], rec["group"]])
