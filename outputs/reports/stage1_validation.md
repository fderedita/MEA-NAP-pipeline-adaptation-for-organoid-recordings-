# Stage 1 — Pipeline validation report (STOPPED FOR REVIEW)

**Status: acceptance criteria NOT met on any of the 4 human recorded subjects
(HO1-HO4), with any of the three methods tried (threshold, wavelet, and now
a real CPU spike sorter, `lupin`, at full scale).**
Per the handoff's explicit instruction ("If not met -> report the discrepancy and
stop for review, do not silently tune"), this report documents the discrepancy
and stops here for human review rather than adjusting parameters or the
comparison methodology to force a pass.

The third avenue (real CPU spike sorting via `spikeinterface`, expected to be
the most promising since it produces genuinely separated units, not raw
multi-unit activity) was run to completion on `HO1` at full scale
(2026-07-10) -- see "CPU spike sorter check" below. **It did not close the
gap** -- firing-rate correlation with ground truth was essentially zero
(rho=-0.025, not significant), the weakest of the three methods tried. Likely
explained by comparing uncurated sorter output (732 units) against
curated/QC-filtered ground truth (131 units), and untuned spatial parameters
-- see the detailed section for the reasoning and what's still open.

## Method

- Spike detection: MEA-NAP's Python-ported threshold detector (`thr4`,
  median - 4*MAD/0.6745), our frozen 300-6000Hz bandpass, full recording
  duration (180s), all electrodes, streamed one channel at a time.
- Ground truth: deposited, Kilosort2-curated `Units` table for the same
  subject (age-matched where the raw/units files aren't the exact same
  session -- see stage0_inventory.md open questions on the `age` tag).
- Units matched to electrodes via nearest-neighbor on (x_pos,y_pos) vs
  (rel_x,rel_y), since the Units table has no explicit electrode-ID column.
- Firing rate comparison: Spearman rho between self-derived and deposited
  per-electrode rate (deposited rate = sum of matched units' spikes / duration,
  0 for electrodes with no matched unit).
- Network burst rate comparison: MEA-NAP's own Bakkum ISI_N network-burst
  detector (`firing_rates_bursts`), applied identically to both the
  self-derived per-electrode spike times and the deposited per-unit spike
  times.

## Results — threshold method (all 4 human recorded subjects, complete)

| Subject | n_electrodes | n_units | self FR mean (Hz) | deposited FR mean (Hz) | Spearman rho | self burst rate (/min) | deposited burst rate (/min) | burst %diff |
|---|---|---|---|---|---|---|---|---|
| HO1 | 1020 | 131 | 4.080 | 0.173 | **0.163** | 860.2 | 68.7 | **1153%** |
| HO2 | 1014 | 173 | 4.215 | 0.086 | **0.091** | 686.3 | 45.7 | **1403%** |
| HO3 | 1020 | 80  | 2.016 | 0.055 | **0.081** | 1070.7 | 14.7 | **7200%** |
| HO4 | 1020 | 123 | 4.135 | 0.068 | **0.214** | 265.7 | 9.7  | **2648%** |

**Acceptance criteria (config/params.yaml):** Spearman rho >= 0.8, burst rate
%diff <= 15%. **No subject is remotely close on either metric.** The pattern
holds consistently across all 4 -- this rules out "unlucky on one subject" as
an explanation.

## Results — wavelet method (bior1.5 CWT, HO1 only)

Tested as an alternative detection method per user request (2026-07-10), on
the hypothesis that a more shape-selective detector (rejects crossings that
don't match a spike-like waveform) might narrow the gap. It did not -- it was
slightly worse on both metrics:

| Subject | Method | self FR mean (Hz) | Spearman rho | self burst rate (/min) | burst %diff |
|---|---|---|---|---|---|
| HO1 | threshold | 4.080 | 0.163 | 860.2  | 1153% |
| HO1 | wavelet   | 6.453 | **0.114** | 1105.1 | **1509%** |

Mechanistic explanation (see conversation log for full detail): MEA-NAP's
wavelet detector combines 5 independent scale-wise threshold checks via a
logical OR, and deliberately uses a "liberal" secondary threshold to minimize
missed spikes at the cost of more false positives -- both properties increase
detected activity relative to a single amplitude threshold, they don't
decrease it. Confirmed on a second, independent dataset too (3Brain
BrainWave5 sample file, see `docs/brainwave5_usage.md`): wavelet detected
~6x more activity than threshold there as well (11.69 Hz vs 1.93 Hz).
**Conclusion: neither available detection method is closer to ground truth
than the other -- the gap is structural (MUA vs curated SUA), not a
detection-method choice problem.**

## CPU spike sorter check (2026-07-10) — real sorting, still doesn't close the gap

Unlike threshold/wavelet (simple detectors), `spikeinterface` bundles real
CPU-capable spike **sorters** (`spykingcircus2`, `tridesclous2`, `lupin`) --
full pipelines with whitening, clustering (HDBSCAN), and template matching,
conceptually much closer to what produced the deposited ground truth
(Kilosort2) than raw threshold crossings.

**Feasibility test** (30-channel, 60-second subset of HO1): all three ran
successfully. `lupin` (spikeinterface's own sorter, combining ideas from
yass/tridesclous/spyking-circus/kilosort) was fastest (30.9s) and found the
most units (27) with plausible, varied spike counts -- chosen for the
full-scale run on that basis.

**Full-scale result** (`lupin`, all 1020 electrodes, full 180s, matched to
electrodes via each unit's computed spatial location, same strategy as the
deposited ground truth):

| Subject | Method | n_units | self FR mean (Hz) | Spearman rho | burst %diff | runtime |
|---|---|---|---|---|---|---|
| HO1 | threshold | -- | 4.080 | 0.163 | 1153% | ~51 min |
| HO1 | wavelet | -- | 6.453 | 0.114 | 1509% | ~40 min |
| HO1 | **lupin (real sorter)** | **732** | 1.754 | **-0.025** (n.s., p=0.42) | 1279% | ~73 min |

**Real spike sorting did not close the gap -- if anything it's the weakest
of the three on firing-rate correlation** (essentially zero/no correlation,
not even a weak positive one). Two likely reasons, neither of which is "the
sorter doesn't work":

1. **`lupin` found 732 units vs. Kilosort2's curated 131** -- ~5.6x more.
   This run used `lupin`'s raw output with no quality curation applied,
   while the deposited ground truth already went through Kilosort2 +
   explicit QC filtering (SNR<5, ISI-violation>0.3, firing-rate<0.05Hz
   exclusion -- see the HO1 notebook exploration's file metadata). Comparing
   "everything a sorter proposed" against "only what survived curation" is
   not an apples-to-apples comparison -- an equivalent curation/merging step
   on `lupin`'s output would be needed before concluding the sorter itself
   underperforms.
2. **Default spatial parameters weren't tuned for this array.** `lupin`'s
   defaults (`detection_radius_um=50`, `template_radius_um=100`, etc.) were
   not adjusted for MaxWell's actual electrode pitch/density -- mismatched
   radii can cause over-splitting (one neuron's signal across nearby
   electrodes treated as separate units), which would inflate the unit
   count in exactly the direction observed.

Neither of these was tuned/adjusted after seeing this result -- they're
documented as open follow-up work, not applied. Per the "don't silently
tune" rule, this result is reported as-is.

## Curation test (2026-07-10) — fixes aggregate stats, not per-electrode ranking

Per user request, applied QC curation to `lupin`'s already-computed output
(reloaded from disk, not re-sorted) using the *same* thresholds as the
deposited ground truth's own curation (SNR>=5, ISI-violation<=0.3,
firing-rate>=0.05Hz), via `spikeinterface.qualitymetrics` on a
`SortingAnalyzer` (waveforms/templates/noise levels computed fresh -- this
step took a few minutes, far less than the original ~73min sort since no
clustering/template-matching is re-run).

| | uncurated `lupin` | **curated `lupin`** | deposited (ground truth) |
|---|---|---|---|
| n_units | 732 | **235** | 131 |
| self FR mean (Hz) | 1.754 | **0.313** | 0.173 |
| Spearman rho | -0.025 | **-0.003** | (target >=0.8) |
| burst rate (/min) | 946.97 | **144.76** | 68.67 |
| burst %diff | 1279% | **111%** | (target <=15%) |

**Curation closes most of the gap on aggregate/population-level statistics**
(unit count 732->235, much closer to 131; mean firing rate 1.8x off instead
of ~10x; burst rate %diff dropped by >10x) **but does essentially nothing
for per-electrode ranking correlation** (rho stayed at ~0, not even weakly
positive). This is a real, informative split, not noise:

- The population-level *amount* of activity curated `lupin` finds is now
  plausibly similar to the deposited ground truth.
- *Which specific electrodes* are active according to `lupin` has no
  detectable relationship to *which specific electrodes* the deposited
  Units are near -- rank order is statistically indistinguishable from
  random (p=0.93).

**Most likely explanation**: the raw and deposited-Units files being
compared are not the exact same recording session (see stage0_inventory.md
-- HO1's two files are ~1h17min apart on the same calendar day, tagged with
the same nominal age but not confirmed to be temporally identical). If the
specific set of active neurons genuinely differs somewhat between the two
sessions (plausible for a live culture over ~1+ hour), *no* detection or
sorting method could recover electrode-level correlation, no matter how
good -- only aggregate population statistics would be expected to stay
comparable, which is exactly the pattern observed. This can't be confirmed
with the data currently available (no subject in 001603 has a raw file and
a deposited-Units file from the literal same session) -- flagged as an
open question, not resolved here.

**Implication for whether to test more sorters**: `spykingcircus2` and
`tridesclous2` do conceptually similar clustering + template matching to
`lupin`; if the session-mismatch hypothesis is right, they would likely
show the same "curation fixes aggregate stats, not per-electrode ranking"
pattern, at a cost of several more hours of compute each. Recommendation:
not run at full scale for now -- see "Open questions" below.

## Interpretation (not a tuning attempt -- explaining the discrepancy)

Self-derived firing rates are ~24-48x higher than deposited rates. This is
very likely NOT primarily a bug, but a real, expected mismatch between what's
being compared:

1. **Multi-unit vs single-unit activity.** Our threshold detector counts every
   threshold crossing on a channel (multi-unit activity, MUA) -- it makes no
   attempt to separate overlapping spikes from multiple nearby neurons.
   Kilosort2 (used for the deposited Units) explicitly deconvolves overlapping
   spikes into separate curated single units, so per-unit rates are inherently
   much lower than per-channel MUA rates.
2. **Curation removes activity, doesn't just relabel it.** The deposited Units
   were filtered by ISI-violation fraction, minimum firing rate, and SNR
   (per the HO1 notebook exploration's file metadata) -- units judged noisy or
   contaminated are dropped entirely, not folded into a remaining unit. Our
   threshold method has no equivalent quality gate.
3. **Sparse unit coverage relative to electrode count.** Only 131-173 curated
   units exist per subject, spread across 1014-1020 electrodes -- roughly
   85-87% of electrodes have NO matched deposited unit (deposited rate = 0 by
   construction) while our method detects activity on nearly all electrodes
   (1018/1020 in an earlier exploratory run). This alone would badly damage a
   Spearman correlation regardless of whether the underlying detection is
   otherwise reasonable, since it compares "activity everywhere" against
   "activity only where a unit happened to survive curation," not two
   estimates of the same underlying quantity.
4. **Network burst rate** is similarly inflated for the same MUA-vs-SUA
   reason: many more (near-)simultaneous threshold crossings across many
   channels look like far more frequent network bursts than the sparser
   curated-unit population activity.

None of this was tuned or reverse-engineered from the numbers after the fact --
it follows directly from what "curated Units via Kilosort2 + QC filtering"
vs "raw per-channel amplitude threshold" mean methodologically, and the
handoff document's own framing already flagged the pragmatic track as
"a coarse check, not full sorting" (Section 3, Task 1.3) -- but the actual
mismatch is far larger than "coarse" suggests.

## Verified vs assumed

- VERIFIED: the numbers above are real outputs of real code run against real
  mirrored raw + deposited-Units NWB files (not simulated/estimated).
- VERIFIED: MEA-NAP's threshold detector and burst detector are themselves
  validated against MATLAB reference output (per external/MEA-NAP's own
  parity test suite) -- the discrepancy is not attributable to a bug in the
  detector implementation itself.
- ASSUMED/NOT VERIFIED: that nearest-neighbor spatial matching (unit
  x_pos/y_pos to electrode rel_x/rel_y) is the correct unit-to-electrode
  assignment. If the deposited Units table's coordinate system differs from
  the raw electrodes table's in origin/scale/orientation, matches could be
  wrong -- not independently confirmed.
- ASSUMED/NOT VERIFIED: that raw+units file pairs are directly comparable
  despite not being the exact same recording session (see stage0_inventory.md
  -- the `age` tag groups sessions from different calendar timestamps). If the
  organoid's activity genuinely differs between the specific raw session used
  and the specific units session used (even at "the same" nominal age), part
  of the mismatch could be biological/temporal rather than methodological.

## Open questions for human review

1. **Is Spearman rho on raw per-electrode rate the right comparison at all**,
   given the fundamental MUA-vs-curated-SUA mismatch and the ~85% zero-rate
   electrodes on the deposited side? An alternative (e.g. restricting to
   electrodes with >=1 matched unit, or comparing rank-order only among
   "active" electrodes on both sides) would be a real methodology change, not
   a tuning fix -- needs your call, not something to silently substitute.
2. **Is threshold/MUA detection even the right acceptance bar for this
   project**, or should "pipeline validated" instead mean something more like
   "reasonable per-electrode activity ranking, not exact rate match"? The
   config's rho>=0.8 criterion was written before this diagnostic; worth
   revisiting given what we now know about what's being compared.
3. Given no GPU on this machine (env_lock.txt), the "rigorous" Kilosort track
   isn't available locally -- if MUA-vs-SUA is judged an unacceptable gap,
   the realistic alternatives are (a) redefine the acceptance criteria/
   comparison for what a CPU-only method can be expected to achieve, or
   (b) move sorting to a GPU-equipped machine.
