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

ONE RECORDING AT A TIME, NOT ALL 25 UPFRONT: converting every recording to
.mat before running anything needs ~340GB (uncompressed float32 .mat
files run 1.5-24.5GB each) -- more disk than a typical dev machine has
free. MEA-NAP's own Step 2/4 CSV writers overwrite
rather than append (`pd.DataFrame(rows).to_csv(...)`, confirmed in
step2.py) -- calling run_pipeline() once per recording means each call's
CSV only has that one recording's row, so this module harvests each
recording's rows into its own accumulator CSVs
(outputs/meanap_pipeline/merged/) right after each run_pipeline() call,
before the next call overwrites MEA-NAP's own copy. The .mat is deleted
immediately after harvesting, keeping peak disk usage to ~1 recording
(worst case ~25GB) instead of the full dataset. Resumable: a recording
already present in the accumulator's `FileName` column is skipped.

HO5-8 (001603 "sourced" subjects, no raw on DANDI) are NOT included here --
MEA-NAP cannot run without raw. They keep spike_source=deposited as a
forced exception, handled separately in build_feature_matrix.py (unchanged).
"""
from __future__ import annotations

import multiprocessing as mp
from pathlib import Path

import pandas as pd

from src.build_meanap_spreadsheet import build_spreadsheet
from src.config import load_config, require
from src.io_nwb_convert import DATA_MEANAP_MAT, list_all_recordings, nwb_to_meanap_mat

OUTPUT_ROOT = Path(__file__).resolve().parent.parent / "outputs" / "meanap_pipeline"
OUTPUT_DATA_FOLDER = OUTPUT_ROOT / "OutputData"
MERGED_DIR = OUTPUT_ROOT / "merged"

# (relative path under OUTPUT_DATA_FOLDER, merged filename)
_CSV_SOURCES = [
    ("2_NeuronalActivity/NeuronalActivity_RecordingLevel.csv", "NeuronalActivity_RecordingLevel.csv"),
    ("2_NeuronalActivity/NeuronalActivity_NodeLevel.csv", "NeuronalActivity_NodeLevel.csv"),
    ("4_NetworkActivity/NetworkActivity_RecordingLevel.csv", "NetworkActivity_RecordingLevel.csv"),
    ("4_NetworkActivity/NetworkActivity_NodeLevel.csv", "NetworkActivity_NodeLevel.csv"),
]


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
        # use the full default metric set rather than a hand-picked subset.
        net_met_to_cal=["aN", "Dens", "NDmean", "NDtop25", "sigEdgesMean", "NSmean",
                         "ElocMean", "CC", "nMod", "Q", "PL", "Eglob", "SW", "SWw"],
        start_analysis_step=1,
        stop_analysis_step=4,
        time_processes=True,
    )


# Recordings to exclude while a Step 4 stall on them is under investigation.
# Deliberately NOT marked done in the merged CSV (this skip is invisible to
# _already_done, so the gap stays visible) -- remove the entry once
# investigated and fixed, with a root-cause note here for the record.
_TEMP_SKIP: set[str] = set()


def _already_done(stem: str) -> bool:
    """Resume check: has this recording's row already been harvested into
    the merged NeuronalActivity_RecordingLevel.csv?"""
    merged_path = MERGED_DIR / "NeuronalActivity_RecordingLevel.csv"
    if not merged_path.exists():
        return False
    df = pd.read_csv(merged_path)
    return "FileName" in df.columns and stem in set(df["FileName"])


def _harvest_csvs(stem: str) -> None:
    """Read the 4 CSVs MEA-NAP just wrote for this single recording (its
    to_csv calls overwrite, so these only contain this recording's rows
    right now) and append them into the merged accumulator CSVs."""
    MERGED_DIR.mkdir(parents=True, exist_ok=True)
    for rel_path, merged_name in _CSV_SOURCES:
        src_path = OUTPUT_DATA_FOLDER / rel_path
        if not src_path.exists():
            continue
        new_rows = pd.read_csv(src_path)
        merged_path = MERGED_DIR / merged_name
        if merged_path.exists():
            existing = pd.read_csv(merged_path)
            existing = existing[existing["FileName"] != stem]  # replace any partial/stale row for this recording
            combined = pd.concat([existing, new_rows], ignore_index=True)
        else:
            combined = new_rows
        combined.to_csv(merged_path, index=False)


def process_one_recording(rec: dict, config: dict) -> None:
    stem = rec["filename"]
    if stem in _TEMP_SKIP:
        print(f"=== {stem} === (TEMPORARILY SKIPPED -- see _TEMP_SKIP, needs investigation)", flush=True)
        return
    if _already_done(stem):
        print(f"=== {stem} === (skipping, already in merged output)", flush=True)
        return

    print(f"=== {stem} ===", flush=True)
    mat_path = DATA_MEANAP_MAT / f"{stem}.mat"
    DATA_MEANAP_MAT.mkdir(parents=True, exist_ok=True)
    try:
        print("  converting to MEA-NAP .mat format...", flush=True)
        nwb_to_meanap_mat(rec["raw_path"], mat_path)

        spreadsheet_path = OUTPUT_ROOT / f"_spreadsheet_{stem}.csv"
        build_spreadsheet([rec], spreadsheet_path)

        params = build_params(config, OUTPUT_DATA_FOLDER, spreadsheet_path, "2:2")

        from meanap.pipeline.runner import run_pipeline
        print("  running MEA-NAP pipeline (steps 1-4)...", flush=True)
        run_pipeline(params, log=lambda msg: print(f"  {msg}", flush=True))

        _harvest_csvs(stem)
        spreadsheet_path.unlink(missing_ok=True)
        print(f"  done, harvested into {MERGED_DIR}", flush=True)
    finally:
        # Always free the disk, even if this recording's run failed partway --
        # the whole point of per-recording processing is bounded peak usage.
        mat_path.unlink(missing_ok=True)

        # Step 4 alone makes 10+ separate joblib.Parallel() calls per
        # recording (NMF's two batched searches, participation_coef_norm per
        # lag) via joblib's cached/reused loky executor, which can leave
        # worker-pool resources (semaphores, temp folders) not fully
        # released between calls. Force a clean executor teardown after
        # every recording (not just on success) so any such leak can't
        # accumulate across a 25-recording run; the ~1s respawn cost next
        # recording is negligible next to
        # multi-hour Step 4 runtimes.
        try:
            from joblib.externals.loky import get_reusable_executor
            get_reusable_executor().shutdown(wait=True)
        except Exception as e:
            print(f"  Warning: could not shut down joblib executor: {e}", flush=True)


def main():
    config = load_config()
    recordings = list_all_recordings(config)
    print(f"{len(recordings)} recordings in scope (smallest to largest).", flush=True)

    # Each recording runs in its own child process rather than inline in
    # this long-running one. Large per-recording allocations (the raw
    # voltage trace, joblib worker pools) were observed to not be fully
    # released back to the OS even after their Python references went out
    # of scope -- confirmed via dmesg: a later recording's OOM-kill RSS
    # matched the sum of an earlier recording's residual footprint plus
    # its own new allocation, i.e. memory was accumulating *across*
    # recordings inside one process, not within a single recording's own
    # processing. Isolating each recording in its own process guarantees
    # the OS reclaims everything on exit, and also contains a crash
    # (including an OOM kill, which gives Python no chance to log
    # anything) to that one recording instead of taking down the whole
    # run -- the next recording still gets a fresh attempt, and a killed
    # recording is simply not yet in the merged CSV for the usual resume
    # logic to pick up later.
    ctx = mp.get_context("fork")
    for i, rec in enumerate(recordings, 1):
        print(f"\n[{i}/{len(recordings)}]", flush=True)
        p = ctx.Process(target=process_one_recording, args=(rec, config))
        p.start()
        p.join()
        if p.exitcode != 0:
            reason = (
                f"terminated by signal {-p.exitcode}"
                if p.exitcode is not None and p.exitcode < 0
                else f"exit code {p.exitcode}"
            )
            print(f"  FAILED ({reason}) -- continuing with next recording", flush=True)

    print(f"\nAll done. Merged CSVs at: {MERGED_DIR}", flush=True)


if __name__ == "__main__":
    main()
