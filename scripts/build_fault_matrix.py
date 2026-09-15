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
            "generatedAt": payload.get("generatedAt") or payload.get("testedAt") or payload.get("completedAt"),
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

    if service_restart_path is not None:
        service_payload = _load(service_restart_path)
        service_scenarios = service_payload.get("scenarios") or {}
        if not isinstance(service_scenarios, dict):
            raise ValueError("service_restart_scenarios_invalid")
        for name, item in service_scenarios.items():
            if not isinstance(item, dict):
                continue
            scenarios[str(name)] = {
                **item,
                "source": str(service_restart_path),
                "scenario": str(name),
            }
        sources.append(
            {
                "kind": "service_restart",
                "path": str(service_restart_path),
                "status": service_payload.get("status"),
                "passed": service_payload.get("passed"),
            }
        )

    for name, path in scenario_paths:
        payload = _load(path)
        scenarios[name] = _normalize_scenario(name, path, payload)
        sources.append(
            {
                "kind": "scenario",
                "scenario": name,
                "path": str(path),
                "status": payload.get("status"),
                "passed": scenarios[name]["passed"],
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
    passed = bool(required) and not missing and not failed and not incomplete
    return {
        "schemaVersion": 1,
        "policyId": policy.get("policyId"),
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "status": "passed" if passed else "blocked",
        "passed": passed,
        "requiredScenarios": required,
        "missingScenarios": missing,
        "failedScenarios": failed,
        "incompleteScenarios": incomplete,
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
