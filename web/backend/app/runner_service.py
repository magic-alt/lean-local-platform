from __future__ import annotations

import hashlib
import json
import os
import secrets
import shutil
import uuid
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from .core.config import (
    ALLOWED_LEAN_DOCKER_IMAGES,
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
        {"source": project_dir, "target": "/Lean/Project", "mode": "ro"},
    ]
    if support_dir:
        mounts.append({"source": support_dir, "target": "/Lean/Run", "mode": "ro"})
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
    ]
    if LEAN_DOCKER_READ_ONLY:
        command.append("--read-only")
    for mount in mounts:
        suffix = ":ro" if mount["mode"] == "ro" else ""
        command.extend(["-v", f"{mount['source']}:{mount['target']}{suffix}"])
    command.append(job.image)

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
    }
    spec["digest"] = hashlib.sha256(
        json.dumps(spec, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return spec


@app.get("/health")
def health() -> dict[str, Any]:
    return {"ok": True, "networkPolicy": LEAN_DOCKER_NETWORK}


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
