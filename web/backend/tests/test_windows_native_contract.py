from __future__ import annotations

import getpass
import json
import os
import subprocess
from pathlib import Path, PureWindowsPath

import pytest


ROOT = Path(__file__).resolve().parents[3]


def _environment_values(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if line and not line.startswith("#") and "=" in line:
            name, value = line.split("=", 1)
            values[name] = value
    return values


def test_windows_native_template_uses_absolute_consistent_paths():
    values = _environment_values(
        ROOT / "config" / "deployment" / "windows-native.env.example"
    )

    for name in (
        "LEAN_NATIVE_RUNTIME_ROOT",
        "LEAN_DATA_DIR",
        "LEAN_RUNTIME_DIR",
        "LEAN_PARQUET_DIR",
        "LEAN_WINDOWS_SANDBOX_POLICY_FILE",
    ):
        assert PureWindowsPath(values[name]).is_absolute(), name
    assert values["LEAN_WINDOWS_SANDBOX_POLICY_FILE"] == (
        r"C:\ProgramData\LeanPlatform\sandbox-policy.json"
    )
    assert values["LEAN_RUNTIME_DIR"] == r"C:\ProgramData\LeanPlatform\runtime"


def test_windows_sandbox_script_defaults_match_environment_template():
    script = (ROOT / "deploy" / "windows" / "configure_windows_sandbox.ps1").read_text(
        encoding="utf-8"
    )

    assert 'Join-Path $resolvedProgramData "sandbox-policy.json"' in script
    assert 'Join-Path $resolvedProgramData "runtime"' in script
    assert "LEAN_WINDOWS_SANDBOX_POLICY_FILE=$resolvedPolicy" in script
    assert "LEAN_RUNTIME_DIR=$runtimeWork" in script


@pytest.mark.skipif(os.name != "nt", reason="Windows contract")
def test_windows_sandbox_verifier_accepts_matching_policy(tmp_path, monkeypatch):
    from app.runners import windows_sandbox

    runtime = tmp_path / "lean"
    data = tmp_path / "data"
    work = tmp_path / "runtime"
    for path in (runtime, data, work):
        path.mkdir()
    policy = tmp_path / "sandbox-policy.json"
    policy.write_text(
        json.dumps(
            {
                "schemaVersion": 1,
                "runnerAccount": getpass.getuser(),
                "firewallRule": "LeanPlatform-RestrictedRunner-BlockOutbound",
                "dataRoot": str(data),
                "runtimeRoot": str(runtime),
                "workRoot": str(work),
            }
        ),
        encoding="utf-8",
    )

    def runner(command, **_kwargs):
        stdout = getpass.getuser() if command[0] == "icacls.exe" else ""
        return subprocess.CompletedProcess(command, 0, stdout=stdout, stderr="")

    monkeypatch.setattr(windows_sandbox, "LEAN_RUNTIME_ROOT", runtime)
    status = windows_sandbox.WindowsSandboxVerifier(policy, runner=runner).verify()

    assert status.ready is True
    assert all(status.checks.values())


@pytest.mark.skipif(os.name != "nt", reason="Windows contract")
def test_windows_job_object_can_be_created_and_closed():
    from app.runners.windows_sandbox import WindowsJobObject

    job = WindowsJobObject(memory_bytes=256 * 1024**2, active_process_limit=1)
    job.close()
    assert job.handle is None


def test_windows_supervisor_uses_solo_workers(monkeypatch):
    from scripts import windows_supervisor

    monkeypatch.setattr(windows_supervisor, "_python", lambda ml=False: "python.exe")
    monkeypatch.setenv("LEAN_DEPLOYMENT_PROFILE", "core")

    workers = [
        child for child in windows_supervisor.platform_children() if child.name.startswith("worker-")
    ]

    assert workers
    assert all("--pool=solo" in child.command for child in workers)
    assert all("--concurrency=1" in child.command for child in workers)
    assert all("--prefetch-multiplier=1" in child.command for child in workers)
