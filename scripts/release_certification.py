#!/usr/bin/env python3
"""Build a fail-closed post-migration release-certification bundle.

The evaluator never enables PRODUCTION/Live/P9. It only verifies evidence
against the current source identity and emits machine-readable blocked reasons.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_POLICY = ROOT / "config" / "certification" / "post-migration-v1.json"
DEFAULT_OUTPUT = ROOT / "web" / "runtime" / "audit" / "release-certification.json"
HEX_64_RE = re.compile(r"^[0-9a-f]{64}$")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"evidence_not_object:{path}")
    return payload


def _git_sha(root: Path) -> str:
    completed = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=root,
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode or not completed.stdout.strip():
        raise RuntimeError(completed.stderr.strip() or "unable_to_resolve_git_sha")
    return completed.stdout.strip()


def _blocked(blocked: list[dict[str, str]], code: str, detail: str) -> None:
    blocked.append({"code": code, "detail": detail})


def _require(
    condition: bool,
    blocked: list[dict[str, str]],
    code: str,
    detail: str,
) -> bool:
    if not condition:
        _blocked(blocked, code, detail)
        return False
    return True


def _evidence_binding(name: str, path: Path, payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": name,
        "path": str(path),
        "sha256": _sha256_file(path),
        "schemaVersion": payload.get("schemaVersion"),
        "status": payload.get("status"),
        "passed": payload.get("passed"),
    }


def _elapsed_days(started: str, completed: str) -> float:
    def parse(value: str) -> datetime:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)

    return max(0.0, (parse(completed) - parse(started)).total_seconds() / 86400.0)


def _float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def build_bundle(
    *,
    root: Path,
    policy_path: Path,
    profile: str,
    runtime: str,
    evidence_paths: dict[str, Path],
    output: Path | None = None,
) -> dict[str, Any]:
    policy = _load_json(policy_path)
    profiles = policy.get("profiles") or {}
    if profile not in profiles:
        raise ValueError(f"unsupported_profile:{profile}")
    runtime_policy = (policy.get("runtimes") or {}).get(runtime)
    if not isinstance(runtime_policy, dict):
        raise ValueError(f"unsupported_runtime:{runtime}")

    blocked: list[dict[str, str]] = []
    current_git_sha = _git_sha(root)

    source_bindings: dict[str, Any] = {}
    for relative in policy.get("sourceLocks") or []:
        path = root / str(relative)
        if not path.is_file():
            _blocked(blocked, "source_lock_missing", str(relative))
            continue
        source_bindings[str(relative)] = {
            "sha256": _sha256_file(path),
            "size": path.stat().st_size,
        }

    required_evidence = list((profiles.get(profile) or {}).get("requiredEvidence") or [])
    if runtime_policy.get("requiresWindowsCertificate"):
        required_evidence.append("windowsCertificate")

    evidence: dict[str, dict[str, Any]] = {}
    bindings: dict[str, Any] = {}
    for name in required_evidence:
        path = evidence_paths.get(name)
        if path is None:
            _blocked(blocked, "evidence_path_missing", name)
            continue
        if not path.is_file():
            _blocked(blocked, "evidence_file_missing", f"{name}:{path}")
            continue
        try:
            payload = _load_json(path)
        except Exception as exc:
            _blocked(blocked, "evidence_invalid_json", f"{name}:{type(exc).__name__}")
            continue
        evidence[name] = payload
        bindings[name] = _evidence_binding(name, path, payload)

    convergence = evidence.get("releaseConvergence") or {}
    health = convergence.get("health") or {}
    release = health.get("release") or {}
    schema = release.get("schema") or {}
    release_id = str(release.get("releaseId") or "")
    release_git_sha = str(release.get("gitSha") or "")
    openapi_sha = str(release.get("openApiSha256") or "")
    frontend_sha = str(release.get("frontendAssetsSha256") or "")
    migration = str(schema.get("latestAppliedMigration") or "")
    migration_checksum = str(schema.get("latestAppliedMigrationChecksum") or "")

    _require(
        bool(convergence.get("passed")) and bool(convergence.get("managedStack")),
        blocked,
        "release_convergence_failed",
        "managed full-Compose convergence evidence is required",
    )
    _require(
        release_git_sha == current_git_sha,
        blocked,
        "git_sha_mismatch",
        f"current={current_git_sha},evidence={release_git_sha or 'missing'}",
    )
    _require(
        bool(release_id) and release_id not in {"dev", "unknown", "local-unversioned"},
        blocked,
        "release_id_missing",
        release_id or "missing",
    )
    _require(
        bool(schema.get("aligned"))
        and bool(migration)
        and HEX_64_RE.fullmatch(migration_checksum) is not None,
        blocked,
        "migration_identity_invalid",
        f"migration={migration or 'missing'},checksum={migration_checksum or 'missing'}",
    )
    _require(
        HEX_64_RE.fullmatch(openapi_sha) is not None,
        blocked,
        "openapi_hash_invalid",
        openapi_sha or "missing",
    )
    _require(
        HEX_64_RE.fullmatch(frontend_sha) is not None,
        blocked,
        "frontend_digest_invalid",
        frontend_sha or "missing",
    )

    database = health.get("database") or {}
    broker = health.get("broker") or {}
    _require(
        database.get("engine") == "postgresql" and database.get("status") == "ready",
        blocked,
        "postgresql_identity_invalid",
        str(database),
    )
    _require(
        broker.get("engine") == "rabbitmq" and broker.get("status") == "ready",
        blocked,
        "rabbitmq_identity_invalid",
        str(broker),
    )

    local_data = evidence.get("localDataCertification") or {}
    local_release = local_data.get("dataRelease") or {}
    data_release_id = str(
        local_release.get("dataReleaseId") or local_data.get("dataReleaseId") or ""
    )
    data_manifest_sha = str(
        local_release.get("manifestSha256") or local_data.get("manifestSha256") or ""
    )
    _require(
        bool(local_data.get("passed")),
        blocked,
        "local_data_certification_failed",
        "immutable DataRelease certification must pass",
    )
    _require(
        str(local_data.get("gitSha") or "") == release_git_sha,
        blocked,
        "local_data_git_mismatch",
        str(local_data.get("gitSha") or "missing"),
    )
    _require(
        bool(local_release.get("passed")) and bool(data_release_id),
        blocked,
        "data_release_identity_missing",
        data_release_id or "missing",
    )
    _require(
        HEX_64_RE.fullmatch(data_manifest_sha) is not None,
        blocked,
        "data_release_manifest_hash_invalid",
        data_manifest_sha or "missing",
    )
    _require(
        bool((local_data.get("leanSmoke") or {}).get("passed")),
        blocked,
        "frozen_datarelease_lean_smoke_failed",
        "local data certificate must include a passing frozen DataRelease -> LEAN smoke",
    )

    restore = evidence.get("restoreDrill") or {}
    _require(
        bool(restore.get("passed")) and restore.get("databaseEngine") == "postgresql",
        blocked,
        "restore_drill_failed",
        str(restore.get("status") or "missing"),
    )
    _require(
        bool(restore.get("checksumMatch")) and int(restore.get("rowCountDiff") or 0) == 0,
        blocked,
        "restore_invariants_failed",
        "restored canonical table row counts/digests must match",
    )
    _require(
        str(restore.get("gitSha") or "") == release_git_sha,
        blocked,
        "restore_git_mismatch",
        str(restore.get("gitSha") or "missing"),
    )
    _require(
        str(restore.get("releaseId") or "") == release_id,
        blocked,
        "restore_release_id_mismatch",
        str(restore.get("releaseId") or "missing"),
    )
    _require(
        str(restore.get("dataReleaseId") or "") == data_release_id,
        blocked,
        "restore_data_release_mismatch",
        str(restore.get("dataReleaseId") or "missing"),
    )
    _require(
        str(restore.get("dataReleaseManifestSha256") or "") == data_manifest_sha,
        blocked,
        "restore_data_manifest_mismatch",
        str(restore.get("dataReleaseManifestSha256") or "missing"),
    )

    fault = evidence.get("faultMatrix") or {}
    fault_scenarios = fault.get("scenarios") or {}
    _require(
        bool(fault.get("passed")),
        blocked,
        "fault_matrix_failed",
        str(fault.get("status") or "missing"),
    )
    fault_release_sha = str(fault.get("releaseGitSha") or fault.get("gitSha") or "")
    _require(
        fault_release_sha == release_git_sha,
        blocked,
        "fault_matrix_git_mismatch",
        fault_release_sha or "missing",
    )
    if fault.get("releaseId") is not None:
        _require(
            str(fault.get("releaseId") or "") == release_id,
            blocked,
            "fault_matrix_release_id_mismatch",
            str(fault.get("releaseId") or "missing"),
        )
    for scenario in policy.get("requiredFaultScenarios") or []:
        item = fault_scenarios.get(scenario) if isinstance(fault_scenarios, dict) else None
        _require(
            isinstance(item, dict) and bool(item.get("passed")),
            blocked,
            "fault_scenario_missing_or_failed",
            str(scenario),
        )
        if isinstance(item, dict):
            _require(
                bool(item.get("trace")) and bool(item.get("invariants")),
                blocked,
                "fault_scenario_evidence_incomplete",
                str(scenario),
            )

    supply = evidence.get("supplyChain") or {}
    _require(
        str(supply.get("status") or "") == "passed" and not supply.get("failures"),
        blocked,
        "supply_chain_failed",
        "pinned dependencies/SBOM/signature evidence must pass",
    )

    if runtime_policy.get("requiresWindowsCertificate"):
        windows = evidence.get("windowsCertificate") or {}
        _require(
            bool(windows.get("ready")) and windows.get("status") == "WINDOWS_CELERY_CERTIFIED",
            blocked,
            "windows_runtime_uncertified",
            str(windows.get("status") or "missing"),
        )

    paper_observation: dict[str, Any] | None = None
    if profile == "paper":
        projection = restore.get("projectionRebuild") or {}
        _require(
            bool(projection.get("passed")) and projection.get("mode") == "apply",
            blocked,
            "restored_projection_rebuild_missing",
            "Paper certification requires projection rebuild on the isolated restored database",
        )

        soak = evidence.get("paperSoak") or {}
        mode = str(soak.get("evidenceMode") or "")
        started = str(soak.get("startedAt") or "")
        completed = str(soak.get("completedAt") or "")
        elapsed_days = 0.0
        try:
            elapsed_days = _elapsed_days(started, completed) if started and completed else 0.0
        except ValueError:
            pass
        minimum_days = int(policy.get("minimumPaperObservationCalendarDays") or 21)
        _require(
            bool(soak.get("passed")) and mode == "production_shape_observation",
            blocked,
            "paper_soak_mode_invalid",
            mode or "missing",
        )
        _require(
            elapsed_days >= minimum_days,
            blocked,
            "paper_soak_too_short",
            f"observed={elapsed_days:.3f},required={minimum_days}",
        )
        _require(
            str(soak.get("gitSha") or "") == release_git_sha
            and str(soak.get("releaseId") or "") == release_id,
            blocked,
            "paper_soak_release_mismatch",
            "soak must be bound to the current release identity",
        )
        _require(
            str(soak.get("dataReleaseId") or "") == data_release_id,
            blocked,
            "paper_soak_data_release_mismatch",
            str(soak.get("dataReleaseId") or "missing"),
        )
        _require(
            bool((soak.get("ledgerProjection") or {}).get("passed")),
            blocked,
            "paper_soak_ledger_projection_failed",
            "ledger/projection invariant evidence must pass",
        )
        _require(
            bool((soak.get("interruptionRecovery") or {}).get("passed")),
            blocked,
            "paper_soak_recovery_failed",
            "production-shape interruption recovery evidence must pass",
        )
        paper_observation = {
            "evidenceMode": mode or None,
            "startedAt": started or None,
            "completedAt": completed or None,
            "observedCalendarDays": round(elapsed_days, 6),
            "minimumCalendarDays": minimum_days,
        }

        webhook = evidence.get("externalWebhook") or {}
        minimum_hours = float(policy.get("minimumExternalWebhookObservationHours") or 24)
        _require(
            bool(webhook.get("passed")) and webhook.get("thirdPartyCertified") is True,
            blocked,
            "external_webhook_not_certified",
            str(webhook.get("status") or "missing"),
        )
        _require(
            _float(webhook.get("observedWindowHours")) >= minimum_hours,
            blocked,
            "external_webhook_window_too_short",
            str(webhook.get("observedWindowHours") or 0),
        )
        _require(
            bool(webhook.get("hasPersistedSuccess")),
            blocked,
            "external_webhook_delivery_not_persisted",
            "persisted successful delivery evidence required",
        )

    certified = not blocked
    bundle: dict[str, Any] = {
        "schemaVersion": 1,
        "policyId": policy.get("policyId"),
        "generatedAt": _utc_now(),
        "profile": profile,
        "runtime": runtime,
        "status": "CERTIFIED" if certified else "NOT_CERTIFIED",
        "certified": certified,
        "liveActivationAllowed": False,
        "release": {
            "releaseId": release_id or None,
            "gitSha": release_git_sha or current_git_sha,
            "migrationRevision": migration or None,
            "migrationChecksum": migration_checksum or None,
            "openApiSha256": openapi_sha or None,
            "frontendAssetsSha256": frontend_sha or None,
            "database": "postgresql",
            "broker": "rabbitmq",
        },
        "dataRelease": {
            "dataReleaseId": data_release_id or None,
            "manifestSha256": data_manifest_sha or None,
        },
        "sourceBindings": source_bindings,
        "evidenceBindings": bindings,
        "blockedReasons": blocked,
    }
    if paper_observation is not None:
        bundle["paperObservation"] = paper_observation
    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps(bundle, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    return bundle


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", choices=("backtest", "paper"), required=True)
    parser.add_argument("--runtime", choices=("linux-docker", "windows-native"), required=True)
    parser.add_argument("--policy", type=Path, default=DEFAULT_POLICY)
    parser.add_argument("--release-convergence", type=Path, required=True)
    parser.add_argument("--local-data-certification", type=Path, required=True)
    parser.add_argument("--restore-drill", type=Path, required=True)
    parser.add_argument("--fault-matrix", type=Path, required=True)
    parser.add_argument("--supply-chain", type=Path, required=True)
    parser.add_argument("--paper-soak", type=Path)
    parser.add_argument("--external-webhook", type=Path)
    parser.add_argument("--windows-certificate", type=Path)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    evidence_paths = {
        "releaseConvergence": args.release_convergence,
        "localDataCertification": args.local_data_certification,
        "restoreDrill": args.restore_drill,
        "faultMatrix": args.fault_matrix,
        "supplyChain": args.supply_chain,
    }
    optional = {
        "paperSoak": args.paper_soak,
        "externalWebhook": args.external_webhook,
        "windowsCertificate": args.windows_certificate,
    }
    evidence_paths.update({name: path for name, path in optional.items() if path is not None})
    try:
        bundle = build_bundle(
            root=ROOT,
            policy_path=args.policy,
            profile=args.profile,
            runtime=args.runtime,
            evidence_paths=evidence_paths,
            output=args.output,
        )
        exit_code = 0 if bundle["certified"] else 1
    except Exception as exc:
        bundle = {
            "schemaVersion": 1,
            "generatedAt": _utc_now(),
            "profile": args.profile,
            "runtime": args.runtime,
            "status": "NOT_CERTIFIED",
            "certified": False,
            "liveActivationAllowed": False,
            "blockedReasons": [
                {"code": "certification_evaluator_error", "detail": f"{type(exc).__name__}:{exc}"}
            ],
        }
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(bundle, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        exit_code = 1
    print(json.dumps(bundle, ensure_ascii=False, indent=2, sort_keys=True))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
