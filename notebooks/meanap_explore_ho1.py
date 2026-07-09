"""Exploratory run: MEA-NAP's Python port (step 1 spike detection + step 2
firing-rate/burst stats) on a window of HO1's raw recording.

Not a permanent pipeline module -- a one-off to see what MEA-NAP produces on
our actual MaxOne data before deciding how (or whether) to fold it into the
project's own Stage 1/2. See docs/handoff_foundation_phase.md and the
conversation log for context.

Uses only a time window (not the full ~14.7GB recording) since this machine
is RAM-constrained (~2GB free at time of writing).
"""
from __future__ import annotations

import time
from pathlib import Path

import numpy as np
from pynwb import NWBHDF5IO

from meanap.pipeline.spike_detection import detect_spikes_recording, SpikeDetectionParams
from meanap.pipeline.firing_rates import firing_rates_bursts
from meanap.params import Params

RAW_PATH = Path(r"C:\Users\franc\MEA project\data\raw\sub-HO1_ses-20250924T011900_ecephys.nwb")
WINDOW_S = 30.0  # keep memory modest on this machine

print(f"Loading {WINDOW_S}s window from {RAW_PATH.name} ...")
io = NWBHDF5IO(str(RAW_PATH), mode="r")
nwbfile = io.read()
ts = nwbfile.acquisition["ElectricalSeries"]
fs = float(ts.rate)
n_window_samples = int(WINDOW_S * fs)
print(f"fs = {fs} Hz, window = {n_window_samples} samples")

t0 = time.time()
dat = ts.data[:n_window_samples, :]  # (n_samples, n_channels), stays uint16 on read
print(f"Loaded dat {dat.shape} dtype={dat.dtype} in {time.time() - t0:.1f}s, "
      f"~{dat.nbytes / 1e9:.2f} GB")

electrodes = nwbfile.electrodes
channels = np.arange(dat.shape[1])  # 0-based index used consistently downstream
rel_x = np.asarray(electrodes["rel_x"][:], dtype=float)
rel_y = np.asarray(electrodes["rel_y"][:], dtype=float)
coords = np.column_stack([rel_x, rel_y])
print(f"electrodes: {len(channels)}, coords range x=[{rel_x.min():.1f},{rel_x.max():.1f}] "
      f"y=[{rel_y.min():.1f},{rel_y.max():.1f}]")

io.close()

# ── Step 1: spike detection ──────────────────────────────────────────────
print("\nRunning spike detection (threshold method, thr4/thr5 -- skipping the "
      "slower wavelet method for this exploratory run)...")
det_params = SpikeDetectionParams(
    fs=fs,
    filter_low_pass=300.0,   # match our own project's frozen config/params.yaml band
    filter_high_pass=6000.0,
    thresholds=[4.0, 5.0],
    wname_list=[],           # skip bior1.5 wavelet method for speed in this exploration
)
t0 = time.time()
result = detect_spikes_recording(dat.astype(np.int16), channels, fs, det_params)
print(f"Spike detection done in {time.time() - t0:.1f}s")

n_spikes_thr4 = sum(len(v.get("thr4", [])) for v in result.spike_times.values())
n_spikes_thr5 = sum(len(v.get("thr5", [])) for v in result.spike_times.values())
n_active_thr4 = sum(1 for v in result.spike_times.values() if len(v.get("thr4", [])) > 0)
print(f"thr4: {n_spikes_thr4} spikes total across {n_active_thr4}/{len(channels)} active channels")
print(f"thr5: {n_spikes_thr5} spikes total")

# ── Step 2: firing rates + bursts ────────────────────────────────────────
print("\nRunning firing-rate / burst analysis (thr4 spikes)...")
spike_times_thr4 = {ch: v["thr4"] for ch, v in result.spike_times.items() if "thr4" in v}
p2 = Params(fs=fs)
ephys = firing_rates_bursts(spike_times_thr4, len(channels), fs, WINDOW_S, p2)

print("\n=== ephys summary (thr4, {}s window) ===".format(WINDOW_S))
for k in ("fr_mean", "fr_std", "fr_median", "num_active_elec", "n_bursts", "nburst_rate"):
    if k in ephys:
        print(f"  {k}: {ephys[k]}")
print("\nfull ephys keys:", sorted(ephys.keys()))

out_dir = Path(r"C:\Users\franc\MEA project\outputs\reports")
np.savez(
    out_dir / "meanap_explore_ho1.npz",
    channels=channels,
    coords=coords,
    fs=fs,
    window_s=WINDOW_S,
    n_spikes_thr4=n_spikes_thr4,
    n_spikes_thr5=n_spikes_thr5,
    n_active_thr4=n_active_thr4,
    **{f"ephys_{k}": v for k, v in ephys.items() if np.isscalar(v) or (hasattr(v, "shape"))},
)
print(f"\nSaved outputs/reports/meanap_explore_ho1.npz")
