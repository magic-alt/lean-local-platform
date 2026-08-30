#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


PLATFORM_DIR = Path(__file__).resolve().parents[1]
BACKEND_DIR = PLATFORM_DIR / "web" / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from app.reporting.html_report import REPORT_LAYOUT_VERSION, build_report  # noqa: E402


@dataclass(frozen=True)
class ReportTarget:
    run_id: str
    result_json: Path
    report_html: Path


def _result_for_report(report_html: Path) -> Path | None:
    results_dir = report_html.parent
    run_id = results_dir.parent.name if results_dir.name == "results" else ""
    preferred = results_dir / f"{run_id}.json" if run_id else None
    if preferred and preferred.is_file():
        return preferred
    demo_result = results_dir / "docker-demo-backtest.json"
    if demo_result.is_file():
        return demo_result
    excluded = ("-summary.json", "-order-events.json", "artifact-manifest.json")
    candidates = [
        path
        for path in sorted(results_dir.glob("*.json"))
        if not path.name.endswith(excluded) and not path.name.startswith("data-monitor-report-")
    ]
    return candidates[0] if len(candidates) == 1 else None


def discover_targets(platform_dir: Path = PLATFORM_DIR) -> list[ReportTarget]:
    reports = list((platform_dir / "web" / "runtime" / "runs").glob("*/results/report.html"))
    reports.extend((platform_dir / "web" / "runtime" / "legacy").glob("**/report.html"))
    targets = []
    for report_html in sorted(set(reports)):
        result_json = _result_for_report(report_html)
        if result_json is None:
            continue
        run_id = report_html.parent.parent.name if report_html.parent.name == "results" else result_json.stem
        targets.append(ReportTarget(run_id, result_json, report_html))
    return targets


def _atomic_write(path: Path, text: str) -> None:
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        temporary.replace(path)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def _refresh_manifest(target: ReportTarget) -> Path | None:
    manifest_path = target.report_html.parent / "artifact-manifest.json"
    if not manifest_path.is_file():
        return None
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    stat = target.report_html.stat()
    artifacts = manifest.get("artifacts") or []
    report_item = next(
        (
            item
            for item in artifacts
            if item.get("name") == "report.html" or item.get("relativePath") == "results/report.html"
        ),
        None,
    )
    if report_item is None:
        report_item = {
            "name": "report.html",
            "kind": "lean-output",
            "path": str(target.report_html),
            "relativePath": "results/report.html",
        }
        artifacts.append(report_item)
        manifest["artifacts"] = artifacts
    report_item.update(
        {
            "size": stat.st_size,
            "mtime": stat.st_mtime,
            "layout": REPORT_LAYOUT_VERSION,
        }
    )
    manifest["reportLayout"] = REPORT_LAYOUT_VERSION
    manifest["reportRegeneratedAt"] = datetime.now(timezone.utc).isoformat()
    _atomic_write(manifest_path, json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    return manifest_path


def regenerate(target: ReportTarget, *, archive: bool = False) -> None:
    payload = json.loads(target.result_json.read_text(encoding="utf-8"))
    _atomic_write(target.report_html, build_report(payload, target.result_json))
    manifest_path = _refresh_manifest(target)
    if archive:
        from app.services.db_object_store import put_file

        put_file(
            "backtest-results",
            f"{target.run_id}/artifacts/report.html",
            target.report_html,
            content_type="text/html",
            metadata={
                "job_id": target.run_id,
                "kind": "html-report",
                "artifact_name": "report.html",
                "layout": REPORT_LAYOUT_VERSION,
                "regenerated": True,
            },
        )
        if manifest_path is not None:
            put_file(
                "backtest-results",
                f"{target.run_id}/artifacts/artifact-manifest.json",
                manifest_path,
                content_type="application/json",
                metadata={
                    "job_id": target.run_id,
                    "kind": "artifact-manifest",
                    "artifact_name": "artifact-manifest.json",
                    "report_layout": REPORT_LAYOUT_VERSION,
                    "regenerated": True,
                },
            )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Regenerate existing LEAN HTML reports with the current canonical report layout."
    )
    parser.add_argument("--dry-run", action="store_true", help="List report targets without writing files.")
    parser.add_argument(
        "--archive",
        action="store_true",
        help="Also add the regenerated report as the latest PostgreSQL stored-object version.",
    )
    args = parser.parse_args()

    targets = discover_targets()
    regenerated = 0
    failed = []
    for target in targets:
        if args.dry_run:
            print(f"would regenerate {target.report_html} from {target.result_json}")
            continue
        try:
            regenerate(target, archive=args.archive)
            regenerated += 1
            print(f"regenerated {target.report_html}")
        except Exception as exc:
            failed.append((target.report_html, str(exc)))
            print(f"failed {target.report_html}: {exc}", file=sys.stderr)
    print(
        json.dumps(
            {
                "layout": REPORT_LAYOUT_VERSION,
                "discovered": len(targets),
                "regenerated": regenerated,
                "failed": len(failed),
                "archived": bool(args.archive and not args.dry_run),
            },
            ensure_ascii=False,
        )
    )
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
