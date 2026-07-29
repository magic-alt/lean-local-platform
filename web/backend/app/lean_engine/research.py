from __future__ import annotations

import json
import os
import shutil
import secrets
import re
import socket
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from ..core.config import (
    ALLOWED_RESEARCH_DOCKER_IMAGES,
    DEFAULT_RESEARCH_IMAGE,
    HOST_DATA_DIR,
    HOST_PARQUET_DIR,
    HOST_PLATFORM_DIR,
    PLATFORM_DIR,
    REPO_ROOT,
    RESEARCH_DIR,
    RESEARCH_DOCKER_CPUS,
    RESEARCH_DOCKER_MEMORY,
    RESEARCH_DOCKER_PIDS_LIMIT,
)
from .errors import LeanPlatformError


def research_container_name(session_id: str) -> str:
    return f"lean-research-{session_id}"[:60]


def _runner_url() -> str:
    return os.environ.get("LEAN_RUNNER_URL", "").strip().rstrip("/")


def _runner_token() -> str:
    configured = os.environ.get("LEAN_RUNNER_TOKEN", "").strip()
    if configured:
        return configured
    path = Path(
        os.environ.get(
            "LEAN_RUNNER_TOKEN_FILE",
            "/workspace/web/runtime/secrets/runner_token",
        )
    )
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def _remote_request(
    method: str,
    path: str,
    payload: dict[str, Any] | None = None,
    *,
    timeout: int = 90,
) -> dict[str, Any]:
    runner_url = _runner_url()
    token = _runner_token()
    if not runner_url or not token:
        raise LeanPlatformError("restricted_runner_not_configured")
    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = urllib.request.Request(
        runner_url + path,
        data=body,
        headers={
            "Authorization": f"Bearer {token}",
            **({"Content-Type": "application/json"} if body is not None else {}),
        },
        method=method,
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            decoded = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        try:
            detail = str(json.loads(detail).get("detail") or detail)
        except (json.JSONDecodeError, AttributeError):
            pass
        raise LeanPlatformError(f"restricted_runner_research_failed: {detail}") from exc
    except OSError as exc:
        raise LeanPlatformError(f"restricted_runner_unavailable: {exc}") from exc
    if not isinstance(decoded, dict):
        raise LeanPlatformError("restricted_runner_invalid_response")
    return decoded


def _remote_session_id(container_id: str) -> str | None:
    prefix = "lean-research-"
    value = str(container_id or "").strip()
    return value[len(prefix):] if value.startswith(prefix) else None


def _host_platform_path(path: Path) -> Path:
    try:
        return HOST_PLATFORM_DIR / path.resolve().relative_to(PLATFORM_DIR.resolve())
    except ValueError:
        return path.resolve()


def validate_research_docker_image(image: str) -> str:
    normalized = str(image or "").strip()
    if normalized not in ALLOWED_RESEARCH_DOCKER_IMAGES:
        raise LeanPlatformError(
            "research_image_not_allowed: Select a digest-pinned image from the operator allowlist."
        )
    if "@sha256:" not in normalized:
        raise LeanPlatformError(
            "research_image_not_pinned: Research images must use an immutable sha256 digest."
        )
    return normalized

def run_detached_research(
    session_id: str,
    project_dir: Path,
    port: int,
    output_callback,
    image: str = DEFAULT_RESEARCH_IMAGE,
) -> dict[str, Any]:
    image = validate_research_docker_image(image)
    host_project_dir = _host_platform_path(project_dir)
    if _runner_url():
        result = _remote_request(
            "POST",
            "/v1/research/start",
            {
                "sessionId": session_id,
                "image": image,
                "projectDir": str(host_project_dir),
                "port": port,
            },
        )
        for line in result.pop("output", []) or []:
            output_callback(str(line))
        return result

    docker = shutil.which("docker")
    if not docker:
        raise LeanPlatformError("docker command not found.")
    token = secrets.token_urlsafe(24)
    snapshots_dir = RESEARCH_DIR / "snapshots"
    snapshots_dir.mkdir(parents=True, exist_ok=True)
    host_snapshots_dir = _host_platform_path(snapshots_dir)
    command = [
        docker,
        "run",
        "-d",
        "--network",
        "none",
        "--name",
        research_container_name(session_id),
        "--cpus",
        RESEARCH_DOCKER_CPUS,
        "--memory",
        RESEARCH_DOCKER_MEMORY,
        "--pids-limit",
        str(RESEARCH_DOCKER_PIDS_LIMIT),
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges:true",
        "-p",
        f"127.0.0.1:{port}:8888",
        "-e",
        f"JUPYTER_TOKEN={token}",
        "-v",
        f"{HOST_DATA_DIR}:/Lean/Data:ro",
        "-v",
        f"{HOST_PARQUET_DIR}:/Lean/Parquet:ro",
        "-v",
        f"{host_snapshots_dir}:/Lean/Snapshots:ro",
        "-v",
        f"{host_project_dir}:/Lean/Project",
        image,
    ]
    output_callback("running: " + " ".join("JUPYTER_TOKEN=<redacted>" if value.startswith("JUPYTER_TOKEN=") else value for value in command))
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
    if _runner_url():
        session_id = _remote_session_id(container_id)
        if not session_id:
            raise LeanPlatformError("restricted_runner_research_container_reference_invalid")
        _remote_request("POST", f"/v1/research/{urllib.parse.quote(session_id, safe='')}/stop")
        return
    docker = shutil.which("docker")
    if not docker:
        raise LeanPlatformError("docker command not found.")
    subprocess.run([docker, "stop", container_id], cwd=REPO_ROOT, check=False)


def remove_container(container_id: str) -> None:
    if _runner_url():
        session_id = _remote_session_id(container_id)
        if session_id:
            _remote_request("DELETE", f"/v1/research/{urllib.parse.quote(session_id, safe='')}")
        return
    docker = shutil.which("docker")
    if not docker:
        return
    subprocess.run([docker, "rm", "-f", container_id], cwd=REPO_ROOT, capture_output=True, text=True, check=False)


def container_state(container_id: str) -> dict[str, Any]:
    if _runner_url():
        session_id = _remote_session_id(container_id)
        if not session_id:
            return {"status": "missing", "running": False}
        return _remote_request("GET", f"/v1/research/{urllib.parse.quote(session_id, safe='')}")
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
    if _runner_url():
        session_id = _remote_session_id(container_id)
        if not session_id:
            return ""
        payload = _remote_request(
            "GET",
            f"/v1/research/{urllib.parse.quote(session_id, safe='')}/logs?tail={max(1, min(tail, 2000))}",
        )
        return str(payload.get("logs") or "")
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
    if _runner_url():
        payload = _remote_request(
            "POST",
            "/v1/research/port",
            {"preferred": preferred, "start": start, "end": end},
        )
        return int(payload["port"])
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
