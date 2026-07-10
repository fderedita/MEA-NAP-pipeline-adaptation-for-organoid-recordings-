# Using MEA-NAP with 3Brain BrainWave5 (.brw) recordings

This lab's MEA hardware is 3Brain (BioCAM-family), which exports recordings as
`.brw` files -- 3Brain's own HDF5-based format. **MEA-NAP does not support
3Brain natively**: its built-in file converter and electrode-layout tables
only cover Multichannel Systems and Axion Maestro hardware. This doc covers
how we work around that, and what each path can and can't do.

Everything referenced here lives in this repo:
- `src/io_brainwave.py` -- loads `.brw` files, exports to MEA-NAP's `.mat` format
- `notebooks/run_meanap_on_brainwave.py` -- runs detection + firing-rate/burst
  analysis end-to-end from a `.brw` file
- `tests/fixtures/BioCAM_BrainWave5_HW_3.0_FW_1.7.brw` -- a real (public,
  from NeuralEnsemble's `ephy_testing_data` test suite) BrainWave5 sample
  file used to verify all of this actually works, not just in theory

## Two ways to use MEA-NAP with your data

### Path A: scripting (recommended -- gives correct results end-to-end)

```
conda activate organoid-mea-foundation
python notebooks\run_meanap_on_brainwave.py path\to\your_recording.brw --method threshold
```

This reads the `.brw` file directly (via `spikeinterface`'s 3Brain reader,
not MEA-NAP's own converter), runs spike detection across all channels in
parallel, computes firing rates and network bursts (MEA-NAP's own algorithms,
just called directly rather than through the GUI), and writes to
`<recording_name>_meanap_output/`:

- `summary.json` -- recording-level stats (mean firing rate, burst rate, etc.)
- `firing_rates_per_channel.csv` -- per-electrode firing rate + real (x,y) position
- `firing_rate_heatmap.png` -- spatial plot, correctly positioned using the
  recording's own real electrode coordinates (not a generic layout table)

**Options:**
- `--method threshold` (fast, default) or `--method wavelet` (much slower --
  budget roughly 15-20x threshold's runtime; more selective, rejects
  crossings that don't look spike-shaped, but see the caveat in "which
  method to use" below)
- `--workers N` -- how many channels to process in parallel (default 6).
  Memory use scales roughly as `(4096/N channels) x (recording duration in
  samples) x 4 bytes` per worker -- for a long recording, use MORE workers
  with smaller batches each if you hit memory limits, not fewer.
- `--out DIR` -- output location (default: next to the input file)

Only steps 1-2 of MEA-NAP (spike detection, firing rates/bursts) are wired
up here. Steps 3-4 (STTC functional connectivity, network graph metrics)
aren't included in this first version -- extend `notebooks/run_meanap_on_brainwave.py`
following the same pattern as `src/validate_pipeline.py` if/when needed.

### Path B: MEA-NAP's GUI (point-and-click, but with a real limitation)

For lab members who'd rather not run scripts:

```
conda activate organoid-mea-foundation
meanap-gui
```

But the GUI can't read `.brw` files directly (no 3Brain converter). First
convert once per recording:

```python
from src.io_brainwave import export_to_meanap_mat
export_to_meanap_mat("your_recording.brw", "your_recording.mat")
```

Then point the GUI at `your_recording.mat`.

**Known limitation: spatial plots will be wrong in the GUI.** MEA-NAP's
channel-layout dropdown only has real entries for Multichannel Systems/Axion
hardware (`MCS60`, `MCS60old`, `MCS59`, `Axion64`, `Axion16`); it also lists
`Mea256` and `Custom` but neither is actually implemented in the Python
port's coordinate lookup (`src/meanap/pipeline/channel_layout.py` raises an
error for both). Selecting any of these for a 3Brain recording will produce
either an error or incorrectly-positioned electrode heatmaps/network plots.
**The numbers themselves (firing rates, burst stats, network metrics) are
still computed correctly** -- the coordinate system only affects *where
MEA-NAP draws things on screen*, not what it calculates. If correct spatial
plots matter, use Path A.

We did not modify `external/MEA-NAP` (the vendored copy of the tool itself)
to add a real 3Brain layout, to keep it easy to pull upstream updates later.
If this limitation becomes a recurring problem, the fix is a real (if small)
code change to `channel_layout.py` and the GUI's recording panel -- ask
Claude Code to do this if/when it's worth prioritizing.

## The event-based compression gap-filling choice

If your recordings are saved in BrainWave5's "raw compressed + events" mode
(3Brain's official name: **"Noise Blanking compression"** -- only waveform
snippets around detected threshold crossings are stored, to save disk
space), reading them requires deciding how to fill the "gaps" between
stored events. `src/io_brainwave.py` defaults to `fill_gaps_strategy="synthetic_noise"`,
**not** `"zeros"`:

- `"synthetic_noise"` fills gaps with Gaussian noise parameterized by the
  REAL per-channel noise mean/stddev that 3Brain's hardware also records
  throughout acquisition (not arbitrary noise). **This is guaranteed by the
  BRW v4.x format spec itself** (3Brain's official "File Format
  Documentation For BRW v4.x, BXR v3.x and BCMP v1.x" -- the same spec
  BrainWave 5.x writes to), not just something our one test file happens to
  have: whenever event-based/Noise-Blanking compression is used, the format
  always includes `NoiseMean`/`NoiseStdDev`/`NoiseTOC`/`NoiseChIdxs`
  datasets alongside the event data -- confirmed by reading the official
  PDF spec directly (Section on `EventsBasedSparseRaw`, pages 12-13), not
  just inferred from the reader's source code. This avoids sharp
  flat-to-signal jumps at every gap/event boundary, which both detection
  methods could otherwise mistake for spikes, and gives more realistic
  noise statistics for threshold-based detection.
- `"zeros"` fills gaps with a flat baseline value and is available (`--
  fill-gaps-strategy zeros` equivalent by passing it explicitly to
  `load_brainwave_recording`/`export_to_meanap_mat`) but not recommended
  for spike detection -- it measurably inflated the detected firing rate in
  our own test (1.93 Hz mean with synthetic_noise vs 9.17 Hz mean with
  zeros, same file, same method -- the difference is gap-boundary artifacts,
  not real activity).

**More fundamentally**: event-based compression means the acquisition
hardware already decided, at recording time, what was "worth keeping" via
its own onboard threshold. No downstream spike-detection method run on the
resulting file can recover activity the hardware itself discarded. If
detection sensitivity matters for a given experiment, that's a BrainWave5
acquisition-setting decision (or use continuous "raw data" mode instead of
event-based compression), not something fixable after the fact in analysis.

## Which detection method to use (threshold vs wavelet)

Both are available (`--method threshold` / `--method wavelet`). From our own
validation work on a different dataset (DANDI human organoid recordings,
see `outputs/reports/stage1_validation.md`): neither simple threshold nor
wavelet detection came close to matching real spike-sorted (Kilosort2 +
curated) ground truth -- wavelet was not meaningfully better, in one direct
comparison it was slightly worse. Both methods detect multi-unit activity
(anything crossing a threshold/matching a spike-like shape), not
individually-identified neurons. Treat either method's output as a coarse,
fast first-pass indicator of activity level and rough timing, not a
substitute for real spike sorting if your analysis needs single-unit
resolution.

## Beyond detection: real CPU spike sorting is possible (not yet wired into the runner script)

`run_meanap_on_brainwave.py` only does simple detection (threshold/wavelet),
not full spike sorting. But `spikeinterface` (already in this environment)
bundles real CPU-capable sorters that do genuine clustering + template
matching, much closer in spirit to Kilosort than to a threshold check:
`spykingcircus2`, `tridesclous2`, `lupin` (spikeinterface's own sorter,
combining ideas from yass/tridesclous/spyking-circus/kilosort). Feasibility-
tested on a 30-channel/60s DANDI subset (2026-07-10):

| Sorter | Time (30ch/60s) | Units found |
|---|---|---|
| `spykingcircus2` | 106.4s | 20 |
| `tridesclous2` | 69.7s | 25 |
| `lupin` | **30.9s** | **27** |

All three produced genuinely distinct units with plausible, varied spike
counts -- not just "everything above a threshold." `lupin` was both fastest
and found the most units. None of these require a GPU. Full-scale runs
(hundreds to thousands of channels, minutes of recording) are estimated at
1+ hours per recording (channel-count scaling for dense-array clustering is
typically worse than linear, so this is a rough lower bound) -- not yet run
to completion on a full recording as of this writing. Basic usage pattern
(not yet wrapped into a script for this repo):

```python
import spikeinterface.extractors as se
import spikeinterface.sorters as ss

recording = se.read_nwb_recording("file.nwb", electrical_series_path="acquisition/ElectricalSeries")
# or, for a .brw file: recording, *_ = src.io_brainwave.load_brainwave_recording("file.brw")
sorting = ss.run_sorter("lupin", recording, folder="output_folder")
```

If GPU access becomes available (see conversation log), Kilosort4 is also
available through the same `spikeinterface.sorters.run_sorter()` interface
(`pip install kilosort` first) -- this machine has no GPU, so Kilosort-class
sorting isn't available here; if that's needed now, it requires different
hardware.
