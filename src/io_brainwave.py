"""Loader/converter for 3Brain BrainWave5 (.brw) raw recording files.

The lab's own MEA hardware is 3Brain (BioCAM-family), not MaxWell -- .brw
files are 3Brain's own HDF5-based format, not natively readable by MEA-NAP
(which only ships named electrode layouts for Multichannel Systems and
Axion hardware) or by our NWB-based DANDI pipeline.

Rather than hand-parsing 3Brain's proprietary HDF5 schema, this uses
spikeinterface's `read_biocam` (backed by neo's BiocamRawIO), which is
maintained by the wider ephys community and already handles both
continuous and event-based-compressed .brw files correctly. Verified
against a real BrainWave5 sample file (tests/fixtures/BioCAM_BrainWave5_HW_3.0_FW_1.7.brw,
from NeuralEnsemble's public ephy_testing_data test suite): 4096 channels,
64x64 grid, 60um pitch, correct real electrode coordinates recovered
directly from the file (no named-layout lookup needed -- same pattern as
this project's NWB/MaxWell handling in validate_pipeline.py).

IMPORTANT: some .brw files use "event-based compression" (3Brain's
acquisition hardware only stores waveform snippets around detected
threshold-crossing events, to save disk space -- everything else is a
"gap") and REQUIRE an explicit `fill_gaps_strategy` to read traces -- see
`load_brainwave_recording`'s docstring. Default here is "synthetic_noise",
not "zeros": neo's reader fills gaps with Gaussian noise parameterized by
the REAL per-channel noise mean/stddev that 3Brain's hardware also records
throughout the recording (not arbitrary noise) -- this avoids the sharp
flat-to-signal discontinuities "zeros" creates at every gap/event boundary,
which both the threshold and wavelet detectors could otherwise mistake for
spikes, and gives a more realistic median/MAD noise estimate for threshold
detection. Residual caveat: any detection landing inside a gap is not a
real spike (statistically equivalent to a false positive on quiet real
noise, not a new kind of artifact). See conversation log / commit history
for the reasoning (verified by reading neo's biocamrawio.py source directly,
not assumed).

ALSO IMPORTANT: event-based compression means the acquisition hardware
already decided, at recording time, what counted as "worth keeping" via
its own onboard threshold. No downstream spike-detection method run on the
resulting file can recover activity the hardware itself discarded --
that's a data-collection-time decision, not something fixable in analysis.
"""
from __future__ import annotations

from pathlib import Path

import h5py
import numpy as np
from spikeinterface.extractors import read_biocam


def load_brainwave_recording(
    brw_path: str | Path, fill_gaps_strategy: str | None = "synthetic_noise"
):
    """Open a .brw file and return (recording, coords, fs, n_channels, duration_s).

    Parameters
    ----------
    brw_path : path to the .brw file
    fill_gaps_strategy : {"zeros", "synthetic_noise", None}
        Only relevant for event-based-compressed recordings (common for
        long BrainWave5 acquisitions to save disk space). "zeros" fills
        gaps with the flat baseline value (2048 for 3Brain's 12-bit
        unsigned representation); "synthetic_noise" fills them with
        generated noise instead. If the file is NOT event-based
        compressed, this parameter has no effect. If it IS compressed and
        this is left None, spikeinterface will raise -- we deliberately
        don't silently pick a default deeper than this module's own
        default, so callers are aware this choice exists.

    Returns
    -------
    recording : spikeinterface BaseRecording (traces via .get_traces())
    coords : (n_channels, 2) array, real electrode coordinates in micrometers
    fs : sampling rate in Hz
    n_channels : int
    duration_s : float
    """
    recording = read_biocam(str(brw_path), fill_gaps_strategy=fill_gaps_strategy)
    coords = np.asarray(recording.get_channel_locations(), dtype=float)
    fs = float(recording.get_sampling_frequency())
    n_channels = recording.get_num_channels()
    duration_s = float(recording.get_total_duration())
    return recording, coords, fs, n_channels, duration_s


def export_to_meanap_mat(
    brw_path: str | Path, out_mat_path: str | Path, fill_gaps_strategy: str = "synthetic_noise"
) -> None:
    """Convert a .brw file to the .mat format MEA-NAP's GUI/File-conversion-free
    pipeline expects (see meanap.pipeline.io.load_raw_recording): a plain
    HDF5 file with `dat` (n_channels, n_samples), `channels` (channel IDs),
    `fs` (sampling rate scalar).

    This is for lab members using MEA-NAP's GUI, which has no built-in 3Brain
    converter (only Multichannel Systems / Axion). After running this once,
    the GUI can load the resulting .mat directly.

    NOTE: this does NOT solve the electrode-coordinate problem for the GUI's
    own spatial plots -- MEA-NAP's channel-layout dropdown only offers
    Multichannel Systems / Axion / a nonfunctional "Custom" placeholder (see
    docs/brainwave5_usage.md). The GUI will run detection, firing-rate, and
    burst analysis correctly on the converted file; spatial network plots
    will not be positioned correctly unless run via the scripting path
    (notebooks/run_meanap_on_brainwave.py), which uses this module's real
    coordinates directly.
    """
    recording, coords, fs, n_channels, duration_s = load_brainwave_recording(
        brw_path, fill_gaps_strategy=fill_gaps_strategy
    )
    n_samples = recording.get_num_frames()

    out_mat_path = Path(out_mat_path)
    out_mat_path.parent.mkdir(parents=True, exist_ok=True)

    # meanap.pipeline.io.load_raw_recording reads f["dat"][()].T expecting
    # the on-disk shape to be (n_channels, n_samples) so the transpose lands
    # on (n_samples, n_channels) -- write it pre-transposed to match.
    channel_ids = np.arange(1, n_channels + 1)  # 1-based, matches 3Brain's own channel numbering

    with h5py.File(out_mat_path, "w") as f:
        dat_ds = f.create_dataset("dat", shape=(n_channels, n_samples), dtype="float32")
        # Stream in chunks to avoid holding the full (4096 x n_samples)
        # array in memory at once for long recordings.
        chunk_frames = 200_000
        for start in range(0, n_samples, chunk_frames):
            end = min(start + chunk_frames, n_samples)
            traces = recording.get_traces(start_frame=start, end_frame=end).astype("float32")  # (frames, channels)
            dat_ds[:, start:end] = traces.T
        f.create_dataset("channels", data=channel_ids)
        f.create_dataset("fs", data=np.array([fs]))
