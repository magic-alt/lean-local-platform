#!/usr/bin/env python3
"""Run the long-lived, fail-closed Issue #61 operational evidence campaign.

The coordinator invokes existing authoritative evidence producers. It never
backdates observations, embeds webhook credentials, enables Live/P9, or treats
missing operational evidence as a pass.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import time
from typing import Any
import urllib.error
import urllib.request
from urllib.parse import urlsplit
import uuid


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "web" / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

DEFAULT_ROOT = ROOT / "web" / "runtime" / "audit" / "post-migration-campaign"
HEX_40_RE = re.compile(r"^[0-9a-f]{40}$")
HEX_64_RE = re.compile(r"^[0-9a-f]{64}$")
SAFE_PREFIX_RE = re.compile(r"^lean_restore_[a-z0-9_]+$")
SERVICE_SCENARIOS = {
    "database_short_disconnect",
    "rabbitmq_outage",
    "worker_crash",
}
REQUIRED_SCENARIOS = {
    "database_short_disconnect",
    "rabbitmq_outage",
    "duplicate_delivery",
    "worker_crash",
    "runner_timeout_cancel",
    "disk_full",
    "object_corruption",
    "lease_expiry_stale_worker",
    "missing_pit_benchmark",
    "notification_failure",
}
TERMINAL_STEP_STATES = {"PASSED", "FAILED", "INDETERMINATE"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"json_object_required:{path}")
    return payload


def _write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _git_sha() -> str:
    completed = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    value = completed.stdout.strip()
    if completed.returncode or not HEX_40_RE.fullmatch(value):
        raise RuntimeError("current_git_sha_unavailable")
    return value


def _api_token() -> str:
    configured = os.environ.get("LEAN_API_TOKEN", "").strip()
    if configured:
        return configured
    token_file = Path(
        os.environ.get(
            "LEAN_API_TOKEN_FILE",
            str(ROOT / "web" / "runtime" / "secrets" / "api_token"),
        )
    )
    try:
        return token_file.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def _health(api_url: str) -> dict[str, Any]:
    headers: dict[str, str] = {}
    token = _api_token()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(api_url.rstrip("/") + "/api/health", headers=headers)
    with urllib.request.urlopen(request, timeout=15) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError("health_payload_invalid")
    return payload


def _relative_or_absolute(value: str) -> Path:
    path = Path(value).expanduser()
    return path.resolve() if path.is_absolute() else (ROOT / path).resolve()


def _validate_config(config: dict[str, Any]) -> dict[str, Any]:
    if config.get("schemaVersion") != 1:
        raise ValueError("campaign_config_schema_invalid")
    if not HEX_40_RE.fullmatch(str(config.get("expectedGitSha") or "")):
        raise ValueError("expected_git_sha_invalid")
    release_id = str(config.get("expectedReleaseId") or "").strip()
    if release_id in {"", "dev", "unknown", "local-unversioned"}:
        raise ValueError("versioned_release_id_required")
    if not str(config.get("dataReleaseId") or "").strip():
        raise ValueError("data_release_id_required")
    if not HEX_64_RE.fullmatch(str(config.get("dataReleaseManifestSha256") or "")):
        raise ValueError("data_release_manifest_sha256_invalid")
    accounts = [str(item).strip() for item in config.get("paperAccountIds") or []]
    if not accounts or any(not item for item in accounts):
        raise ValueError("paper_account_ids_required")
    api_url = str(config.get("apiUrl") or "")
    parsed = urlsplit(api_url)
    if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise ValueError("campaign_api_must_be_loopback_http")
    observation = config.get("observation") or {}
    if float(observation.get("webhookHours") or 0) < 24:
        raise ValueError("webhook_observation_must_be_at_least_24_hours")
    if int(observation.get("paperDays") or 0) < 21:
        raise ValueError("paper_observation_must_be_at_least_21_days")
    if int(observation.get("paperSampleSeconds") or 0) < 300:
        raise ValueError("paper_sample_interval_too_short")
    if int(observation.get("loopSeconds") or 0) < 5:
        raise ValueError("campaign_loop_interval_too_short")
    restore = config.get("restore") or {}
    if not SAFE_PREFIX_RE.fullmatch(str(restore.get("targetPrefix") or "")):
        raise ValueError("restore_target_prefix_invalid")
    if (config.get("deployment") or {}).get("runtime") != "linux-docker":
        raise ValueError("campaign_runtime_requires_linux_docker")
    scenario_evidence = (config.get("evidence") or {}).get("scenarioEvidence") or {}
    if not isinstance(scenario_evidence, dict):
        raise ValueError("scenario_evidence_mapping_required")
    unknown = set(scenario_evidence) - (REQUIRED_SCENARIOS - SERVICE_SCENARIOS)
    if unknown:
        raise ValueError("unknown_fault_scenarios:" + ",".join(sorted(unknown)))
    encoded = json.dumps(config, ensure_ascii=False).lower()
    for forbidden in ("webhookurl", "token", "password", "secret", "credential"):
        if forbidden in encoded:
            raise ValueError(f"secret_material_forbidden_in_campaign_config:{forbidden}")
    return config


def _new_state(config_path: Path, config: dict[str, Any]) -> dict[str, Any]:
    return {
        "schemaVersion": 1,
        "campaignId": config["campaignId"],
        "configPath": str(config_path),
        "createdAt": _now(),
        "updatedAt": _now(),
        "status": "INITIALIZED",
        "liveActivationAllowed": False,
        "steps": {},
        "blockers": [],
        "events": [],
    }


def _event(state: dict[str, Any], event: str, **details: Any) -> None:
    state.setdefault("events", []).append({"at": _now(), "event": event, **details})
    state["events"] = state["events"][-200:]
    state["updatedAt"] = _now()


def _step(state: dict[str, Any], name: str) -> dict[str, Any]:
    return state.setdefault("steps", {}).setdefault(name, {"status": "PENDING"})


def _set_step(state: dict[str, Any], name: str, status: str, **details: Any) -> None:
    state.setdefault("steps", {})[name] = {
        **_step(state, name),
        "status": status,
        "updatedAt": _now(),
        **details,
    }
    _event(state, "step_status", step=name, status=status)


def _run_once(
    state: dict[str, Any],
    state_path: Path,
    name: str,
    command: list[str],
    *,
    log_path: Path,
    environment: dict[str, str] | None = None,
    timeout: int = 7200,
) -> bool:
    current = _step(state, name)
    if current.get("status") == "PASSED":
        return True
    if current.get("status") in {"FAILED", "INDETERMINATE", "RUNNING"}:
        return False
    _set_step(state, name, "RUNNING", startedAt=_now(), log=str(log_path))
    _write(state_path, state)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("ab") as log:
        try:
            completed = subprocess.run(
                command,
                cwd=ROOT,
                env=environment,
                stdin=subprocess.DEVNULL,
                stdout=log,
                stderr=subprocess.STDOUT,
                timeout=timeout,
                check=False,
            )
            code = completed.returncode
        except Exception as exc:
            _set_step(state, name, "FAILED", failureType=type(exc).__name__)
            _write(state_path, state)
            return False
    _set_step(
        state,
        name,
        "PASSED" if code == 0 else "FAILED",
        exitCode=code,
        completedAt=_now(),
    )
    _write(state_path, state)
    return code == 0


def _process_running(pid: int | None) -> bool:
    if not pid:
        return False
    try:
        os.kill(int(pid), 0)
        return True
    except OSError:
        return False


def _acquire_lock(state_path: Path) -> Path:
    state_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = state_path.with_suffix(state_path.suffix + ".lock")
    for _attempt in range(2):
        try:
            descriptor = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            try:
                owner = int(lock_path.read_text(encoding="utf-8").strip())
            except (OSError, ValueError):
                owner = 0
            if _process_running(owner):
                raise RuntimeError(f"campaign_already_running:{owner}")
            lock_path.unlink(missing_ok=True)
            continue
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(f"{os.getpid()}\n")
        return lock_path
    raise RuntimeError("campaign_lock_unavailable")


def _launch_webhook(
    config: dict[str, Any], state: dict[str, Any], state_path: Path, paths: dict[str, Path]
) -> None:
    step = _step(state, "externalWebhook")
    evidence = paths["externalWebhook"]
    if evidence.is_file():
        payload = _load(evidence)
        if payload.get("passed") and payload.get("thirdPartyCertified") is True:
            _set_step(state, "externalWebhook", "PASSED", evidence=str(evidence))
        elif not _process_running(step.get("pid")):
            _set_step(state, "externalWebhook", "FAILED", evidence=str(evidence))
        return
    if step.get("status") in {"FAILED", "INDETERMINATE"}:
        return
    if _process_running(step.get("pid")):
        return
    log_path = paths["logs"] / "external-webhook.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log = log_path.open("ab")
    try:
        process = subprocess.Popen(
            [
                sys.executable,
                str(ROOT / "scripts" / "run_external_webhook_acceptance.py"),
                "--monitor-hours",
                str(config["observation"]["webhookHours"]),
                "--poll-seconds",
                str(config["observation"]["webhookPollSeconds"]),
                "--api-url",
                config["apiUrl"],
                "--evidence",
                str(evidence),
            ],
            cwd=ROOT,
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=subprocess.STDOUT,
            creationflags=(
                subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP
                if os.name == "nt"
                else 0
            ),
            start_new_session=os.name != "nt",
        )
    finally:
        log.close()
    _set_step(
        state,
        "externalWebhook",
        "RUNNING",
        pid=process.pid,
        startedAt=_now(),
        evidence=str(evidence),
        log=str(log_path),
    )
    _write(state_path, state)


def _campaign_paths(config: dict[str, Any]) -> dict[str, Path]:
    root = _relative_or_absolute(config["campaignRoot"])
    evidence = root / "evidence"
    return {
        "root": root,
        "logs": root / "logs",
        "backupRoot": root / "backups",
        "restore": evidence / "restore-drill.json",
        "serviceFaults": evidence / "service-restart-faults.json",
        "faultMatrix": evidence / "fault-matrix.json",
        "paperState": evidence / "paper-soak-state.json",
        "paperSoak": evidence / "paper-soak-evidence.json",
        "externalWebhook": evidence / "external-webhook-acceptance.json",
        "certificate": evidence / "release-certification.json",
    }


def _paper_command(config: dict[str, Any], paths: dict[str, Path], action: str) -> list[str]:
    command = [
        sys.executable,
        str(ROOT / "scripts" / "paper_soak_observer.py"),
        "--state",
        str(paths["paperState"]),
        "--base-url",
        config["apiUrl"],
        action,
    ]
    if action == "start":
        for account_id in config["paperAccountIds"]:
            command.extend(["--account-id", account_id])
        command.extend(
            [
                "--data-release-id",
                config["dataReleaseId"],
                "--data-release-manifest-sha256",
                config["dataReleaseManifestSha256"],
            ]
        )
    elif action == "finalize":
        command.extend(
            [
                "--minimum-days",
                str(config["observation"]["paperDays"]),
                "--fault-matrix",
                str(paths["faultMatrix"]),
                "--evidence",
                str(paths["paperSoak"]),
            ]
        )
    return command


def _sample_due(config: dict[str, Any], paths: dict[str, Path]) -> bool:
    if not paths["paperState"].is_file():
        return False
    state = _load(paths["paperState"])
    if not state.get("samples"):
        return True
    last = str(state.get("lastObservedAt") or state.get("startedAt") or "")
    if not last:
        return True
    parsed = datetime.fromisoformat(last.replace("Z", "+00:00"))
    return (datetime.now(timezone.utc) - parsed).total_seconds() >= int(
        config["observation"]["paperSampleSeconds"]
    )


def _paper_ready_to_finalize(config: dict[str, Any], paths: dict[str, Path]) -> bool:
    if not paths["paperState"].is_file():
        return False
    state = _load(paths["paperState"])
    samples = list(state.get("samples") or [])
    if not samples:
        return False
    started = datetime.fromisoformat(str(state.get("startedAt") or "").replace("Z", "+00:00"))
    completed = datetime.fromisoformat(
        str(samples[-1].get("observedAt") or "").replace("Z", "+00:00")
    )
    minimum_days = int(config["observation"]["paperDays"])
    observed_dates = {str(item.get("localDate")) for item in samples if item.get("localDate")}
    return (
        (completed - started).total_seconds() >= minimum_days * 86400
        and len(observed_dates) >= minimum_days
    )


def _assemble_fault_matrix(config: dict[str, Any], paths: dict[str, Path]) -> dict[str, Any]:
    from scripts.build_fault_matrix import build_matrix

    bindings = [
        (name, _relative_or_absolute(value))
        for name, value in ((config.get("evidence") or {}).get("scenarioEvidence") or {}).items()
        if _relative_or_absolute(value).is_file()
    ]
    payload = build_matrix(
        policy_path=ROOT / "config" / "certification" / "post-migration-v1.json",
        service_restart_path=paths["serviceFaults"] if paths["serviceFaults"].is_file() else None,
        scenario_paths=bindings,
    )
    _write(paths["faultMatrix"], payload)
    return payload


def _tick(config: dict[str, Any], state: dict[str, Any], state_path: Path) -> None:
    paths = _campaign_paths(config)
    paths["root"].mkdir(parents=True, exist_ok=True)
    state["blockers"] = []
    try:
        health = _health(config["apiUrl"])
    except (OSError, urllib.error.URLError, RuntimeError, json.JSONDecodeError) as exc:
        state["status"] = "WAITING_PREREQUISITES"
        state["blockers"] = [{"code": "api_health_unavailable", "detail": type(exc).__name__}]
        _write(state_path, state)
        return
    release = health.get("release") or {}
    current_git = _git_sha()
    if (
        current_git != config["expectedGitSha"]
        or release.get("gitSha") != config["expectedGitSha"]
        or release.get("releaseId") != config["expectedReleaseId"]
    ):
        state["status"] = "BLOCKED"
        state["blockers"] = [
            {"code": "release_identity_mismatch", "detail": "source/runtime/config"}
        ]
        _write(state_path, state)
        return

    if not paths["paperState"].is_file():
        _run_once(
            state,
            state_path,
            "paperSoakStart",
            _paper_command(config, paths, "start"),
            log_path=paths["logs"] / "paper-soak-start.log",
            timeout=300,
        )
    if paths["paperState"].is_file() and _sample_due(config, paths):
        subprocess.run(
            _paper_command(config, paths, "sample"),
            cwd=ROOT,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=300,
            check=False,
        )
    if os.environ.get("LEAN_ALERT_WEBHOOK_URL", "").strip():
        _launch_webhook(config, state, state_path, paths)
    else:
        state["blockers"].append(
            {"code": "external_webhook_not_configured", "detail": "LEAN_ALERT_WEBHOOK_URL"}
        )

    backup_step = _step(state, "backup")
    if backup_step.get("status") == "PENDING":
        _set_step(state, "backup", "RUNNING", startedAt=_now())
        _write(state_path, state)
        try:
            from app.services.postgres_backup import create_backup

            result = create_backup(paths["backupRoot"])
            _set_step(state, "backup", "PASSED", backup=result.get("backup"), completedAt=_now())
        except Exception as exc:
            _set_step(state, "backup", "FAILED", failureType=type(exc).__name__)
        _write(state_path, state)

    if _step(state, "backup").get("status") == "PASSED":
        backup = str(_step(state, "backup").get("backup") or "")
        environment = dict(os.environ)
        environment["LEAN_RELEASE_ID"] = config["expectedReleaseId"]
        environment["LEAN_DEPLOYMENT_PROFILE"] = config["deployment"]["profile"]
        _run_once(
            state,
            state_path,
            "restoreDrill",
            [
                sys.executable,
                str(ROOT / "scripts" / "run_restore_drill.py"),
                "--backup",
                backup,
                "--target-prefix",
                config["restore"]["targetPrefix"],
                "--confirm",
                "RESTORE_ISOLATED_DATABASE",
                "--data-release-id",
                config["dataReleaseId"],
                "--data-release-manifest-sha256",
                config["dataReleaseManifestSha256"],
                "--verify-paper-projections",
                "--evidence",
                str(paths["restore"]),
            ],
            log_path=paths["logs"] / "restore-drill.log",
            environment=environment,
        )

    if _step(state, "restoreDrill").get("status") == "PASSED":
        _run_once(
            state,
            state_path,
            "serviceFaults",
            [
                sys.executable,
                str(ROOT / "scripts" / "run_service_restart_fault_acceptance.py"),
                "--project",
                config["deployment"]["composeProject"],
                "--api-url",
                config["apiUrl"],
                "--services",
                "worker,rabbitmq,postgres",
                "--confirm",
                "RESTART_LOCAL_SERVICES",
                "--output",
                str(paths["serviceFaults"]),
            ],
            log_path=paths["logs"] / "service-faults.log",
            timeout=1800,
        )

    matrix = _assemble_fault_matrix(config, paths)
    if matrix.get("passed"):
        _set_step(state, "faultMatrix", "PASSED", evidence=str(paths["faultMatrix"]))
    else:
        missing = sorted(set(matrix.get("missingScenarios") or []))
        _set_step(state, "faultMatrix", "WAITING_EVIDENCE", missingScenarios=missing)
        state["blockers"].append({"code": "fault_scenarios_missing", "detail": ",".join(missing)})

    if (
        matrix.get("passed")
        and _paper_ready_to_finalize(config, paths)
        and not paths["paperSoak"].is_file()
    ):
        _run_once(
            state,
            state_path,
            "paperSoakFinalize",
            _paper_command(config, paths, "finalize"),
            log_path=paths["logs"] / "paper-soak-finalize.log",
            timeout=300,
        )

    required_files = {
        "releaseConvergence": _relative_or_absolute(config["evidence"]["releaseConvergence"]),
        "localDataCertification": _relative_or_absolute(
            config["evidence"]["localDataCertification"]
        ),
        "supplyChain": _relative_or_absolute(config["evidence"]["supplyChain"]),
        "restoreDrill": paths["restore"],
        "faultMatrix": paths["faultMatrix"],
        "paperSoak": paths["paperSoak"],
        "externalWebhook": paths["externalWebhook"],
    }
    missing_files = [name for name, path in required_files.items() if not path.is_file()]
    if not missing_files:
        from scripts.release_certification import build_bundle

        bundle = build_bundle(
            root=ROOT,
            policy_path=ROOT / "config" / "certification" / "post-migration-v1.json",
            profile="paper",
            runtime=config["deployment"]["runtime"],
            evidence_paths=required_files,
            output=paths["certificate"],
        )
        _set_step(
            state,
            "certificate",
            "PASSED" if bundle.get("certified") else "WAITING_EVIDENCE",
            evidence=str(paths["certificate"]),
        )
        state["status"] = "CERTIFIED" if bundle.get("certified") else "RUNNING"
        state["blockers"] = list(bundle.get("blockedReasons") or [])
    else:
        state["status"] = "RUNNING"
        state["blockers"].append(
            {"code": "certification_evidence_incomplete", "detail": ",".join(missing_files)}
        )
    if any(
        item.get("status") in {"FAILED", "INDETERMINATE"}
        for item in (state.get("steps") or {}).values()
    ):
        state["status"] = "BLOCKED"
    _write(state_path, state)


def _recover_interrupted(state: dict[str, Any]) -> None:
    for name, step in (state.get("steps") or {}).items():
        if step.get("status") == "RUNNING" and name != "externalWebhook":
            step["status"] = "INDETERMINATE"
            step["updatedAt"] = _now()
            _event(state, "step_interrupted", step=name)


def run_loop(config_path: Path, state_path: Path, *, once: bool = False) -> int:
    lock_path = _acquire_lock(state_path)
    try:
        config = _validate_config(_load(config_path))
        state = _load(state_path) if state_path.is_file() else _new_state(config_path, config)
        _recover_interrupted(state)
        state["daemonPid"] = os.getpid()
        _write(state_path, state)
        stop_path = state_path.with_suffix(state_path.suffix + ".stop")
        while not stop_path.exists():
            _tick(config, state, state_path)
            if once or state.get("status") == "CERTIFIED":
                break
            time.sleep(int(config["observation"]["loopSeconds"]))
        if stop_path.exists():
            stop_path.unlink()
            webhook_pid = _step(state, "externalWebhook").get("pid")
            if _process_running(webhook_pid):
                os.kill(int(webhook_pid), signal.SIGTERM)
            state["status"] = "STOPPED"
            _event(state, "campaign_stopped")
            _write(state_path, state)
        return (
            0
            if state.get("status")
            in {"RUNNING", "WAITING_PREREQUISITES", "CERTIFIED"}
            else 2
        )
    finally:
        lock_path.unlink(missing_ok=True)


def _binding(value: str) -> tuple[str, str]:
    if "=" not in value:
        raise ValueError("scenario_binding_requires_name_equals_path")
    name, path = value.split("=", 1)
    if name not in REQUIRED_SCENARIOS - SERVICE_SCENARIOS or not path.strip():
        raise ValueError("scenario_binding_invalid")
    return name, path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    init = commands.add_parser("init")
    init.add_argument("--config", type=Path, required=True)
    init.add_argument("--state", type=Path, required=True)
    init.add_argument("--confirm", required=True)
    init.add_argument("--release-id", required=True)
    init.add_argument("--data-release-id", required=True)
    init.add_argument("--data-release-manifest-sha256", required=True)
    init.add_argument("--paper-account-id", action="append", required=True)
    init.add_argument("--api-url", default="http://127.0.0.1:8000")
    init.add_argument("--runtime", choices=("linux-docker",), default="linux-docker")
    init.add_argument("--deployment-profile", default="full")
    init.add_argument("--compose-project", default="lean-platform")
    init.add_argument("--campaign-root")
    init.add_argument("--release-convergence", required=True)
    init.add_argument("--local-data-certification", required=True)
    init.add_argument("--supply-chain", required=True)
    init.add_argument("--scenario", action="append", default=[])
    init.add_argument("--loop-seconds", type=int, default=60)
    init.add_argument("--paper-sample-seconds", type=int, default=21600)
    init.add_argument("--webhook-poll-seconds", type=int, default=300)
    init.add_argument("--restore-target-prefix", default="lean_restore_issue61")

    for name in ("run", "launch", "status", "stop"):
        command = commands.add_parser(name)
        command.add_argument("--config", type=Path, required=name in {"run", "launch"})
        command.add_argument("--state", type=Path, required=True)
        if name == "run":
            command.add_argument("--once", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    state_path = args.state.expanduser().resolve()
    if args.command == "init":
        if args.confirm != "RUN_POST_MIGRATION_CERTIFICATION_CAMPAIGN":
            raise SystemExit(
                "--confirm must be RUN_POST_MIGRATION_CERTIFICATION_CAMPAIGN"
            )
        campaign_id = str(uuid.uuid4())
        root = args.campaign_root or str(DEFAULT_ROOT / campaign_id)
        scenarios = dict(_binding(item) for item in args.scenario)
        config = _validate_config(
            {
                "schemaVersion": 1,
                "campaignId": campaign_id,
                "expectedGitSha": _git_sha(),
                "expectedReleaseId": args.release_id,
                "dataReleaseId": args.data_release_id,
                "dataReleaseManifestSha256": args.data_release_manifest_sha256.lower(),
                "paperAccountIds": list(dict.fromkeys(args.paper_account_id)),
                "apiUrl": args.api_url,
                "campaignRoot": root,
                "deployment": {
                    "runtime": args.runtime,
                    "profile": args.deployment_profile,
                    "composeProject": args.compose_project,
                },
                "restore": {"targetPrefix": args.restore_target_prefix},
                "observation": {
                    "webhookHours": 24,
                    "webhookPollSeconds": args.webhook_poll_seconds,
                    "paperDays": 21,
                    "paperSampleSeconds": args.paper_sample_seconds,
                    "loopSeconds": args.loop_seconds,
                },
                "evidence": {
                    "releaseConvergence": args.release_convergence,
                    "localDataCertification": args.local_data_certification,
                    "supplyChain": args.supply_chain,
                    "scenarioEvidence": scenarios,
                },
            }
        )
        config_path = args.config.expanduser().resolve()
        _write(config_path, config)
        state = _new_state(config_path, config)
        _write(state_path, state)
        print(json.dumps(state, ensure_ascii=False, indent=2))
        return 0
    if args.command == "status":
        print(json.dumps(_load(state_path), ensure_ascii=False, indent=2))
        return 0
    if args.command == "stop":
        state_path.with_suffix(state_path.suffix + ".stop").write_text("stop\n", encoding="utf-8")
        return 0
    config_path = args.config.expanduser().resolve()
    if args.command == "run":
        return run_loop(config_path, state_path, once=args.once)
    existing = _load(state_path)
    if _process_running(existing.get("daemonPid")):
        raise SystemExit(f"campaign already running: pid {existing['daemonPid']}")
    log_path = state_path.with_suffix(".daemon.log")
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log = log_path.open("ab")
    try:
        process = subprocess.Popen(
            [
                sys.executable,
                str(Path(__file__).resolve()),
                "run",
                "--config",
                str(config_path),
                "--state",
                str(state_path),
            ],
            cwd=ROOT,
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=subprocess.STDOUT,
            creationflags=(
                subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP
                if os.name == "nt"
                else 0
            ),
            start_new_session=os.name != "nt",
        )
    finally:
        log.close()
    state = _load(state_path)
    state["daemonPid"] = process.pid
    state["daemonLog"] = str(log_path)
    _event(state, "campaign_launched", pid=process.pid)
    _write(state_path, state)
    print(json.dumps({"pid": process.pid, "state": str(state_path), "log": str(log_path)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
