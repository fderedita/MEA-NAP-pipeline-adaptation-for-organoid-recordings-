# organoid-mea-foundation

Foundational analysis phase for human cortical-organoid MEA classification project (Lodato lab, Humanitas).

## Scope of this phase

This repo covers **only** the foundational phase described in the project handoff
(`docs/handoff_foundation_phase.md`), run on two public raw human cortical-organoid
MEA datasets:

| Dataset | Type | Platform | Role |
|---|---|---|---|
| `DANDI:001603` | cortical/forebrain (human iPSC), raw + deposited Units for *recorded* subjects | MaxWell MaxOne HD-MEA | ground-truth anchor |
| `DANDI:001872` | cerebral/unguided (human iPSC), raw | MaxWell MaxTwo 24-well HD-MEA | independent-lab cortical replicate |

**Both datasets are cortical.** This phase does **not** attempt regional-type
classification. Its purpose is to measure and neutralize the lab/MEA-system
confound, validate the raw→features pipeline against ground truth, and define a
cross-lab canonical cortical reference signature — so that future regional data
(Lodato 3Brain cortical, Faravelli 3Brain spinal, etc.) attaches to validated,
harmonized infrastructure instead of a cold start.

## Non-negotiable guardrails

- **Grouping unit = biological organoid, never the file.** All CV/statistics group
  on `organoid_id`. No metric leaks across recordings from the same organoid.
- **Verify, do not assume.** Facts flagged ⚠️ VERIFY in the handoff must be
  confirmed from the data (Stage 0) before being relied on downstream.
- **Raw vs processed provenance is tracked per recording**, always labelled
  `deposited` vs `self-derived`.
- **Config-first.** Every threshold/band/window lives in `config/params.yaml`.
  Code must fail loudly if a required parameter is missing — no silent defaults.
- **No regional-classification claims in this phase.**

## Repo layout

```
config/params.yaml             all frozen parameters -- code fails loudly if a
                                required value is missing, no silent defaults
external/MEA-NAP/               vendored SAND-Lab/MEA-NAP clone (gitignored, not
                                tracked -- see Setup below). Several local-only
                                patches (correctness + performance/memory fixes)
                                are required after every fresh clone; see
                                docs/technical_overview.md Sec 2.2.1-2.2.2

src/io_dandi.py                 DANDI asset discovery + streaming/download
src/mirror_priority.py          Stage 0.5: curated raw-file mirroring to data/raw/
src/inventory.py                Stage 0 manifest builder
src/validate_pipeline.py        Stage 1 pipeline validation vs ground truth
src/io_nwb_convert.py           NWB -> MEA-NAP .mat converter (current Stage 2 path)
src/build_meanap_spreadsheet.py writes the CSV "spreadsheet" MEA-NAP's own
                                pipeline requires before it will run at all
src/run_meanap_pipeline.py      Stage 2 orchestrator (current path): converts one
                                recording at a time, then calls MEA-NAP's own
                                run_pipeline() end-to-end (Steps 1-4) on it, then
                                harvests its rows into outputs/meanap_pipeline/merged/.
                                Each recording runs in its own child process so an
                                OOM or other crash on one recording can't take down
                                the run -- see docs/technical_overview.md Sec 3.4 for
                                the pipeline's general architecture
src/build_feature_matrix.py     HO5-8's forced deposited-Units exception (no raw on
                                DANDI for those 4 subjects) + superseded piecemeal-
                                MEA-NAP-calls path, kept for comparison
src/build_feature_matrix_001872.py  canonical 001872 raw-file list, imported by
                                io_nwb_convert.py; superseded as its own pipeline path
src/io_brainwave.py             3Brain BrainWave5 .brw -> MEA-NAP .mat converter,
                                mirrors io_nwb_convert.py for the lab's own recordings
src/self_derived_sorting.py     superseded self-derived spike-sorting path (spikeinterface
                                / lupin), kept only for the already-computed 001872 comparison
src/features/                  feature extractors (spike/network/spectral/complexity) --
                                spike_train.py/network.py superseded as the primary path
                                by run_meanap_pipeline.py; spectral.py/complexity.py have
                                no MEA-NAP equivalent and stay supplementary for Stage 3-5
src/batch_effect.py            Stage 3 batch-effect characterization
src/harmonize.py               Stage 4 ComBat harmonization test
src/reference.py               Stage 5 canonical cortical reference + manifold
src/provenance.py              git commit hash / config hash stamping helpers
src/config.py                  config/params.yaml loader with the fail-loudly guardrail

notebooks/                     exploratory notebooks, one per stage
outputs/manifests/             Stage 0 manifests
outputs/meanap_pipeline/       current Stage 2 output -- MEA-NAP's own native CSV/JSON
                                structure under OutputData/ (gitignored, regenerated per
                                run) plus merged/ (small, tracked, one row per recording --
                                the resumable accumulator run_meanap_pipeline.py writes to
                                and reads from). No consolidated Parquet by design; see
                                docs/technical_overview.md Sec 3.4/3.5
outputs/features/              superseded Stage 2 output paths (Parquet), kept for comparison
outputs/figures/                figures
outputs/reports/               per-stage markdown reports (checkpoints)
docs/technical_overview.md     full technical detail: architecture decisions, vendored
                                MEA-NAP patches and why, current status -- read this for
                                anything not covered here (in Italian)
data/raw/                      local mirror of prioritised raw NWB files (gitignored)
data/meanap_mat/               NWB/BRW files converted to MEA-NAP's .mat format (gitignored)
tests/                         unit tests for feature functions
```

## Execution order & checkpoints

1. Repo/environment scaffold → **Checkpoint A** (done)
2. Stage 0 inventory + settings audit (MaxOne vs MaxTwo) → **Checkpoint B** (done, stopped for review)
3. Stage 0.5 prioritised mirroring of raw NWB files (done)
4. Stage 1 pipeline validation on `001603` → **Checkpoint C** (done, stopped for review --
   see `outputs/reports/stage1_validation.md`'s closing decision)
5. Stage 2 unified feature extraction → **Checkpoint D** (in progress -- MEA-NAP's own
   `run_pipeline()` running per-recording on a lab workstation; resumable, see
   `outputs/meanap_pipeline/merged/` for what's completed so far)
6. Stage 3 batch-effect characterization → Stage 4 harmonization → Stage 5 reference signature (not started)
7. `outputs/reports/foundation_phase_summary.md` (not started)

Each `outputs/reports/stageN_*.md` ends with an explicit "verified vs assumed" and
open-questions section for human review; stages that would tempt a regional-type
claim must stop and flag instead of proceeding.

## Setup

```powershell
conda env create -f environment.yml
conda activate organoid-mea-foundation
```

MEA-NAP's own pipeline is a vendored, gitignored dependency, not installed from PyPI:

```powershell
git clone https://github.com/SAND-Lab/MEA-NAP.git external\MEA-NAP
pip install -e external\MEA-NAP
```

**Several local-only patches are required after every fresh clone** (a real
correctness bug in upstream `step2.py`'s duration calculation, plus
performance/memory fixes needed to run at HD-MEA channel counts far beyond
what upstream was tested at -- `external/MEA-NAP` isn't tracked by git, so
nothing carries these over automatically). Diffs and rationale:
`docs/technical_overview.md` Sec 2.2.1-2.2.2.

## Environment

See `environment.yml`. Resolved versions are recorded in
`outputs/reports/env_lock.txt` — pay particular attention to the `spikeinterface`
version, since its NWB extractor API has drifted across releases.

## Reproducibility

Global seed is set in `config/params.yaml` (`random_seed`). Every output file
produced by this pipeline is stamped with the current git commit hash and a hash
of the config used to produce it (see `src/provenance.py`).
