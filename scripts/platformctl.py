#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "web" / "backend"
FRONTEND = ROOT / "web" / "frontend"
RUNTIME = ROOT / "web" / "runtime"
DEPLOYMENT_STATE = RUNTIME / "deployment" / "state.json"
LOG_DIR = RUNTIME / "logs"

MODES = {"docker", "native"}
PROFILES = {"core", "ml", "observability", "full", "dev"}
DOCKER_PROFILE_SERVICES = {
    "core": ["mysql", "redis", "api", "worker", "data-worker", "data-lineage-worker", "data-demand-worker", "backtest-worker", "beat", "lean-runner"],
    "ml": ["mysql", "redis", "api", "worker", "data-worker", "data-lineage-worker", "data-demand-worker", "backtest-worker", "beat", "lean-runner", "mlflow-db-init", "mlflow", "ml-worker"],
    "observability": ["mysql", "redis", "api", "worker", "data-worker", "data-lineage-worker", "data-demand-worker", "backtest-worker", "beat", "lean-runner", "prometheus", "grafana"],
    "full": ["mysql", "redis", "clickhouse", "api", "worker", "data-worker", "data-lineage-worker", "data-demand-worker", "backtest-worker", "beat", "lean-runner", "mlflow-db-init", "mlflow", "ml-worker", "prometheus", "grafana"],
    "dev": ["mysql", "redis", "api", "worker", "backtest-worker", "lean-runner"],
}
NATIVE_QUEUES = ("default", "data-bulk", "data-lineage", "data-demand", "backtest")


class PlatformCtlError(RuntimeError):
    pass


@dataclass(frozen=True)
class Selection:
    mode: str
    profile: str


def _read_state() -> dict[str, Any]:
    try:
        payload = json.loads(DEPLOYMENT_STATE.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _write_state(payload: dict[str, Any]) -> None:
    DEPLOYMENT_STATE.parent.mkdir(parents=True, exist_ok=True)
    temporary = DEPLOYMENT_STATE.with_suffix(".tmp")
    temporary.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    temporary.replace(DEPLOYMENT_STATE)


def resolve_selection(mode: str | None, profile: str | None) -> Selection:
    state = _read_state()
    configured_mode = os.environ.get("LEAN_DEPLOYMENT_MODE", "").strip().lower()
    persisted_mode = str(state.get("mode") or "").strip().lower()
    requested = (mode or "").strip().lower()
    if requested == "auto":
        candidates = {value for value in (configured_mode, persisted_mode) if value}
        if len(candidates) != 1:
            raise PlatformCtlError("auto_mode_ambiguous: configure or persist exactly one deployment mode")
        selected_mode = candidates.pop()
    else:
        selected_mode = requested or configured_mode or persisted_mode
    if selected_mode not in MODES:
        raise PlatformCtlError("deployment_mode_required: use --mode docker or --mode native")
    configured_profile = os.environ.get("LEAN_DEPLOYMENT_PROFILE", "").strip().lower()
    selected_profile = (profile or configured_profile or str(state.get("profile") or "")).strip().lower()
    if not selected_profile:
        selected_profile = "full" if selected_mode == "docker" else "core"
    if selected_profile not in PROFILES:
        raise PlatformCtlError("deployment_profile_invalid")
    return Selection(selected_mode, selected_profile)


def _python(ml: bool = False) -> Path:
    name = ".venv-ml" if ml else ".venv"
    executable = "python.exe" if os.name == "nt" else "python"
    path = BACKEND / name / ("Scripts" if os.name == "nt" else "bin") / executable
    if not path.is_file():
        raise PlatformCtlError(f"python_environment_missing:{name}")
    return path


def _run(command: list[str], *, cwd: Path = ROOT, env: dict[str, str] | None = None) -> int:
    return subprocess.run(command, cwd=cwd, env=env, check=False).returncode


def _tcp_ready(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=1):
            return True
    except OSError:
        return False


def _http_ready(url: str, *, token_file: Path | None = None) -> bool:
    headers: dict[str, str] = {}
    if token_file is not None:
        try:
            token = token_file.read_text(encoding="utf-8").strip()
        except OSError:
            token = ""
        if token:
            headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=2) as response:
            return response.status < 500
    except (OSError, urllib.error.URLError):
        return False


def doctor(selection: Selection) -> int:
    required_commands = ["node", "npm"]
    if selection.mode == "docker":
        required_commands.append("docker")
    else:
        required_commands.extend(["dotnet"])
        if selection.profile != "dev" and sys.platform.startswith("linux"):
            required_commands.append("bwrap")
    checks: list[tuple[str, bool, str]] = []
    for name in required_commands:
        checks.append((name, shutil.which(name) is not None, "command"))
    checks.extend(
        [
            ("mysql", _tcp_ready(os.environ.get("LEAN_MYSQL_HOST", "127.0.0.1"), int(os.environ.get("LEAN_MYSQL_PORT", "3306"))), "tcp"),
            ("redis", _tcp_ready("127.0.0.1", int(os.environ.get("LEAN_REDIS_PORT", "6379"))), "tcp"),
        ]
    )
    if selection.mode == "native":
        sys.path.insert(0, str(BACKEND))
        try:
            from app.runners.runtime_registry import RuntimeRegistry

            RuntimeRegistry().resolve()
            runtime_ready = True
        except Exception:
            runtime_ready = False
        checks.append(("lean-runtime", runtime_ready, "pinned/signed"))
    print(f"Deployment: {selection.mode} ({selection.profile})")
    for name, ready, detail in checks:
        print(f"{name:<18} {'READY' if ready else 'MISSING':<8} {detail}")
    return 0 if all(item[1] for item in checks) else 2


def bootstrap(selection: Selection, *, install_deps: bool, build_frontend: bool) -> int:
    if selection.mode != "native":
        raise PlatformCtlError("bootstrap_is_native_only")
    RUNTIME.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    if not (BACKEND / ".venv").exists():
        code = _run([sys.executable, "-m", "venv", str(BACKEND / ".venv")])
        if code:
            return code
    if install_deps:
        code = _run([str(_python()), "-m", "pip", "install", "-r", str(BACKEND / "requirements.txt")])
        if code:
            return code
        if selection.profile in {"ml", "full"}:
            if not (BACKEND / ".venv-ml").exists():
                code = _run([sys.executable, "-m", "venv", str(BACKEND / ".venv-ml")])
                if code:
                    return code
            code = _run([str(_python(ml=True)), "-m", "pip", "install", "-r", str(BACKEND / "requirements-ml.txt")])
            if code:
                return code
        if selection.profile == "dev":
            research_venv = BACKEND / ".venv-research"
            if not research_venv.exists():
                code = _run([sys.executable, "-m", "venv", str(research_venv)])
                if code:
                    return code
            research_python = research_venv / ("Scripts" if os.name == "nt" else "bin") / (
                "python.exe" if os.name == "nt" else "python"
            )
            code = _run(
                [
                    str(research_python),
                    "-m",
                    "pip",
                    "install",
                    "-r",
                    str(BACKEND / "requirements-research.txt"),
                ]
            )
            if code:
                return code
    if build_frontend:
        if shutil.which("npm") is None:
            raise PlatformCtlError("npm_command_missing")
        code = _run(["npm", "ci"], cwd=FRONTEND)
        if code:
            return code
        code = _run(["npm", "run", "build"], cwd=FRONTEND)
        if code:
            return code
    print("Native user-space bootstrap complete. System packages and services were not modified.")
    return 0


def _native_commands(selection: Selection) -> list[tuple[str, list[str], Path, bool]]:
    python = str(_python())
    commands: list[tuple[str, list[str], Path, bool]] = [
        ("api", [python, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000"], BACKEND, False),
        ("runner", [python, "-m", "uvicorn", "app.runner_service:app", "--host", "127.0.0.1", "--port", "8010"], BACKEND, False),
    ]
    for queue in NATIVE_QUEUES:
        commands.append(
            (
                f"worker-{queue}",
                [python, "-m", "celery", "-A", "app.tasks.celery_app:celery_app", "worker", "-Q", queue, "-n", f"{queue}@%h", "--loglevel=INFO"],
                BACKEND,
                False,
            )
        )
    commands.append(("beat", [python, "-m", "celery", "-A", "app.tasks.celery_app:celery_app", "beat", "--loglevel=INFO"], BACKEND, False))
    if selection.profile in {"ml", "full"}:
        ml_python = str(_python(ml=True))
        commands.append(
            ("worker-ml", [ml_python, "-m", "celery", "-A", "app.tasks.celery_app:celery_app", "worker", "-Q", "ml", "-n", "ml@%h", "--loglevel=INFO"], BACKEND, True)
        )
        commands.append(("mlflow", [ml_python, "-m", "mlflow", "server", "--host", "127.0.0.1", "--port", "5000"], ROOT, True))
    if selection.profile == "dev":
        commands.append(("vite", ["npm", "run", "dev", "--", "--host", "127.0.0.1"], FRONTEND, False))
    return commands


def start(selection: Selection) -> int:
    if selection.mode == "docker":
        command = ["docker", "compose", "--profile", "app", "up", "-d", "--build", *DOCKER_PROFILE_SERVICES[selection.profile]]
        compose_env = dict(os.environ)
        compose_env["LEAN_DEPLOYMENT_PROFILE"] = selection.profile
        compose_env["CLICKHOUSE_ENABLED"] = "1" if selection.profile == "full" else "0"
        compose_env["LEAN_MYSQL_ADDITIONAL_BACKUP_DATABASES"] = "lean_mlflow" if selection.profile in {"ml", "full"} else ""
        code = _run(command, env=compose_env)
        if code == 0:
            _write_state({"schemaVersion": 1, "mode": selection.mode, "profile": selection.profile, "manager": "compose"})
        return code
    if sys.platform.startswith("linux") and shutil.which("systemctl") and os.environ.get("LEAN_NATIVE_MANAGER", "").lower() == "systemd":
        code = _run(["systemctl", "start", "lean-platform.target"])
        if code == 0:
            _write_state({"schemaVersion": 1, "mode": selection.mode, "profile": selection.profile, "manager": "systemd"})
        return code
    previous = _read_state()
    if previous.get("processes"):
        raise PlatformCtlError("native_processes_already_recorded: run stop or status")
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    processes: list[dict[str, Any]] = []
    child_env = dict(os.environ)
    child_env["LEAN_DEPLOYMENT_MODE"] = "native"
    child_env.setdefault("LEAN_EXECUTION_BACKEND", "native")
    child_env["LEAN_DEPLOYMENT_PROFILE"] = selection.profile
    child_env.setdefault("CLICKHOUSE_ENABLED", "0" if selection.profile in {"core", "dev", "ml"} else "1")
    for name, command, cwd, _ in _native_commands(selection):
        log_path = LOG_DIR / f"{name}.log"
        log_handle = log_path.open("ab")
        try:
            process = subprocess.Popen(
                command,
                cwd=cwd,
                env=child_env,
                stdin=subprocess.DEVNULL,
                stdout=log_handle,
                stderr=subprocess.STDOUT,
                start_new_session=os.name != "nt",
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0,
            )
        finally:
            log_handle.close()
        processes.append({"name": name, "pid": process.pid, "log": str(log_path)})
    _write_state(
        {
            "schemaVersion": 1,
            "mode": selection.mode,
            "profile": selection.profile,
            "manager": "local",
            "startedAt": int(time.time()),
            "processes": processes,
        }
    )
    print(f"Started {len(processes)} native processes.")
    return 0


def _pid_running(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def stop(selection: Selection) -> int:
    state = _read_state()
    manager = state.get("manager")
    if selection.mode == "docker" or manager == "compose":
        return _run(["docker", "compose", "stop", *DOCKER_PROFILE_SERVICES[selection.profile]])
    if manager == "systemd":
        return _run(["systemctl", "stop", "lean-platform.target"])
    processes = state.get("processes") or []
    for item in reversed(processes):
        pid = int(item["pid"])
        if _pid_running(pid):
            os.kill(pid, signal.SIGTERM)
    _write_state({"schemaVersion": 1, "mode": selection.mode, "profile": selection.profile, "manager": "local", "processes": []})
    print(f"Stopped {len(processes)} recorded native processes.")
    return 0


def status(selection: Selection) -> int:
    state = _read_state()
    print(f"Deployment: {selection.mode} ({selection.profile})")
    if selection.mode == "docker":
        return _run(["docker", "compose", "ps", *DOCKER_PROFILE_SERVICES[selection.profile]])
    manager = state.get("manager")
    if manager == "systemd":
        return _run(["systemctl", "--no-pager", "status", "lean-platform.target"])
    failed = False
    for item in state.get("processes") or []:
        ready = _pid_running(int(item["pid"]))
        failed = failed or not ready
        print(f"{item['name']:<24} {'RUNNING' if ready else 'STOPPED'}")
    runner_ready = _http_ready(
        "http://127.0.0.1:8010/health",
        token_file=RUNTIME / "secrets" / "runner_token",
    )
    print(f"{'runner-health':<24} {'READY' if runner_ready else 'NOT_READY'}")
    return 2 if failed or not runner_ready else 0


def logs(selection: Selection, service: str | None) -> int:
    if selection.mode == "docker":
        command = ["docker", "compose", "logs", "--tail", "200"]
        if service:
            command.append(service)
        return _run(command)
    state = _read_state()
    selected = [item for item in state.get("processes") or [] if not service or item["name"] == service]
    if not selected:
        raise PlatformCtlError("service_log_not_found")
    for item in selected:
        print(f"== {item['name']} ==")
        try:
            lines = Path(item["log"]).read_text(encoding="utf-8", errors="replace").splitlines()[-200:]
        except OSError:
            lines = []
        print("\n".join(lines))
    return 0


def install_system() -> int:
    if not sys.platform.startswith("linux"):
        raise PlatformCtlError("system_install_supported_on_linux_only")
    source = ROOT / "deploy" / "native" / "systemd"
    destination = Path("/etc/systemd/system")
    for unit in source.glob("lean-platform*"):
        shutil.copy2(unit, destination / unit.name)
    return _run(["systemctl", "daemon-reload"])


def database_command(command: str) -> int:
    if command == "init":
        code = _run([str(_python()), str(ROOT / "scripts" / "init_native_database.py")], cwd=ROOT)
        if code:
            return code
        return _run([str(_python()), str(ROOT / "scripts" / "db_migrate.py"), "apply"], cwd=ROOT)
    if command == "migrate":
        return _run([str(_python()), str(ROOT / "scripts" / "db_migrate.py"), "apply"], cwd=ROOT)
    raise PlatformCtlError("database_command_invalid")


def backup(output: str | None) -> int:
    sys.path.insert(0, str(BACKEND))
    from app.services.mysql_backup import create_backup

    result = create_backup(Path(output).resolve() if output else None)
    print(json.dumps({key: value for key, value in result.items() if key not in {"databases"}}, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="platform", description="Docker/native platform lifecycle controller")
    parser.add_argument("--mode", choices=("docker", "native", "auto"))
    parser.add_argument("--profile", choices=tuple(sorted(PROFILES)))
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("doctor")
    bootstrap_parser = sub.add_parser("bootstrap")
    bootstrap_parser.add_argument("--install-deps", action="store_true")
    bootstrap_parser.add_argument("--skip-frontend", action="store_true")
    install_parser = sub.add_parser("install")
    install_parser.add_argument("--system", action="store_true", required=True)
    sub.add_parser("start")
    sub.add_parser("stop")
    sub.add_parser("restart")
    sub.add_parser("status")
    logs_parser = sub.add_parser("logs")
    logs_parser.add_argument("service", nargs="?")
    db_parser = sub.add_parser("db")
    db_parser.add_argument("action", choices=("init", "migrate"))
    backup_parser = sub.add_parser("backup")
    backup_parser.add_argument("--output")
    restore_parser = sub.add_parser("restore")
    restore_parser.add_argument("--backup", required=True)
    restore_parser.add_argument("--source-database", default="lean_market")
    restore_parser.add_argument("--target-database", required=True)
    restore_parser.add_argument("--confirm", required=True)
    runtime_parser = sub.add_parser("runtime")
    runtime_parser.add_argument("action", choices=("install", "status"))
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        selection = resolve_selection(args.mode, args.profile)
        if args.command == "doctor":
            return doctor(selection)
        if args.command == "bootstrap":
            return bootstrap(selection, install_deps=args.install_deps, build_frontend=not args.skip_frontend)
        if args.command == "install":
            return install_system()
        if args.command == "start":
            return start(selection)
        if args.command == "stop":
            return stop(selection)
        if args.command == "restart":
            code = stop(selection)
            return code or start(selection)
        if args.command == "status":
            return status(selection)
        if args.command == "logs":
            return logs(selection, args.service)
        if args.command == "db":
            return database_command(args.action)
        if args.command == "backup":
            return backup(args.output)
        if args.command == "restore":
            return _run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "restore_mysql.py"),
                    "--backup",
                    args.backup,
                    "--source-database",
                    args.source_database,
                    "--target-database",
                    args.target_database,
                    "--confirm",
                    args.confirm,
                ]
            )
        if args.command == "runtime":
            command = [sys.executable, str(ROOT / "scripts" / "install_lean_runtime.py"), args.action]
            return _run(command)
        raise PlatformCtlError("command_not_implemented")
    except PlatformCtlError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
