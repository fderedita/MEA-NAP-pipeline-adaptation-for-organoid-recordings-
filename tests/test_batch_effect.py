"""Unit tests for batch_effect.py's Stage 2 -> Stage 3 data-loading layer,
on hand-constructed data matching the real merged-CSV schema (see
outputs/reports/stage2_data_quality_notes.md for where that schema and
these feature-selection decisions came from).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd
import pytest

from src import batch_effect

CONFIG = {"network": {"sttc_lag_ms": [10, 15, 25]}}


# ── _dataset_and_organoid_id ──────────────────────────────────────────────

def test_organoid_id_ho_subject_same_across_sessions():
    # HO2 recorded at two different ages is the same physical organoid.
    d1, o1 = batch_effect._dataset_and_organoid_id("sub-HO2_ses-20250912T144839_ecephys")
    d2, o2 = batch_effect._dataset_and_organoid_id("sub-HO2_ses-20250912T144837_ecephys")
    assert (d1, o1) == ("001603", "HO2")
    assert (d2, o2) == ("001603", "HO2")


def test_organoid_id_001872_namespaced_by_batch_and_well():
    d1, o1 = batch_effect._dataset_and_organoid_id("sub-sample-well000_ses-20260622T233922_ecephys")
    d2, o2 = batch_effect._dataset_and_organoid_id("sub-sample2-well000_ses-20260623T155950_ecephys")
    assert d1 == d2 == "001872"
    # Same well number, different batch -> deliberately different organoid_id
    # (see stage0_inventory.md's unresolved well-vs-organoid open question).
    assert o1 == "1872_sample_well000"
    assert o2 == "1872_sample2_well000"
    assert o1 != o2


def test_organoid_id_unrecognized_pattern_raises():
    with pytest.raises(ValueError):
        batch_effect._dataset_and_organoid_id("sub-unknown-thing_ecephys")


# ── load_meanap_features ──────────────────────────────────────────────────

def _write_merged_csvs(tmp_path, filenames):
    neuronal = pd.DataFrame({
        "FileName": filenames,
        "Grp": ["g"] * len(filenames),
        "DIV": [7] * len(filenames),
        "FRmean": [1.0, 2.0][: len(filenames)],
    })
    rows = []
    for fn in filenames:
        for lag in (10, 15, 25):
            rows.append({
                "FileName": fn, "Grp": "g", "DIV": 7, "Lag": f"{lag}mslag",
                "aN": 100, "Dens": 0.5, "CC_rawMean": 0.3, "PL_raw": 2.0,
                "SW": 0.2, "SWw": -0.4, "CC": 0.25, "PL": 1.8,
                "PCmean": 0.6, "PCmeanTop10": 0.8, "NCpn1": 10, "Hub3": 2,
                "percentZscoreGreaterThanZero": 0.4,
                "SmallWorldnessSkippedHighDensity": False,
            })
    network = pd.DataFrame(rows)

    merged_dir = tmp_path / "merged"
    merged_dir.mkdir()
    neuronal.to_csv(merged_dir / "NeuronalActivity_RecordingLevel.csv", index=False)
    network.to_csv(merged_dir / "NetworkActivity_RecordingLevel.csv", index=False)
    return merged_dir


def test_load_meanap_features_pivots_and_tags_ids(tmp_path, monkeypatch):
    filenames = ["sub-HO1_ses-20250924T011900_ecephys", "sub-sample-well000_ses-20260622T233922_ecephys"]
    merged_dir = _write_merged_csvs(tmp_path, filenames)
    monkeypatch.setattr(batch_effect, "MERGED_DIR", merged_dir)

    df = batch_effect.load_meanap_features(CONFIG)

    assert len(df) == 2
    assert set(df["dataset_id"]) == {"001603", "001872"}
    assert set(df["organoid_id"]) == {"HO1", "1872_sample_well000"}
    # one column per (metric, lag) combination, not one column per metric
    assert "Dens_10mslag" in df.columns
    assert "Dens_15mslag" in df.columns
    assert "Dens_25mslag" in df.columns


def test_load_meanap_features_raises_on_missing_directory(tmp_path, monkeypatch):
    monkeypatch.setattr(batch_effect, "MERGED_DIR", tmp_path / "does_not_exist")
    with pytest.raises(FileNotFoundError):
        batch_effect.load_meanap_features(CONFIG)


def test_load_meanap_features_raises_on_recording_mismatch(tmp_path, monkeypatch):
    filenames = ["sub-HO1_ses-20250924T011900_ecephys"]
    merged_dir = _write_merged_csvs(tmp_path, filenames)
    # Add an extra recording to NeuronalActivity only -- simulates a partial/
    # corrupted harvest where one merged CSV has a row the other lacks.
    neuronal_path = merged_dir / "NeuronalActivity_RecordingLevel.csv"
    neuronal = pd.read_csv(neuronal_path)
    extra = pd.DataFrame({"FileName": ["sub-HO2_ses-x_ecephys"], "Grp": ["g"], "DIV": [7], "FRmean": [1.0]})
    pd.concat([neuronal, extra], ignore_index=True).to_csv(neuronal_path, index=False)
    monkeypatch.setattr(batch_effect, "MERGED_DIR", merged_dir)

    with pytest.raises(ValueError):
        batch_effect.load_meanap_features(CONFIG)


# ── primary_feature_columns ────────────────────────────────────────────────

def test_primary_feature_columns_excludes_pc_and_null_model_normalized():
    df = pd.DataFrame(columns=[
        "FileName", "Grp", "DIV", "dataset_id", "organoid_id",
        "SmallWorldnessSkippedHighDensity", "ElocSkippedHighDensity", "PCNormalized",
        "FRmean",
        "Dens_10mslag", "CC_rawMean_10mslag", "PL_raw_10mslag",
        "SW_10mslag", "SWw_10mslag", "CC_10mslag", "PL_10mslag",
        "PCmean_10mslag", "PCmeanTop10_10mslag", "NCpn1_10mslag", "Hub3_10mslag",
        "percentZscoreGreaterThanZero_10mslag",
    ])
    primary = batch_effect.primary_feature_columns(df, CONFIG)

    assert "FRmean" in primary
    assert "Dens_10mslag" in primary
    assert "CC_rawMean_10mslag" in primary  # raw, deterministic -> stays primary
    assert "PL_raw_10mslag" in primary

    for excluded in [
        "SW_10mslag", "SWw_10mslag", "CC_10mslag", "PL_10mslag",
        "PCmean_10mslag", "PCmeanTop10_10mslag", "NCpn1_10mslag", "Hub3_10mslag",
        "percentZscoreGreaterThanZero_10mslag",
        "FileName", "dataset_id", "organoid_id", "PCNormalized",
    ]:
        assert excluded not in primary, f"{excluded} should have been excluded"
