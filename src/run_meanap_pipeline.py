"""Runs MEA-NAP's own pipeline (meanap.pipeline.runner.run_pipeline, the
Python port of MEApipeline.m) end-to-end on DANDI:001603 (HO1-HO4) and
DANDI:001872 -- Steps 1-4: spike detection, neuronal activity, functional
connectivity, network metrics.

This is the third piece of MEA-NAP's own required setup ritual (see its own
README's "How to use the pipeline"): data converted to .mat
(src/io_nwb_convert.py) + a batch-analysis spreadsheet
(src/build_meanap_spreadsheet.py) + calling the pipeline itself, which is
this file. build_params() only translates config/params.yaml's already-
frozen values into the Params object run_pipeline() requires (the project's
own "config-first, nothing hard-coded" guardrail) -- it computes nothing
itself; every actual analysis step happens inside run_pipeline().

2026-07-13 "unicamente MEA-NAP" decision: this replaces the earlier
piecemeal-MEA-NAP-function-calls architecture (build_feature_matrix*.py
calling features/*.py) so every network metric MEA-NAP computes by default
(modularity/Louvain, node cartography, participation coefficient,
small-worldness, rich club -- see
external/MEA-NAP/python/PIPELINE_PORT_STATUS.md) is available, not just the
deterministic subset previously wired in.

HO5-8 (001603 "sourced" subjects, no raw on DANDI) are NOT included here --
MEA-NAP cannot run without raw. They keep spike_source=deposited as a
forced exception, handled separately in build_feature_matrix.py (unchanged).
"""
from __future__ import annotations

from pathlib import Path

from src.build_meanap_spreadsheet import build_spreadsheet
from src.config import load_config, require
from src.io_nwb_convert import DATA_MEANAP_MAT, convert_all_recordings

OUTPUT_ROOT = Path(__file__).resolve().parent.parent / "outputs" / "meanap_pipeline"


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
