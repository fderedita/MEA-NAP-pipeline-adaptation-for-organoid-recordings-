"""Self-derived spike source: curated `lupin` sorting for recordings with no
deposited ground truth (DANDI:001872, and any future recording without
Units). Frozen policy per config/params.yaml `spike_detection` and
outputs/reports/stage1_validation.md's "Closing decision".

Consolidates the sorting + curation logic first prototyped ad-hoc in
notebooks/run_sorter_validation.py and notebooks/run_sorter_curation.py
(both HO1-specific, written during Stage 1) into a reusable function.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np

from src.config import require


def run_curated_sorting(raw_path: str, sorter_folder: str, config: dict) -> dict:
    """Run (or reload) `lupin` sorting on a raw recording, then apply QC
    curation matching the deposited ground truth's own criteria.

    Resumable: if `sorter_folder` already contains a completed sort, reloads
    it instead of re-running (sorting is the expensive step, up to several
    hours for a large recording -- see stage1_validation.md).

    Returns dict with: spike_times (dict[local_idx -> seconds]),
    n_units_total (pre-curation), n_units (post-curation), coords
    (curated units' spatial locations), electrode_coords, fs, duration_s,
    n_channels.
    """
    import spikeinterface as si
    import spikeinterface.extractors as se
    import spikeinterface.qualitymetrics as sqm
    import spikeinterface.sorters as ss

    sorter_name = require(config, "spike_detection.sorter_name")
    snr_min = require(config, "spike_detection.curation.snr_min")
    isi_max = require(config, "spike_detection.curation.isi_violation_max")
    fr_min = require(config, "spike_detection.curation.firing_rate_min_hz")

    recording = se.read_nwb_recording(raw_path, electrical_series_path="acquisition/ElectricalSeries")
    fs = recording.get_sampling_frequency()
    duration_s = recording.get_total_duration()
    n_channels = recording.get_num_channels()
    electrode_coords = recording.get_channel_locations()

    sorter_folder_path = Path(sorter_folder)
    log_path = sorter_folder_path / "spikeinterface_log.json"
    if sorter_folder_path.exists() and log_path.exists():
        sorting = ss.read_sorter_folder(str(sorter_folder_path))
    else:
        sorting = ss.run_sorter(
            sorter_name, recording, folder=str(sorter_folder_path), remove_existing_folder=True, verbose=False
        )

    all_unit_ids = list(sorting.get_unit_ids())
    n_units_total = len(all_unit_ids)
    if n_units_total == 0:
        return {
            "spike_times": {}, "n_units_total": 0, "n_units": 0,
            "coords": np.zeros((0, 2)), "electrode_coords": electrode_coords,
            "fs": fs, "duration_s": duration_s, "n_channels": n_channels,
        }

    analyzer = si.create_sorting_analyzer(sorting, recording, format="memory", sparse=True)
    analyzer.compute("random_spikes")
    analyzer.compute("waveforms")
    analyzer.compute("templates")
    analyzer.compute("noise_levels")
    analyzer.compute("unit_locations")
    metrics = sqm.compute_quality_metrics(analyzer, metric_names=["firing_rate", "snr", "isi_violation"])

    isi_col = [c for c in metrics.columns if "isi_violations_ratio" in c or c == "isi_violation"][0]
    keep_mask = (metrics["snr"] >= snr_min) & (metrics[isi_col] <= isi_max) & (metrics["firing_rate"] >= fr_min)
    kept_unit_ids = metrics.index[keep_mask].tolist()
    kept_indices = [all_unit_ids.index(u) for u in kept_unit_ids]

    unit_locations_all = analyzer.get_extension("unit_locations").get_data()
    spike_times = {i: sorting.get_unit_spike_train(all_unit_ids[idx]) / fs for i, idx in enumerate(kept_indices)}
    coords = unit_locations_all[kept_indices][:, :2] if len(kept_indices) else np.zeros((0, 2))

    return {
        "spike_times": spike_times,
        "n_units_total": n_units_total,
        "n_units": len(kept_indices),
        "coords": coords,
        "electrode_coords": electrode_coords,
        "fs": fs,
        "duration_s": duration_s,
        "n_channels": n_channels,
    }
