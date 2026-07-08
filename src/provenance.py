"""Reproducibility stamping: git commit hash + config hash for output files.

Every artifact this pipeline writes (manifests, feature matrices, reports)
should be tagged with the output of `stamp()` so results can be traced back
to the exact code + parameters that produced them.
"""
from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path
from typing import Any


def get_git_commit_hash(repo_dir: str | Path = ".") -> str:
    """Return the current git commit hash, or 'unknown' if unavailable (e.g. dirty tree with no commits yet)."""
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_dir,
            capture_output=True,
            text=True,
            check=True,
        )
        return out.stdout.strip()
    except Exception:
        return "unknown"


def config_hash(config: dict[str, Any]) -> str:
    """Stable hash of a loaded config dict, order-independent."""
    import json

    canonical = json.dumps(config, sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:12]


def stamp(config: dict[str, Any], repo_dir: str | Path = ".") -> dict[str, str]:
    """Metadata block to attach to any output artifact."""
    return {
        "git_commit": get_git_commit_hash(repo_dir),
        "config_hash": config_hash(config),
    }
