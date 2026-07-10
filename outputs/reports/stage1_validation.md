# Stage 1 — Pipeline validation report (IN PROGRESS / STOPPED FOR REVIEW)

**Status: acceptance criteria NOT met on the 2 subjects completed so far (HO1, HO2).**
Per the handoff's explicit instruction ("If not met -> report the discrepancy and
stop for review, do not silently tune"), this report documents the discrepancy
and stops here for human review rather than adjusting parameters or the
comparison methodology to force a pass. HO3/HO4 may still be running in the
background (long compute, ~50min/subject) for completeness, but the outcome
pattern is already clear and unlikely to change qualitatively.

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

## Results

| Subject | n_electrodes | n_units | self FR mean (Hz) | deposited FR mean (Hz) | Spearman rho | self burst rate (/min) | deposited burst rate (/min) | burst %diff |
|---|---|---|---|---|---|---|---|---|
| HO1 | 1020 | 131 | 4.080 | 0.173 | **0.163** | 860.2 | 68.7 | **1153%** |
| HO2 | 1014 | 173 | 4.215 | 0.086 | **0.091** | 686.3 | 45.7 | **1403%** |

**Acceptance criteria (config/params.yaml):** Spearman rho >= 0.8, burst rate
%diff <= 15%. **Neither subject is remotely close on either metric.**

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
