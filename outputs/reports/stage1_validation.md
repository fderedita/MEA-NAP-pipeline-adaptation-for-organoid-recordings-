# Stage 1 — Pipeline validation report (CLOSED, 2026-07-10)

**Status: acceptance criteria (rho>=0.8, burst %diff<=15%) NOT met by any of
the four methods tried (threshold, wavelet, uncurated CPU sorter, curated
CPU sorter), on any of the 4 human recorded subjects tested. Accept this 
outcome and proceed to Stage 2** -- see "Closing decision" at the end of 
this report for what that means for Stage 2's methodology.

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
compared are not the exact same recording session (see `_RAW_FILE_FOR_UNITS`
in `src/build_feature_matrix.py` for the exact age-matched pairing used).
Checked precisely for all four subjects (raw file timestamp vs. paired
deposited-Units file timestamp, from `outputs/manifests/manifest_001603.csv`):

| Subject | Raw session | Units session | Gap |
|---|---|---|---|
| HO1 | 2025-09-24 01:19:00.52 | 2025-09-24 00:21:25.11 | **~57 min 35 s** |
| HO4 | 2025-09-24 01:19:00.33 | 2025-09-24 00:21:26.47 | **~57 min 34 s** |
| HO2 | 2025-09-12 14:48:39.45 | 2025-09-16 19:09:27.39 | **~4 days, 4h 21min** |
| HO3 | 2025-09-12 15:08:17.54 | 2025-09-16 19:09:30.48 | **~4 days, 4h 1min** |

(Earlier drafts of this report cited "~1h17min" for HO1 from a rougher
estimate -- 57min35s is the precise figure from the actual paired files.)

This is not just plausible but **quantitatively consistent with the
observed rho pattern**: the two subjects with the short (~1h) gap have the
two highest per-electrode correlations (HO4 rho=0.214, HO1 rho=0.163), and
the two subjects with the long (~4-day) gap have the two lowest (HO2
rho=0.091, HO3 rho=0.081) -- see the results table above. A live culture's
active-neuron population plausibly drifts more over 4 days than over 1
hour, and if the specific set of active neurons genuinely differs between
the compared sessions, *no* detection or sorting method could recover
electrode-level correlation, no matter how good -- only aggregate
population statistics would be expected to stay comparable, which is
exactly the pattern observed for all four subjects.

With n=4 subjects this is an association, not a controlled proof (no
subject in 001603 has a raw file and a deposited-Units file from the
literal same session, so the gap-vs-rho relationship can't be tested
within-subject) -- but it is now the best-supported explanation available,
not merely a hypothesis of last resort. Flagged as strengthened evidence
for the "Closing decision" below, not a fully resolved question.

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

## Closing decision (human, 2026-07-10)

Four methods tested (threshold, wavelet, uncurated CPU sorter, curated CPU
sorter), all on real HO1-HO4 raw+deposited-Units pairs, none met the
original per-electrode rate/burst acceptance criteria. Curation (`lupin` +
QC matching the deposited criteria) fixed aggregate/population-level
statistics substantially (unit count, mean rate, burst rate all much
closer to ground truth) but left per-electrode ranking at chance level --
most plausibly because no subject in 001603 has a raw file and a
deposited-Units file from the literal same recording session (see
"Curation test" above), which would cap electrode-level agreement
regardless of method quality. Running the other two available CPU sorters
(`spykingcircus2`, `tridesclous2`) at full scale was considered and
declined -- they do conceptually similar clustering/template-matching to
`lupin` and would likely reproduce the same pattern at a cost of several
more hours each, per the same reasoning.

**Addendum (2026-07-13):** precise raw/Units session-gap timestamps for all
four subjects were checked (see "Most likely explanation" above) -- HO1 and
HO4 have a ~57-minute gap, HO2 and HO3 have a ~4-day gap, and rho ranks
exactly the same way (HO4 0.214 > HO1 0.163 > HO2 0.091 > HO3 0.081). This
doesn't change the decision below, but meaningfully strengthens its
rationale: the session-mismatch explanation is no longer just the most
plausible account of a null result, it's quantitatively consistent with the
one variable (session gap) most likely to drive genuine biological drift in
a live culture.

**SUPERSEDED 2026-07-13** -- see "Second addendum" at the end of this
section. The bullet list immediately below is the ORIGINAL 2026-07-10
decision, kept verbatim for the historical record; it is no longer the
active Stage 2 policy.

**Decision: proceed to Stage 2 accepting this outcome**, with the following
consequences for Stage 2's methodology (to be applied consistently, not
re-litigated per-recording):

- **For DANDI:001603 subjects with deposited Units (both "recorded" HO1-4
  and "sourced" HO5-8)**: use the deposited Units directly as the spike
  source for Stage 2 features, per the handoff's own Task 4.5 guidance
  ("using deposited Units where present ... always labelled"). Do NOT
  re-derive spikes for these subjects -- the deposited data is the best
  available ground truth, and Stage 1 showed our self-derived methods don't
  improve on it.
- **For DANDI:001872 (raw-only, no deposited Units) and any future subject
  without deposited Units**: self-derived spike source is the only option.
  Given curated CPU sorting (`lupin` + QC) is the best-validated method
  available (closest aggregate-level agreement with real ground truth, even
  though per-electrode ranking wasn't recoverable in this test), use it as
  the frozen self-derived method -- but treat resulting single-unit-labelled
  features with the same caution as the rest of this report: aggregate/
  population-level statistics (mean firing rate, burst rate, network-level
  measures) are reasonably trustworthy; anything that depends on *which
  specific electrode* corresponds to *which specific neuron* should not be
  over-interpreted.
- **Per-recording provenance labelling (`spike_source`: `deposited` vs
  `self_derived_lupin_curated`) is mandatory** in the Stage 2 feature
  matrix, per the project's own "never mix without labelling" guardrail --
  this Stage 1 finding is exactly why that guardrail exists.
- Compute cost is real: curated `lupin` sorting took ~75-80 minutes per
  full-length HO1-scale recording on this machine. Stage 2's scope (which
  001872 recordings get self-derived features, how many) should account for
  this rather than assuming it's cheap.

## Second addendum (human decision, 2026-07-13) -- uniform MEA-NAP policy

The 2026-07-13 addendum above (precise session-gap timestamps, gap-rho
ordering) prompted a re-examination of the 2026-07-10 decision itself, not
just its rationale: if the null per-electrode result is best explained by
*which session* is being compared rather than *which method* detects
spikes, then using a DIFFERENT detection method for 001603
(deposited Units) than for 001872 (self-derived `lupin` sorting) adds a
second, uncontrolled source of cross-dataset difference on top of the
lab/platform difference this whole project exists to characterize --
arguably worse for the project's actual goal than using one method that is
imperfect but identical everywhere.

**Revised decision: Stage 2 uses MEA-NAP threshold detection
(`mea_nap_threshold`) as the uniform spike source for every recording with
raw available**, superseding the "deposited where available, self-derived
sorting elsewhere" split above:

- `DANDI:001603` HO1-HO4 (raw available): MEA-NAP threshold, not deposited
  Units.
- `DANDI:001603` HO5-HO8 ("sourced" subjects, no raw deposited on DANDI at
  all): **forced exception**, not a choice -- MEA-NAP cannot run without
  raw. Kept as `spike_source: deposited`, explicitly flagged so these rows
  can be excluded from Stage 3-5's primary analysis (human decision:
  flag and keep, don't drop outright).
- `DANDI:001872` (all 15 mirrored recordings): MEA-NAP threshold, not
  self-derived `lupin` sorting.
- The self-derived-sorting background job for 001872 was stopped
  deliberately once this pivot was decided (was 2/15 recordings complete,
  3 real bugs found and fixed along the way) -- its output no longer feeds
  Stage 3-5, kept as `feature_matrix_001872.parquet` for comparison, not
  deleted. Likewise `feature_matrix_001603_deposited_only.parquet`
  preserves the pre-pivot all-deposited 001603 matrix.
- Config: `config/params.yaml` `spike_detection.method` = `mea_nap_threshold`
  (was `self_derived_lupin_curated`); see that file's comment block for the
  full policy text.
- `spike_source` values going forward: `mea_nap_threshold` (default),
  `deposited` (HO5-8 only), `self_derived_lupin_curated` (comparison data
  only, not primary).

This does not reopen Stage 1's closure -- the four methods tested there
remain the record of what was tried and why none met the original
acceptance criteria. It changes what Stage 2 does with that finding.

## Third addendum (human decision, 2026-07-13) -- MEA-NAP's own pipeline, not piecemeal calls

Same day, pushed one step further: rather than calling individual MEA-NAP
functions (`detect_spikes_full_recording`, `single_channel_burst_detection`,
`firing_rates_bursts`, `adjm_thr`, a subset of `network_metrics.py`) from
custom orchestrator scripts, Stage 2 now runs MEA-NAP's own full pipeline
end-to-end (`meanap.pipeline.runner.run_pipeline()`, the Python port of
`MEApipeline.m`, Steps 1-4). Motivation: the piecemeal approach only wired
in the deterministic subset of MEA-NAP's network metrics (degree, density,
clustering, path length, efficiency); MEA-NAP's own default pipeline
computes substantially more (modularity/Louvain, node cartography,
participation coefficient, small-worldness, rich club -- see
`external/MEA-NAP/python/PIPELINE_PORT_STATUS.md`), all of which is now
available with no extra integration work.

Two supporting facts confirmed by reading the pipeline source before
committing to this:
- `channel_layout` (electrode coordinates) only affects spatial network
  *plots* (`step4.py`, wrapped in a try/except that skips the plot on
  failure) -- no computed metric depends on it, so no electrode-coordinate-
  mapping problem needs solving for MaxWell/3Brain data to get correct
  numeric results.
- `fs` is read per-recording from each converted `.mat` file
  (`load_raw_recording`), not from a single global `Params.fs` -- 001603
  (20kHz) and 001872 (10kHz) run through one `run_pipeline()` call together.

New modules (split into three, one per step of MEA-NAP's own required setup
ritual, 2026-07-13): `src/io_nwb_convert.py` (`nwb_to_meanap_mat` +
`convert_all_recordings` -- MEA-NAP cannot read NWB directly, only Axion/
Multichannel-Systems `.mat`, confirmed in `meanap.pipeline.io`'s own
docstring, so this conversion is a hard requirement, not a stylistic
choice), `src/build_meanap_spreadsheet.py` (`build_spreadsheet` -- the CSV
`run_pipeline()` requires), and `src/run_meanap_pipeline.py`
(`build_params` translates `config/params.yaml`'s frozen values into the
`Params` object `run_pipeline()` expects, `main()` calls `run_pipeline()`).
`build_feature_matrix.py` and `build_feature_matrix_001872.py` are
superseded as the primary Stage 2 path (their outputs kept for comparison,
not deleted) but not removed from the repo: `build_feature_matrix.py`'s
`process_deposited_recording()` is still active for HO5-8's forced
`deposited` exception (those subjects never enter the MEA-NAP pipeline at
all, no raw), and `build_feature_matrix_001872.py`'s `_RAW_FILES`/
`_parse_filename` are still imported by `io_nwb_convert.py` as the
canonical 001872 file list. `build_feature_matrix_001872_meanap.py` (the
piecemeal-MEA-NAP-calls path for 001872) had zero remaining imports from
anywhere in the codebase and was deleted outright, not just marked
superseded -- its output parquet, if produced, remains on disk.

**No consolidated feature-matrix Parquet going forward.** MEA-NAP's own
pipeline already writes clean, ready-to-read CSVs
(`NeuronalActivity_RecordingLevel.csv`/`NodeLevel.csv`,
`NetworkActivity_RecordingLevel.csv`/`NodeLevel.csv` under
`outputs/meanap_pipeline/OutputData/`). Decision: Stage 3-5 will read these
directly rather than pre-building a merged Parquet -- the necessary
transformations (pivoting `NetworkActivity_RecordingLevel.csv` from long,
one row per recording x lag, to wide; joining HO5-8's `deposited` rows from
the separate code path; optionally computing ISI mean/CV/skew/Lv and the
spectral/complexity blocks, none of which have a MEA-NAP equivalent) belong
in Stage 3-5's own design, not pre-built speculatively now.
