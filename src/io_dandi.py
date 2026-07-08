"""DANDI asset discovery and streaming/download helpers.

Stage 0 (inventory.py) uses this module to list assets for a dandiset and
open NWB files by streaming (metadata-only pass, no full download). Stage
0.5 uses it to download the prioritised raw files to data/raw/.

Not yet implemented — scaffolded ahead of Stage 0 (see docs/handoff_foundation_phase.md).
"""
from __future__ import annotations


def list_assets(dandiset_id: str, version: str = "draft"):
    """List all assets for a dandiset via DandiAPIClient."""
    raise NotImplementedError


def stream_nwb_metadata(asset):
    """Open an NWB asset's metadata only, via remfile/lindi streaming (no full download)."""
    raise NotImplementedError


def download_asset(asset, dest_dir):
    """Download a single asset to dest_dir, returning the local path and checksum."""
    raise NotImplementedError
