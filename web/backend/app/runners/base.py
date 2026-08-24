from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path, PurePath, PurePosixPath
from typing import Callable, Literal, Protocol


ExecutionBackendName = Literal["docker", "native"]


@dataclass(frozen=True)
class LeanPathLayout:
    """Paths as they are visible to the LEAN Launcher."""

    launcher_dir: PurePath
    data_dir: PurePath
    results_dir: PurePath
    project_dir: PurePath
    storage_dir: PurePath
    support_dir: PurePath | None = None

    @classmethod
    def docker(cls, *, include_support: bool) -> "LeanPathLayout":
        return cls(
            launcher_dir=PurePosixPath("/Lean/Launcher/bin/Debug"),
            data_dir=PurePosixPath("/Lean/Data"),
            results_dir=PurePosixPath("/Lean/Results"),
            project_dir=PurePosixPath("/Lean/Project"),
            storage_dir=PurePosixPath("/Lean/Launcher/bin/Debug/storage"),
            support_dir=PurePosixPath("/Lean/Run") if include_support else None,
        )


@dataclass(frozen=True)
class RuntimeIdentity:
    backend: ExecutionBackendName
    runtime_id: str
    artifact_sha256: str
    lean_commit: str | None = None
    platform: str | None = None
    docker_image: str | None = None

    def as_dict(self) -> dict[str, str | None]:
        return {
            "backend": self.backend,
            "runtimeId": self.runtime_id,
            "artifactSha256": self.artifact_sha256,
            "leanCommit": self.lean_commit,
            "platform": self.platform,
            "dockerImage": self.docker_image,
        }


@dataclass(frozen=True)
class ExecutionSpec:
    run_id: str
    config_path: Path
    host_data_dir: Path
    host_results_dir: Path
    host_project_dir: Path
    host_storage_dir: Path
    host_support_dir: Path | None
    path_layout: LeanPathLayout
    timeout_seconds: int
    docker_image: str | None = None


@dataclass(frozen=True)
class ExecutionPlan:
    backend: ExecutionBackendName
    execution_id: str
    command: list[str]
    spec: ExecutionSpec
    runtime_identity: RuntimeIdentity
    metadata: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class ExecutionResult:
    exit_code: int
    timed_out: bool = False
    backend: ExecutionBackendName = "docker"
    execution_id: str = ""
    error: str | None = None
    runtime_identity: RuntimeIdentity | None = None


@dataclass(frozen=True)
class BackendHealth:
    backend: ExecutionBackendName
    ready: bool
    detail: str
    runtime_identity: RuntimeIdentity | None = None
    sandbox: str | None = None


class ExecutionBackend(Protocol):
    name: ExecutionBackendName

    def path_layout(self, spec: ExecutionSpec | None = None, *, include_support: bool = False) -> LeanPathLayout:
        ...

    def prepare(self, spec: ExecutionSpec) -> ExecutionPlan:
        ...

    def run(self, plan: ExecutionPlan, output_callback: Callable[[str], None]) -> ExecutionResult:
        ...

    def stop(self, execution_id: str, output_callback: Callable[[str], None] | None = None) -> None:
        ...

    def health(self) -> BackendHealth:
        ...
