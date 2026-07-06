from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

from ..core.config import ALGORITHM_PATH, DEFAULT_DOCKER_IMAGE, JOB_TIMEOUT_SECONDS
from ..lean_engine.config import base_config
from ..lean_engine.docker import docker_command
from ..lean_engine.reports import render_report
from ..lean_engine.results import extract_statistics
from ..services.ashare_execution import write_ashare_execution_artifacts
from .docker_runner import DockerRunner


class LeanRunner:
    def __init__(self, timeout_seconds: int = JOB_TIMEOUT_SECONDS):
        self.timeout_seconds = timeout_seconds

    @staticmethod
    def container_name_for(run_id: str) -> str:
        return f"lean-{run_id}"[:60]

    @staticmethod
    def _artifact_manifest(
        *,
        run_id: str,
        run_dir: Path,
        results_dir: Path,
        config_path: Path,
        exit_code: int,
        timed_out: bool,
        error: str | None,
        container_name: str,
    ) -> dict[str, Any]:
        def item(path: Path, kind: str) -> dict[str, Any]:
            return {
                "name": path.name,
                "kind": kind,
                "path": str(path),
                "relativePath": path.relative_to(run_dir).as_posix() if path.is_relative_to(run_dir) else path.name,
                "size": path.stat().st_size,
                "mtime": path.stat().st_mtime,
            }

        artifacts: list[dict[str, Any]] = []
        if config_path.exists():
            artifacts.append(item(config_path, "input-config"))
        for support_name in ("ashare_execution.py", "ashare_trade_status.json"):
            support_path = run_dir / support_name
            if support_path.exists():
                artifacts.append(item(support_path, "input-support"))
        if results_dir.exists():
            for path in sorted(child for child in results_dir.iterdir() if child.is_file()):
                artifacts.append(item(path, "lean-output"))
        return {
            "schemaVersion": 1,
            "runId": run_id,
            "containerName": container_name,
            "exitCode": exit_code,
            "timedOut": timed_out,
            "error": error,
            "artifacts": artifacts,
        }

    def run_backtest(
        self,
        run_id: str,
        parameters: dict[str, Any],
        run_dir: Path,
        output_callback: Callable[[str], None],
        docker_image: str = DEFAULT_DOCKER_IMAGE,
        algorithm_path: Path = ALGORITHM_PATH,
        algorithm_class: str = "DockerDemoAlgorithm",
        language: str = "Python",
        project_dir: Path | None = None,
    ) -> dict[str, Any]:
        results_dir = run_dir / "results"
        results_dir.mkdir(parents=True, exist_ok=True)
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
        container_name = self.container_name_for(run_id)
        output = DockerRunner(self.timeout_seconds).run(command, output_callback, container_name=container_name)

        result_json = results_dir / f"{run_id}.json"
        summary_json = results_dir / f"{run_id}-summary.json"
        report_html = results_dir / "report.html"
        if output.exit_code == 0 and result_json.exists():
            render_report(result_json, report_html)
        manifest_path = results_dir / "artifact-manifest.json"
        manifest_path.write_text(
            json.dumps(
                self._artifact_manifest(
                    run_id=run_id,
                    run_dir=run_dir,
                    results_dir=results_dir,
                    config_path=config_path,
                    exit_code=output.exit_code,
                    timed_out=output.timed_out,
                    error=output.error,
                    container_name=container_name,
                ),
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        return {
            "exit_code": output.exit_code,
            "timed_out": output.timed_out,
            "container_name": container_name,
            "work_dir": str(run_dir),
            "results_dir": str(results_dir),
            "result_json_path": str(result_json) if result_json.exists() else None,
            "summary_json_path": str(summary_json) if summary_json.exists() else None,
            "report_html_path": str(report_html) if report_html.exists() else None,
            "artifact_manifest_path": str(manifest_path),
            "statistics": extract_statistics(result_json, summary_json if summary_json.exists() else None)
            if result_json.exists()
            else {},
            "error": output.error,
        }
