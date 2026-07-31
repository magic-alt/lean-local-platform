from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from ..core.config import DEFAULT_DOCKER_IMAGE, JOB_TIMEOUT_SECONDS
from ..core.request_context import current_trace_id, current_workflow_id
from ..lean_engine.config import base_config
from ..lean_engine.docker import docker_command
from ..lean_engine.errors import LeanPlatformError
from ..lean_engine.reports import render_report
from ..lean_engine.results import extract_statistics
from ..lean_engine.screening import extract_screening_report
from ..lean_engine.trend_pullback import extract_trend_pullback_report
from ..services.ashare_execution import write_ashare_execution_artifacts
from ..services.hk_execution import write_hk_execution_artifacts
from ..services.screening_results import enrich_screening_file
from .docker_runner import DockerRunResult, DockerRunner


@dataclass(frozen=True)
class BacktestWorkspace:
    run_id: str
    run_dir: Path
    results_dir: Path
    config_path: Path
    stdout_path: Path
    command: list[str]
    container_name: str
    algorithm_container_path: str


@dataclass(frozen=True)
class LeanArtifacts:
    result_json: Path
    summary_json: Path
    report_html: Path
    manifest_path: Path


@dataclass(frozen=True)
class LeanExecutionResult:
    docker: DockerRunResult
    artifacts: LeanArtifacts
    container_name: str
    work_dir: Path
    results_dir: Path


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
        for support_name in (
            "ashare_execution.py",
            "ashare_trade_status.json",
            "ashare-trend-pullback-input.json.gz",
            "hk_execution.py",
            "trace-context.json",
        ):
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
            "traceId": current_trace_id(),
            "workflowId": current_workflow_id(),
            "artifacts": artifacts,
        }

    def prepare(
        self,
        run_id: str,
        parameters: dict[str, Any],
        run_dir: Path,
        *,
        docker_image: str = DEFAULT_DOCKER_IMAGE,
        algorithm_path: Path,
        algorithm_class: str,
        language: str,
        project_dir: Path,
    ) -> BacktestWorkspace:
        results_dir = run_dir / "results"
        results_dir.mkdir(parents=True, exist_ok=True)
        write_ashare_execution_artifacts(run_dir, parameters)
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
        config = base_config(
            run_id,
            parameters,
            algorithm_class=algorithm_class,
            algorithm_location=algorithm_container_path,
            language=language,
        )
        config["lean-platform-trace-id"] = current_trace_id()
        config["lean-platform-workflow-id"] = current_workflow_id()
        config_path.write_text(
            json.dumps(config, indent=2),
            encoding="utf-8",
        )
        (run_dir / "trace-context.json").write_text(
            json.dumps(
                {
                    "schemaVersion": 1,
                    "runId": run_id,
                    "traceId": current_trace_id(),
                    "workflowId": current_workflow_id(),
                },
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
        return BacktestWorkspace(
            run_id=run_id,
            run_dir=run_dir,
            results_dir=results_dir,
            config_path=config_path,
            stdout_path=results_dir / "stdout.log",
            command=command,
            container_name=self.container_name_for(run_id),
            algorithm_container_path=algorithm_container_path,
        )

    def run(self, workspace: BacktestWorkspace, output_callback: Callable[[str], None]) -> DockerRunResult:
        workspace.stdout_path.parent.mkdir(parents=True, exist_ok=True)
        with workspace.stdout_path.open("a", encoding="utf-8") as stdout_file:
            def tee_output(line: str) -> None:
                stdout_file.write(line + "\n")
                stdout_file.flush()
                output_callback(line)

            return DockerRunner(self.timeout_seconds).run(
                workspace.command,
                tee_output,
                container_name=workspace.container_name,
            )

    def collect(self, workspace: BacktestWorkspace) -> LeanArtifacts:
        return LeanArtifacts(
            result_json=workspace.results_dir / f"{workspace.run_id}.json",
            summary_json=workspace.results_dir / f"{workspace.run_id}-summary.json",
            report_html=workspace.results_dir / "report.html",
            manifest_path=workspace.results_dir / "artifact-manifest.json",
        )

    def parse(self, artifacts: LeanArtifacts) -> dict[str, Any]:
        if not artifacts.result_json.exists():
            return {}
        summary = artifacts.summary_json if artifacts.summary_json.exists() else None
        return extract_statistics(artifacts.result_json, summary)

    def archive(self, workspace: BacktestWorkspace, docker_output: DockerRunResult, artifacts: LeanArtifacts) -> None:
        artifacts.manifest_path.write_text(
            json.dumps(
                self._artifact_manifest(
                    run_id=workspace.run_id,
                    run_dir=workspace.run_dir,
                    results_dir=workspace.results_dir,
                    config_path=workspace.config_path,
                    exit_code=docker_output.exit_code,
                    timed_out=docker_output.timed_out,
                    error=docker_output.error,
                    container_name=workspace.container_name,
                ),
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

    def execute(self, workspace: BacktestWorkspace, output_callback: Callable[[str], None]) -> LeanExecutionResult:
        docker_output = self.run(workspace, output_callback)
        artifacts = self.collect(workspace)
        if docker_output.exit_code == 0 and artifacts.result_json.exists():
            screening_path = extract_screening_report(workspace.results_dir)
            if screening_path is not None:
                enrich_screening_file(screening_path)
            extract_trend_pullback_report(workspace.results_dir)
            render_report(artifacts.result_json, artifacts.report_html)
        self.archive(workspace, docker_output, artifacts)
        return LeanExecutionResult(
            docker=docker_output,
            artifacts=artifacts,
            container_name=workspace.container_name,
            work_dir=workspace.run_dir,
            results_dir=workspace.results_dir,
        )

    def result_payload(self, execution: LeanExecutionResult) -> dict[str, Any]:
        artifacts = execution.artifacts
        return {
            "exit_code": execution.docker.exit_code,
            "timed_out": execution.docker.timed_out,
            "container_name": execution.container_name,
            "work_dir": str(execution.work_dir),
            "results_dir": str(execution.results_dir),
            "result_json_path": str(artifacts.result_json) if artifacts.result_json.exists() else None,
            "summary_json_path": str(artifacts.summary_json) if artifacts.summary_json.exists() else None,
            "report_html_path": str(artifacts.report_html) if artifacts.report_html.exists() else None,
            "artifact_manifest_path": str(artifacts.manifest_path),
            "stdout_log_path": str(execution.work_dir / "results" / "stdout.log"),
            "statistics": self.parse(artifacts),
            "error": execution.docker.error,
        }

    def run_backtest(
        self,
        run_id: str,
        parameters: dict[str, Any],
        run_dir: Path,
        output_callback: Callable[[str], None],
        *,
        docker_image: str = DEFAULT_DOCKER_IMAGE,
        algorithm_path: Path,
        algorithm_class: str,
        language: str,
        project_dir: Path,
    ) -> dict[str, Any]:
        workspace = self.prepare(
            run_id,
            parameters,
            run_dir,
            docker_image=docker_image,
            algorithm_path=algorithm_path,
            algorithm_class=algorithm_class,
            language=language,
            project_dir=project_dir,
        )
        return self.result_payload(self.execute(workspace, output_callback))
