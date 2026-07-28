from pathlib import Path

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app import runner_service
from app.core.config import DEFAULT_DOCKER_IMAGE, DEFAULT_RESEARCH_IMAGE


def _valid_payload() -> dict[str, object]:
    platform = str(runner_service.HOST_PLATFORM_DIR)
    data = str(runner_service.HOST_DATA_DIR)
    return {
        "runId": "unit",
        "image": DEFAULT_DOCKER_IMAGE,
        "configPath": f"{platform}/web/runtime/runs/unit/config.json",
        "dataDir": data,
        "resultsDir": f"{platform}/web/runtime/runs/unit/results",
        "storageDir": f"{platform}/web/runtime/runs/unit/results/object-store",
        "projectDir": f"{platform}/web/runtime/runs/unit/strategy",
        "timeoutSeconds": 60,
    }


def test_restricted_runner_builds_fixed_command_from_structured_paths(monkeypatch):
    monkeypatch.setattr(runner_service.shutil, "which", lambda name: "/usr/bin/docker")
    spec = runner_service._validate_job(runner_service.RunnerJob(**_valid_payload()))

    assert spec["schemaVersion"] == 2
    assert spec["image"] == DEFAULT_DOCKER_IMAGE
    assert spec["network"] == "none"
    assert spec["containerName"] == "lean-unit"
    assert len(spec["digest"]) == 64
    assert "--cap-drop" in spec["command"]
    assert "--privileged" not in spec["command"]
    assert "--mount" not in spec["command"]


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("image", "ubuntu:latest"),
        ("projectDir", "/etc"),
        ("configPath", "/etc/passwd"),
        ("dataDir", "/"),
    ],
)
def test_restricted_runner_rejects_untrusted_structured_values(monkeypatch, field, value):
    monkeypatch.setattr(runner_service.shutil, "which", lambda name: "/usr/bin/docker")
    payload = _valid_payload()
    payload[field] = value

    with pytest.raises(HTTPException):
        runner_service._validate_job(runner_service.RunnerJob(**payload))


@pytest.mark.parametrize(
    "freeform",
    [
        ["--mount", "type=bind,src=/,dst=/host"],
        ["--cap-add", "SYS_ADMIN"],
        ["--network", "none", "--network", "host"],
        ["--privileged=true"],
    ],
)
def test_runner_rejects_freeform_flags(freeform):
    payload = {
        **_valid_payload(),
        "command": ["docker", "run", "--rm", *freeform, DEFAULT_DOCKER_IMAGE],
    }

    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        runner_service.RunnerJob(**payload)


def test_restricted_runner_validates_research_workspace_and_owns_container_name(
    monkeypatch,
    tmp_path,
):
    visible_platform = tmp_path / "workspace"
    visible_project = visible_platform / "web/runtime/research/session-1/workspace"
    visible_project.mkdir(parents=True)
    host_platform = Path("/operator/lean-platform")
    monkeypatch.setattr(runner_service, "PLATFORM_DIR", visible_platform)
    monkeypatch.setattr(runner_service, "HOST_PLATFORM_DIR", host_platform)

    spec = runner_service._validate_research_job(
        runner_service.ResearchJob(
            sessionId="session-1",
            image=DEFAULT_RESEARCH_IMAGE,
            projectDir=str(host_platform / "web/runtime/research/session-1/workspace"),
            port=8892,
        )
    )

    assert spec["containerName"] == "lean-research-session-1"
    assert spec["visibleProjectDir"] == str(visible_project)
    assert spec["port"] == 8892


def test_restricted_runner_rejects_research_workspace_outside_allowlist(
    monkeypatch,
    tmp_path,
):
    monkeypatch.setattr(runner_service, "PLATFORM_DIR", tmp_path)
    monkeypatch.setattr(runner_service, "HOST_PLATFORM_DIR", Path("/operator/lean-platform"))

    with pytest.raises(HTTPException, match="runner_research_project_dir_outside_allowlist"):
        runner_service._validate_research_job(
            runner_service.ResearchJob(
                sessionId="session-1",
                image=DEFAULT_RESEARCH_IMAGE,
                projectDir="/etc",
                port=8892,
            )
        )
