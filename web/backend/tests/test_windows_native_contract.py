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
        "LEAN_DOTNET_PATH",
        "LEAN_DATA_DIR",
        "LEAN_RUNTIME_DIR",
        "LEAN_PARQUET_DIR",
        "LEAN_WINDOWS_SANDBOX_POLICY_FILE",
    ):
        assert PureWindowsPath(values[name]).is_absolute(), name
    assert values["LEAN_WINDOWS_SANDBOX_POLICY_FILE"] == (
        r"C:\ProgramData\LeanPlatform\sandbox-policy.json"
    )
    assert values["LEAN_DOTNET_PATH"] == r"C:\Program Files\dotnet\dotnet.exe"
    assert values["LEAN_RUNTIME_DIR"] == r"C:\ProgramData\LeanPlatform\runtime"


def test_windows_sandbox_script_defaults_match_environment_template():
    script = (ROOT / "deploy" / "windows" / "configure_windows_sandbox.ps1").read_text(
        encoding="utf-8"
    )

    assert 'Join-Path $resolvedProgramData "sandbox-policy.json"' in script
    assert 'Join-Path $resolvedProgramData "runtime"' in script
    assert "LEAN_WINDOWS_SANDBOX_POLICY_FILE=$resolvedPolicy" in script
    assert "LEAN_RUNTIME_DIR=$runtimeWork" in script
    assert "scripts\\resolve_dotnet.py" in script
    assert '"runtime"' in script
    assert ".NET runtime 10.x is required on the deployment host." in script


def test_windows_runtime_builder_requires_sdk_10_but_deployment_does_not():
    builder = (ROOT / "deploy" / "windows" / "build_native_lean_runtime.ps1").read_text(
        encoding="utf-8"
    )
    release = (
        ROOT / "deploy" / "windows" / "run_local_native_runtime_release.ps1"
    ).read_text(encoding="utf-8")

    assert '[string]$DotnetPath = ""' in builder
    assert "scripts\\resolve_dotnet.py" in builder
    assert '"sdk"' in builder
    assert ".NET SDK 10.x is required on the native runtime build host." in builder
    assert "-DotnetPath $DotnetPath" in release


def test_windows_native_acceptance_spec_and_smoke_project_are_frozen():
    spec_path = ROOT / "config" / "acceptance" / "windows-native-core.v1.json"
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    project = (spec_path.parent / spec["projectDir"]).resolve()

    assert spec["schemaVersion"] == 1
    assert spec["qualificationId"] == "windows-native-core-v1"
    assert (project / spec["mainFile"]).is_file()
    assert spec["expected"]["minimumOrders"] >= 1
    assert spec["expected"]["minimumFilledOrders"] >= 1
    assert len(spec["fixture"]["rows"]) >= 2
    assert spec["parameters"]["ticker"] == spec["fixture"]["symbol"]
    assert spec["parameters"]["market"] == spec["fixture"]["market"]


def test_windows_golden_preflight_is_strict_and_precedes_system_mutation():
    script = (
        ROOT / "deploy" / "windows" / "run_dockerless_golden_acceptance.ps1"
    ).read_text(encoding="utf-8")

    for check in (
        "cliAbsent",
        "serviceAbsent",
        "desktopAbsent",
        "wslDistrosAbsent",
        "installationAbsent",
    ):
        assert check in script
    assert "signedRuntimeLockReady" in script
    assert "dotnetRuntime10Available" in script
    assert "acceptanceSpecSha256" in script
    assert "acceptanceAlgorithmSha256" in script
    assert "serviceAccountsReady" in script
    assert "serviceCredentialVariablesPresent" in script
    assert "Test-Path Env:LEAN_WINDOWS_RUNNER_PASSWORD" in script
    assert "rabbitmq_cli_cookie_not_core_gated" in script
    assert script.index('steps["preflight"]') < script.index(
        'Invoke-CheckedStep "sandbox_configure"'
    )


def test_native_runtime_lock_remains_fail_closed_until_release():
    lock = json.loads(
        (ROOT / "config" / "runtime" / "lean-native.lock.json").read_text(
            encoding="utf-8"
        )
    )

    assert lock["supported"] is False


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
