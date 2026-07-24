# Stage 2 — data quality notes (interim, while Stage 2 is still running)

Not a closure report (Stage 2 is not finished) — a running record of methodological
issues found while sanity-checking the merged output so far, so they aren't lost
before Stage 3 design starts. Based on the first 8 recordings harvested with the
current code (4x `DANDI:001603` HO*, 4x `DANDI:001872` sample*) after purging 4
recordings that had been processed before the density-limit fix existed (see
`docs/technical_overview.md` Sec 2.2.2 / §7 for that fix's own history).

## Finding 1 — `PCmean` is not computed the same way across recordings

`network_metrics.NULL_MODEL_DENSITY_LIMIT` (0.5) governs whether `participation_coef_norm`
returns the true null-model-normalized PC or falls back to the raw, unnormalized PC
(signalled per-row by `PCNormalized`). In the data so far:

- All 4 `001603` (HO*) recordings and 1 of 4 `001872` recordings (`sample-well000_233922`,
  the only large 001872 file processed so far) have density > 0.5 → `PCmean` is the
  **raw**, unnormalized fallback (`PCNormalized=False`).
- The 3 smaller `001872 sample2-well*` recordings have density < 0.5 → `PCmean` is the
  **true**, null-model-normalized value (`PCNormalized=True`).

A naive group average of `PCmean` (001603: 0.521, 001872: 0.746) mixes two different
quantities and should **not** be interpreted as a real biological/platform difference
without conditioning on `PCNormalized` first. The same caveat applies to everything
downstream of PC in `network_metrics.py` per that module's own docstring: node
cartography (`NCpn1-6`), hub classification (`Hub3`/`Hub4`), `PCmeanTop10`/
`PCmeanBottom10`, `percentZscoreGreaterThanZero`/`percentZscoreLessThanZero` — all of
these are fed the same PC value, so all of them inherit this inconsistency.

**Decision (2026-07-24):** exclude PC-derived features from Stage 3-5's primary
comparative feature set. Keep the raw values and the `PCNormalized` flag in the data
(not deleted) so a restricted sensitivity analysis (e.g. low-density recordings only)
remains possible later. Rationale: consistent with the project's own existing
"never mix without labelling" guardrail, already applied once before to
`spike_source: deposited` vs `self_derived` — mixing normalized and raw PC in a
quantitative model (PERMANOVA, mixed models) risks introducing a spurious "batch"
signal that is really just a computational-method switch, exactly the kind of
confound this project exists to avoid.

## Finding 2 — small-worldness (`SW`/`SWw`) is currently missing for the entire `001603` (HO*) side

Same density-limit gate, but with a starker outcome: **0 of 4** HO* recordings (0 of 12
lag-rows) have `SW`/`SWw` computed at all — every one is above the 0.5 density limit.
`001872` has it for 3 of 4 recordings (9 of 12 lag-rows) — only the smaller `sample2-well*`
files stayed under the limit.

If this pattern holds as more recordings complete (plausible: every 1000+-channel
recording processed so far, regardless of dataset, has landed well above 0.5 density —
see Finding 3), `SW`/`SWw` risks being **structurally unusable** as a cross-dataset
comparison metric for this project's central question, not because of a bug but because
of a genuine data/scale limitation of degree-preserving null-model randomization at this
channel count. This needs a decision before Stage 3, not an assumption.

**Decision (2026-07-24):** drop `SW`/`SWw` from Stage 3-5's primary feature set (same
treatment already given to spectral/complexity features in `config/params.yaml` --
supplementary, not primary). Keep computing and recording it where available for a
possible within-`001872`-only analysis later. See the literature review below for why
this metric specifically was the least defensible one to keep as a primary
cross-dataset feature regardless of the missing-data problem.

## Finding 3 (preliminary hypothesis, n=4, not yet solid) — density may track network size more than dataset identity

Within `001872` alone, density increases with active-electrode count (`aN`) in a way
that looks more like a size effect than a dataset effect:

| Recording | aN | Density (10ms lag) |
|---|---|---|
| `sample2-well016` | 130 | 0.386 |
| `sample2-well008` | 144 | 0.470 |
| `sample2-well000` | 251 | 0.459 |
| `sample-well000_233922` | 369 | 0.807 |

The jump to high density coincides with the jump to more channels, not with switching
datasets. All `001603` recordings are ~1014-1020 channels and all show high density
(0.63-0.97) too — consistent with, though not proof of, a size-driven effect rather
than (or in addition to) a lab/platform-driven one. Only 8 data points total; revisit
once more recordings of varying size have completed.

### Literature review (2026-07-24)

This is a known, well-studied problem in graph-theoretic network analysis generally,
not something specific to this project or a sign of a bug -- and there is no fully
satisfactory solution in the literature.

- A paper on comparing brain networks of different size/density tested multiple
  correction approaches (fixed thresholds, fixed average degree, normalization by
  random surrogates, normalization by range) and found **none fully satisfactory**.
  Most relevant to us: normalizing by random surrogates -- i.e. exactly what MEA-NAP's
  `SW`/`CC`/`PL`/normalized-PC computation does via degree-preserving null models --
  "paradoxically increases sensitivity to N,k changes" for clustering and small-world
  metrics rather than correcting for it. The **small-world index specifically shows
  strong linear dependence on node count**, making it one of the least defensible
  metrics for cross-recording comparison at very different network sizes even where
  it *is* computed. The **non-normalized clustering coefficient (`CC_raw`, which
  MEA-NAP saves separately from the null-model-normalized `CC`) was comparatively more
  robust** to N/k in their tests.
- MEA-NAP's own documentation confirms the null-model normalization was specifically
  designed to solve this exact problem ("this pipeline normalises several of these
  features in order to allow comparison between different networks"), but the
  published paper states the tool "is designed for 60-electrode (MCS) or 64-electrode
  (Axion) microelectrode arrays" and never discusses comparing networks with node
  counts as different as ours (130 vs 1000+).
- **The two problems in this document are the same root cause, not a coincidence**:
  the mechanism MEA-NAP built to correct for network-size effects (null-model
  normalization) is exactly what becomes algorithmically infeasible at the
  near-complete-graph density our HD-MEA recordings reach (`NULL_MODEL_DENSITY_LIMIT`,
  see `docs/technical_overview.md` Sec 2.2.2) -- the recordings that would most need
  size-correction are the ones where the correction mechanism is unavailable.
- A plausible mechanistic explanation, not just a statistical artifact: MaxWell HD-MEA
  electrodes are packed at **~17.5 μm pitch** (vs. hundreds of μm for the 60-64
  electrode arrays MEA-NAP was validated on). Combined with the MUA threshold-detection
  method already in use here (no spike sorting, no cross-electrode deduplication --
  the same limitation `outputs/reports/stage1_validation.md` already documented, ~85-87%
  of electrodes with no matched curated unit), it is plausible that some "significant"
  STTC edges between spatially close electrodes reflect the *same* neuron detected
  redundantly on multiple nearby electrodes rather than genuine inter-neuron synchrony
  -- an effect that would scale with how many nearby electrodes are active (`aN`),
  independent of any real change in connectivity. Not proven with 8 recordings, but
  ties Finding 3 to an already-known, already-accepted limitation rather than
  introducing a new one.

## Open questions for human review

1. ~~`PCmean` (and everything downstream of it)~~ — **resolved 2026-07-24**: excluded
   from Stage 3-5's primary feature set, raw values kept for a possible sensitivity
   analysis. See Finding 1.
2. ~~`SW`/`SWw`~~ — **resolved 2026-07-24**: dropped from the primary feature set,
   kept as supplementary/within-001872-only. See Finding 2.
3. **`Dens` and node-count-dependent metrics — no clean solution exists in the
   literature, so this needs an explicit modeling choice, not a normalization fix**:
   - Use `CC_raw`/`PL_raw` (deterministic, computed for every recording regardless of
     density, and comparatively more robust to N/k per the literature above) as the
     primary clustering/path-length features instead of the null-model-normalized
     `CC`/`PL`/`SW`, even for recordings where the latter happens to be available.
   - Include `aN` as an explicit covariate in Stage 3's batch-effect model for `Dens`
     and other degree-dependent metrics, rather than assuming any transformation has
     already removed the confound.
   - Document the MUA/electrode-pitch hypothesis as a known methodological limitation
     in the eventual write-up, explicitly linked to Stage 1's already-accepted MUA
     finding rather than presented as a new, unexplained issue.
