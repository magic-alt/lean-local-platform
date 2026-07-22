from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

from ..core.config import (
    ALLOWED_LEAN_DOCKER_IMAGES,
    DATA_DIR,
    DEFAULT_DOCKER_IMAGE,
    HOST_DATA_DIR,
    HOST_PLATFORM_DIR,
    LEAN_DOCKER_CPUS,
    LEAN_DOCKER_MEMORY,
    LEAN_DOCKER_NETWORK,
    LEAN_DOCKER_PIDS_LIMIT,
    LEAN_DOCKER_READ_ONLY,
    PLATFORM_DIR,
    REPO_ROOT,
)
from .config import base_config
from .errors import LeanPlatformError
from .reports import render_report
from .results import extract_statistics


def validate_lean_docker_image(image: str) -> str:
    normalized = str(image or "").strip()
    if normalized not in ALLOWED_LEAN_DOCKER_IMAGES:
        raise LeanPlatformError("docker_image_not_allowed: Select a digest-pinned image from the operator allowlist.")
    if "@sha256:" not in normalized:
        raise LeanPlatformError("docker_image_not_pinned: LEAN images must use an immutable sha256 digest.")
    return normalized

def docker_command(
    config_path: Path,
    results_dir: Path,
    image: str = DEFAULT_DOCKER_IMAGE,
    *,
    project_dir: Path,
    support_dir: Path | None = None,
) -> list[str]:
    docker = shutil.which("docker")
    if not docker:
        raise LeanPlatformError("docker command not found.")
    def mount_source(path: Path) -> str:
        resolved = Path(path)
        data_mount_root = HOST_DATA_DIR if os.environ.get("LEAN_HOST_DATA_DIR") else DATA_DIR
        platform_mount_root = HOST_PLATFORM_DIR if os.environ.get("LEAN_HOST_PLATFORM_DIR") else PLATFORM_DIR
        try:
            relative = resolved.relative_to(DATA_DIR)
            return str(data_mount_root / relative)
        except ValueError:
            pass
        try:
            relative = resolved.relative_to(PLATFORM_DIR)
            return str(platform_mount_root / relative)
        except ValueError:
            return str(resolved)

    image = validate_lean_docker_image(image)
    storage_dir = results_dir / "object-store"
    storage_dir.mkdir(parents=True, exist_ok=True)
    command = [
        docker,
        "run",
        "--rm",
        "--name",
        f"lean-{config_path.parent.name}"[:60],
        "--network",
        LEAN_DOCKER_NETWORK,
        "--cpus",
        LEAN_DOCKER_CPUS,
        "--memory",
        LEAN_DOCKER_MEMORY,
        "--pids-limit",
        str(LEAN_DOCKER_PIDS_LIMIT),
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges:true",
        "-e",
        "PYTHONDONTWRITEBYTECODE=1",
        "--tmpfs",
        "/tmp:rw,noexec,nosuid,size=256m",
        "-v",
        f"{mount_source(config_path)}:/Lean/Launcher/bin/Debug/config.json:ro",
        "-v",
        f"{mount_source(DATA_DIR)}:/Lean/Data:ro",
        "-v",
        f"{mount_source(results_dir)}:/Lean/Results",
        "-v",
        f"{mount_source(storage_dir)}:/Lean/Launcher/bin/Debug/storage",
        image,
    ]
    if LEAN_DOCKER_READ_ONLY:
        command[5:5] = ["--read-only"]
    command[-1:-1] = ["-v", f"{mount_source(project_dir)}:/Lean/Project:ro"]
    if support_dir is not None:
        command[-1:-1] = ["-v", f"{mount_source(support_dir)}:/Lean/Run:ro"]
    return command

def run_command_stream(command: list[str], output_callback, cwd: Path = REPO_ROOT) -> int:
    output_callback("running: " + " ".join(command))
    process = subprocess.Popen(
        command,
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    assert process.stdout is not None
    for line in process.stdout:
        output_callback(line.rstrip())
    return process.wait()


def run_docker_backtest(
    run_id: str,
    parameters: dict[str, Any],
    docker_image: str,
    run_dir: Path,
    output_callback,
    *,
    algorithm_path: Path,
    algorithm_class: str,
    language: str,
    project_dir: Path,
) -> dict[str, Any]:
    results_dir = run_dir / "results"
    results_dir.mkdir(parents=True, exist_ok=True)
    if parameters.get("ashareRules"):
        from ..services.ashare_execution import write_ashare_execution_artifacts

        write_ashare_execution_artifacts(run_dir, parameters)
    if parameters.get("hkRules"):
        from ..services.hk_execution import write_hk_execution_artifacts

        write_hk_execution_artifacts(run_dir, parameters)
    config_path = run_dir / "config.json"
    project_dir = project_dir.resolve()
    algorithm_path = algorithm_path.resolve()
    try:
        relative_algorithm_path = algorithm_path.relative_to(project_dir)
    except ValueError as exc:
        raise LeanPlatformError("Project algorithm must be located inside the project directory.") from exc
    if not algorithm_path.is_file():
        raise LeanPlatformError(f"Project algorithm not found: {algorithm_path}")
    algorithm_container_path = f"/Lean/Project/{relative_algorithm_path.as_posix()}"
    config_path.write_text(
        json.dumps(
            base_config(
                run_id,
                parameters,
                algorithm_class=algorithm_class,
                algorithm_location=algorithm_container_path,
                language=language,
            ),
            indent=2,
        ),
        encoding="utf-8",
    )

    command = docker_command(
        config_path,
        results_dir,
        docker_image,
        project_dir=project_dir,
        support_dir=run_dir if parameters.get("ashareRules") or parameters.get("hkRules") else None,
    )
    exit_code = run_command_stream(command, output_callback)

    result_json = results_dir / f"{run_id}.json"
    summary_json = results_dir / f"{run_id}-summary.json"
    report_html = results_dir / "report.html"
    if exit_code == 0 and result_json.exists():
        render_report(result_json, report_html)

    return {
        "exit_code": exit_code,
        "result_json_path": str(result_json) if result_json.exists() else None,
        "summary_json_path": str(summary_json) if summary_json.exists() else None,
        "report_html_path": str(report_html) if report_html.exists() else None,
        "statistics": extract_statistics(result_json, summary_json if summary_json.exists() else None)
        if result_json.exists()
        else {},
    }
