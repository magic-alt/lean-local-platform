from __future__ import annotations

import hashlib
import json
import os
import secrets
import signal
import socket
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from ..core.config import BACKEND_DIR, DATA_DIR, PARQUET_DIR, RESEARCH_DIR
from ..lean_engine.errors import LeanPlatformError
from .windows_sandbox import WindowsJobObject, WindowsSandboxVerifier


_WINDOWS_RESEARCH_JOBS: dict[str, WindowsJobObject] = {}


class NativeResearchBackend:
    """Workstation-only Jupyter lifecycle; never used by native production core."""

    name = "native"

    @staticmethod
    def _session_dir(session_id: str) -> Path:
        return RESEARCH_DIR / "sessions" / session_id

    @staticmethod
    def _python() -> Path:
        executable = "python.exe" if os.name == "nt" else "python"
        path = BACKEND_DIR / ".venv-research" / ("Scripts" if os.name == "nt" else "bin") / executable
        if not path.is_file():
            raise LeanPlatformError("native_research_environment_missing")
        return path

    @classmethod
    def _metadata(cls, session_id: str) -> dict[str, Any]:
        try:
            return json.loads((cls._session_dir(session_id) / "session.json").read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}

    @staticmethod
    def _running(pid: int) -> bool:
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False

    def start(
        self,
        session_id: str,
        project_dir: Path,
        port: int,
        output_callback: Callable[[str], None],
    ) -> dict[str, Any]:
        profile = os.environ.get("LEAN_DEPLOYMENT_PROFILE", "dev").strip().lower()
        if profile != "dev":
            if os.name != "nt":
                raise LeanPlatformError("native_research_workstation_only")
            status = WindowsSandboxVerifier().verify()
            if not status.ready:
                raise LeanPlatformError(status.detail)
        project = project_dir.resolve()
        if not project.is_dir():
            raise LeanPlatformError("native_research_project_missing")
        session_dir = self._session_dir(session_id)
        session_dir.mkdir(parents=True, exist_ok=False)
        token = secrets.token_urlsafe(32)
        credential = session_dir / "jupyter.token"
        credential.write_text(token, encoding="utf-8")
        credential.chmod(0o600)
        stdout_path = session_dir / "stdout.log"
        stderr_path = session_dir / "stderr.log"
        command = [
            str(self._python()),
            "-m",
            "jupyterlab",
            "--no-browser",
            "--ServerApp.ip=127.0.0.1",
            f"--ServerApp.port={port}",
            f"--ServerApp.root_dir={project}",
            f"--ServerApp.token={token}",
            "--ServerApp.allow_remote_access=False",
        ]
        safe_env = {
            key: os.environ[key]
            for key in ("PATH", "TZ", "SYSTEMROOT")
            if key in os.environ
        }
        safe_env.update(
            {
                "LEAN_DATA_DIR": str(DATA_DIR.resolve()),
                "LEAN_PARQUET_DIR": str(PARQUET_DIR.resolve()),
                "PYTHONDONTWRITEBYTECODE": "1",
            }
        )
        with stdout_path.open("ab") as stdout, stderr_path.open("ab") as stderr:
            process = subprocess.Popen(
                command,
                cwd=project,
                env=safe_env,
                stdin=subprocess.DEVNULL,
                stdout=stdout,
                stderr=stderr,
                start_new_session=os.name != "nt",
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0,
            )
        if os.name == "nt":
            try:
                job = WindowsJobObject(
                    memory_bytes=max(
                        512, int(os.environ.get("LEAN_WINDOWS_RESEARCH_MEMORY_MB", "4096"))
                    )
                    * 1024**2,
                    active_process_limit=max(
                        1, int(os.environ.get("LEAN_WINDOWS_RESEARCH_PROCESS_LIMIT", "16"))
                    ),
                )
                job.assign(int(process._handle))  # type: ignore[attr-defined]
                _WINDOWS_RESEARCH_JOBS[session_id] = job
            except Exception:
                process.kill()
                process.wait(timeout=10)
                raise LeanPlatformError("LEAN_RUNNER_UNSAFE:research_job_object")
        metadata = {
            "schemaVersion": 1,
            "sessionId": session_id,
            "executionBackend": "native",
            "executionId": f"native-research-{session_id}"[:80],
            "pid": process.pid,
            "startTime": datetime.now(timezone.utc).isoformat(),
            "runtimeId": hashlib.sha256(str(self._python()).encode("utf-8")).hexdigest(),
            "port": port,
            "tokenHash": hashlib.sha256(token.encode("utf-8")).hexdigest(),
            "project": str(project),
            "state": "starting",
        }
        (session_dir / "session.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise LeanPlatformError(f"native_research_exited:{process.returncode}")
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
                probe.settimeout(0.5)
                if probe.connect_ex(("127.0.0.1", port)) == 0:
                    metadata["state"] = "running"
                    (session_dir / "session.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
                    output_callback("Native Jupyter research session is ready on localhost.")
                    return {
                        "container_id": metadata["executionId"],
                        "executionBackend": "native",
                        "executionId": metadata["executionId"],
                        "runtimeIdentity": {
                            "backend": "native",
                            "runtimeId": metadata["runtimeId"],
                        },
                        "url": f"http://127.0.0.1:{port}/",
                        "container_status": "running",
                        "readiness_status": "ready",
                    }
            time.sleep(0.5)
        self.stop(session_id)
        raise LeanPlatformError("native_research_readiness_timeout")

    def stop(self, session_id: str) -> None:
        metadata = self._metadata(session_id)
        pid = int(metadata.get("pid") or 0)
        if pid and self._running(pid):
            if os.name == "nt":
                job = _WINDOWS_RESEARCH_JOBS.pop(session_id, None)
                if job is None:
                    raise LeanPlatformError("LEAN_RUNNER_UNSAFE:research_job_handle_missing")
                job.terminate()
                job.close()
            else:
                os.killpg(pid, signal.SIGTERM)
        if metadata:
            metadata["state"] = "stopped"
            (self._session_dir(session_id) / "session.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")

    def remove(self, session_id: str) -> None:
        self.stop(session_id)
        # Preserve logs and metadata for audit; mark the session removed.
        metadata = self._metadata(session_id)
        if metadata:
            metadata["state"] = "removed"
            (self._session_dir(session_id) / "session.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
        (self._session_dir(session_id) / "jupyter.token").unlink(missing_ok=True)

    def state(self, session_id: str) -> dict[str, Any]:
        metadata = self._metadata(session_id)
        if not metadata:
            return {"status": "missing", "running": False}
        running = self._running(int(metadata.get("pid") or 0))
        return {
            "status": "running" if running else str(metadata.get("state") or "stopped"),
            "running": running,
            "executionBackend": "native",
            "executionId": metadata.get("executionId"),
        }

    def logs(self, session_id: str, *, tail: int = 200) -> str:
        session_dir = self._session_dir(session_id)
        lines: list[str] = []
        for name in ("stdout.log", "stderr.log"):
            try:
                lines.extend((session_dir / name).read_text(encoding="utf-8", errors="replace").splitlines())
            except OSError:
                pass
        return "\n".join(lines[-max(1, min(tail, 2000)):])
