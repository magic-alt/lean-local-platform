#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "web" / "backend"
FRONTEND = ROOT / "web" / "frontend"
DEFAULT_EVIDENCE = ROOT / "web" / "runtime" / "audit" / "system-verification.json"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _python() -> str:
    configured = os.environ.get("SYSTEM_VERIFY_PYTHON", "").strip()
    if configured:
        return configured
    candidate = BACKEND / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    return str(candidate) if candidate.is_file() else sys.executable


def _command(name: str) -> str:
    resolved = shutil.which(name)
    if resolved:
        return resolved
    if os.name == "nt" and not name.endswith(".cmd"):
        resolved = shutil.which(f"{name}.cmd")
        if resolved:
            return resolved
    return name


def _run_stage(
    name: str,
    command: list[str],
    *,
    cwd: Path = ROOT,
    env: dict[str, str] | None = None,
    timeout: int = 3600,
) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        completed = subprocess.run(
            command,
            cwd=cwd,
            env={**os.environ, **(env or {})},
            text=True,
            capture_output=True,
            check=False,
            timeout=timeout,
        )
        output = ((completed.stdout or "") + ("\n" + completed.stderr if completed.stderr else "")).strip()
        return {
            "name": name,
            "passed": completed.returncode == 0,
            "exitCode": completed.returncode,
            "command": command,
            "cwd": str(cwd),
            "durationSeconds": round(time.perf_counter() - started, 3),
            "outputTail": output[-12000:],
        }
    except subprocess.TimeoutExpired as exc:
        output = ((exc.stdout or "") + ("\n" + exc.stderr if exc.stderr else "")).strip()
        return {
            "name": name,
            "passed": False,
            "exitCode": None,
            "command": command,
            "cwd": str(cwd),
            "durationSeconds": round(time.perf_counter() - started, 3),
            "outputTail": output[-12000:],
            "error": f"timeout after {timeout}s",
        }
    except Exception as exc:
        return {
            "name": name,
            "passed": False,
            "exitCode": None,
            "command": command,
            "cwd": str(cwd),
            "durationSeconds": round(time.perf_counter() - started, 3),
            "outputTail": "",
            "error": f"{type(exc).__name__}: {exc}",
        }


def _git_sha() -> str | None:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=False
    )
    return result.stdout.strip() if result.returncode == 0 else None


def verify(args: argparse.Namespace) -> dict[str, Any]:
    python = _python()
    npm = _command("npm")
    npx = _command("npx")
    stages: list[dict[str, Any]] = []

    governance_commands = [
        [python, "scripts/check_repository_hygiene.py"],
        [python, "scripts/check_developer_governance.py"],
        [python, "scripts/check_frontend_api_contract.py"],
        [python, "scripts/check_oss_governance.py"],
    ]
    for command in governance_commands:
        stages.append(_run_stage(f"governance:{Path(command[-1]).stem}", command))

    stages.append(
        _run_stage(
            "backend:pytest",
            [python, "-m", "pytest", "-q"],
            cwd=BACKEND,
            timeout=args.backend_timeout,
        )
    )
    stages.append(
        _run_stage(
            "frontend:build",
            [npm, "run", "build"],
            cwd=FRONTEND,
            timeout=900,
        )
    )
    stages.append(
        _run_stage(
            "frontend:ui-audit",
            [
                npx,
                "playwright",
                "test",
                "15-ui-audit.spec.ts",
                "--project=chromium-1280",
                "--project=tablet",
                "--project=mobile",
            ],
            cwd=FRONTEND,
            env={"E2E_UI_ONLY": "1"},
            timeout=900,
        )
    )

    e2e_base_env = {
        "E2E_PYTHON": python,
        "E2E_STOP_STACK": "1",
        "E2E_REQUIRE_LEAN_RUNTIME": "0" if args.profile == "pr" else "1",
    }
    if args.profile == "pr":
        stages.append(
            _run_stage(
                "web:e2e-smoke",
                [npx, "playwright", "test", "--project=chromium", "--grep", "@smoke"],
                cwd=FRONTEND,
                env=e2e_base_env,
                timeout=args.e2e_timeout,
            )
        )
    else:
        stages.append(
            _run_stage(
                "web:e2e-full",
                [npx, "playwright", "test", "--project=chromium"],
                cwd=FRONTEND,
                env=e2e_base_env,
                timeout=args.e2e_timeout,
            )
        )

    local_cert_evidence: str | None = None
    if args.profile == "local-data":
        if args.data_dir is None:
            stages.append(
                {
                    "name": "local-data:certification",
                    "passed": False,
                    "exitCode": None,
                    "command": [],
                    "cwd": str(ROOT),
                    "durationSeconds": 0,
                    "outputTail": "",
                    "error": "--data-dir is required for profile=local-data",
                }
            )
        else:
            local_cert_path = ROOT / "web" / "runtime" / "audit" / "local-data-certification.json"
            local_cert_evidence = str(local_cert_path)
            cert_command = [
                python,
                "scripts/local_data_certification.py",
                "--data-dir",
                str(args.data_dir),
                "--evidence",
                str(local_cert_path),
            ]
            if args.local_data_symbol:
                cert_command.extend(["--symbol", args.local_data_symbol])
            if args.no_pull_image:
                cert_command.append("--no-pull-image")
            stages.append(
                _run_stage(
                    "local-data:certification",
                    cert_command,
                    cwd=ROOT,
                    timeout=args.local_data_timeout,
                )
            )
            stages.append(
                _run_stage(
                    "web:real-local-data",
                    [
                        npx,
                        "playwright",
                        "test",
                        "20-data-preview-local.spec.ts",
                        "--project=chromium",
                    ],
                    cwd=FRONTEND,
                    env={
                        **e2e_base_env,
                        "E2E_REAL_LOCAL_DATA": "1",
                        "E2E_SKIP_SEED": "1",
                        "E2E_LEAN_DATA_DIR": str(args.data_dir.expanduser().resolve()),
                        "E2E_REQUIRE_LEAN_RUNTIME": "0",
                    },
                    timeout=args.e2e_timeout,
                )
            )

    convergence_evidence: str | None = None
    if args.base_url:
        convergence_path = ROOT / "web" / "runtime" / "audit" / "release-convergence.json"
        convergence_evidence = str(convergence_path)
        stages.append(
            _run_stage(
                "release:convergence",
                [
                    python,
                    "scripts/verify_release_convergence.py",
                    "--base-url",
                    args.base_url,
                    "--evidence",
                    str(convergence_path),
                ],
                timeout=600,
            )
        )

    return {
        "schemaVersion": 1,
        "generatedAt": _utc_now(),
        "gitSha": _git_sha(),
        "profile": args.profile,
        "dataDir": str(args.data_dir.expanduser().resolve()) if args.data_dir else None,
        "baseUrl": args.base_url,
        "passed": bool(stages) and all(bool(stage.get("passed")) for stage in stages),
        "stages": stages,
        "evidence": {
            "system": str(args.evidence),
            "localData": local_cert_evidence,
            "releaseConvergence": convergence_evidence,
        },
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run one fail-closed verification ladder for the LEAN Local Platform."
    )
    parser.add_argument("--profile", choices=("pr", "full", "local-data"), default="pr")
    parser.add_argument("--data-dir", type=Path)
    parser.add_argument("--local-data-symbol")
    parser.add_argument("--base-url")
    parser.add_argument("--evidence", type=Path, default=DEFAULT_EVIDENCE)
    parser.add_argument("--backend-timeout", type=int, default=3600)
    parser.add_argument("--e2e-timeout", type=int, default=3600)
    parser.add_argument("--local-data-timeout", type=int, default=7200)
    parser.add_argument("--no-pull-image", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    args.evidence = args.evidence.expanduser().resolve()
    try:
        result = verify(args)
    except Exception as exc:
        result = {
            "schemaVersion": 1,
            "generatedAt": _utc_now(),
            "gitSha": _git_sha(),
            "profile": args.profile,
            "passed": False,
            "failure": {"type": type(exc).__name__, "detail": str(exc)},
        }
    args.evidence.parent.mkdir(parents=True, exist_ok=True)
    args.evidence.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("passed") else 1


if __name__ == "__main__":
    raise SystemExit(main())
