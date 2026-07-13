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
config/params.yaml            all frozen parameters
src/io_dandi.py                DANDI asset discovery + streaming/download
src/inventory.py               Stage 0 manifest builder
src/validate_pipeline.py       Stage 1 pipeline validation vs ground truth
src/io_nwb_convert.py          NWB -> MEA-NAP .mat converter (Stage 2, current path)
src/build_meanap_spreadsheet.py  writes the CSV "spreadsheet" MEA-NAP's own
                                pipeline requires before it will run at all
src/run_meanap_pipeline.py     Stage 2 orchestrator, current path -- builds a Params
                                object from config/params.yaml and calls MEA-NAP's own
                                run_pipeline() end-to-end (Steps 1-4) on every recording
                                with raw available (see docs/technical_overview.md
                                Sec 3.4 for the 2026-07-13 architecture history)
src/build_feature_matrix.py    Stage 2, HO5-8 deposited-Units exception only
                                (no raw on DANDI for those 4 subjects) + superseded
                                piecemeal-MEA-NAP-calls path, kept for comparison
src/features/                  Stage 2 feature extractors (spike/network/spectral/complexity)
                                -- superseded as the primary path by run_meanap_pipeline.py,
                                spectral/complexity have no MEA-NAP equivalent (supplementary only)
src/batch_effect.py            Stage 3 batch-effect characterization
src/harmonize.py               Stage 4 ComBat harmonization test
src/reference.py               Stage 5 canonical cortical reference + manifold
src/provenance.py              git commit hash / config hash stamping helpers
notebooks/                     exploratory notebooks, one per stage
outputs/manifests/             Stage 0 manifests
outputs/meanap_pipeline/       Stage 2 output, current path -- MEA-NAP's own native
                                CSV/JSON structure (NOT a consolidated Parquet --
                                that step was deliberately dropped, see
                                docs/technical_overview.md Sec 3.4/3.5)
outputs/features/              Stage 2 output, superseded paths (Parquet), kept for comparison
outputs/figures/                figures
outputs/reports/               per-stage markdown reports (checkpoints)
data/raw/                      local mirror of prioritised raw NWB files (gitignored)
data/meanap_mat/               NWB/BRW files converted to MEA-NAP's .mat format (gitignored)
tests/                         unit tests for feature functions
```

## Execution order & checkpoints

1. Repo/environment scaffold → **Checkpoint A**
2. Stage 0 inventory + settings audit (MaxOne vs MaxTwo) → **Checkpoint B (stop)**
3. Stage 0.5 prioritised mirroring of raw NWB files
4. Stage 1 pipeline validation on `001603` → **Checkpoint C (stop)**
5. Stage 2 unified feature extraction → **Checkpoint D**
6. Stage 3 batch-effect characterization → Stage 4 harmonization → Stage 5 reference signature
7. `outputs/reports/foundation_phase_summary.md`

Each `outputs/reports/stageN_*.md` ends with an explicit "verified vs assumed" and
open-questions section for human review; stages that would tempt a regional-type
claim must stop and flag instead of proceeding.

## Environment

See `environment.yml`. Resolved versions (once created) are recorded in
`outputs/reports/env_lock.txt` — pay particular attention to the `spikeinterface`
version, since its NWB extractor API has drifted across releases.

## Reproducibility

Global seed is set in `config/params.yaml` (`random_seed`). Every output file
produced by this pipeline is stamped with the current git commit hash and a hash
of the config used to produce it (see `src/provenance.py`).
