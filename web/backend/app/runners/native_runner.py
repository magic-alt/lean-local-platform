from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Callable

from ..core.config import LEAN_NATIVE_SANDBOX
from ..lean_engine.errors import LeanPlatformError
from .base import BackendHealth, ExecutionPlan, ExecutionResult, ExecutionSpec, LeanPathLayout
from .dotnet import dotnet_major_available, resolve_dotnet
from .process import ProcessRunner
from .runtime_registry import NativeRuntime, RuntimeRegistry
from .runner_client import RestrictedRunnerClient
from .windows_sandbox import WindowsSandboxVerifier


class NativeLeanBackend:
    name = "native"

    def __init__(
        self,
        timeout_seconds: int,
        *,
        registry: RuntimeRegistry | None = None,
        allow_remote: bool = True,
    ):
        self.timeout_seconds = timeout_seconds
        self.registry = registry or RuntimeRegistry()
        self.allow_remote = allow_remote
        self.process_runner = ProcessRunner(timeout_seconds)

    def path_layout(self, spec: ExecutionSpec | None = None, *, include_support: bool = False) -> LeanPathLayout:
        if spec is None:
            raise LeanPlatformError("native_path_layout_requires_execution_spec")
        runtime = self.registry.resolve()
        return LeanPathLayout(
            launcher_dir=runtime.launcher.parent,
            data_dir=spec.host_data_dir.resolve(),
            results_dir=spec.host_results_dir.resolve(),
            project_dir=spec.host_project_dir.resolve(),
            storage_dir=spec.host_storage_dir.resolve(),
            support_dir=spec.host_support_dir.resolve() if include_support and spec.host_support_dir else None,
        )

    @staticmethod
    def _safe_env(runtime: NativeRuntime) -> dict[str, str]:
        allowed = {name: os.environ[name] for name in ("PATH", "TZ", "DOTNET_ROOT") if name in os.environ}
        allowed["PYTHONDONTWRITEBYTECODE"] = "1"
        if runtime.python_home is not None:
            allowed["PYTHONHOME"] = str(runtime.python_home)
        if runtime.python_library is not None:
            allowed["PYTHONNET_PYDLL"] = str(runtime.python_library)
        return allowed

    def _sandbox_command(self, spec: ExecutionSpec, runtime: NativeRuntime) -> tuple[list[str], str]:
        dotnet = resolve_dotnet()
        if not dotnet:
            raise LeanPlatformError("native_dotnet_runtime_missing")
        if not dotnet_major_available(dotnet):
            raise LeanPlatformError("native_dotnet_runtime_incompatible:requires_10.x")
        direct = [str(dotnet), str(runtime.launcher), "--config", str(spec.config_path)]
        requested = LEAN_NATIVE_SANDBOX
        if os.name == "nt":
            status = WindowsSandboxVerifier().verify()
            if not status.ready:
                raise LeanPlatformError(status.detail)
            return direct, "windows-restricted-job"
        if requested == "process":
            return direct, "process"
        bwrap = shutil.which("bwrap")
        if not bwrap:
            raise LeanPlatformError("native_sandbox_unavailable:bwrap is required")
        runtime_root = runtime.root
        command = [
            bwrap,
            "--unshare-all",
            "--die-with-parent",
            "--new-session",
            "--clearenv",
            "--setenv", "PATH", str(Path(dotnet).parent),
            "--setenv", "PYTHONDONTWRITEBYTECODE", "1",
        ]
        for system_root in (Path("/usr"), Path("/bin"), Path("/lib"), Path("/lib64")):
            if system_root.exists():
                command.extend(["--ro-bind", str(system_root), str(system_root)])
        bind_paths = {
            runtime_root,
            spec.host_data_dir.resolve(),
            spec.host_project_dir.resolve(),
            spec.config_path.resolve(),
            spec.host_results_dir.resolve(),
            spec.host_storage_dir.resolve(),
        }
        if spec.host_support_dir is not None:
            bind_paths.add(spec.host_support_dir.resolve())
        namespace_dirs: set[Path] = set()
        for bind_path in bind_paths:
            namespace_dirs.update(parent for parent in bind_path.parents if parent != Path("/"))
        system_roots = (Path("/usr"), Path("/bin"), Path("/lib"), Path("/lib64"))
        for directory in sorted(namespace_dirs, key=lambda item: len(item.parts)):
            if any(directory == root or directory.is_relative_to(root) for root in system_roots):
                continue
            command.extend(["--dir", str(directory)])
        command.extend(
            [
                "--ro-bind", str(runtime_root), str(runtime_root),
                "--ro-bind", str(spec.host_data_dir.resolve()), str(spec.host_data_dir.resolve()),
                "--ro-bind", str(spec.host_project_dir.resolve()), str(spec.host_project_dir.resolve()),
                "--ro-bind", str(spec.config_path.resolve()), str(spec.config_path.resolve()),
                "--bind", str(spec.host_results_dir.resolve()), str(spec.host_results_dir.resolve()),
                "--bind", str(spec.host_storage_dir.resolve()), str(spec.host_storage_dir.resolve()),
                "--proc", "/proc",
                "--dev", "/dev",
                "--tmpfs", "/tmp",
            ]
        )
        if spec.host_support_dir is not None:
            command.extend(["--ro-bind", str(spec.host_support_dir.resolve()), str(spec.host_support_dir.resolve())])
        if runtime.python_home is not None:
            command.extend(["--setenv", "PYTHONHOME", str(runtime.python_home)])
        if runtime.python_library is not None:
            command.extend(["--setenv", "PYTHONNET_PYDLL", str(runtime.python_library)])
        command.extend(direct)
        return command, "bwrap"

    def prepare(self, spec: ExecutionSpec) -> ExecutionPlan:
        runtime = self.registry.resolve()
        command, sandbox = self._sandbox_command(spec, runtime)
        return ExecutionPlan(
            backend="native",
            execution_id=f"lean-{spec.run_id}"[:60],
            command=command,
            spec=spec,
            runtime_identity=runtime.identity,
            metadata={"sandbox": sandbox, "launcherDir": str(runtime.launcher.parent)},
        )

    def run(self, plan: ExecutionPlan, output_callback: Callable[[str], None]) -> ExecutionResult:
        if self.allow_remote and os.environ.get("LEAN_RUNNER_URL", "").strip():
            return RestrictedRunnerClient().run(plan, output_callback)
        runtime = self.registry.resolve()
        result = self.process_runner.run(
            plan.command,
            output_callback,
            execution_id=plan.execution_id,
            cwd=runtime.launcher.parent,
            env=self._safe_env(runtime),
        )
        return ExecutionResult(
            exit_code=result.exit_code,
            timed_out=result.timed_out,
            backend="native",
            execution_id=plan.execution_id,
            error=result.error,
            runtime_identity=plan.runtime_identity,
        )

    def stop(self, execution_id: str, output_callback: Callable[[str], None] | None = None) -> None:
        if self.allow_remote and os.environ.get("LEAN_RUNNER_URL", "").strip():
            RestrictedRunnerClient().stop(execution_id.removeprefix("lean-"))
            if output_callback:
                output_callback(f"restricted native runner stop {execution_id}: requested")
            return
        stopped = self.process_runner.stop(execution_id)
        if output_callback:
            output_callback(f"native process stop {execution_id}: {'requested' if stopped else 'not_found'}")

    def health(self) -> BackendHealth:
        if self.allow_remote and os.environ.get("LEAN_RUNNER_URL", "").strip():
            try:
                return RestrictedRunnerClient().health("native")
            except (LeanPlatformError, OSError) as exc:
                return BackendHealth(backend="native", ready=False, detail=str(exc))
        try:
            runtime = self.registry.resolve()
            if os.name == "nt":
                status = WindowsSandboxVerifier().verify()
                if not status.ready:
                    raise LeanPlatformError(status.detail)
                sandbox = "windows-restricted-job"
            else:
                sandbox = "process" if LEAN_NATIVE_SANDBOX == "process" else "bwrap"
            if sandbox == "bwrap" and shutil.which("bwrap") is None:
                raise LeanPlatformError("native_sandbox_unavailable")
            dotnet = resolve_dotnet()
            if dotnet is None:
                raise LeanPlatformError("native_dotnet_runtime_missing")
            if not dotnet_major_available(dotnet):
                raise LeanPlatformError("native_dotnet_runtime_incompatible:requires_10.x")
            return BackendHealth(
                backend="native",
                ready=True,
                detail="native LEAN runtime ready",
                runtime_identity=runtime.identity,
                sandbox=sandbox,
            )
        except LeanPlatformError as exc:
            return BackendHealth(backend="native", ready=False, detail=str(exc), sandbox=LEAN_NATIVE_SANDBOX)
