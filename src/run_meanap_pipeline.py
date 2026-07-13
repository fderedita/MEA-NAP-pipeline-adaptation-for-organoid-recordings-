"""Run MEA-NAP's own full pipeline (meanap.pipeline.runner.run_pipeline,
Steps 1-4) end-to-end on DANDI:001603 (HO1-HO4) and DANDI:001872, instead of
calling individual MEA-NAP functions piecemeal from build_feature_matrix*.py.

2026-07-13 "unicamente MEA-NAP" decision: use MEA-NAP's own orchestrator so
every network metric it computes by default (modularity/Louvain, node
cartography, participation coefficient, small-worldness, rich club --
see external/MEA-NAP/python/PIPELINE_PORT_STATUS.md) is available, not just
the deterministic subset build_feature_matrix.py's network.py wires in.
Controllability and NMF are computed too (step4.py doesn't gate them
separately) but are NOT selected into our feature matrix by
parse_meanap_pipeline_output.py, per that same decision (excluded from the
"MEA-NAP default set" scope).

Three stages, each independently re-runnable:
1. convert_all_recordings() -- NWB -> MEA-NAP .mat (src/io_nwb_convert.py),
   skipped if the .mat already exists.
2. build_spreadsheet() -- the CSV read_recording_csv() expects.
3. main() -- builds a Params object from config/params.yaml's frozen
   values and calls run_pipeline().

HO5-8 (001603 "sourced" subjects, no raw on DANDI) are NOT included here --
MEA-NAP cannot run without raw. They keep spike_source=deposited as a
forced exception, handled separately in build_feature_matrix.py (unchanged).
"""
from __future__ import annotations

import csv
import re
from pathlib import Path

from src.build_feature_matrix import _MEA_NAP_RAW_FILES, _units_metadata
from src.build_feature_matrix_001872 import _RAW_FILES as _RAW_FILES_001872
from src.config import load_config, require
from src.io_nwb_convert import nwb_to_meanap_mat

DATA_RAW = Path(__file__).resolve().parent.parent / "data" / "raw"
DATA_MEANAP_MAT = Path(__file__).resolve().parent.parent / "data" / "meanap_mat"
OUTPUT_ROOT = Path(__file__).resolve().parent.parent / "outputs" / "meanap_pipeline"

_AGE_RE = re.compile(r"P(\d+)M")


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


def build_spreadsheet(recordings: list[dict], out_csv_path: Path) -> None:
    """Write the CSV meanap.pipeline.spreadsheet.read_recording_csv() expects:
    columns read positionally (Recording Filename, DIV group, Genotype,
    [Ground]) -- header text isn't enforced by that function, but written
    with MATLAB's own header names for readability."""
    out_csv_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["Recording Filename", "DIV group", "Genotype"])
        for rec in recordings:
            writer.writerow([rec["filename"], rec["div"], rec["group"]])


def build_params(config: dict, output_folder: Path, spreadsheet_path: Path, spreadsheet_range: str):
    """Build a meanap.params.Params object from config/params.yaml's frozen
    values -- same parameters build_feature_matrix*.py already uses, so
    results are comparable across the two code paths, not just superficially
    similar."""
    from meanap.params import Params

    low, high = require(config, "preprocessing.bandpass_hz")
    threshold_mult = require(config, "spike_detection.threshold_mad_multiplier")
    ref_period_ms = require(config, "spike_detection.ref_period_ms")
    lags = require(config, "network.sttc_lag_ms")
    n_surrogates = require(config, "network.surrogate_control.n_surrogates")
    tail = require(config, "network.surrogate_control.tail")
    min_spikes = require(config, "burst_detection.meanap_isi_n.min_spikes")
    isi_threshold = require(config, "burst_detection.meanap_isi_n.isi_threshold")

    return Params(
        raw_data=str(DATA_MEANAP_MAT),
        output_data_folder=str(output_folder.parent),
        output_data_folder_name=output_folder.name,
        spreadsheet_file_name=str(spreadsheet_path),
        spreadsheet_range=spreadsheet_range,
        detect_spikes=True,
        thresholds=[float(threshold_mult)],
        wname_list=[],  # threshold only, per Stage 1's closing decision -- no wavelet
        spikes_method=f"thr{int(threshold_mult)}",
        filter_low_pass=float(low),
        filter_high_pass=float(high),  # auto-clipped below Nyquist by bandpass_filter for 10kHz recordings
        ref_period=float(ref_period_ms),
        func_con_lag_val=list(lags),
        prob_thresh_rep_num=int(n_surrogates),
        prob_thresh_tail=float(tail),
        single_channel_burst_min_spike=int(min_spikes),
        single_channel_isi_threshold=isi_threshold,
        min_spike_network_burst=10,
        min_channel_network_burst=3,
        bakkum_network_burst_isi_n_threshold="automatic",
        # MATLAB's own default net_met_to_cal (Params' own default list) --
        # "tutto il set di default di MATLAB" per the 2026-07-13 decision.
        net_met_to_cal=["aN", "Dens", "NDmean", "NDtop25", "sigEdgesMean", "NSmean",
                         "ElocMean", "CC", "nMod", "Q", "PL", "Eglob", "SW", "SWw"],
        start_analysis_step=1,
        stop_analysis_step=4,
        time_processes=True,
    )


def main():
    config = load_config()
    print("Converting raw recordings to MEA-NAP .mat format...", flush=True)
    recordings = convert_all_recordings(config)
    print(f"{len(recordings)} recordings ready.", flush=True)

    spreadsheet_path = OUTPUT_ROOT / "recordings.csv"
    build_spreadsheet(recordings, spreadsheet_path)
    print(f"Spreadsheet written: {spreadsheet_path}", flush=True)

    output_folder = OUTPUT_ROOT / "OutputData"
    spreadsheet_range = f"2:{len(recordings) + 1}"
    params = build_params(config, output_folder, spreadsheet_path, spreadsheet_range)

    from meanap.pipeline.runner import run_pipeline
    print("Running MEA-NAP pipeline (steps 1-4)...", flush=True)
    result_path = run_pipeline(params, log=lambda msg: print(msg, flush=True))
    print(f"\nDone. Output at: {result_path}", flush=True)


if __name__ == "__main__":
    main()
