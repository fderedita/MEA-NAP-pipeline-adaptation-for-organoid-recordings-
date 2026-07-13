# Claude Code Handoff — Foundational Analysis Phase
## Human cortical organoid MEA (raw): DANDI:001603 + DANDI:001872

**Owner:** Francesca (Lodato lab, Humanitas) · **Date:** 8 July 2026
---

## 0. Context & non-negotiable framing (read before coding)

We are building an ML project to classify brain-organoid **regional identity** (cortical, midbrain, striatal, hippocampal, thalamic, cerebellar, spinal, assembloid) from **MEA electrophysiological signatures**. This handoff covers **only the foundational phase**, on the two best publicly downloadable **raw, human, organoid, MEA** datasets:

| Dataset | Type | Platform | Role |
|---|---|---|---|
| **DANDI:001603** | cortical/forebrain (human iPSC) — has raw **and** deposited spike-sorted Units for *recorded* subjects | MaxWell **MaxOne** HD-MEA | **Ground-truth anchor** for pipeline validation |
| **DANDI:001872** | cerebral/unguided (human iPSC) — raw; "Statistical Analysis of Brain Organoid MEA Data" (owner: A. Pignatelli) | MaxWell **MaxTwo** 24-well HD-MEA; 261.2 GB, 120 files, CC-BY-4.0 | Independent-lab **cortical replicate** on standard HD-MEA |

**Both datasets are cortical.** Therefore this phase **cannot and must not** attempt regional-type classification — there is no type contrast yet. The scientific purpose here is different and foundational:

> With organoid **type held constant (cortical)**, measure and neutralize the **lab/MEA-system confound**, validate the feature-extraction pipeline against ground truth, and define a **cross-lab canonical cortical reference signature**. This de-risks the entire downstream project so that when Lodato (3Brain) and Faravelli (spinal, 3Brain) data arrive, they attach to a validated, harmonized infrastructure instead of a cold start.

**Hard guardrails (enforce in every stage):**
- **Grouping unit = biological organoid, never the file.** All cross-validation and statistics use the distinct-organoid ID as the group. No metric may leak across recordings from the same organoid. (Prevents pseudoreplication.)
- **Verify, do not assume.** Several facts below are marked ⚠️ VERIFY — Claude Code must confirm them from the data and report, not proceed on assumption.
- **Raw vs processed provenance is tracked per recording.** Never mix a deposited-feature value with a self-derived one without labelling which is which.
- **Freeze parameters via a single YAML config.** Every threshold, band, and window lives in `config/params.yaml`; nothing hard-coded in functions.
- **NIH-review risk:** DANDI shows a "under review by NIH" banner. Prioritise **downloading/mirroring** the raw human `_ecephys.nwb` files early (Stage 0.5), don't assume continued availability.

---

## 1. Environment & repo scaffold

**Task 1.1 — Create repo structure:**
```
organoid-mea-foundation/
├── config/
│   └── params.yaml            # all parameters, frozen here
├── src/
│   ├── io_dandi.py            # streaming + download, asset discovery
│   ├── inventory.py           # Stage 0 manifest builder
│   ├── validate_pipeline.py   # Stage 1
│   ├── features/
│   │   ├── spike_train.py     # single-unit / burst features
│   │   ├── network.py         # STTC, network bursts, graph metrics
│   │   ├── spectral.py        # LFP PSD, FOOOF aperiodic
│   │   └── complexity.py      # avalanches, entropy, LZ
│   ├── build_feature_matrix.py# Stage 2 orchestrator
│   ├── batch_effect.py        # Stage 3
│   ├── harmonize.py           # Stage 4
│   └── reference.py           # Stage 5
├── notebooks/                 # exploratory, one per stage
├── outputs/
│   ├── manifests/
│   ├── features/
│   ├── figures/
│   └── reports/
├── tests/
├── environment.yml
└── README.md
```

**Task 1.2 — Environment (`environment.yml`, Python 3.11):**
Core: `numpy scipy pandas matplotlib seaborn pyyaml tqdm`
DANDI/NWB: `dandi pynwb h5py remfile lindi fsspec aiohttp`
Ephys: `spikeinterface[full] probeinterface neo elephant quantities`
Spectral/complexity: `neurodsp fooof` (a.k.a. `specparam`) `bycycle antropy`
Graph: `networkx bctpy`
ML/stats: `scikit-learn statsmodels umap-learn`
Harmonization: `neuroCombat` (or `neurocombat-sklearn` / `pycombat`)
Optional: `cebra` (manifold), `scikit-bio` (PERMANOVA)

Pin versions in the lockfile and record them in `outputs/reports/env_lock.txt`. Log the `spikeinterface` version explicitly — extractor APIs drift.

**Task 1.3 — Reproducibility:** global seed in config; every output file stamped with git commit hash + config hash.

**⏸ CHECKPOINT A — report the scaffold + resolved environment (esp. spikeinterface version) before Stage 0.**

---

## 2. Stage 0 — Inventory (the single most important early step)

**Objective:** build a per-recording manifest that establishes the *biological* units of analysis, confirms raw availability, and exposes any settings differences between MaxOne and MaxTwo.

**Task 0.1 — Asset discovery** (`io_dandi.py`, `inventory.py`):
- Use the `dandi` Python API / `DandiAPIClient` to list all assets for `001603` and `001872`.
- For each asset, open the NWB **metadata only** via streaming (`remfile` + `pynwb` or `lindi`) — do **not** download full raw yet.

**Task 0.2 — Extract per recording:**
`dataset_id, asset_path, subject_id, session_id, species, has_raw_ElectricalSeries (bool), n_ElectricalSeries, sampling_rate_Hz, duration_s, n_electrodes, electrode_geometry/pitch, has_Units (bool), n_units, DIV/age (if present), well_id (001872), file_size_GB, license`.

**Task 0.3 — Resolve the biological grouping variable — ⚠️ VERIFY:**
- **001603:** distinguish **"recorded"** subjects (raw + spikesorted) from **"sourced"** subjects (spikesorted only, e.g. Sharf 2022, Yuan 2020). Only *recorded* subjects have raw. Tag each.
- **001872:** 120 files on a **24-well** chip → determine how many **distinct organoids / wells / independent sessions** exist. 120 files ≠ 120 organoids. Map file → well → organoid → timepoint. This decides whether 001872 is a broad training source or a small replicated methods deposit. **Report the distinct-organoid count explicitly.**

**Task 0.4 — Settings audit (MaxOne vs MaxTwo) — ⚠️ VERIFY:**
Tabulate and compare across the two datasets: sampling rate, ADC gain/scaling to µV, whether the stored `ElectricalSeries` is **wideband raw** or already high-pass filtered, active-electrode selection/threshold, number of readout channels, electrode pitch. Flag every mismatch — these drive downstream harmonization decisions. (This is the concrete instantiation of the project's "settings audit before re-derivation" principle.)

**Deliverables:** `outputs/manifests/manifest_001603.csv`, `manifest_001872.csv`, a merged `manifest_all.csv`, and `outputs/reports/stage0_inventory.md` (counts, distinct-organoid tallies, settings-audit table, raw-availability summary, any red flags).

**⏸ CHECKPOINT B — STOP. Report the inventory + settings audit + distinct-organoid counts. Human review decides scope before any heavy compute.**

---

## 2.5. Stage 0.5 — Prioritised mirroring (do promptly, NIH-review risk)

Once the manifest confirms which files are raw human cortical, **download** those `_ecephys.nwb` (dandi CLI or `DandiAPIClient.get_asset().download()`) to local/lab storage. Prioritise: (1) a representative set of 001603 *recorded* subjects across DIV; (2) the 001872 raw files. Keep everything else streaming-only. Record checksums.

---

## 3. Stage 1 — Pipeline validation on 001603 (ground-truth anchor)

**Objective:** prove that our raw→features pipeline reproduces the depositors' spike-sorted results, so we can trust self-derivation on datasets that have **only** raw (001872 partially, and future Lodato/Faravelli).

**Task 1.1 — Load raw** via `spikeinterface.extractors.read_nwb_recording` (or `NwbRecordingExtractor`) with streaming; select a subset of 001603 *recorded* recordings spanning DIV.

**Task 1.2 — Preprocess:** bandpass 300–6000 Hz (spikes), common-median reference; keep parameters in config. Confirm whether the stored series was already filtered (avoid double-filtering — from Task 0.4).

**Task 1.3 — Spike detection/sorting — two-track, pick per compute budget:**
- **Rigorous:** run a full sorter (ideally the same family the depositors used — check their methods; MaxWell HD-MEA commonly Kilosort2.5/3 → needs GPU). Compare recovered units to deposited `Units`: unit count, per-unit firing rate, waveform match, and per-electrode MFR maps.
- **Pragmatic (CPU, if no GPU):** threshold-based detection per electrode; validate by correlating per-electrode spike rates and network-burst structure with the deposited units. Document this is a coarse check, not full sorting.

**Task 1.4 — Acceptance criterion (state numeric target in config):** e.g. per-electrode firing-rate Spearman ρ ≥ 0.8 between self-derived and deposited, and network-burst rate within ±15%. If met → **freeze all preprocessing/detection parameters** as the canonical pipeline. If not → report the discrepancy and stop for review (do not silently tune).

**Deliverables:** `outputs/reports/stage1_validation.md` with the comparison figures/metrics and the frozen-parameter block.

**⏸ CHECKPOINT C — STOP. Report validation result. Only proceed if acceptance met (or explicitly waived).**

---

## 4. Stage 2 — Unified feature extraction (both datasets, identical params)

> **Amendment, 2026-07-13 (human decision):** the spike-source approach
> below (deposited-where-present, self-derived elsewhere) was implemented
> first, then revised after Stage 1 found that per-electrode validation
> failures were better explained by raw/Units session-gap than by method
> quality (see `outputs/reports/stage1_validation.md`, "Second addendum").
> Mixing detection methods across the two datasets was judged a bigger,
> less controlled confound than this handoff's own goal of neutralizing
> the lab/platform confound. Stage 2 now uses ONE uniform method (MEA-NAP
> threshold detection) on every recording with raw available, with
> deposited Units kept only as a forced exception for the 4 subjects
> (HO5-HO8) that have no raw at all. Not a rejection of the "always
> labelled" principle below -- `spike_source` is still mandatory on every
> row -- just a different default.
>
> **Second amendment, same day:** pushed further to "use MEA-NAP itself,
> not just its algorithms" -- Stage 2 now runs MEA-NAP's own
> `run_pipeline()` end-to-end (Steps 1-4) via a new `src/io_nwb_convert.py`
> (NWB -> the `.mat` format MEA-NAP's I/O layer requires) +
> `src/run_meanap_pipeline.py`, instead of `build_feature_matrix.py`
> calling individual `features/*.py` functions. This surfaces MEA-NAP's
> full default metric set (modularity, node cartography, participation
> coefficient, small-worldness, rich club -- not just the deterministic
> subset 4.2 below originally scoped) at no extra integration cost. **4.5's
> `feature_matrix.parquet` is also superseded** -- Stage 2's output is now
> MEA-NAP's own native CSVs under `outputs/meanap_pipeline/OutputData/`;
> Stage 3-5 will read those directly (with a light pivot/join, done in
> Stage 3-5 itself) rather than a pre-built consolidated matrix.
> `features/spectral.py`/`features/complexity.py` (4.3/4.4) have no MEA-NAP
> equivalent and are kept only as supplementary, non-primary computations.
> See `config/params.yaml` `spike_detection`, `outputs/reports/
> stage1_validation.md`'s "Third addendum", and `docs/technical_overview.md`
> §3.4 for the current, final policy.

**Objective:** one tidy feature matrix, rows = recordings, columns = features, with provenance metadata. Same battery, same parameters, applied to both datasets from the **raw** (using deposited Units where present for the spike-based block, self-derived where not — always labelled).

Build modular extractors; each returns a named vector. Battery:

**4.1 Spike-train / single-unit (`spike_train.py`)** — MFR, ISI mean/CV/skew, % spikes in bursts, intra-burst frequency, burst rate/duration/spikes-per-burst (Max-Interval method; params in config), local variation Lv (Elephant). Aggregate per recording (mean + dispersion across units).

**4.2 Network (`network.py`)** — population network-burst rate/duration/amplitude/participation; pairwise **STTC** (`elephant.spike_train_correlation.spike_time_tiling_coefficient`); build functional-connectivity graph by thresholding STTC (threshold + surrogate control in config); graph metrics via `networkx`/`bctpy`: mean degree, density, clustering coefficient, characteristic path length, global efficiency, modularity (Louvain), small-worldness σ.

**4.3 Spectral / aperiodic (`spectral.py`)** — derive **LFP** by low-pass + downsample of raw (e.g. → 1 kHz; config); Welch PSD (`scipy`/`neurodsp`); **FOOOF/specparam** → aperiodic **exponent** + **offset** (primary), oscillatory peak params if present; band power in low bands if oscillations exist. (Aperiodic exponent is a strong maturation/E-I proxy — keep central.)

**4.4 Complexity / criticality (`complexity.py`)** — neuronal-avalanche detection on binned population activity; avalanche size & duration distributions, power-law exponents + goodness (with cutoffs), **branching ratio**; **sample entropy** and **Lempel-Ziv complexity** (`antropy`) on population rate.

**4.5 Assemble (`build_feature_matrix.py`):** `outputs/features/feature_matrix.parquet` with columns for features + metadata: `dataset(lab/platform)`, `organoid_id`, `DIV`, `well_id`, `spike_source ∈ {deposited, self-derived}`, `raw_provenance`. Handle NaNs explicitly (e.g. graph metrics undefined for silent recordings) — document policy, don't drop silently.

**Guardrail:** apply the **same active-electrode criterion** to both datasets (from Task 0.4). If MaxOne vs MaxTwo differ irreconcilably in a parameter, flag the affected features as "platform-sensitive" in a sidecar file.

**⏸ CHECKPOINT D — report feature-matrix shape, missingness map, and per-feature distributions split by dataset.**

---

## 5. Stage 3 — Batch-effect characterization (the crux)

**Objective:** with type constant, quantify how much feature variance is lab/platform vs maturation, and list robust vs confounded features.

- **5.1 EDA:** PCA and UMAP of standardized features, coloured by `dataset` vs by `DIV`. Question to answer in text: do recordings separate by **lab** or by **maturation**?
- **5.2 Variance partitioning:** per-feature and multivariate. Multivariate: **PERMANOVA** (`skbio`) on feature distance matrix with factors `dataset`, `DIV` (binned), `organoid` (nested/random). Per-feature: linear mixed model (`statsmodels`) `feature ~ dataset + DIV + (1|organoid)`; extract variance components / effect sizes.
- **5.3 Robust-feature shortlist:** rank features by (low `dataset` effect) × (meaningful `DIV` effect). Output `outputs/reports/robust_features.csv` — this list gates every future cross-lab / cross-type comparison.

**Deliverable:** `outputs/reports/stage3_batcheffect.md` with the batch-effect magnitude estimate and the robust/confounded partition.

---

## 6. Stage 4 — Harmonization test

**Objective:** validate *now* the harmonization strategy needed later for cross-type work.

- **6.1** Apply **ComBat** (`neuroCombat`) with `batch = dataset`, preserving `DIV` as covariate. Also test simpler within-lab z-scoring as baseline.
- **6.2 Key metric — "dataset classifier" test:** train a classifier to predict `dataset` from features, **before vs after** harmonization, under organoid-grouped CV. Success = AUC drops from ≈1.0 toward ≈0.5 (the two cortical cohorts become indistinguishable). Optionally add kBET / iLISI mixing metrics.
- **6.3** Confirm biological signal survives: `DIV` should remain predictable after harmonization (we removed lab, not maturation).

**Deliverable:** `outputs/reports/stage4_harmonization.md` (before/after AUCs, chosen method, caveats).

---

## 7. Stage 5 — Canonical cortical reference signature + manifold

**Objective:** define the anchor class for all future regional contrasts.

- **7.1** On **robust features only**, compute the canonical human cortical-organoid phenotype with **cross-lab confidence intervals**, as a function of `DIV` (developmental trajectory).
- **7.2** Unsupervised **UMAP** embedding (optionally **CEBRA** with `DIV` as auxiliary) → "reference manifold" of cortical maturation. Save the fitted transform for projecting future datasets.
- **7.3 Stretch (001603 only):** explore sequential/assembly structure ("protosequences") — the distinctive trait of that dataset; connects to the cell-assembly framing.

**Deliverable:** `outputs/reports/stage5_reference.md` + saved reference-signature table + fitted embedding artifact.

---

## 8. Cross-cutting requirements

- **CV everywhere:** `GroupKFold` / `StratifiedGroupKFold` with `group = organoid_id`. No exception.
- **No regional-classification claims** in this phase — if a stage tempts it, stop and flag.
- **Every report** ends with: what was verified vs assumed, and open questions for the human.
- **Tests:** minimal unit tests for feature functions on a tiny synthetic spike train (known MFR/ISI) to catch silent numeric errors.
- **Config-first:** if a parameter is missing from `params.yaml`, fail loudly rather than default silently.

---

## 9. Suggested execution order for Claude Code

1. Stage 1 scaffold → **Checkpoint A**
2. Stage 0 inventory + settings audit → **Checkpoint B** *(stop, human review)*
3. Stage 0.5 prioritised mirroring
4. Stage 1 pipeline validation on 001603 → **Checkpoint C** *(stop)*
5. Stage 2 feature matrix → **Checkpoint D**
6. Stage 3 batch-effect → Stage 4 harmonization → Stage 5 reference
7. Final consolidated `outputs/reports/foundation_phase_summary.md`

---

## 10. Explicit open questions to resolve early (do not assume)

1. 001872: how many **distinct organoids/wells**, at which **DIV**, and is every file a raw `ElectricalSeries` (vs some processed-only)?
2. 001603: exact list of **recorded** (raw) vs **sourced** (spikesorted-only) subjects.
3. Is the stored `ElectricalSeries` **wideband raw** or pre-filtered, in each dataset?
4. Do MaxOne (001603) and MaxTwo (001872) differ in µV-scaling / active-electrode logic in a way that forces raw re-derivation rather than direct feature comparison?
5. Which sorter did each depositor use (for the rigorous validation track)?

*When answered, these convert the ⚠️ VERIFY flags above into settled facts and finalize the feature-comparability decision.*
