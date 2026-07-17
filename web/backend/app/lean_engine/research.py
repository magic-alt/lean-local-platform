from __future__ import annotations

import shutil
import secrets
import re
import socket
import subprocess
import time
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
    token = secrets.token_urlsafe(24)
    command = [
        docker,
        "run",
        "-d",
        "--name",
        f"lean-research-{session_id}"[:60],
        "-p",
        f"{port}:8888",
        "-e",
        f"JUPYTER_TOKEN={token}",
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
    container_id = completed.stdout.strip()
    deadline = time.monotonic() + 60
    last_state = "starting"
    while time.monotonic() < deadline:
        state = container_state(container_id)
        last_state = str(state.get("status") or "unknown")
        if not state.get("running"):
            logs = container_logs(container_id, tail=80)
            remove_container(container_id)
            raise LeanPlatformError(f"Research container exited before readiness ({last_state}): {logs[-2000:]}")
        if container_port_ready(container_id):
            return {
                "container_id": container_id,
                "url": f"http://127.0.0.1:{port}/?token={token}",
                "container_status": last_state,
                "readiness_status": "ready",
            }
        time.sleep(1)
    logs = container_logs(container_id, tail=80)
    stop_container(container_id)
    remove_container(container_id)
    raise LeanPlatformError(f"Research Jupyter did not become ready within 60 seconds: {logs[-2000:]}")


def stop_container(container_id: str) -> None:
    docker = shutil.which("docker")
    if not docker:
        raise LeanPlatformError("docker command not found.")
    subprocess.run([docker, "stop", container_id], cwd=REPO_ROOT, check=False)


def remove_container(container_id: str) -> None:
    docker = shutil.which("docker")
    if not docker:
        return
    subprocess.run([docker, "rm", "-f", container_id], cwd=REPO_ROOT, capture_output=True, text=True, check=False)


def container_state(container_id: str) -> dict[str, Any]:
    docker = shutil.which("docker")
    if not docker or not container_id:
        return {"status": "missing", "running": False}
    completed = subprocess.run(
        [docker, "inspect", "--format", "{{.State.Status}}|{{.State.Running}}|{{.State.ExitCode}}", container_id],
        cwd=REPO_ROOT, capture_output=True, text=True, check=False,
    )
    if completed.returncode != 0:
        return {"status": "missing", "running": False, "error": completed.stderr.strip()}
    status, running, exit_code = (completed.stdout.strip().split("|") + ["", "", ""])[:3]
    return {"status": status, "running": running.lower() == "true", "exitCode": int(exit_code or 0)}


def container_logs(container_id: str, *, tail: int = 200) -> str:
    docker = shutil.which("docker")
    if not docker or not container_id:
        return ""
    completed = subprocess.run(
        [docker, "logs", "--tail", str(max(1, min(tail, 2000))), container_id],
        cwd=REPO_ROOT, capture_output=True, text=True, check=False,
    )
    return "\n".join(item for item in (completed.stdout.strip(), completed.stderr.strip()) if item)


def container_port_ready(container_id: str) -> bool:
    docker = shutil.which("docker")
    if not docker or not container_id:
        return False
    completed = subprocess.run(
        [
            docker, "exec", container_id, "python", "-c",
            "import socket; s=socket.create_connection(('127.0.0.1',8888),1); s.close()",
        ],
        cwd=REPO_ROOT, capture_output=True, text=True, check=False,
    )
    return completed.returncode == 0


def find_available_port(preferred: int | None = None, *, start: int = 8888, end: int = 8999) -> int:
    used: set[int] = set()
    docker = shutil.which("docker")
    if docker:
        completed = subprocess.run(
            [docker, "ps", "--format", "{{.Ports}}"], cwd=REPO_ROOT,
            capture_output=True, text=True, check=False,
        )
        used.update(int(value) for value in re.findall(r"(?:0\.0\.0\.0|127\.0\.0\.1|\[::\]):(\d+)->", completed.stdout or ""))
    candidates = [preferred] if preferred else []
    candidates.extend(port for port in range(start, end + 1) if port != preferred)
    for port in candidates:
        if port is None or not 1024 <= int(port) <= 65535 or int(port) in used:
            continue
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                probe.bind(("127.0.0.1", int(port)))
            except OSError:
                continue
        return int(port)
    raise LeanPlatformError("No available Research port was found in 8888-8999.")
