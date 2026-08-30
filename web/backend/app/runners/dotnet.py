from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Callable, Mapping


DOTNET_PATH_ENV = "LEAN_DOTNET_PATH"
DOTNET_RUNTIME_MAJOR = 10


def _usable_executable(path: Path) -> bool:
    if not path.is_file():
        return False
    return os.name == "nt" or os.access(path, os.X_OK)


def resolve_dotnet(
    *,
    environment: Mapping[str, str] | None = None,
    which: Callable[[str], str | None] = shutil.which,
    windows: bool | None = None,
) -> Path | None:
    """Resolve the host dotnet executable without requiring a PATH mutation."""
    values = os.environ if environment is None else environment
    configured = str(values.get(DOTNET_PATH_ENV) or "").strip()
    if configured:
        candidate = Path(configured).expanduser()
        if candidate.is_absolute() and _usable_executable(candidate):
            return candidate.resolve()

    discovered = which("dotnet")
    if discovered:
        candidate = Path(discovered)
        if _usable_executable(candidate):
            return candidate.resolve()

    is_windows = os.name == "nt" if windows is None else windows
    if is_windows:
        program_files = str(values.get("ProgramFiles") or r"C:\Program Files").strip()
        candidate = Path(program_files) / "dotnet" / "dotnet.exe"
        if _usable_executable(candidate):
            return candidate.resolve()
    return None


def dotnet_major_available(
    executable: Path,
    *,
    major: int = DOTNET_RUNTIME_MAJOR,
    sdk: bool = False,
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> bool:
    flag = "--list-sdks" if sdk else "--list-runtimes"
    try:
        result = runner(
            [str(executable), flag],
            check=False,
            capture_output=True,
            text=True,
            timeout=20,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    if result.returncode != 0:
        return False
    if sdk:
        pattern = re.compile(rf"^{major}\.", re.MULTILINE)
    else:
        pattern = re.compile(rf"^Microsoft\.NETCore\.App\s+{major}\.", re.MULTILINE)
    return pattern.search(result.stdout or "") is not None
