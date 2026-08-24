#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "web" / "backend"
RUNTIME = Path(os.environ.get("LEAN_RUNTIME_DIR", ROOT / "web" / "runtime"))
LOG_DIR = RUNTIME / "logs"

try:  # pragma: no cover - available only on the Windows deployment host.
    import servicemanager
    import win32event
    import win32service
    import win32serviceutil
except ImportError:  # pragma: no cover
    servicemanager = win32event = win32service = win32serviceutil = None


def _python(*, ml: bool = False) -> str:
    environment = ".venv-ml" if ml else ".venv"
    path = BACKEND / environment / "Scripts" / "python.exe"
    if not path.is_file():
        raise RuntimeError(f"python_environment_missing:{environment}")
    return str(path)


@dataclass(frozen=True)
class ChildSpec:
    name: str
    command: tuple[str, ...]
    cwd: Path = BACKEND
    env: dict[str, str] = field(default_factory=dict)


def platform_children() -> list[ChildSpec]:
    python = _python()
    children = [
        ChildSpec("api", (python, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000")),
        ChildSpec("beat", (python, "-m", "celery", "-A", "app.tasks.celery_app:celery_app", "beat", "--loglevel=INFO")),
    ]
    replicas = {
        "default": 1,
        "data-bulk": 1,
        "data-lineage": 1,
        "data-demand": max(1, int(os.environ.get("LEAN_WINDOWS_DATA_DEMAND_WORKERS", "2"))),
        "backtest": 1,
    }
    for queue, count in replicas.items():
        for index in range(1, count + 1):
            name = f"worker-{queue}-{index}"
            children.append(
                ChildSpec(
                    name,
                    (
                        python,
                        "-m",
                        "celery",
                        "-A",
                        "app.tasks.celery_app:celery_app",
                        "worker",
                        "--pool=solo",
                        "--concurrency=1",
                        "--prefetch-multiplier=1",
                        "--queues",
                        queue,
                        "--hostname",
                        f"{name}@%h",
                        "--loglevel=INFO",
                    ),
                )
            )
    if os.environ.get("LEAN_DEPLOYMENT_PROFILE", "core") in {"ml", "full"}:
        ml_python = _python(ml=True)
        children.extend(
            [
                ChildSpec(
                    "worker-ml-1",
                    (
                        ml_python, "-m", "celery", "-A", "app.tasks.celery_app:celery_app",
                        "worker", "--pool=solo", "--concurrency=1", "--prefetch-multiplier=1",
                        "--queues", "ml", "--hostname", "worker-ml-1@%h", "--loglevel=INFO",
                    ),
                ),
                ChildSpec(
                    "mlflow",
                    (
                        ml_python, "-m", "mlflow", "server", "--host", "127.0.0.1",
                        "--port", "5000", "--backend-store-uri",
                        os.environ["LEAN_MLFLOW_DATABASE_URL"], "--artifacts-destination",
                        str(RUNTIME / "mlartifacts"), "--serve-artifacts",
                    ),
                    cwd=ROOT,
                ),
            ]
        )
    return children


def runner_children() -> list[ChildSpec]:
    return [
        ChildSpec(
            "restricted-runner",
            (_python(), "-m", "uvicorn", "app.runner_service:app", "--host", "127.0.0.1", "--port", "8010"),
            env={"LEAN_RUNNER_URL": "", "LEAN_EXECUTION_BACKEND": "native", "LEAN_RESEARCH_BACKEND": "native"},
        )
    ]


class ChildSupervisor:
    def __init__(self, specs: list[ChildSpec]) -> None:
        self.specs = specs
        self.stop_event = threading.Event()
        self.processes: dict[str, subprocess.Popen[bytes]] = {}
        self.threads: list[threading.Thread] = []

    def _run_child(self, spec: ChildSpec) -> None:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        delay = 1.0
        while not self.stop_event.is_set():
            environment = dict(os.environ)
            environment.update(spec.env)
            environment["LEAN_DEPLOYMENT_MODE"] = "windows-native"
            environment["LEAN_EXECUTION_BACKEND"] = "native"
            environment["LEAN_RESEARCH_BACKEND"] = "native"
            environment["LEAN_STRICT_RUNTIME_V2"] = "1"
            if spec.name != "restricted-runner":
                environment.setdefault("LEAN_RUNNER_URL", "http://127.0.0.1:8010")
            log_path = LOG_DIR / f"{spec.name}.log"
            with log_path.open("ab") as log:
                process = subprocess.Popen(
                    list(spec.command),
                    cwd=spec.cwd,
                    env=environment,
                    stdin=subprocess.DEVNULL,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    creationflags=subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP,
                )
                self.processes[spec.name] = process
                while process.poll() is None and not self.stop_event.wait(0.5):
                    pass
                if process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(timeout=15)
                    except subprocess.TimeoutExpired:
                        process.kill()
            self.processes.pop(spec.name, None)
            if self.stop_event.is_set():
                break
            time.sleep(delay)
            delay = min(delay * 2, 30.0)

    def start(self) -> None:
        for spec in self.specs:
            thread = threading.Thread(target=self._run_child, args=(spec,), name=spec.name, daemon=True)
            thread.start()
            self.threads.append(thread)

    def stop(self) -> None:
        self.stop_event.set()
        for process in list(self.processes.values()):
            if process.poll() is None:
                process.terminate()
        for thread in self.threads:
            thread.join(timeout=20)


if win32serviceutil is not None:  # pragma: no branch
    class _BaseService(win32serviceutil.ServiceFramework):
        _children_factory: Any = staticmethod(list)

        def __init__(self, args):
            super().__init__(args)
            self.stop_handle = win32event.CreateEvent(None, 0, 0, None)
            self.supervisor = ChildSupervisor(self._children_factory())

        def SvcStop(self):
            self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
            self.supervisor.stop()
            win32event.SetEvent(self.stop_handle)

        def SvcDoRun(self):
            servicemanager.LogInfoMsg(f"{self._svc_name_} starting")
            self.supervisor.start()
            win32event.WaitForSingleObject(self.stop_handle, win32event.INFINITE)
            servicemanager.LogInfoMsg(f"{self._svc_name_} stopped")


    class LeanPlatformSupervisorService(_BaseService):
        _svc_name_ = "LeanPlatformSupervisor"
        _svc_display_name_ = "LEAN Platform Supervisor"
        _svc_description_ = "Supervises the LEAN API, Celery solo workers, beat, and MLflow."
        _children_factory = staticmethod(platform_children)


    class LeanRestrictedRunnerService(_BaseService):
        _svc_name_ = "LeanRestrictedRunner"
        _svc_display_name_ = "LEAN Restricted Runner"
        _svc_description_ = "Runs native LEAN and Research behind the loopback-only runner API."
        _children_factory = staticmethod(runner_children)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Install or control LEAN Windows services.")
    parser.add_argument("service", choices=("platform", "runner"))
    parser.add_argument("service_args", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    if os.name != "nt" or win32serviceutil is None:
        print("pywin32 is required on Windows.", file=sys.stderr)
        return 2
    service_class = (
        LeanPlatformSupervisorService if args.service == "platform" else LeanRestrictedRunnerService
    )
    sys.argv = [sys.argv[0], *args.service_args]
    win32serviceutil.HandleCommandLine(service_class)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
