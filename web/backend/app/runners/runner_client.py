from __future__ import annotations

import json
import os
import urllib.request
from pathlib import Path
from typing import Callable

from ..core.request_context import current_trace_id, current_workflow_id
from ..lean_engine.errors import LeanPlatformError
from .base import BackendHealth, ExecutionPlan, ExecutionResult, RuntimeIdentity


class RestrictedRunnerClient:
    def __init__(self, url: str | None = None, token: str | None = None):
        self.url = (url or os.environ.get("LEAN_RUNNER_URL", "")).strip().rstrip("/")
        self.token = token if token is not None else self._runner_token()
        if not self.url or not self.token:
            raise LeanPlatformError("restricted_runner_not_configured")

    @staticmethod
    def _runner_token() -> str:
        configured = os.environ.get("LEAN_RUNNER_TOKEN", "").strip()
        if configured:
            return configured
        path = Path(
            os.environ.get(
                "LEAN_RUNNER_TOKEN_FILE",
                "/workspace/web/runtime/secrets/runner_token",
            )
        )
        try:
            return path.read_text(encoding="utf-8").strip()
        except OSError:
            return ""

    def _request(self, path: str, *, payload: dict[str, object] | None = None, method: str = "GET") -> dict[str, object]:
        request = urllib.request.Request(
            self.url + path,
            data=json.dumps(payload).encode("utf-8") if payload is not None else None,
            headers={
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json",
            },
            method=method,
        )
        with urllib.request.urlopen(request, timeout=90) as response:
            return json.loads(response.read().decode("utf-8"))

    def run(self, plan: ExecutionPlan, output_callback: Callable[[str], None]) -> ExecutionResult:
        spec = plan.spec
        payload: dict[str, object] = {
            "runId": spec.run_id,
            "executionBackend": plan.backend,
            "runtimeRef": plan.runtime_identity.runtime_id,
            "runtimeDigest": plan.runtime_identity.artifact_sha256,
            "configPath": str(spec.config_path),
            "dataDir": str(spec.host_data_dir),
            "resultsDir": str(spec.host_results_dir),
            "storageDir": str(spec.host_storage_dir),
            "projectDir": str(spec.host_project_dir),
            "timeoutSeconds": spec.timeout_seconds,
            "traceId": current_trace_id(),
            "workflowId": current_workflow_id(),
        }
        if spec.host_support_dir is not None:
            payload["supportDir"] = str(spec.host_support_dir)
        body = self._request("/v2/jobs/run", payload=payload, method="POST")
        for line in body.get("output") or []:
            output_callback(str(line))
        identity_payload = body.get("runtimeIdentity")
        identity = plan.runtime_identity
        if isinstance(identity_payload, dict):
            identity = RuntimeIdentity(
                backend=str(identity_payload.get("backend") or plan.backend),  # type: ignore[arg-type]
                runtime_id=str(identity_payload.get("runtimeId") or ""),
                artifact_sha256=str(identity_payload.get("artifactSha256") or ""),
                lean_commit=identity_payload.get("leanCommit"),
                platform=identity_payload.get("platform"),
                docker_image=identity_payload.get("dockerImage"),
            )
        return ExecutionResult(
            exit_code=int(body.get("exitCode") or 0),
            timed_out=bool(body.get("timedOut")),
            backend=plan.backend,
            execution_id=str(body.get("executionId") or plan.execution_id),
            error=body.get("error"),
            runtime_identity=identity,
        )

    def stop(self, run_id: str) -> None:
        self._request(f"/v2/jobs/{run_id}/stop", payload={}, method="POST")

    def health(self, backend: str) -> BackendHealth:
        body = self._request("/health")
        ready = bool(body.get("ok")) and body.get("executionBackend") == backend
        return BackendHealth(
            backend=backend,  # type: ignore[arg-type]
            ready=ready,
            detail="restricted runner ready" if ready else "restricted runner backend mismatch",
            sandbox=str(body.get("sandbox") or ""),
        )
