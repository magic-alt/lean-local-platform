from __future__ import annotations

import os
import queue
import signal
import subprocess
import threading
import time
from pathlib import Path
from typing import Callable

from .base import ExecutionResult
from .windows_sandbox import WindowsJobObject


class ProcessRunner:
    def __init__(self, timeout_seconds: int | None = None):
        self.timeout_seconds = timeout_seconds
        self._processes: dict[str, subprocess.Popen[str]] = {}
        self._jobs: dict[str, WindowsJobObject] = {}

    @staticmethod
    def _stop_process(process: subprocess.Popen[str]) -> None:
        if process.poll() is not None:
            return
        if os.name == "nt":
            process.terminate()
        else:
            os.killpg(process.pid, signal.SIGTERM)
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            if os.name == "nt":
                process.kill()
            else:
                os.killpg(process.pid, signal.SIGKILL)

    def stop(self, execution_id: str) -> bool:
        process = self._processes.get(execution_id)
        if process is None:
            return False
        job = self._jobs.get(execution_id)
        if job is not None:
            job.terminate()
        else:
            self._stop_process(process)
        return True

    def run(
        self,
        command: list[str],
        output_callback: Callable[[str], None],
        *,
        execution_id: str,
        cwd: Path,
        env: dict[str, str] | None = None,
    ) -> ExecutionResult:
        output_callback("running native LEAN launcher")
        creationflags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
        process = subprocess.Popen(
            command,
            cwd=cwd,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            start_new_session=os.name != "nt",
            creationflags=creationflags,
        )
        job: WindowsJobObject | None = None
        if os.name == "nt":
            try:
                memory_mb = max(256, int(os.environ.get("LEAN_WINDOWS_JOB_MEMORY_MB", "4096")))
                process_limit = max(1, int(os.environ.get("LEAN_WINDOWS_JOB_PROCESS_LIMIT", "8")))
                job = WindowsJobObject(
                    memory_bytes=memory_mb * 1024**2,
                    active_process_limit=process_limit,
                )
                job.assign(int(process._handle))  # type: ignore[attr-defined]
                self._jobs[execution_id] = job
            except Exception:
                process.kill()
                process.wait(timeout=10)
                raise
        self._processes[execution_id] = process
        assert process.stdout is not None
        output_queue: queue.Queue[str | None] = queue.Queue()

        def read_output() -> None:
            assert process.stdout is not None
            for line in process.stdout:
                output_queue.put(line.rstrip())
            output_queue.put(None)

        reader = threading.Thread(target=read_output, name=f"native-output-{execution_id}", daemon=True)
        reader.start()
        started = time.monotonic()
        timed_out = False
        try:
            while True:
                if self.timeout_seconds and time.monotonic() - started > self.timeout_seconds:
                    timed_out = True
                    output_callback(f"Backtest timed out after {self.timeout_seconds} seconds.")
                    self._stop_process(process)
                    break
                try:
                    line = output_queue.get(timeout=0.5)
                except queue.Empty:
                    line = ""
                if line is None:
                    break
                if line:
                    output_callback(line)
        finally:
            reader.join(timeout=2)
            process.stdout.close()
            self._processes.pop(execution_id, None)
            active_job = self._jobs.pop(execution_id, None)
            if active_job is not None:
                active_job.close()
        exit_code = process.wait()
        return ExecutionResult(
            exit_code=exit_code,
            timed_out=timed_out,
            backend="native",
            execution_id=execution_id,
            error="Backtest timed out." if timed_out else None,
        )
