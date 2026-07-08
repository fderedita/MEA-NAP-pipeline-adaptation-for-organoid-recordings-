"""Config loading with fail-loud semantics.

Per project guardrail: if a parameter is missing from config/params.yaml,
code must raise rather than silently default. Use `require()` to pull
nested keys out of the loaded config.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "params.yaml"


def load_config(path: str | Path = DEFAULT_CONFIG_PATH) -> dict[str, Any]:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")
    with open(path, "r") as f:
        config = yaml.safe_load(f)
    if not config:
        raise ValueError(f"Config file is empty: {path}")
    return config


def require(config: dict[str, Any], dotted_key: str) -> Any:
    """Fetch a nested key like 'preprocessing.bandpass_hz'; raise if missing or null.

    A key present but set to null (YAML) is treated as "not yet decided" and
    still raises — several params.yaml entries are intentionally left null
    with a TODO comment pending Stage 0/1 findings, and code must not
    silently proceed with None.
    """
    node: Any = config
    parts = dotted_key.split(".")
    for i, part in enumerate(parts):
        if not isinstance(node, dict) or part not in node:
            raise KeyError(
                f"Missing required config key '{dotted_key}' "
                f"(failed at '{'.'.join(parts[: i + 1])}'). "
                f"Add it to config/params.yaml — do not default silently."
            )
        node = node[part]
    if node is None:
        raise ValueError(
            f"Config key '{dotted_key}' is present but unset (null) in params.yaml. "
            f"This value must be determined and frozen before this code path runs."
        )
    return node
