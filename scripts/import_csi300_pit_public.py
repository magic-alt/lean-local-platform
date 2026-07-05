#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
import urllib.request
import uuid
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT / "web" / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.core.errors import LeanWebError  # noqa: E402
from app.db import DB_PATH, init_db  # noqa: E402
from app.services.csi300_pit import (  # noqa: E402
    DEFAULT_SOURCE,
    build_membership_intervals,
    content_hash,
    materialize_membership_intervals,
    membership_counts,
    parse_adjustment_notice,
    upsert_membership_events,
    upsert_source_artifact,
)


def _load_manifest(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise RuntimeError(f"Manifest not found: {path}. Copy data_sources/csi300_pit_sources.example.json first.")
    return json.loads(path.read_text(encoding="utf-8"))


def _source_url(source: dict[str, Any], index: int) -> str:
    if source.get("url"):
        return str(source["url"])
    if source.get("path"):
        return f"file:{source['path']}"
    return f"manual:{source.get('id') or index}"


def _content_type(source: dict[str, Any], source_url: str) -> str | None:
    if source.get("content_type"):
        return str(source["content_type"])
    suffix = Path(source_url.split("?", 1)[0]).suffix.lower().lstrip(".")
    return suffix or None


def _read_source(source: dict[str, Any], *, cache_dir: Path, source_url: str) -> tuple[bytes, str | None]:
    if source.get("path"):
        path = Path(str(source["path"]))
        if not path.is_absolute():
            path = ROOT / path
        return path.read_bytes(), str(path)
    if source.get("url"):
        request = urllib.request.Request(
            str(source["url"]),
            headers={
                "User-Agent": "Mozilla/5.0 lean-platform CSI300 PIT importer",
                "Accept": "text/html,application/xhtml+xml,application/xml,application/pdf,application/vnd.ms-excel,*/*",
            },
        )
        with urllib.request.urlopen(request, timeout=int(source.get("timeout_seconds") or 30)) as response:
            content = response.read()
        cache_dir.mkdir(parents=True, exist_ok=True)
        suffix = Path(str(source["url"]).split("?", 1)[0]).suffix or ".bin"
        digest = content_hash(content)
        cached = cache_dir / f"{digest[:16]}{suffix}"
        cached.write_bytes(content)
        return content, str(cached)
    manual_content = json.dumps(source.get("manual_records") or [], ensure_ascii=False, sort_keys=True).encode("utf-8")
    return manual_content, None


def _manifest_events(
    manifest: dict[str, Any],
    *,
    cache_dir: Path,
    batch_id: str,
    dry_run: bool,
) -> tuple[list[dict[str, Any]], list[str]]:
    index_code = str(manifest.get("index_code") or "CSI300").upper()
    all_events: list[dict[str, Any]] = []
    warnings: list[str] = []
    for index, source in enumerate(manifest.get("sources") or [], start=1):
        source_url = _source_url(source, index)
        content_type = _content_type(source, source_url)
        try:
            content, local_path = _read_source(source, cache_dir=cache_dir, source_url=source_url)
            parsed = parse_adjustment_notice(
                content,
                index_code=index_code,
                source_url=source_url,
                announce_date=source["announce_date"],
                effective_date=source["effective_date"],
                content_type=content_type,
                adjustment_type=str(source.get("adjustment_type") or "regular"),
                default_action=source.get("default_action"),
                manual_records=source.get("manual_records") or [],
            )
            metadata = {
                "batch_id": batch_id,
                "announce_date": source["announce_date"],
                "effective_date": source["effective_date"],
                "adjustment_type": source.get("adjustment_type") or "regular",
                "warnings": parsed["warnings"],
            }
            if not dry_run:
                upsert_source_artifact(
                    index_code=index_code,
                    source_url=source_url,
                    raw_file_hash=parsed["raw_file_hash"],
                    local_path=local_path,
                    content_type=content_type,
                    parse_status=parsed["parse_status"],
                    metadata=metadata,
                )
            all_events.extend(parsed["events"])
            warnings.extend(f"{source_url}:{warning}" for warning in parsed["warnings"])
            print(
                f"source[{index}] status={parsed['parse_status']} events={len(parsed['events'])} "
                f"announce={source['announce_date']} effective={source['effective_date']} url={source_url}"
            )
        except Exception as exc:
            warnings.append(f"{source_url}:failed:{exc}")
            if not dry_run:
                upsert_source_artifact(
                    index_code=index_code,
                    source_url=source_url,
                    raw_file_hash=content_hash(str(exc).encode("utf-8")),
                    content_type=content_type,
                    parse_status="failed",
                    metadata={"batch_id": batch_id},
                    error=str(exc),
                )
            if source.get("required", True):
                raise
            print(f"source[{index}] failed optional url={source_url}: {exc}", file=sys.stderr)
    return all_events, warnings


def _interval_counts(intervals: list[dict[str, Any]], as_of_dates: list[str]) -> list[dict[str, Any]]:
    counts = []
    for as_of in as_of_dates:
        symbols = sorted(
            interval["symbol"]
            for interval in intervals
            if interval["start_date"] <= as_of
            and (interval.get("end_date") is None or interval["end_date"] >= as_of)
            and (interval.get("announce_date") is None or interval["announce_date"] <= as_of)
            and (interval.get("effective_date") is None or interval["effective_date"] <= as_of)
        )
        counts.append({"as_of_date": as_of, "count": len(symbols), "symbols": symbols})
    return counts


def main() -> int:
    parser = argparse.ArgumentParser(description="Import CSI300 point-in-time membership from public source manifests.")
    parser.add_argument(
        "--manifest",
        default=str(ROOT / "data_sources" / "csi300_pit_sources.json"),
        help="JSON manifest with official CSIndex notices and manual corrections.",
    )
    parser.add_argument(
        "--cache-dir",
        default=str(ROOT / "web" / "runtime" / "source-cache" / "csi300"),
        help="Directory for downloaded source artifacts.",
    )
    parser.add_argument("--replace-universe", action="store_true", help="Delete existing rows for manifest index_code before materializing.")
    parser.add_argument("--dry-run", action="store_true", help="Parse and build intervals without writing database rows.")
    parser.add_argument("--validate", action="store_true", help="Validate configured as-of dates after materialization.")
    args = parser.parse_args()

    init_db()
    manifest = _load_manifest(Path(args.manifest))
    index_code = str(manifest.get("index_code") or "CSI300").upper()
    source = str(manifest.get("source") or DEFAULT_SOURCE)
    batch_id = str(uuid.uuid4())

    events, parse_warnings = _manifest_events(manifest, cache_dir=Path(args.cache_dir), batch_id=batch_id, dry_run=args.dry_run)
    if not args.dry_run:
        upsert_membership_events(events, batch_id=batch_id)
    built = build_membership_intervals(
        index_code=index_code,
        initial_members=manifest.get("initial_members") or [],
        initial_effective_date=manifest["initial_effective_date"],
        initial_announce_date=manifest.get("initial_announce_date") or manifest["initial_effective_date"],
        events=events,
        source=source,
        batch_id=batch_id,
    )
    if not args.dry_run:
        materialize_membership_intervals(
            index_code=index_code,
            intervals=built["intervals"],
            source=source,
            batch_id=batch_id,
            replace=args.replace_universe,
        )

    print(f"database={DB_PATH}")
    print(
        f"batch_id={batch_id} index_code={index_code} sources={len(manifest.get('sources') or [])} "
        f"events={len(events)} intervals={len(built['intervals'])} dry_run={args.dry_run}"
    )
    for warning in [*parse_warnings, *built["warnings"]]:
        print(f"warning: {warning}", file=sys.stderr)

    if args.validate:
        expected = manifest.get("expected_count")
        dates = manifest.get("validate_as_of_dates") or []
        counts = _interval_counts(built["intervals"], dates) if args.dry_run else membership_counts(index_code, dates)
        for item in counts:
            print(f"validate as_of={item['as_of_date']} count={item['count']}")
            if expected is not None and int(item["count"]) != int(expected):
                print(
                    f"validation failed: as_of={item['as_of_date']} count={item['count']} expected={expected}",
                    file=sys.stderr,
                )
                return 1
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (LeanWebError, RuntimeError, OSError, KeyError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(1)
