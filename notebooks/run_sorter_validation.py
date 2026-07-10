"""Stage 1 (extended) -- validate a real CPU spike sorter (lupin, via
spikeinterface) against deposited ground truth, on the full recording (not
just a feasibility subset). See src/validate_pipeline.py's
compare_sorter_to_deposited_units for the comparison logic.

Estimated runtime: 1+ hours per subject (see conversation log / commit
history for the feasibility-test timing this estimate is based on).
"""
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.validate_pipeline import compare_sorter_to_deposited_units

DATA_RAW = Path(r"C:\Users\franc\MEA project\data\raw")

PAIRS = {
    "HO1": (
        DATA_RAW / "sub-HO1_ses-20250924T011900_ecephys.nwb",
        DATA_RAW / "sub-HO1_ses-20250924T002125.nwb",
    ),
}

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--subjects", default=",".join(PAIRS.keys()))
    parser.add_argument("--sorter", default="lupin")
    parser.add_argument("--out", default="stage1_sorter_validation_results.json")
    args = parser.parse_args()
    subjects = args.subjects.split(",")

    out_path = Path(r"C:\Users\franc\MEA project\outputs\reports") / args.out
    results = {}
    if out_path.exists():
        results = json.loads(out_path.read_text(encoding="utf-8"))
        print(f"Resuming: already have results for {list(results.keys())}", flush=True)

    for subject in subjects:
        key = f"{subject}_{args.sorter}"
        if key in results:
            print(f"=== {key} === (skipping, already done)", flush=True)
            continue
        raw_path, units_path = PAIRS[subject]
        print(f"=== {key} ===", flush=True)
        t0 = time.time()
        r = compare_sorter_to_deposited_units(raw_path, units_path, sorter_name=args.sorter)
        r["elapsed_s"] = time.time() - t0
        results[key] = r
        print(json.dumps(r, indent=2), flush=True)
        out_path.write_text(json.dumps(results, indent=2), encoding="utf-8")
        print(f"  (saved progress to {out_path.name})", flush=True)

    print(f"\nAll done. Results in {out_path}")
