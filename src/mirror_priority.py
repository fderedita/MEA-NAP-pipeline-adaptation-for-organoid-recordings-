"""Stage 0.5 — prioritised mirroring of raw NWB files to data/raw/.

Manually curated selection (not a general-purpose "download everything"
tool): see docs/handoff_foundation_phase.md Section 2.5 and
outputs/reports/stage0_inventory.md for the reasoning behind which
subjects/wells were chosen. Re-run is idempotent -- already-downloaded
files are skipped.

DANDI:001872 is 261 GB total, larger than free disk on this machine, so
only a representative subset is mirrored (a handful of wells spanning
both the "sample" and "sample2" batches). DANDI:001603 non-human subjects
(Mus musculus / Rattus norvegicus) are excluded entirely per Checkpoint B.
"""
from __future__ import annotations

from pathlib import Path

from src import io_dandi

DATA_RAW = Path(__file__).resolve().parent.parent / "data" / "raw"

# 001603: human recorded subjects (HO1-HO4) only. HO1 already mirrored by
# hand earlier (raw + curated units). For HO2/HO3, one raw + one Units
# asset per distinct `age` tag observed (P6M/P7M/P8M/P8MT4H) -- note this
# tag does NOT appear to track literal chronological recording time (see
# stage0_inventory.md open questions), so treat it as a diversity/coverage
# heuristic, not verified DIV.
ASSETS_001603 = [
    # HO2
    "sub-HO2/sub-HO2_ses-20250912T144835_obj-9jlzq1_ecephys.nwb",  # raw, age=P6M
    "sub-HO2/sub-HO2_ses-20250916T190936.nwb",  # units, age=P6M
    "sub-HO2/sub-HO2_ses-20250912T144839_ecephys.nwb",  # raw, age=P7M
    "sub-HO2/sub-HO2_ses-20250916T190927_obj-1s1jcwl.nwb",  # units, age=P7M
    "sub-HO2/sub-HO2_ses-20250912T144837_ecephys.nwb",  # raw, age=P8M
    "sub-HO2/sub-HO2_ses-20250916T190928_obj-86y47o.nwb",  # units, age=P8M
    "sub-HO2/sub-HO2_ses-20250912T144835_obj-77d92a_ecephys.nwb",  # raw, age=P8MT4H
    "sub-HO2/sub-HO2_ses-20250916T190927_obj-vm83mt.nwb",  # units, age=P8MT4H
    # HO3
    "sub-HO3/sub-HO3_ses-20250912T144841_ecephys.nwb",  # raw, age=P6M
    "sub-HO3/sub-HO3_ses-20250916T190937.nwb",  # units, age=P6M
    "sub-HO3/sub-HO3_ses-20250912T150817_ecephys.nwb",  # raw, age=P7M
    "sub-HO3/sub-HO3_ses-20250916T190930_obj-2sqh9d.nwb",  # units, age=P7M
    "sub-HO3/sub-HO3_ses-20250912T144835_obj-1hc8buj_ecephys.nwb",  # raw, age=P8M
    "sub-HO3/sub-HO3_ses-20250916T190930_obj-ikzmsj.nwb",  # units, age=P8M
    "sub-HO3/sub-HO3_ses-20250912T144846_ecephys.nwb",  # raw, age=P8MT4H
    "sub-HO3/sub-HO3_ses-20250916T190928.nwb",  # units, age=P8MT4H
    # HO4 (single session)
    "sub-HO4/sub-HO4_ses-20250924T011900_ecephys.nwb",  # raw
    "sub-HO4/sub-HO4_ses-20250924T002126.nwb",  # units
]

# 001872: 3 wells from each batch, spread across the 24-well plate
# (well000/008/016). "sample" = longitudinal (4 sessions/well); "sample2" =
# single cross-sectional session/well. well001 (sample) already mirrored by
# hand earlier.
ASSETS_001872 = [
    # sample (longitudinal, 4 sessions each)
    "sub-sample-well000/sub-sample-well000_ses-20260622T175109_ecephys.nwb",
    "sub-sample-well000/sub-sample-well000_ses-20260622T195034_ecephys.nwb",
    "sub-sample-well000/sub-sample-well000_ses-20260622T215252_ecephys.nwb",
    "sub-sample-well000/sub-sample-well000_ses-20260622T233922_ecephys.nwb",
    "sub-sample-well008/sub-sample-well008_ses-20260622T182607_ecephys.nwb",
    "sub-sample-well008/sub-sample-well008_ses-20260622T202514_ecephys.nwb",
    "sub-sample-well008/sub-sample-well008_ses-20260622T222259_ecephys.nwb",
    "sub-sample-well008/sub-sample-well008_ses-20260623T000326_ecephys.nwb",
    "sub-sample-well016/sub-sample-well016_ses-20260622T185903_ecephys.nwb",
    "sub-sample-well016/sub-sample-well016_ses-20260622T210111_ecephys.nwb",
    "sub-sample-well016/sub-sample-well016_ses-20260622T225444_ecephys.nwb",
    "sub-sample-well016/sub-sample-well016_ses-20260623T003647_ecephys.nwb",
    # sample2 (single cross-sectional session/well)
    "sub-sample2-well000/sub-sample2-well000_ses-20260623T155950_ecephys.nwb",
    "sub-sample2-well008/sub-sample2-well008_ses-20260623T183144_ecephys.nwb",
    "sub-sample2-well016/sub-sample2-well016_ses-20260623T183945_ecephys.nwb",
]


def mirror(dandiset_id: str, wanted_paths: list[str]) -> None:
    assets, _ = io_dandi.list_assets(dandiset_id)
    by_path = {a.path: a for a in assets}
    for path in wanted_paths:
        asset = by_path.get(path)
        if asset is None:
            print(f"  MISSING from dandiset (skip): {path}")
            continue
        dest = DATA_RAW / Path(path).name
        if dest.exists():
            if dest.stat().st_size == asset.size:
                print(f"  already have (size verified): {dest.name}")
                continue
            print(f"  incomplete file on disk ({dest.stat().st_size} of {asset.size} bytes) -- re-downloading: {dest.name}")
            dest.unlink()

        max_attempts = 4
        for attempt in range(1, max_attempts + 1):
            try:
                print(f"  downloading ({asset.size / 1e9:.2f} GB, attempt {attempt}/{max_attempts}): {path}")
                io_dandi.download_asset(asset, DATA_RAW)
                if dest.stat().st_size != asset.size:
                    raise IOError(
                        f"size mismatch after download: got {dest.stat().st_size}, expected {asset.size}"
                    )
                break
            except Exception as e:  # noqa: BLE001 - retry on any transient network/IO error
                print(f"    attempt {attempt} failed: {type(e).__name__}: {e}")
                if dest.exists():
                    dest.unlink()
                if attempt == max_attempts:
                    print(f"  GAVE UP after {max_attempts} attempts: {path}")


if __name__ == "__main__":
    print("=== 001603 ===")
    mirror("001603", ASSETS_001603)
    print("=== 001872 ===")
    mirror("001872", ASSETS_001872)
    print("done")
