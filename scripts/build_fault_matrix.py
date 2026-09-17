#!/usr/bin/env python3
"""Assemble release fault-injection evidence into one fail-closed matrix."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_POLICY = ROOT / "config" / "certification" / "post-migration-v1.json"
DEFAULT_OUTPUT = ROOT / "web" / "runtime" / "audit" / "fault-matrix.json"


def _load(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"evidence_not_object:{path}")
    return payload


def _parse_binding(value: str) -> tuple[str, Path]:
    if "=" not in value:
        raise ValueError(f"scenario_binding_requires_name_equals_path:{value}")
    name, raw_path = value.split("=", 1)
    name = name.strip()
    if not name:
        raise ValueError("scenario_name_required")
    return name, Path(raw_path).expanduser().resolve()


def _normalize_scenario(name: str, path: Path, payload: dict[str, Any]) -> dict[str, Any]:
    trace = payload.get("trace")
    invariants = payload.get("invariants")
    if not isinstance(trace, dict):
        trace = {
            "source": str(path),
            "status": payload.get("status"),
            "generatedAt": payload.get("generatedAt")
            or payload.get("testedAt")
            or payload.get("completedAt"),
        }
    if not isinstance(invariants, dict):
        invariants = payload.get("invariantResults")
    if not isinstance(invariants, dict):
        invariants = {
            "passed": bool(payload.get("passed")),
            "sourceStatus": payload.get("status"),
        }
    passed = bool(payload.get("passed"))
    if "passed" not in payload:
        passed = str(payload.get("status") or "").lower() in {
            "passed",
            "pass",
            "success",
            "fault_pass",
        }
    return {
        "passed": passed,
        "source": str(path),
        "gitSha": payload.get("gitSha"),
        "releaseGitSha": payload.get("releaseGitSha") or payload.get("gitSha"),
        "releaseId": payload.get("releaseId"),
        "evidenceMode": payload.get("evidenceMode") or "fault_acceptance",
        "trace": trace,
        "invariants": invariants,
        "rejectionReason": payload.get("rejectionReason") or payload.get("failure"),
        "sourceSchemaVersion": payload.get("schemaVersion"),
        "scenario": name,
    }


def build_matrix(
    *,
    policy_path: Path,
    service_restart_path: Path | None,
    scenario_paths: list[tuple[str, Path]],
) -> dict[str, Any]:
    policy = _load(policy_path)
    required = [str(item) for item in policy.get("requiredFaultScenarios") or []]
    scenarios: dict[str, dict[str, Any]] = {}
    sources: list[dict[str, Any]] = []
    identity_errors: list[dict[str, str]] = []
    duplicate_scenarios: list[str] = []
    identity: dict[str, Any] = {
        "gitSha": None,
        "releaseGitSha": None,
        "releaseId": None,
    }

    def bind_identity(source: str, payload: dict[str, Any]) -> dict[str, str]:
        source_git_sha = str(payload.get("gitSha") or "")
        release_git_sha = str(payload.get("releaseGitSha") or source_git_sha)
        release_id = str(payload.get("releaseId") or "")
        resolved = {
            "gitSha": source_git_sha,
            "releaseGitSha": release_git_sha,
            "releaseId": release_id,
        }
        for field, value in resolved.items():
            if not value:
                identity_errors.append(
                    {
                        "source": source,
                        "code": "identity_missing",
                        "detail": field,
                    }
                )
        if source_git_sha and release_git_sha and source_git_sha != release_git_sha:
            identity_errors.append(
                {
                    "source": source,
                    "code": "source_runtime_git_mismatch",
                    "detail": f"gitSha={source_git_sha},releaseGitSha={release_git_sha}",
                }
            )
        if not identity["releaseGitSha"] and release_git_sha and release_id:
            identity.update(resolved)
        elif identity["releaseGitSha"]:
            for field in ("gitSha", "releaseGitSha", "releaseId"):
                expected = str(identity.get(field) or "")
                actual = resolved[field]
                if expected and actual and expected != actual:
                    identity_errors.append(
                        {
                            "source": source,
                            "code": "identity_mismatch",
                            "detail": f"{field}:expected={expected},actual={actual}",
                        }
                    )
        return resolved

    if service_restart_path is not None:
        service_payload = _load(service_restart_path)
        service_scenarios = service_payload.get("scenarios") or {}
        if not isinstance(service_scenarios, dict):
            raise ValueError("service_restart_scenarios_invalid")
        service_identity = bind_identity(str(service_restart_path), service_payload)
        for name, item in service_scenarios.items():
            if not isinstance(item, dict):
                continue
            scenarios[str(name)] = {
                **item,
                **service_identity,
                "source": str(service_restart_path),
                "scenario": str(name),
            }
        sources.append(
            {
                "kind": "service_restart",
                "path": str(service_restart_path),
                "status": service_payload.get("status"),
                "passed": service_payload.get("passed"),
                **service_identity,
            }
        )

    for name, path in scenario_paths:
        payload = _load(path)
        scenario_identity = bind_identity(str(path), payload)
        if name in scenarios:
            duplicate_scenarios.append(name)
            continue
        scenarios[name] = _normalize_scenario(name, path, payload)
        sources.append(
            {
                "kind": "scenario",
                "scenario": name,
                "path": str(path),
                "status": payload.get("status"),
                "passed": scenarios[name]["passed"],
                **scenario_identity,
            }
        )

    missing = [name for name in required if name not in scenarios]
    failed = [name for name in required if name in scenarios and not scenarios[name].get("passed")]
    incomplete = [
        name
        for name in required
        if name in scenarios
        and (
            not isinstance(scenarios[name].get("trace"), dict)
            or not scenarios[name].get("trace")
            or not isinstance(scenarios[name].get("invariants"), dict)
            or not scenarios[name].get("invariants")
        )
    ]
    identity_missing = (
        not identity.get("releaseId")
        or not identity.get("releaseGitSha")
        or not identity.get("gitSha")
    )
    passed = (
        bool(required)
        and not missing
        and not failed
        and not incomplete
        and not identity_missing
        and not identity_errors
        and not duplicate_scenarios
    )
    return {
        "schemaVersion": 2,
        "policyId": policy.get("policyId"),
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "status": "passed" if passed else "blocked",
        "passed": passed,
        **identity,
        "requiredScenarios": required,
        "missingScenarios": missing,
        "failedScenarios": failed,
        "incompleteScenarios": incomplete,
        "identityMissing": identity_missing,
        "identityErrors": identity_errors,
        "duplicateScenarios": sorted(set(duplicate_scenarios)),
        "scenarios": scenarios,
        "sources": sources,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--policy", type=Path, default=DEFAULT_POLICY)
    parser.add_argument("--service-restart", type=Path)
    parser.add_argument(
        "--scenario",
        action="append",
        default=[],
        metavar="NAME=PATH",
        help="Bind one scenario name to a JSON evidence file. May be repeated.",
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    try:
        bindings = [_parse_binding(item) for item in args.scenario]
        payload = build_matrix(
            policy_path=args.policy,
            service_restart_path=args.service_restart,
            scenario_paths=bindings,
        )
        exit_code = 0 if payload["passed"] else 1
    except Exception as exc:
        payload = {
            "schemaVersion": 1,
            "generatedAt": datetime.now(timezone.utc).isoformat(),
            "status": "blocked",
            "passed": False,
            "failure": {"type": type(exc).__name__, "detail": str(exc)},
            "scenarios": {},
        }
        exit_code = 1
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
