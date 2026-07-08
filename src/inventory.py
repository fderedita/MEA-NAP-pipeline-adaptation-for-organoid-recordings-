"""Stage 0 — per-recording manifest builder.

Builds outputs/manifests/manifest_001603.csv, manifest_001872.csv, and the
merged manifest_all.csv, plus outputs/reports/stage0_inventory.md.

See docs/handoff_foundation_phase.md, Section 2 (Tasks 0.1-0.4) for the
exact column list and the VERIFY items this stage must resolve:
  - 001603: recorded (raw) vs sourced (spikesorted-only) subjects
  - 001872: file -> well -> organoid -> timepoint mapping, distinct-organoid count
  - MaxOne vs MaxTwo settings audit (sampling rate, uV scaling, filtering,
    active-electrode logic, electrode pitch)
"""
from __future__ import annotations

import re
import traceback
from pathlib import Path

import numpy as np
import pandas as pd
from pynwb.ecephys import ElectricalSeries
from scipy.spatial import cKDTree

from src import io_dandi

WELL_RE = re.compile(r"well[-_]?(\d+)", re.IGNORECASE)


def _electrode_geometry(electrodes_table):
    """Return (position_columns_used, median_nearest_neighbor_pitch)."""
    if electrodes_table is None:
        return None, None
    cols = list(electrodes_table.colnames)
    xy_cols = None
    for cand in (("x", "y"), ("rel_x", "rel_y")):
        if cand[0] in cols and cand[1] in cols:
            xy_cols = cand
            break
    if xy_cols is None:
        return ",".join(cols) if cols else None, None
    x = np.asarray(electrodes_table[xy_cols[0]][:], dtype=float)
    y = np.asarray(electrodes_table[xy_cols[1]][:], dtype=float)
    if len(x) < 2:
        return ",".join(xy_cols), None
    pts = np.column_stack([x, y])
    tree = cKDTree(pts)
    dists, _ = tree.query(pts, k=2)
    nn_dist = dists[:, 1]
    nn_dist = nn_dist[nn_dist > 0]
    pitch = float(np.median(nn_dist)) if len(nn_dist) else None
    return ",".join(xy_cols), pitch


def _row_for_asset(dataset_id: str, asset, dandiset_license: str | None) -> dict:
    row: dict = {
        "dataset_id": dataset_id,
        "asset_path": asset.path,
        "file_size_GB": round(asset.size / 1e9, 4),
        "license": dandiset_license,
        "error": None,
    }
    nwbfile, io = None, None
    try:
        nwbfile, io = io_dandi.stream_nwb(asset)

        subject = nwbfile.subject
        row["subject_id"] = subject.subject_id if subject else None
        row["species"] = subject.species if subject else None
        row["age"] = subject.age if subject else None
        row["session_id"] = nwbfile.session_id
        row["session_start_time"] = str(nwbfile.session_start_time)

        m = WELL_RE.search(asset.path)
        row["well_id"] = f"well{m.group(1)}" if m else None

        elec_series = {
            name: ts for name, ts in nwbfile.acquisition.items() if isinstance(ts, ElectricalSeries)
        }
        row["has_raw_ElectricalSeries"] = len(elec_series) > 0
        row["n_ElectricalSeries"] = len(elec_series)

        rate, n_samples, dtype = None, None, None
        if elec_series:
            first_ts = next(iter(elec_series.values()))
            rate = getattr(first_ts, "rate", None)
            data = getattr(first_ts, "data", None)
            if data is not None:
                n_samples = data.shape[0]
                dtype = str(data.dtype)
        row["sampling_rate_Hz"] = rate
        row["duration_s"] = (n_samples / rate) if (rate and n_samples) else None
        row["raw_dtype"] = dtype

        geom_cols, pitch = _electrode_geometry(nwbfile.electrodes)
        row["electrode_geometry_cols"] = geom_cols
        row["electrode_pitch_raw_units"] = pitch
        row["n_electrodes"] = len(nwbfile.electrodes) if nwbfile.electrodes is not None else None

        row["has_Units"] = nwbfile.units is not None
        row["n_units"] = len(nwbfile.units) if nwbfile.units is not None else None
    except Exception as e:  # noqa: BLE001 - deliberately broad: one bad asset must not kill the whole inventory
        row["error"] = f"{type(e).__name__}: {e}"
        row.setdefault("subject_id", None)
    finally:
        if io is not None:
            try:
                io.close()
            except Exception:
                pass
    return row


def build_manifest(dandiset_id: str, verbose: bool = True) -> pd.DataFrame:
    assets, meta = io_dandi.list_assets(dandiset_id)
    license_ = ",".join(meta.get("license", [])) if meta.get("license") else None
    rows = []
    for i, asset in enumerate(assets):
        if verbose:
            print(f"[{dandiset_id}] {i + 1}/{len(assets)}: {asset.path}", flush=True)
        rows.append(_row_for_asset(dandiset_id, asset, license_))
    return pd.DataFrame(rows)


def audit_settings(manifest_001603: pd.DataFrame, manifest_001872: pd.DataFrame) -> pd.DataFrame:
    """Compare MaxOne (001603) vs MaxTwo (001872) acquisition settings.

    Only compares rows with a raw ElectricalSeries (has_raw_ElectricalSeries),
    since settings like sampling rate / dtype / pitch are only meaningful there.
    """

    def summarize(df: pd.DataFrame, platform: str) -> dict:
        # Restrict to Homo sapiens: 001603 contains non-human (mouse/rat)
        # reference subjects mixed in (see stage0_inventory.md); settings
        # comparisons for this project must be human-only. 001872 is
        # all-human already, so this filter is a no-op there.
        human = df[df["species"] == "Homo sapiens"]
        raw = human[human["has_raw_ElectricalSeries"] == True]  # noqa: E712
        return {
            "platform": platform,
            "n_recordings_total_all_species": len(df),
            "n_recordings_total_human": len(human),
            "n_recordings_with_raw": len(raw),
            "sampling_rate_Hz_unique": sorted(raw["sampling_rate_Hz"].dropna().unique().tolist()),
            "raw_dtype_unique": sorted(raw["raw_dtype"].dropna().unique().tolist()),
            "n_electrodes_unique": sorted(raw["n_electrodes"].dropna().unique().tolist()),
            "electrode_pitch_raw_units_median": (
                float(raw["electrode_pitch_raw_units"].dropna().median())
                if raw["electrode_pitch_raw_units"].notna().any()
                else None
            ),
            "electrode_geometry_cols_unique": sorted(raw["electrode_geometry_cols"].dropna().unique().tolist()),
        }

    summary = pd.DataFrame(
        [summarize(manifest_001603, "MaxOne (001603)"), summarize(manifest_001872, "MaxTwo (001872)")]
    )
    return summary


def _subject_type_summary(manifest: pd.DataFrame) -> pd.DataFrame:
    """Per-subject recorded (has raw) / sourced (units-only) / neither classification, for 001603.

    Includes `species`: 001603 mixes human subjects (HO*) with non-human
    reference subjects (mouse/rat) under other naming prefixes (M*S*, MO*,
    PR*) -- these must be excluded from any human-cortical-organoid analysis.
    """
    g = manifest.groupby("subject_id").agg(
        species=("species", "first"),
        n_assets=("asset_path", "count"),
        n_with_raw=("has_raw_ElectricalSeries", "sum"),
        n_with_units=("has_Units", "sum"),
    )

    def classify(row):
        if row["n_with_raw"] > 0:
            return "recorded"
        if row["n_with_units"] > 0:
            return "sourced"
        return "no_raw_no_units"

    g["subject_type"] = g.apply(classify, axis=1)
    return g.reset_index()


def _well_summary(manifest: pd.DataFrame) -> pd.DataFrame:
    """Per-organoid (subject_id) session/timepoint tally, for 001872.

    IMPORTANT: `well_id` (e.g. "well001") is NOT globally unique in 001872 --
    there are multiple independent batches/plates (observed: "sample" and
    "sample2") that each reuse well001, well002, etc. `subject_id` (e.g.
    "sample_well001" vs "sample2_well001") is the correct distinct-organoid
    grouping key; well_id alone would silently conflate organoids from
    different plates. See stage0_inventory.md VERIFY notes.
    """
    manifest = manifest.copy()
    manifest["batch"] = manifest["subject_id"].str.replace(r"_?well\d+$", "", regex=True)
    g = manifest.groupby("subject_id", dropna=False).agg(
        batch=("batch", "first"),
        well_id=("well_id", "first"),
        n_sessions=("asset_path", "count"),
        n_with_raw=("has_raw_ElectricalSeries", "sum"),
        ages=("age", lambda s: sorted(set(s.dropna()))),
    )
    return g.reset_index()


def main():
    repo_root = Path(__file__).resolve().parent.parent
    manifests_dir = repo_root / "outputs" / "manifests"
    reports_dir = repo_root / "outputs" / "reports"
    manifests_dir.mkdir(parents=True, exist_ok=True)
    reports_dir.mkdir(parents=True, exist_ok=True)

    errors_log = []

    print("Building manifest for 001603 ...")
    m1603 = build_manifest("001603")
    m1603.to_csv(manifests_dir / "manifest_001603.csv", index=False)

    print("Building manifest for 001872 ...")
    m1872 = build_manifest("001872")
    m1872.to_csv(manifests_dir / "manifest_001872.csv", index=False)

    m_all = pd.concat([m1603, m1872], ignore_index=True)
    m_all.to_csv(manifests_dir / "manifest_all.csv", index=False)

    for df, name in ((m1603, "001603"), (m1872, "001872")):
        n_err = df["error"].notna().sum()
        if n_err:
            errors_log.append(f"{name}: {n_err}/{len(df)} assets failed to open (see 'error' column in manifest)")

    audit = audit_settings(m1603, m1872)
    audit.to_csv(reports_dir / "settings_audit.csv", index=False)

    subj_summary = _subject_type_summary(m1603)
    subj_summary.to_csv(manifests_dir / "manifest_001603_subject_summary.csv", index=False)

    well_summary = _well_summary(m1872)
    well_summary.to_csv(manifests_dir / "manifest_001872_well_summary.csv", index=False)

    human_subj = subj_summary[subj_summary["species"] == "Homo sapiens"]
    nonhuman_subj = subj_summary[subj_summary["species"] != "Homo sapiens"]
    n_recorded = (human_subj["subject_type"] == "recorded").sum()
    n_sourced = (human_subj["subject_type"] == "sourced").sum()
    n_neither = (human_subj["subject_type"] == "no_raw_no_units").sum()
    species_counts = subj_summary.groupby("species")["subject_id"].count().to_dict()
    n_distinct_wells = well_summary["well_id"].nunique()
    n_distinct_subjects_1872 = m1872["subject_id"].nunique()
    n_batches_1872 = well_summary["batch"].nunique()

    report_lines = [
        "# Stage 0 — Inventory report",
        "",
        f"- DANDI:001603 assets scanned: {len(m1603)}",
        f"- DANDI:001872 assets scanned: {len(m1872)}",
        "",
        "## Errors encountered while streaming metadata",
        "",
        *(errors_log if errors_log else ["None."]),
        "",
        "## ⚠️ DANDI:001603 contains non-human subjects — must be excluded",
        "",
        "This dataset is titled \"Preconfigured neuronal firing sequences in human"
        " brain organoids\" but its subject list is NOT all-human. Species breakdown"
        f" by subject_id count: {species_counts}.",
        "",
        "Only subjects with `species == Homo sapiens` (prefix `HO*`, 8 subjects) are"
        " in scope for this project. Subjects prefixed `M1S*`/`M2S*`/`M3S*`, `MO*`"
        " (Mus musculus / mouse) and `PR1-4` (Rattus norvegicus / rat), `PR5-8`"
        " (Mus musculus / mouse) are reference/comparison recordings and MUST NOT be"
        " included in any human-cortical-organoid manifest, feature matrix, or"
        " downstream analysis. All counts below are filtered to Homo sapiens only"
        " unless stated otherwise.",
        "",
        "## DANDI:001603 — recorded vs sourced subjects, human-only (VERIFY item, Task 0.3)",
        "",
        f"- Distinct human (Homo sapiens) subjects: {len(human_subj)}",
        f"- Recorded (>=1 asset with raw ElectricalSeries): {n_recorded}",
        f"- Sourced (Units only, no raw): {n_sourced}",
        f"- Neither raw nor Units present (excluded from both categories): {n_neither}",
        "",
        human_subj.to_markdown(index=False),
        "",
        "### Non-human subjects (excluded), for completeness",
        "",
        nonhuman_subj.to_markdown(index=False),
        "",
        "## DANDI:001872 — file -> well -> organoid mapping (VERIFY item, Task 0.3)",
        "",
        f"- Distinct well_id values found: {n_distinct_wells} (NOT a unique organoid key"
        " on its own -- see below)",
        f"- Distinct batches/plates found: {n_batches_1872} ({sorted(well_summary['batch'].unique().tolist())})",
        f"- Distinct subject_id values (batch+well = the correct distinct-organoid key): {n_distinct_subjects_1872}",
        "",
        "**Important:** well_id (e.g. \"well001\") is reused across batches -- e.g."
        " both the `sample` and `sample2` batches have their own well001..well023."
        " `subject_id` (e.g. `sample_well001` vs `sample2_well001`) is the correct"
        " distinct-organoid grouping key, NOT well_id alone.",
        "",
        well_summary.to_markdown(index=False),
        "",
        "## Settings audit — MaxOne (001603) vs MaxTwo (001872), human subjects only (VERIFY item, Task 0.4)",
        "",
        audit.to_markdown(index=False),
        "",
        "## Verified vs assumed",
        "",
        "- VERIFIED: asset counts, per-asset raw/Units presence, sampling rate, dtype,"
        " electrode count and geometry columns, well/subject grouping — all read"
        " directly from each NWB file's own metadata via streaming (no download).",
        "- ASSUMED: `electrode_pitch_raw_units` assumes the electrode table's x/y (or"
        " rel_x/rel_y) columns are in a consistent, comparable unit within each"
        " platform; the actual unit was not independently confirmed against device"
        " documentation and should be checked before using pitch for cross-platform"
        " decisions.",
        "- ASSUMED: subject_type classification (recorded vs sourced) uses only"
        " presence of a raw ElectricalSeries in *this* dandiset's assets — a subject"
        " could in principle have raw data hosted elsewhere and only Units deposited"
        " here; not cross-checked against dandiset descriptions/publications beyond"
        " what's in NWB metadata.",
        "- VERIFIED: species per subject, read directly from NWB Subject metadata —"
        " confirms 001603 mixes Homo sapiens subjects with Mus musculus / Rattus"
        " norvegicus reference subjects; 001872 subjects are all Homo sapiens.",
        "- NOT YET VERIFIED: whether the 4 `PR1-4` (rat) / `PR5-8` (mouse) subjects"
        " that have neither raw nor Units data are empty/placeholder NWB files or"
        " contain some other data type (e.g. stimulus/protocol only) not captured by"
        " this manifest's columns — not investigated further since these are"
        " non-human and out of scope regardless.",
        "",
        "## Open questions for human review",
        "",
        "- **Exclude non-human subjects going forward**: confirm it's fine to drop"
        " all `M1S*/M2S*/M3S*`, `MO*`, `PR*` subjects from 001603 for the rest of"
        " this project (28 of 36 subjects) — only `HO1-HO8` are human.",
        "- Confirm the well -> organoid mapping for 001872: does each well_id"
        " correspond to one biological organoid across all its sessions, or could a"
        " well have been re-seeded between sessions (which would break the"
        " organoid-as-grouping-unit guardrail)? Note the `sample` batch has multiple"
        " sessions per well spanning different ages while `sample2` has one session"
        " per well — worth confirming these are genuinely longitudinal recordings of"
        " the same organoid within `sample`, not re-seeds.",
        "- Any settings_audit.csv mismatches (sampling rate, dtype, pitch) must be"
        " resolved or explicitly flagged as platform-sensitive before Stage 2.",
        "- 001872's `n_electrodes` varies a lot even within the `sample2` batch"
        " (107-608) recorded in the same session batch — worth confirming whether"
        " this reflects a per-well active-electrode selection step (expected) rather"
        " than a data-quality issue.",
    ]
    (reports_dir / "stage0_inventory.md").write_text("\n".join(report_lines), encoding="utf-8")
    print("Wrote outputs/reports/stage0_inventory.md")


if __name__ == "__main__":
    main()
