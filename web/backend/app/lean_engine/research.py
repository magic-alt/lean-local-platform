from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Any

from ..core.config import DATA_DIR, DEFAULT_RESEARCH_IMAGE, OBJECT_STORE_DIR, REPO_ROOT
from .errors import LeanPlatformError

def run_detached_research(
    session_id: str,
    project_dir: Path,
    port: int,
    output_callback,
    image: str = DEFAULT_RESEARCH_IMAGE,
) -> dict[str, Any]:
    docker = shutil.which("docker")
    if not docker:
        raise LeanPlatformError("docker command not found.")
    command = [
        docker,
        "run",
        "-d",
        "--name",
        f"lean-research-{session_id}"[:60],
        "-p",
        f"{port}:8888",
        "-v",
        f"{DATA_DIR}:/Lean/Data:ro",
        "-v",
        f"{project_dir}:/Lean/Project",
        "-v",
        f"{OBJECT_STORE_DIR}:/Lean/Launcher/bin/Debug/storage",
        image,
    ]
    output_callback("running: " + " ".join(command))
    completed = subprocess.run(
        command,
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    if completed.stdout:
        output_callback(completed.stdout.strip())
    if completed.stderr:
        output_callback(completed.stderr.strip())
    if completed.returncode != 0:
        raise LeanPlatformError(f"Research container failed to start: {completed.stderr or completed.stdout}")
    return {"container_id": completed.stdout.strip(), "url": f"http://127.0.0.1:{port}"}


def stop_container(container_id: str) -> None:
    docker = shutil.which("docker")
    if not docker:
        raise LeanPlatformError("docker command not found.")
    subprocess.run([docker, "stop", container_id], cwd=REPO_ROOT, check=False)
