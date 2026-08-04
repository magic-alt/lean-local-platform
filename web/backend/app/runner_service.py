from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import shutil
import uuid
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from .core.config import (
    ALLOWED_LEAN_DOCKER_IMAGES,
    ALLOWED_RESEARCH_DOCKER_IMAGES,
    DATA_DIR,
    HOST_DATA_DIR,
    HOST_PLATFORM_DIR,
    LEAN_DOCKER_CPUS,
    LEAN_DOCKER_MEMORY,
    LEAN_DOCKER_NETWORK,
    LEAN_DOCKER_PIDS_LIMIT,
    LEAN_DOCKER_READ_ONLY,
    PLATFORM_DIR,
)
from .db import db, json_dump, utc_now
from .lean_engine.errors import LeanPlatformError
from .lean_engine.research import (
    container_logs as research_container_logs,
    container_state as research_container_state,
    find_available_port as find_research_port,
    remove_container as remove_research_container,
    research_container_name,
    run_detached_research,
    stop_container as stop_research_container,
)
from .runners.docker_runner import DockerRunner


app = FastAPI(title="Restricted LEAN Runner", docs_url=None, redoc_url=None)


@app.on_event("startup")
def recover_interrupted_runner_jobs() -> None:
    """Fail closed for jobs whose owning runner process no longer exists."""
    now = utc_now()
    with db() as connection:
        connection.execute(
            """
            update restricted_runner_jobs
            set status='failed',exit_code=coalesce(exit_code,1),
                error=coalesce(error,'restricted_runner_restarted'),
                finished_at=coalesce(finished_at,?)
            where status='running'
            """,
            (now,),
        )


class RunnerJob(BaseModel):
    model_config = ConfigDict(extra="forbid")

    runId: str = Field(min_length=1, max_length=48, pattern=r"^[A-Za-z0-9._-]+$")
    image: str = Field(min_length=1, max_length=512)
    configPath: str = Field(min_length=1, max_length=4096)
    dataDir: str = Field(min_length=1, max_length=4096)
    resultsDir: str = Field(min_length=1, max_length=4096)
    storageDir: str = Field(min_length=1, max_length=4096)
    projectDir: str = Field(min_length=1, max_length=4096)
    supportDir: str | None = Field(default=None, min_length=1, max_length=4096)
    timeoutSeconds: int = Field(ge=1, le=86400)
    traceId: str | None = Field(default=None, min_length=1, max_length=128)
    workflowId: str | None = Field(default=None, min_length=1, max_length=128)


class ResearchJob(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sessionId: str = Field(min_length=1, max_length=48, pattern=r"^[A-Za-z0-9._-]+$")
    image: str = Field(min_length=1, max_length=512)
    projectDir: str = Field(min_length=1, max_length=4096)
    port: int = Field(ge=1024, le=65535)


class ResearchPortRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    preferred: int | None = Field(default=None, ge=1024, le=65535)
    start: int = Field(default=8888, ge=1024, le=65535)
    end: int = Field(default=8999, ge=1024, le=65535)


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


def _authenticate(authorization: str | None) -> None:
    expected = _runner_token()
    supplied = str(authorization or "").removeprefix("Bearer ").strip()
    if not expected or not supplied or not secrets.compare_digest(expected, supplied):
        raise HTTPException(status_code=401, detail="runner_authentication_failed")


def _within(value: str, root: Path) -> bool:
    root_text = str(root)
    return value == root_text or value.startswith(root_text.rstrip("/") + "/")


def _validated_path(
    value: str,
    root: Path,
    *,
    visible_root: Path,
    label: str,
) -> str:
    path = Path(value)
    if not path.is_absolute() or ".." in path.parts or not _within(str(path), root):
        raise HTTPException(status_code=400, detail=f"runner_{label}_outside_allowlist")
    relative = path.relative_to(root)
    resolved_visible_root = visible_root.resolve()
    resolved_visible = (visible_root / relative).resolve()
    if not _within(str(resolved_visible), resolved_visible_root):
        raise HTTPException(status_code=400, detail=f"runner_{label}_symlink_escape")
    return str(path)


def _validate_job(job: RunnerJob) -> dict[str, Any]:
    if job.image not in ALLOWED_LEAN_DOCKER_IMAGES:
        raise HTTPException(status_code=400, detail="runner_image_or_entrypoint_invalid")
    if "@sha256:" not in job.image:
        raise HTTPException(status_code=400, detail="runner_image_not_pinned")
    if LEAN_DOCKER_NETWORK != "none":
        raise HTTPException(status_code=400, detail="runner_network_policy_must_be_none")
    config_path = _validated_path(
        job.configPath, HOST_PLATFORM_DIR, visible_root=PLATFORM_DIR, label="config_path"
    )
    data_dir = _validated_path(
        job.dataDir, HOST_DATA_DIR, visible_root=DATA_DIR, label="data_dir"
    )
    results_dir = _validated_path(
        job.resultsDir, HOST_PLATFORM_DIR, visible_root=PLATFORM_DIR, label="results_dir"
    )
    storage_dir = _validated_path(
        job.storageDir, HOST_PLATFORM_DIR, visible_root=PLATFORM_DIR, label="storage_dir"
    )
    project_dir = _validated_path(
        job.projectDir, HOST_PLATFORM_DIR, visible_root=PLATFORM_DIR, label="project_dir"
    )
    support_dir = (
        _validated_path(
            job.supportDir,
            HOST_PLATFORM_DIR,
            visible_root=PLATFORM_DIR,
            label="support_dir",
        )
        if job.supportDir
        else None
    )
    if Path(storage_dir) != Path(results_dir) / "object-store":
        raise HTTPException(status_code=400, detail="runner_storage_path_invalid")
    container_name = f"lean-{job.runId}"[:60]
    mounts = [
        {"source": config_path, "target": "/Lean/Launcher/bin/Debug/config.json", "mode": "ro"},
        {"source": data_dir, "target": "/Lean/Data", "mode": "ro"},
        {"source": results_dir, "target": "/Lean/Results", "mode": "rw"},
        {"source": storage_dir, "target": "/Lean/Launcher/bin/Debug/storage", "mode": "rw"},
        {"source": project_dir, "target": "/Lean/Staging/Project", "mode": "ro"},
    ]
    if support_dir:
        mounts.append({"source": support_dir, "target": "/Lean/Staging/Run", "mode": "ro"})
    docker = shutil.which("docker")
    if not docker:
        raise HTTPException(status_code=503, detail="runner_docker_unavailable")
    command = [
        docker,
        "run",
        "--rm",
        "--name",
        container_name,
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
        "--tmpfs",
        "/Lean/Project:rw,noexec,nosuid,nodev,size=64m",
    ]
    stage_commands = ["cp -a /Lean/Staging/Project/. /Lean/Project/"]
    if support_dir:
        command.extend(
            ["--tmpfs", "/Lean/Run:rw,noexec,nosuid,nodev,size=64m"]
        )
        # The support directory is the whole run root and also contains the
        # growing results tree. Copy only the fixed, server-owned inputs; a
        # recursive copy can race output creation and stall Docker Desktop's
        # bind filesystem for minutes.
        stage_commands.append(
            "for file in ashare_execution.py ashare_trade_status.json "
            "ashare-trend-pullback-input.json.gz hk_execution.py trace-context.json; "
            "do if [ -f /Lean/Staging/Run/$file ]; then "
            "cp /Lean/Staging/Run/$file /Lean/Run/$file; fi; done"
        )
    if job.traceId:
        command.extend(["-e", f"LEAN_TRACE_ID={job.traceId}"])
    if job.workflowId:
        command.extend(["-e", f"LEAN_WORKFLOW_ID={job.workflowId}"])
    if LEAN_DOCKER_READ_ONLY:
        command.append("--read-only")
    for mount in mounts:
        suffix = ":ro" if mount["mode"] == "ro" else ""
        command.extend(["-v", f"{mount['source']}:{mount['target']}{suffix}"])
    command.extend(["--entrypoint", "/bin/sh", job.image, "-c"])
    stage_commands.append(
        "exec dotnet /Lean/Launcher/bin/Debug/QuantConnect.Lean.Launcher.dll"
    )
    command.append(" && ".join(stage_commands))

    spec = {
        "schemaVersion": 2,
        "runId": job.runId,
        "containerName": container_name,
        "command": command,
        "image": job.image,
        "mounts": mounts,
        "resources": {
            "cpus": LEAN_DOCKER_CPUS,
            "memory": LEAN_DOCKER_MEMORY,
            "pidsLimit": str(LEAN_DOCKER_PIDS_LIMIT),
            "capDrop": "ALL",
            "noNewPrivileges": True,
            "readOnly": bool(LEAN_DOCKER_READ_ONLY),
        },
        "network": LEAN_DOCKER_NETWORK,
        "timeoutSeconds": job.timeoutSeconds,
        "traceId": job.traceId,
        "workflowId": job.workflowId,
    }
    spec["digest"] = hashlib.sha256(
        json.dumps(spec, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return spec


def _validate_research_job(job: ResearchJob) -> dict[str, Any]:
    if job.image not in ALLOWED_RESEARCH_DOCKER_IMAGES or "@sha256:" not in job.image:
        raise HTTPException(status_code=400, detail="runner_research_image_invalid")
    project_dir = _validated_path(
        job.projectDir,
        HOST_PLATFORM_DIR,
        visible_root=PLATFORM_DIR,
        label="research_project_dir",
    )
    visible_project_dir = (
        PLATFORM_DIR / Path(project_dir).relative_to(HOST_PLATFORM_DIR)
    ).resolve()
    if not visible_project_dir.is_dir():
        raise HTTPException(status_code=400, detail="runner_research_project_dir_missing")
    return {
        "sessionId": job.sessionId,
        "containerName": research_container_name(job.sessionId),
        "image": job.image,
        "projectDir": project_dir,
        "visibleProjectDir": str(visible_project_dir),
        "port": job.port,
    }


def _research_session_id(value: str) -> str:
    if not value or len(value) > 48 or re.fullmatch(r"[A-Za-z0-9._-]+", value) is None:
        raise HTTPException(status_code=400, detail="runner_research_session_id_invalid")
    return value


@app.get("/health")
def health() -> dict[str, Any]:
    return {"ok": True, "networkPolicy": LEAN_DOCKER_NETWORK}


@app.post("/v1/research/port")
def available_research_port(
    request: ResearchPortRequest,
    authorization: str | None = Header(default=None),
) -> dict[str, int]:
    _authenticate(authorization)
    if request.start > request.end:
        raise HTTPException(status_code=400, detail="runner_research_port_range_invalid")
    try:
        return {
            "port": find_research_port(
                request.preferred,
                start=request.start,
                end=request.end,
            )
        }
    except LeanPlatformError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post("/v1/research/start")
def start_research(
    job: ResearchJob,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    _authenticate(authorization)
    spec = _validate_research_job(job)
    output: list[str] = []
    try:
        result = run_detached_research(
            spec["sessionId"],
            Path(spec["visibleProjectDir"]),
            spec["port"],
            output.append,
            image=spec["image"],
        )
    except LeanPlatformError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {
        **result,
        "container_id": spec["containerName"],
        "output": output[-2000:],
    }


@app.get("/v1/research/{session_id}")
def research_state(
    session_id: str,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    _authenticate(authorization)
    normalized = _research_session_id(session_id)
    return research_container_state(research_container_name(normalized))


@app.get("/v1/research/{session_id}/logs")
def research_logs(
    session_id: str,
    tail: int = 200,
    authorization: str | None = Header(default=None),
) -> dict[str, str]:
    _authenticate(authorization)
    normalized = _research_session_id(session_id)
    return {
        "logs": research_container_logs(
            research_container_name(normalized),
            tail=max(1, min(tail, 2000)),
        )
    }


@app.post("/v1/research/{session_id}/stop")
def stop_research(
    session_id: str,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    _authenticate(authorization)
    normalized = _research_session_id(session_id)
    container_name = research_container_name(normalized)
    stop_research_container(container_name)
    return research_container_state(container_name)


@app.delete("/v1/research/{session_id}")
def delete_research(
    session_id: str,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    _authenticate(authorization)
    normalized = _research_session_id(session_id)
    remove_research_container(research_container_name(normalized))
    return {"removed": True, "sessionId": normalized}


@app.post("/v1/jobs/run")
def run_job(job: RunnerJob, authorization: str | None = Header(default=None)) -> dict[str, Any]:
    _authenticate(authorization)
    spec = _validate_job(job)
    job_id = str(uuid.uuid4())
    now = utc_now()
    with db() as connection:
        existing = connection.execute(
            "select * from restricted_runner_jobs where run_id=?",
            (job.runId,),
        ).fetchone()
        if existing:
            if str(existing["spec_digest"]) != spec["digest"]:
                raise HTTPException(status_code=409, detail="runner_job_spec_drift")
            if str(existing["status"]) == "success":
                return {
                    "jobId": existing["id"],
                    "exitCode": int(existing["exit_code"] or 0),
                    "timedOut": bool(existing["timed_out"]),
                    "error": existing["error"],
                    "output": [],
                    "idempotentReplay": True,
                }
            job_id = str(existing["id"])
            connection.execute(
                """
                update restricted_runner_jobs
                set status='running',started_at=?,finished_at=null,error=null
                where id=?
                """,
                (now, job_id),
            )
        else:
            connection.execute(
                """
                insert into restricted_runner_jobs
                    (id,run_id,spec_digest,image_digest,command_json,mounts_json,
                     resource_limits_json,network_policy,status,created_at,started_at)
                values (?,?,?,?,?,?,?,?,'running',?,?)
                """,
                (
                    job_id,
                    job.runId,
                    spec["digest"],
                    spec["image"],
                    json_dump(spec["command"]),
                    json_dump(spec["mounts"]),
                    json_dump(spec["resources"]),
                    spec["network"],
                    now,
                    now,
                ),
            )
    output: list[str] = []
    result = DockerRunner(job.timeoutSeconds, allow_remote=False).run(
        spec["command"],
        output.append,
        container_name=spec["containerName"],
    )
    with db() as connection:
        connection.execute(
            """
            update restricted_runner_jobs
            set status=?,exit_code=?,timed_out=?,error=?,finished_at=?
            where id=?
            """,
            (
                "success" if result.exit_code == 0 else "failed",
                result.exit_code,
                1 if result.timed_out else 0,
                result.error,
                utc_now(),
                job_id,
            ),
        )
    return {
        "jobId": job_id,
        "exitCode": result.exit_code,
        "timedOut": result.timed_out,
        "error": result.error,
        "output": output[-10000:],
        "idempotentReplay": False,
    }
