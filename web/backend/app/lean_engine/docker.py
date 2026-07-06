from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

from ..core.config import (
    ALGORITHM_PATH,
    DATA_DIR,
    DEFAULT_DOCKER_IMAGE,
    HOST_DATA_DIR,
    HOST_PLATFORM_DIR,
    OBJECT_STORE_DIR,
    PLATFORM_DIR,
    REPO_ROOT,
)
from .config import base_config
from .errors import LeanPlatformError
from .reports import render_report
from .results import extract_statistics

def docker_command(
    config_path: Path,
    results_dir: Path,
    image: str = DEFAULT_DOCKER_IMAGE,
    algorithm_path: Path = ALGORITHM_PATH,
    algorithm_container_path: str = "/Lean/DockerDemoAlgorithm.py",
    project_dir: Path | None = None,
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

    command = [
        docker,
        "run",
        "--rm",
        "--name",
        f"lean-{config_path.parent.name}"[:60],
        "-v",
        f"{mount_source(config_path)}:/Lean/Launcher/bin/Debug/config.json:ro",
        "-v",
        f"{mount_source(DATA_DIR)}:/Lean/Data:ro",
        "-v",
        f"{mount_source(results_dir)}:/Lean/Results",
        "-v",
        f"{mount_source(OBJECT_STORE_DIR)}:/Lean/Launcher/bin/Debug/storage",
        image,
    ]
    if project_dir is not None:
        command[-1:-1] = ["-v", f"{mount_source(project_dir)}:/Lean/Project:ro"]
    else:
        command[-1:-1] = ["-v", f"{mount_source(algorithm_path)}:{algorithm_container_path}:ro"]
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
    algorithm_path: Path = ALGORITHM_PATH,
    algorithm_class: str = "DockerDemoAlgorithm",
    language: str = "Python",
    project_dir: Path | None = None,
) -> dict[str, Any]:
    results_dir = run_dir / "results"
    results_dir.mkdir(parents=True, exist_ok=True)
    if parameters.get("ashareRules"):
        from ..services.ashare_execution import write_ashare_execution_artifacts

        write_ashare_execution_artifacts(run_dir, parameters)
    config_path = run_dir / "config.json"
    algorithm_container_path = "/Lean/Project/main.py" if project_dir is not None else "/Lean/DockerDemoAlgorithm.py"
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
        algorithm_path=algorithm_path,
        algorithm_container_path=algorithm_container_path,
        project_dir=project_dir,
        support_dir=run_dir if parameters.get("ashareRules") else None,
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
