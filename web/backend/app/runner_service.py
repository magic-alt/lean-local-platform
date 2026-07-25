from __future__ import annotations

import hashlib
import json
import os
import secrets
import uuid
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

from .core.config import (
    ALLOWED_LEAN_DOCKER_IMAGES,
    HOST_DATA_DIR,
    HOST_PLATFORM_DIR,
    LEAN_DOCKER_CPUS,
    LEAN_DOCKER_MEMORY,
    LEAN_DOCKER_NETWORK,
    LEAN_DOCKER_PIDS_LIMIT,
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
    runId: str = Field(min_length=1, max_length=128)
    command: list[str] = Field(min_length=3, max_length=64)
    containerName: str = Field(min_length=1, max_length=64)
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


def _validate_job(job: RunnerJob) -> dict[str, Any]:
    command = list(job.command)
    if Path(command[0]).name != "docker" or command[1:3] != ["run", "--rm"]:
        raise HTTPException(status_code=400, detail="runner_command_schema_invalid")
    forbidden = {
        "--privileged",
        "--network=host",
        "--pid=host",
        "--ipc=host",
        "--entrypoint",
        "--device",
        "--userns=host",
    }
    if any(part in forbidden or part.startswith("--entrypoint=") for part in command):
        raise HTTPException(status_code=400, detail="runner_forbidden_option")
    image_indexes = [
        index
        for index, value in enumerate(command)
        if value in ALLOWED_LEAN_DOCKER_IMAGES
    ]
    if len(image_indexes) != 1 or image_indexes[0] != len(command) - 1:
        raise HTTPException(status_code=400, detail="runner_image_or_entrypoint_invalid")
    image = command[-1]
    if "@sha256:" not in image:
        raise HTTPException(status_code=400, detail="runner_image_not_pinned")

    required_pairs = {
        "--network": LEAN_DOCKER_NETWORK,
        "--cpus": LEAN_DOCKER_CPUS,
        "--memory": LEAN_DOCKER_MEMORY,
        "--pids-limit": str(LEAN_DOCKER_PIDS_LIMIT),
        "--cap-drop": "ALL",
        "--security-opt": "no-new-privileges:true",
    }
    for flag, required_value in required_pairs.items():
        try:
            index = command.index(flag)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=f"runner_required_option_missing:{flag}") from exc
        if index + 1 >= len(command) or command[index + 1] != required_value:
            raise HTTPException(status_code=400, detail=f"runner_required_option_mismatch:{flag}")
    if LEAN_DOCKER_NETWORK != "none":
        raise HTTPException(status_code=400, detail="runner_network_policy_must_be_none")

    mounts: list[dict[str, Any]] = []
    allowed_targets = {
        "/Lean/Launcher/bin/Debug/config.json": "ro",
        "/Lean/Data": "ro",
        "/Lean/Results": "rw",
        "/Lean/Launcher/bin/Debug/storage": "rw",
        "/Lean/Project": "ro",
        "/Lean/Run": "ro",
    }
    for index, value in enumerate(command):
        if value != "-v":
            continue
        if index + 1 >= len(command):
            raise HTTPException(status_code=400, detail="runner_mount_missing")
        raw = command[index + 1]
        parts = raw.split(":")
        if len(parts) not in {2, 3}:
            raise HTTPException(status_code=400, detail="runner_mount_invalid")
        source, target = parts[0], parts[1]
        mode = parts[2] if len(parts) == 3 else "rw"
        if target not in allowed_targets or mode != allowed_targets[target]:
            raise HTTPException(status_code=400, detail=f"runner_mount_target_invalid:{target}")
        if not (_within(source, HOST_PLATFORM_DIR) or _within(source, HOST_DATA_DIR)):
            raise HTTPException(status_code=400, detail="runner_mount_source_outside_allowlist")
        if ".." in Path(source).parts:
            raise HTTPException(status_code=400, detail="runner_mount_path_traversal")
        mounts.append({"source": source, "target": target, "mode": mode})
    if {item["target"] for item in mounts} < {
        "/Lean/Launcher/bin/Debug/config.json",
        "/Lean/Data",
        "/Lean/Results",
        "/Lean/Project",
    }:
        raise HTTPException(status_code=400, detail="runner_mount_set_incomplete")

    spec = {
        "runId": job.runId,
        "containerName": job.containerName,
        "command": command,
        "image": image,
        "mounts": mounts,
        "resources": required_pairs,
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
        job.command,
        output.append,
        container_name=job.containerName,
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
