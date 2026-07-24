"""Stage 3 — batch-effect characterization.

PCA/UMAP EDA colored by dataset vs DIV; PERMANOVA (skbio) on feature
distance matrix with factors dataset, DIV (binned), organoid (nested/
random); per-feature linear mixed models (statsmodels):
feature ~ dataset + DIV + (1|organoid). Produces robust_features.csv,
ranking features by (low dataset effect) x (meaningful DIV effect).

Data loading reads MEA-NAP's own merged CSVs directly (see
src/run_meanap_pipeline.py; outputs/meanap_pipeline/merged/), not a
consolidated Parquet -- no such file is built by design (see
docs/technical_overview.md Sec 3.4/3.5). HO5-8 (001603's forced
`deposited` exception, no raw on DANDI) come from a structurally
different feature-extraction pipeline (src/build_feature_matrix.py) with
its own, non-overlapping column schema -- loaded separately and NOT
merged into the primary feature space; see load_ho5_8_deposited()'s
docstring for why.

Feature-selection decisions frozen after reviewing the first 8 harvested
recordings (see outputs/reports/stage2_data_quality_notes.md): PC-derived
features (PCmean and everything downstream of it -- node cartography,
hub classification, PCmeanTop10/Bottom10) and the null-model-normalized
SW/SWw/CC/PL are excluded from the primary feature set -- all depend on
degree-preserving null-model randomization that becomes infeasible above
NULL_MODEL_DENSITY_LIMIT, so they're computed inconsistently (or not at
all) across recordings. Kept in the loaded data, not dropped -- just
segregated so downstream analysis has to opt in rather than accidentally
include them. CC_rawMean/PL_raw (deterministic, always available) stay
primary.

The PCA/PERMANOVA/mixed-model functions below remain unimplemented --
gated behind Stage 2 actually finishing (Checkpoint D) so the DIV-binning
and model design can be set once the real distribution of recordings/ages
is known, not guessed at from a partial run.
"""
from __future__ import annotations

import re
from pathlib import Path

import pandas as pd

from src.config import require

MERGED_DIR = Path(__file__).resolve().parent.parent / "outputs" / "meanap_pipeline" / "merged"
DEPOSITED_ONLY_PATH = (
    Path(__file__).resolve().parent.parent / "outputs" / "features"
    / "feature_matrix_001603_deposited_only.parquet"
)

# Exact column names (before the per-lag suffix is stripped, see
# _base_metric_name) excluded from the primary feature set -- CC/PL here
# are the null-model-normalized versions, gated by the SAME density check
# as SW/SWw (NOT CC_rawMean/PL_raw, which are deterministic and stay
# primary). See module docstring / stage2_data_quality_notes.md Finding 2.
_SUPPLEMENTARY_EXACT = frozenset({"SW", "SWw", "CC", "PL"})

# Prefix-matched exclusions -- everything fed by PCmean (Finding 1).
_SUPPLEMENTARY_PREFIXES = ("PC", "NCpn", "Hub", "percentZscore")

_ID_COLUMNS = frozenset({"FileName", "Grp", "DIV", "dataset_id", "organoid_id"})
_FLAG_COLUMNS = frozenset(
    {"SmallWorldnessSkippedHighDensity", "ElocSkippedHighDensity", "PCNormalized"}
)


def _lag_suffixes(config: dict) -> list[str]:
    return [f"_{lag}mslag" for lag in require(config, "network.sttc_lag_ms")]


def _base_metric_name(column: str, lag_suffixes: list[str]) -> str:
    """Strip a pivoted column's per-lag suffix (e.g. 'Dens_10mslag' ->
    'Dens') so it can be checked against the supplementary-feature lists,
    which are defined in terms of MEA-NAP's own un-suffixed metric names."""
    for suffix in lag_suffixes:
        if column.endswith(suffix):
            return column[: -len(suffix)]
    return column


def primary_feature_columns(df: pd.DataFrame, config: dict) -> list[str]:
    """Column names in `df` (as returned by load_meanap_features) that
    belong in the primary Stage 3 comparison, per the exclusions above.
    Does not mutate or drop anything from `df` itself -- callers select
    `df[primary_feature_columns(df, config)]` explicitly."""
    lag_suffixes = _lag_suffixes(config)
    out = []
    for col in df.columns:
        if col in _ID_COLUMNS or col in _FLAG_COLUMNS:
            continue
        base = _base_metric_name(col, lag_suffixes)
        if base in _SUPPLEMENTARY_EXACT or base.startswith(_SUPPLEMENTARY_PREFIXES):
            continue
        out.append(col)
    return out


def _dataset_and_organoid_id(filename: str) -> tuple[str, str]:
    """Derive (dataset_id, organoid_id) from a MEA-NAP recording FileName.

    001603 (`sub-HOn_...`): organoid_id is the subject itself (HO1-HO8) --
    multiple sessions of the same HOn subject (different `age` tags) are
    the same physical organoid recorded longitudinally, confirmed by
    feature_matrix_001603_deposited_only.parquet's own organoid_id column
    (HO2/HO3 each appear once per age tag, same organoid_id).

    001872 (`sub-sample[2]-wellNNN_...`): organoid_id is namespaced by
    BOTH batch and well (`1872_sample_well000` vs `1872_sample2_well000`
    are treated as DIFFERENT organoids), not just well number. Deliberately
    conservative: outputs/reports/stage0_inventory.md's "Open questions"
    section flags that the well->organoid mapping across sessions was
    never verified (could a well have been re-seeded between sessions?) --
    collapsing sample/sample2 of the same well number into one organoid_id
    would be assuming an answer the project hasn't confirmed.
    """
    if filename.startswith("sub-HO"):
        return "001603", filename.split("_")[0].removeprefix("sub-")
    if filename.startswith("sub-sample"):
        m = re.match(r"sub-(sample2?)-(well\d+)_", filename)
        if not m:
            raise ValueError(f"Unrecognized 001872 FileName pattern: {filename}")
        batch, well = m.group(1), m.group(2)
        return "001872", f"1872_{batch}_{well}"
    raise ValueError(f"Unrecognized FileName pattern (neither HO* nor sample*): {filename}")


def load_meanap_features(config: dict) -> pd.DataFrame:
    """Load and reshape the current Stage 2 (MEA-NAP) output into one row
    per recording -- the primary Stage 3 feature matrix.

    Reads outputs/meanap_pipeline/merged/{NeuronalActivity,NetworkActivity}
    _RecordingLevel.csv directly (raises if either is missing -- Stage 2
    must have harvested at least one recording first). NetworkActivity is
    long (one row per recording x lag); pivoted here to wide, one row per
    recording with each lag's values suffixed onto the column name (e.g.
    `Dens_10mslag`). Raises if a recording is present in one merged CSV
    but not the other -- a mismatch here means a partial/corrupted harvest,
    not something to silently paper over with NaN.
    """
    neuronal_path = MERGED_DIR / "NeuronalActivity_RecordingLevel.csv"
    network_path = MERGED_DIR / "NetworkActivity_RecordingLevel.csv"
    if not neuronal_path.exists() or not network_path.exists():
        raise FileNotFoundError(
            f"Stage 2 merged output not found under {MERGED_DIR} -- "
            "run src/run_meanap_pipeline.py first."
        )

    neuronal = pd.read_csv(neuronal_path)
    network = pd.read_csv(network_path)

    network_value_cols = [c for c in network.columns if c not in ("FileName", "Grp", "DIV", "Lag")]
    network_wide = network.pivot(index="FileName", columns="Lag", values=network_value_cols)
    network_wide.columns = [f"{metric}_{lag}" for metric, lag in network_wide.columns]
    network_wide = network_wide.reset_index()

    merged = neuronal.merge(network_wide, on="FileName", how="left", validate="one_to_one")
    missing = merged[network_wide.columns.drop("FileName")].isna().all(axis=1)
    if missing.any():
        raise ValueError(
            "Recording(s) present in NeuronalActivity_RecordingLevel.csv but missing from "
            f"NetworkActivity_RecordingLevel.csv: {merged.loc[missing, 'FileName'].tolist()}"
        )

    ids = [_dataset_and_organoid_id(fn) for fn in merged["FileName"]]
    merged.insert(1, "dataset_id", [d for d, _ in ids])
    merged.insert(2, "organoid_id", [o for _, o in ids])

    return merged


def load_ho5_8_deposited(config: dict) -> pd.DataFrame:
    """Load HO5-8's forced `deposited` exception rows (no raw on DANDI,
    MEA-NAP cannot run without raw -- see docs/technical_overview.md Sec
    3.4 / outputs/reports/stage1_validation.md's closing decision).

    Returns them as-is, WITHOUT attempting to merge into
    load_meanap_features()'s column space: this file's features
    (`network__density_10ms`, etc.) come from a structurally different
    pipeline (src/features/network.py operating on deposited spike times)
    than MEA-NAP's own run_pipeline() (STTC + probabilistic thresholding +
    BCT-ported metrics) -- nominally-similar column names are NOT the same
    computation, and silently joining them on renamed columns would treat
    two different measurement methods as one, exactly the confound this
    project's provenance-labelling guardrail exists to prevent. Decide
    deliberately in Stage 3's own analysis code whether/how to bring HO5-8
    into any given comparison, per-analysis, not here.
    """
    if not DEPOSITED_ONLY_PATH.exists():
        raise FileNotFoundError(f"Deposited-only feature matrix not found: {DEPOSITED_ONLY_PATH}")
    df = pd.read_parquet(DEPOSITED_ONLY_PATH)
    return df[df["organoid_id"].isin(["HO5", "HO6", "HO7", "HO8"])].reset_index(drop=True)


def run_pca_umap(feature_matrix, config: dict):
    raise NotImplementedError


def run_permanova(feature_matrix, config: dict):
    raise NotImplementedError


def fit_mixed_models(feature_matrix, config: dict):
    raise NotImplementedError


def rank_robust_features(mixed_model_results, config: dict):
    raise NotImplementedError
