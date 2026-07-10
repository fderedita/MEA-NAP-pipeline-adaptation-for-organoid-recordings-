"""Apply quality curation to an already-computed sorter output (reloaded
from disk, not re-run) and re-compare to deposited ground truth. Reuses
the same QC criteria the HO1 deposited Units were filtered by (per the
notebook exploration's file metadata): SNR<5, ISI-violation-ratio>0.3,
firing-rate<0.05Hz all excluded.

See src/validate_pipeline.py for the shared comparison helpers and
outputs/reports/stage1_validation.md for why this curation step matters
(the uncurated lupin result had 732 units vs deposited's curated 131 --
not an apples-to-apples comparison).
"""
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
import spikeinterface as si
import spikeinterface.extractors as se
import spikeinterface.sorters as ss
import spikeinterface.qualitymetrics as sqm
from scipy.stats import spearmanr

from src.validate_pipeline import (
    load_deposited_units,
    match_units_to_electrodes,
    aggregate_deposited_rate_per_electrode,
    network_burst_rate,
)

RAW_PATH = r"C:\Users\franc\MEA project\data\raw\sub-HO1_ses-20250924T011900_ecephys.nwb"
UNITS_PATH = r"C:\Users\franc\MEA project\data\raw\sub-HO1_ses-20250924T002125.nwb"
SORTER_FOLDER = r"C:\Users\franc\MEA project\data\raw\_sorter_lupin_sub-HO1_ses-20250924T011900_ecephys"

SNR_MIN = 5.0
ISI_VIOLATION_MAX = 0.3
FIRING_RATE_MIN = 0.05

if __name__ == "__main__":
    print("Reloading sorting + recording...", flush=True)
    sorting = ss.read_sorter_folder(SORTER_FOLDER)
    recording = se.read_nwb_recording(RAW_PATH, electrical_series_path="acquisition/ElectricalSeries")
    fs = recording.get_sampling_frequency()
    duration_s = recording.get_total_duration()
    n_channels = recording.get_num_channels()
    electrode_coords = recording.get_channel_locations()
    n_units_total = len(sorting.get_unit_ids())
    print(f"{n_units_total} units, {n_channels} channels, {duration_s:.1f}s", flush=True)

    print("\nComputing quality metrics (waveforms/templates needed for SNR)...", flush=True)
    t0 = time.time()
    analyzer = si.create_sorting_analyzer(sorting, recording, format="memory", sparse=True)
    analyzer.compute("random_spikes")
    analyzer.compute("waveforms")
    analyzer.compute("templates")
    analyzer.compute("noise_levels")
    analyzer.compute("unit_locations")
    metrics = sqm.compute_quality_metrics(analyzer, metric_names=["firing_rate", "snr", "isi_violation"])
    print(f"Quality metrics computed in {time.time()-t0:.1f}s", flush=True)
    print(metrics.head(10), flush=True)
    print("columns:", list(metrics.columns), flush=True)

    metrics_path = Path(r"C:\Users\franc\MEA project\outputs\reports\stage1_sorter_lupin_quality_metrics.csv")
    metrics.to_csv(metrics_path)
    print(f"Saved {metrics_path}", flush=True)

    isi_col = [c for c in metrics.columns if "isi_violations_ratio" in c or c == "isi_violation"][0]
    keep_mask = (
        (metrics["snr"] >= SNR_MIN)
        & (metrics[isi_col] <= ISI_VIOLATION_MAX)
        & (metrics["firing_rate"] >= FIRING_RATE_MIN)
    )
    kept_unit_ids = metrics.index[keep_mask].tolist()
    print(f"\nCurated: kept {len(kept_unit_ids)}/{n_units_total} units "
          f"(SNR>={SNR_MIN}, ISI-violation<={ISI_VIOLATION_MAX}, FR>={FIRING_RATE_MIN}Hz)", flush=True)

    unit_locations_all = analyzer.get_extension("unit_locations").get_data()
    all_unit_ids = list(sorting.get_unit_ids())
    kept_indices = [all_unit_ids.index(u) for u in kept_unit_ids]

    spike_times_curated = {
        i: sorting.get_unit_spike_train(all_unit_ids[idx]) / fs for i, idx in enumerate(kept_indices)
    }
    curated_locations = unit_locations_all[kept_indices]
    n_curated = len(kept_indices)

    unit_to_electrode = match_units_to_electrodes(curated_locations[:, :2], electrode_coords)
    self_rate = np.zeros(n_channels)
    for i in range(n_curated):
        self_rate[unit_to_electrode[i]] += len(spike_times_curated[i]) / duration_s

    deposited = load_deposited_units(UNITS_PATH)
    deposited_unit_to_electrode = match_units_to_electrodes(deposited["coords"], electrode_coords)
    deposited_rate = aggregate_deposited_rate_per_electrode(deposited, deposited_unit_to_electrode, n_channels)

    rho, pval = spearmanr(self_rate, deposited_rate)
    self_burst_rate = network_burst_rate(spike_times_curated, n_curated, fs, duration_s)
    deposited_burst_rate = network_burst_rate(
        deposited["spike_times"], deposited["n_units"], fs, deposited["duration_s"]
    )
    burst_pct_diff = (
        100.0 * abs(self_burst_rate - deposited_burst_rate) / deposited_burst_rate
        if deposited_burst_rate > 0 else (float("inf") if self_burst_rate > 0 else 0.0)
    )

    result = {
        "raw_path": RAW_PATH,
        "units_path": UNITS_PATH,
        "sorter_name": "lupin_curated",
        "n_electrodes": n_channels,
        "n_sorted_units_total": n_units_total,
        "n_sorted_units_curated": n_curated,
        "n_deposited_units": deposited["n_units"],
        "curation_criteria": {"snr_min": SNR_MIN, "isi_violation_max": ISI_VIOLATION_MAX, "firing_rate_min_hz": FIRING_RATE_MIN},
        "self_rate_mean_hz": float(np.mean(self_rate)),
        "deposited_rate_mean_hz": float(np.mean(deposited_rate)),
        "firing_rate_spearman_rho": float(rho),
        "firing_rate_spearman_pval": float(pval),
        "self_network_burst_rate_per_min": self_burst_rate,
        "deposited_network_burst_rate_per_min": deposited_burst_rate,
        "network_burst_rate_pct_diff": burst_pct_diff,
    }
    print("\n" + json.dumps(result, indent=2), flush=True)

    out_path = Path(r"C:\Users\franc\MEA project\outputs\reports\stage1_sorter_curated_validation_results.json")
    out_path.write_text(json.dumps({"HO1_lupin_curated": result}, indent=2), encoding="utf-8")
    print(f"\nWrote {out_path}", flush=True)
