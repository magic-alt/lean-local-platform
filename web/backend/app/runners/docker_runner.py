from __future__ import annotations

import selectors
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from ..core.config import REPO_ROOT
from ..lean_engine.errors import LeanPlatformError


@dataclass
class DockerRunResult:
    exit_code: int
    timed_out: bool = False
    error: str | None = None


class DockerRunner:
    def __init__(self, timeout_seconds: int | None = None):
        self.timeout_seconds = timeout_seconds

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
