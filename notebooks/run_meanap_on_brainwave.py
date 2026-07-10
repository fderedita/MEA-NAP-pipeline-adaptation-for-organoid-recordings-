"""Run MEA-NAP spike detection + firing-rate/burst analysis on a 3Brain
BrainWave5 (.brw) recording, using the lab's own real electrode coordinates
(not MEA-NAP's built-in MCS/Axion layout tables, which don't cover 3Brain
hardware -- see docs/brainwave5_usage.md).

This is the SCRIPTING path (vs. MEA-NAP's point-and-click GUI). It gives
correct numbers *and* a correctly-positioned spatial firing-rate heatmap.
The GUI can also read files converted via src.io_brainwave.export_to_meanap_mat,
but its spatial plots will NOT be positioned correctly for 3Brain data (its
channel-layout dropdown has no real 3Brain entry) -- see the usage doc.

Usage:
    python notebooks\\run_meanap_on_brainwave.py <path_to.brw> [--method threshold|wavelet]
                                                  [--out OUTDIR] [--workers N]

Only spike detection + firing-rate/burst stats (MEA-NAP steps 1-2) are run
here -- functional connectivity and network graph metrics (steps 3-4) are
not included in this first version; extend by following the same pattern
used in src/validate_pipeline.py if/when needed.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from meanap.pipeline.spike_detection import bandpass_filter, detect_spikes_threshold, detect_spikes_wavelet
from meanap.pipeline.firing_rates import firing_rates_bursts
from meanap.params import Params

from src.io_brainwave import load_brainwave_recording


def _process_channel_batch(
    brw_path: str, ch_indices: list[int], low: float, high: float, method: str,
) -> dict[int, np.ndarray]:
    """Worker: opens its own recording handle (spikeinterface/neo objects
    aren't guaranteed safe to share across process boundaries), processes a
    batch of channels. Mirrors src/validate_pipeline.py's approach.

    Fetches this worker's whole channel batch in ONE get_traces() call
    (not one call per channel) -- a single-channel-at-a-time version of this
    was tried first and measured at ~0.2s/channel of pure call overhead
    (unrelated to the actual filtering/detection work), dominating runtime.
    Bulk-fetching trades that for higher peak memory: roughly
    len(ch_indices) x n_samples x 4 bytes (float32) held at once per worker
    -- for a long recording, use MORE workers with SMALLER channel batches
    each (not fewer/bigger) if memory is tight, since filtering needs each
    channel's full duration in one piece to avoid edge artifacts at chunk
    boundaries. See docs/brainwave5_usage.md for sizing guidance.
    """
    from src.io_brainwave import load_brainwave_recording  # re-import in worker process

    recording, _coords, fs, _n, _dur = load_brainwave_recording(brw_path)
    all_channel_ids = recording.get_channel_ids()
    batch_ids = [all_channel_ids[i] for i in ch_indices]
    traces = recording.get_traces(channel_ids=batch_ids).astype(np.float32)  # (n_samples, len(ch_indices))

    results: dict[int, np.ndarray] = {}
    for local_i, ch_idx in enumerate(ch_indices):
        trace = traces[:, local_i].astype(float)
        filtered = bandpass_filter(trace, fs, low, high)
        if method == "threshold":
            frames, _thr = detect_spikes_threshold(filtered, 4.0, 2.0, fs, filter_flag=False)
        else:
            frames = detect_spikes_wavelet(filtered, fs, wid_ms=(0.4, 0.8), ns=5, option="l", L=-0.12, wname="bior1.5")
        results[ch_idx] = frames.astype(float) / fs
    return results


def run(brw_path: str, method: str, out_dir: Path, n_workers: int, low: float = 300.0, high: float = 6000.0):
    out_dir.mkdir(parents=True, exist_ok=True)

    recording, coords, fs, n_channels, duration_s = load_brainwave_recording(brw_path)
    print(f"Loaded {brw_path}: {n_channels} channels, fs={fs:.1f}Hz, duration={duration_s:.1f}s")

    chunks = [c.tolist() for c in np.array_split(np.arange(n_channels), n_workers) if len(c) > 0]
    spike_times: dict[int, np.ndarray] = {}
    t0 = time.time()
    with ProcessPoolExecutor(max_workers=n_workers) as executor:
        futures = [
            executor.submit(_process_channel_batch, brw_path, chunk, low, high, method)
            for chunk in chunks
        ]
        for future in as_completed(futures):
            spike_times.update(future.result())
    print(f"Spike detection ({method}) done in {time.time() - t0:.1f}s")

    p = Params(fs=fs)
    ephys = firing_rates_bursts(spike_times, n_channels, fs, duration_s, p)

    # Per-channel CSV (channel id, coords, firing rate)
    fr = ephys.get("FR", np.full(n_channels, np.nan))
    df = pd.DataFrame({
        "channel_idx": np.arange(n_channels),
        "x_um": coords[:, 0],
        "y_um": coords[:, 1],
        "firing_rate_hz": fr,
    })
    csv_path = out_dir / "firing_rates_per_channel.csv"
    df.to_csv(csv_path, index=False)

    # Recording-level summary
    summary = {
        "brw_path": str(brw_path),
        "method": method,
        "n_channels": n_channels,
        "fs": fs,
        "duration_s": duration_s,
        "FRmean": ephys.get("FRmean"),
        "FRmedian": ephys.get("FRmedian"),
        "numActiveElec": ephys.get("numActiveElec"),
        "NBurstRate": ephys.get("NBurstRate"),
        "numNbursts": ephys.get("numNbursts"),
        "fracInNburst": ephys.get("fracInNburst"),
    }
    summary_path = out_dir / "summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, default=float), encoding="utf-8")

    # Spatial firing-rate heatmap using REAL 3Brain coordinates (not
    # MEA-NAP's own plot_heatmap, which only supports its built-in
    # MCS/Axion layout lookup -- see docs/brainwave5_usage.md)
    fig, ax = plt.subplots(figsize=(6, 5))
    valid = ~np.isnan(fr)
    sc = ax.scatter(coords[valid, 0], coords[valid, 1], c=fr[valid], cmap="viridis", s=8)
    plt.colorbar(sc, label="Firing rate (Hz)")
    ax.set_xlabel("x (um)")
    ax.set_ylabel("y (um)")
    ax.set_title(f"Firing rate heatmap ({method} detection)\n{Path(brw_path).name}")
    ax.set_aspect("equal")
    fig.tight_layout()
    fig.savefig(out_dir / "firing_rate_heatmap.png", dpi=200)
    plt.close(fig)

    print(f"\nWrote {csv_path}, {summary_path}, and firing_rate_heatmap.png to {out_dir}")
    print(json.dumps(summary, indent=2, default=float))
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("brw_path")
    parser.add_argument("--method", choices=["threshold", "wavelet"], default="threshold")
    parser.add_argument("--out", default=None, help="output directory (default: alongside the .brw file)")
    parser.add_argument("--workers", type=int, default=6)
    args = parser.parse_args()

    brw = Path(args.brw_path)
    out_dir = Path(args.out) if args.out else brw.parent / f"{brw.stem}_meanap_output"
    run(args.brw_path, args.method, out_dir, args.workers)
