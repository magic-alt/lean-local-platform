from __future__ import annotations

import json
import os
import selectors
import shutil
import subprocess
import time
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from ..core.config import REPO_ROOT
from ..core.request_context import current_trace_id, current_workflow_id
from ..lean_engine.errors import LeanPlatformError


@dataclass
class DockerRunResult:
    exit_code: int
    timed_out: bool = False
    error: str | None = None


class DockerRunner:
    def __init__(self, timeout_seconds: int | None = None, *, allow_remote: bool = True):
        self.timeout_seconds = timeout_seconds
        self.allow_remote = allow_remote

    @staticmethod
    def _runner_token() -> str:
        configured = os.environ.get("LEAN_RUNNER_TOKEN", "").strip()
        if configured:
            return configured
        token_path = Path(
            os.environ.get(
                "LEAN_RUNNER_TOKEN_FILE",
                "/workspace/web/runtime/secrets/runner_token",
            )
        )
        try:
            return token_path.read_text(encoding="utf-8").strip()
        except OSError:
            return ""

    def _run_remote(
        self,
        command: list[str],
        output_callback: Callable[[str], None],
        *,
        container_name: str,
    ) -> DockerRunResult:
        runner_url = os.environ.get("LEAN_RUNNER_URL", "").strip().rstrip("/")
        token = self._runner_token()
        if not runner_url or not token:
            raise LeanPlatformError("restricted_runner_not_configured")
        mounts: dict[str, str] = {}
        for index, value in enumerate(command):
            if value != "-v" or index + 1 >= len(command):
                continue
            raw = command[index + 1]
            parts = raw.rsplit(":", 2)
            if len(parts) == 3 and parts[-1] in {"ro", "rw"}:
                source, target = parts[0], parts[1]
            elif len(parts) >= 2:
                source, target = ":".join(parts[:-1]), parts[-1]
            else:
                continue
            mounts[target] = source
        required_targets = {
            "/Lean/Launcher/bin/Debug/config.json",
            "/Lean/Data",
            "/Lean/Results",
            "/Lean/Launcher/bin/Debug/storage",
            "/Lean/Project",
        }
        if not required_targets.issubset(mounts):
            raise LeanPlatformError("restricted_runner_structured_mounts_incomplete")
        payload_item = {
            "runId": container_name.removeprefix("lean-"),
            "image": command[-1],
            "configPath": mounts["/Lean/Launcher/bin/Debug/config.json"],
            "dataDir": mounts["/Lean/Data"],
            "resultsDir": mounts["/Lean/Results"],
            "storageDir": mounts["/Lean/Launcher/bin/Debug/storage"],
            "projectDir": mounts["/Lean/Project"],
            "timeoutSeconds": int(self.timeout_seconds or 3600),
            "traceId": current_trace_id(),
            "workflowId": current_workflow_id(),
        }
        if "/Lean/Run" in mounts:
            payload_item["supportDir"] = mounts["/Lean/Run"]
        payload = json.dumps(payload_item).encode("utf-8")
        request = urllib.request.Request(
            runner_url + "/v1/jobs/run",
            data=payload,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with urllib.request.urlopen(
            request,
            timeout=max(60, int(self.timeout_seconds or 3600) + 30),
        ) as response:
            body = json.loads(response.read().decode("utf-8"))
        for line in body.get("output") or []:
            output_callback(str(line))
        return DockerRunResult(
            exit_code=int(body.get("exitCode") or 0),
            timed_out=bool(body.get("timedOut")),
            error=body.get("error"),
        )

    @staticmethod
    def docker_path() -> str:
        docker = shutil.which("docker")
        if not docker:
            raise LeanPlatformError("Docker command not found. Start Docker Desktop and verify `docker info` works.")
        return docker

    @classmethod
    def stop_container(cls, container_name: str, output_callback: Callable[[str], None] | None = None) -> None:
        docker = cls.docker_path()
        completed = subprocess.run(
            [docker, "stop", container_name],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        if output_callback:
            detail = completed.stdout.strip() or completed.stderr.strip()
            output_callback(f"docker stop {container_name}: {detail or completed.returncode}")

    def run(
        self,
        command: list[str],
        output_callback: Callable[[str], None],
        cwd: Path = REPO_ROOT,
        container_name: str | None = None,
    ) -> DockerRunResult:
        if self.allow_remote and os.environ.get("LEAN_RUNNER_URL", "").strip():
            if not container_name:
                raise LeanPlatformError("restricted_runner_container_name_required")
            return self._run_remote(command, output_callback, container_name=container_name)
        self.docker_path()
        output_callback("running: " + " ".join(command))
        start = time.monotonic()
        process = subprocess.Popen(
            command,
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        assert process.stdout is not None
        selector = selectors.DefaultSelector()
        selector.register(process.stdout, selectors.EVENT_READ)
        timed_out = False
        try:
            while True:
                if self.timeout_seconds and time.monotonic() - start > self.timeout_seconds:
                    timed_out = True
                    output_callback(f"Backtest timed out after {self.timeout_seconds} seconds.")
                    if container_name:
                        self.stop_container(container_name, output_callback)
                    process.kill()
                    break
                for key, _ in selector.select(timeout=0.5):
                    line = key.fileobj.readline()
                    if line:
                        output_callback(line.rstrip())
                if process.poll() is not None:
                    for line in process.stdout:
                        output_callback(line.rstrip())
                    break
        finally:
            selector.close()
            process.stdout.close()
        exit_code = process.wait()
        if timed_out:
            return DockerRunResult(exit_code=exit_code if exit_code is not None else -1, timed_out=True, error="Backtest timed out.")
        return DockerRunResult(exit_code=exit_code)
