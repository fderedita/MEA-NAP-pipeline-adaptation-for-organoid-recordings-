"""DANDI asset discovery and streaming/download helpers.

Stage 0 (inventory.py) uses this module to list assets for a dandiset and
open NWB files by streaming (metadata-only pass, no full download). Stage
0.5 uses it to download the prioritised raw files to data/raw/.
"""
from __future__ import annotations

from pathlib import Path

import h5py
import remfile
from dandi.dandiapi import DandiAPIClient
from pynwb import NWBHDF5IO


def list_assets(dandiset_id: str):
    """Return (nwb_assets, dandiset_raw_metadata) for a dandiset's default version."""
    with DandiAPIClient() as client:
        dandiset = client.get_dandiset(dandiset_id)
        meta = dandiset.get_raw_metadata()
        assets = [a for a in dandiset.get_assets() if a.path.endswith(".nwb")]
    return assets, meta


def stream_nwb(asset):
    """Open an NWB asset for metadata-only streaming access (no full download).

    Returns (nwbfile, io). Caller must close `io` when done (releases the
    remote HTTP stream); see inventory._row_for_asset for the try/finally
    pattern.
    """
    url = asset.get_content_url(follow_redirects=1, strip_query=True)
    remote_file = remfile.File(url)
    h5_file = h5py.File(remote_file, "r")
    io = NWBHDF5IO(file=h5_file, mode="r", load_namespaces=True)
    nwbfile = io.read()
    return nwbfile, io


def download_asset(asset, dest_dir: str | Path) -> Path:
    """Download a single asset to dest_dir, returning the local path."""
    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_path = dest_dir / Path(asset.path).name
    asset.download(dest_path)
    return dest_path
