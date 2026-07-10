"""Stage 1 — run pipeline validation across the 4 human recorded subjects
(HO1-HO4), each using their P7M-tagged raw + deposited-Units pair (the age
tag common across all 4). See src/validate_pipeline.py for the comparison
logic and config/params.yaml for the frozen parameters / acceptance criteria.
"""
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, r"C:\Users\franc\MEA project")

from src.config import load_config, require
from src.validate_pipeline import compare_to_deposited_units

DATA_RAW = Path(r"C:\Users\franc\MEA project\data\raw")

PAIRS = {
    "HO1": (
        DATA_RAW / "sub-HO1_ses-20250924T011900_ecephys.nwb",
        DATA_RAW / "sub-HO1_ses-20250924T002125.nwb",
    ),
    "HO2": (
        DATA_RAW / "sub-HO2_ses-20250912T144839_ecephys.nwb",
        DATA_RAW / "sub-HO2_ses-20250916T190927_obj-1s1jcwl.nwb",
    ),
    "HO3": (
        DATA_RAW / "sub-HO3_ses-20250912T150817_ecephys.nwb",
        DATA_RAW / "sub-HO3_ses-20250916T190930_obj-2sqh9d.nwb",
    ),
    "HO4": (
        DATA_RAW / "sub-HO4_ses-20250924T011900_ecephys.nwb",
        DATA_RAW / "sub-HO4_ses-20250924T002126.nwb",
    ),
}

if __name__ == "__main__":
    out_path = Path(r"C:\Users\franc\MEA project\outputs\reports\stage1_validation_results.json")

    config = load_config()
    results = {}
    if out_path.exists():
        results = json.loads(out_path.read_text(encoding="utf-8"))
        print(f"Resuming: already have results for {list(results.keys())}", flush=True)

    for subject, (raw_path, units_path) in PAIRS.items():
        if subject in results:
            print(f"=== {subject} === (skipping, already done)", flush=True)
            continue
        print(f"=== {subject} ===", flush=True)
        t0 = time.time()
        r = compare_to_deposited_units(raw_path, units_path, config)
        r["elapsed_s"] = time.time() - t0
        results[subject] = r
        print(json.dumps(r, indent=2), flush=True)
        # Save after every subject, not just at the end -- a prior run of this
        # script was killed (machine sleep) with zero output saved.
        out_path.write_text(json.dumps(results, indent=2), encoding="utf-8")
        print(f"  (saved progress to {out_path.name})", flush=True)

    print(f"\nAll done. Results in {out_path}")
