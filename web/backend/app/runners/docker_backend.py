from __future__ import annotations

import shutil
from typing import Callable

from ..lean_engine.docker import docker_command, validate_lean_docker_image
from .base import BackendHealth, ExecutionPlan, ExecutionResult, ExecutionSpec, LeanPathLayout, RuntimeIdentity
from .docker_runner import DockerRunner


class DockerLeanBackend:
    name = "docker"

    def __init__(
        self,
        timeout_seconds: int,
        *,
        command_factory: Callable[..., list[str]] = docker_command,
        runner_factory: Callable[[int], DockerRunner] = DockerRunner,
    ):
        self.timeout_seconds = timeout_seconds
        self.command_factory = command_factory
        self.runner_factory = runner_factory

    def path_layout(self, spec: ExecutionSpec | None = None, *, include_support: bool = False) -> LeanPathLayout:
        return LeanPathLayout.docker(include_support=include_support)

    @staticmethod
    def _identity(image: str) -> RuntimeIdentity:
        normalized = validate_lean_docker_image(image)
        digest = normalized.split("@sha256:", 1)[1]
        return RuntimeIdentity(
            backend="docker",
            runtime_id=normalized,
            artifact_sha256=digest,
            docker_image=normalized,
        )

    def prepare(self, spec: ExecutionSpec) -> ExecutionPlan:
        image = validate_lean_docker_image(str(spec.docker_image or ""))
        command = self.command_factory(
            spec.config_path,
            spec.host_results_dir,
            image,
            project_dir=spec.host_project_dir,
            support_dir=spec.host_support_dir,
        )
        return ExecutionPlan(
            backend="docker",
            execution_id=f"lean-{spec.run_id}"[:60],
            command=command,
            spec=spec,
            runtime_identity=self._identity(image),
        )

    def run(self, plan: ExecutionPlan, output_callback: Callable[[str], None]) -> ExecutionResult:
        result = self.runner_factory(self.timeout_seconds).run(
            plan.command,
            output_callback,
            container_name=plan.execution_id,
        )
        return ExecutionResult(
            exit_code=result.exit_code,
            timed_out=result.timed_out,
            backend="docker",
            execution_id=plan.execution_id,
            error=result.error,
            runtime_identity=plan.runtime_identity,
        )

    def stop(self, execution_id: str, output_callback: Callable[[str], None] | None = None) -> None:
        DockerRunner.stop_container(execution_id, output_callback)

    def health(self) -> BackendHealth:
        ready = shutil.which("docker") is not None
        return BackendHealth(backend="docker", ready=ready, detail="docker command ready" if ready else "docker command missing")
