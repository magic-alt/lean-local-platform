from pathlib import Path

import pytest
from fastapi import HTTPException

from app import runner_service
from app.core.config import DEFAULT_DOCKER_IMAGE


def _valid_command() -> list[str]:
    platform = str(runner_service.HOST_PLATFORM_DIR)
    data = str(runner_service.HOST_DATA_DIR)
    return [
        "/usr/bin/docker",
        "run",
        "--rm",
        "--name",
        "lean-unit",
        "--read-only",
        "--network",
        runner_service.LEAN_DOCKER_NETWORK,
        "--cpus",
        runner_service.LEAN_DOCKER_CPUS,
        "--memory",
        runner_service.LEAN_DOCKER_MEMORY,
        "--pids-limit",
        str(runner_service.LEAN_DOCKER_PIDS_LIMIT),
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges:true",
        "-e",
        "PYTHONDONTWRITEBYTECODE=1",
        "--tmpfs",
        "/tmp:rw,noexec,nosuid,size=256m",
        "-v",
        f"{platform}/web/runtime/runs/unit/config.json:/Lean/Launcher/bin/Debug/config.json:ro",
        "-v",
        f"{data}:/Lean/Data:ro",
        "-v",
        f"{platform}/web/runtime/runs/unit/results:/Lean/Results",
        "-v",
        f"{platform}/web/runtime/runs/unit/results/object-store:/Lean/Launcher/bin/Debug/storage",
        "-v",
        f"{platform}/web/runtime/runs/unit/strategy:/Lean/Project:ro",
        DEFAULT_DOCKER_IMAGE,
    ]


def test_restricted_runner_accepts_only_fixed_digest_and_mount_schema():
    spec = runner_service._validate_job(
        runner_service.RunnerJob(
            runId="unit",
            command=_valid_command(),
            containerName="lean-unit",
            timeoutSeconds=60,
        )
    )

    assert spec["image"] == DEFAULT_DOCKER_IMAGE
    assert spec["network"] == "none"
    assert len(spec["digest"]) == 64


@pytest.mark.parametrize(
    "mutation",
    [
        lambda command: command.__setitem__(-1, "ubuntu:latest"),
        lambda command: command.insert(3, "--privileged"),
        lambda command: command.extend(["bash", "-c", "cat /workspace/.env"]),
        lambda command: command.__setitem__(
            command.index(next(value for value in command if ":/Lean/Project:ro" in value)),
            "/etc:/Lean/Project:ro",
        ),
    ],
)
def test_restricted_runner_rejects_image_privilege_entrypoint_and_mount_escape(mutation):
    command = _valid_command()
    mutation(command)

    with pytest.raises(HTTPException):
        runner_service._validate_job(
            runner_service.RunnerJob(
                runId="malicious",
                command=command,
                containerName="lean-malicious",
                timeoutSeconds=60,
            )
        )
