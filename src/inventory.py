"""Stage 0 — per-recording manifest builder.

Builds outputs/manifests/manifest_001603.csv, manifest_001872.csv, and the
merged manifest_all.csv, plus outputs/reports/stage0_inventory.md.

See docs/handoff_foundation_phase.md, Section 2 (Tasks 0.1-0.4) for the
exact column list and the ⚠️ VERIFY items this stage must resolve:
  - 001603: recorded (raw) vs sourced (spikesorted-only) subjects
  - 001872: file -> well -> organoid -> timepoint mapping, distinct-organoid count
  - MaxOne vs MaxTwo settings audit (sampling rate, µV scaling, filtering,
    active-electrode logic, electrode pitch)

Not yet implemented — this is the next stage after Checkpoint A.
"""
from __future__ import annotations


def build_manifest(dandiset_id: str):
    raise NotImplementedError


def audit_settings(manifest_001603, manifest_001872):
    raise NotImplementedError
