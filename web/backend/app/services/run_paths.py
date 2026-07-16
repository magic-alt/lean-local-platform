from __future__ import annotations

from pathlib import Path
from typing import Any

from ..core import config


def run_directory(run_id: str, path_value: Any = None, *, relative: str = "") -> Path:
    original = Path(str(path_value or ""))
    candidates = [original] if path_value else []
    parts = original.parts
    try:
        marker = parts.index("runs")
    except ValueError:
        marker = -1
    if marker >= 0 and marker + 1 < len(parts) and parts[marker + 1] == run_id:
        candidates.append(config.RUNS_DIR / Path(*parts[marker + 1 :]))
    candidates.append(config.RUNS_DIR / run_id / relative)
    return next((candidate for candidate in candidates if candidate.is_dir()), candidates[-1])


def run_file(run_id: str, path_value: Any, relative: str) -> Path:
    original = Path(str(path_value or ""))
    candidates = [original] if path_value else []
    parts = original.parts
    try:
        marker = parts.index("runs")
    except ValueError:
        marker = -1
    if marker >= 0 and marker + 1 < len(parts) and parts[marker + 1] == run_id:
        candidates.append(config.RUNS_DIR / Path(*parts[marker + 1 :]))
    candidates.append(config.RUNS_DIR / run_id / relative)
    return next((candidate for candidate in candidates if candidate.is_file()), candidates[-1])
