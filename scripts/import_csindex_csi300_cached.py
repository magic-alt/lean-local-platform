#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
import uuid
from collections import Counter
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT / "web" / "backend"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.db import database_descriptor, db, init_db  # noqa: E402
from app.services.csi300_pit import (  # noqa: E402
    build_membership_intervals,
    content_hash,
    materialize_membership_intervals,
    parse_adjustment_notice,
    upsert_membership_events,
    upsert_source_artifact,
)
from scripts.import_csindex_csi300_pit import (  # noqa: E402
    INDEX_CODE,
    _previous_trade_date,
    current_csi300_members,
    derive_initial_members,
)


SOURCE = "csindex:official:cache"
COVERAGE_START = "2017-12-08"
COVERAGE_NOTE = (
    "Official CSIndex cached attachment reconstruction covers CSI300 from 2017-12-08 onward. "
    "It is real source data, but not full 2005-present history because earlier official notices "
    "were not available in the local cache."
)

CACHED_SOURCES = [
    {
        "file": "e291b4d9f388279e.xlsx",
        "announce_date": "2017-11-27",
        "effective_date": "2017-12-11",
        "title": "关于调整沪深300和中证香港100等指数样本股的公告",
    },
    {
        "file": "4afaa21688b3f00b.xlsx",
        "announce_date": "2018-05-28",
        "effective_date": "2018-06-11",
        "title": "关于调整沪深300和中证香港100等指数样本股的公告",
    },
    {
        "file": "ff9c823bc031d7ac.xlsx",
        "announce_date": "2018-11-30",
        "effective_date": "2018-12-17",
        "title": "沪深300、上证50和中证500等指数2018年第二次定期调整样本股",
    },
    {
        "file": "4e1908605be2b722.xls",
        "announce_date": "2019-05-31",
        "effective_date": "2019-06-17",
        "title": "沪深300、上证50和中证500等指数2019年第一次定期调整样本股",
    },
    {
        "file": "41605c35abf583c2.xlsx",
        "announce_date": "2019-11-29",
        "effective_date": "2019-12-16",
        "title": "沪深300、上证50和中证500等指数2019年第二次定期调整样本股",
    },
    {
        "file": "1c1df5893a9f2a68.xlsx",
        "announce_date": "2020-05-29",
        "effective_date": "2020-06-15",
        "title": "上交所及中证指数调整沪深300、上证50和中证500等指数样本股",
    },
    {
        "file": "1094e0a6f284a6a6.xlsx",
        "announce_date": "2020-11-27",
        "effective_date": "2020-12-14",
        "title": "上交所及中证指数调整沪深300、上证50、科创50和中证500等指数样本",
    },
    {
        "file": "ea291da157e67749.xlsx",
        "announce_date": "2021-05-28",
        "effective_date": "2021-06-15",
        "title": "关于调整沪深300和中证香港100等指数样本的公告",
    },
    {
        "file": "f6b9d596f3fa6072.xlsx",
        "announce_date": "2021-11-26",
        "effective_date": "2021-12-13",
        "title": "关于调整沪深300和中证香港100等指数样本的公告",
    },
    {
        "file": "a3cceb28f6df96a7.xlsx",
        "announce_date": "2022-05-27",
        "effective_date": "2022-06-13",
        "title": "关于沪深300和中证香港100等指数定期调整结果的公告",
    },
    {
        "file": "acbf06876606a980.xlsx",
        "announce_date": "2022-11-25",
        "effective_date": "2022-12-12",
        "title": "关于沪深300和中证香港100等指数定期调整结果的公告",
    },
    {
        "file": "5b6b0487112108e6.pdf",
        "announce_date": "2023-05-26",
        "effective_date": "2023-06-12",
        "title": "关于沪深300、中证500、中证1000等指数定期调整结果的公告",
    },
    {
        "file": "1ccc9012bcb5e539.pdf",
        "announce_date": "2023-11-24",
        "effective_date": "2023-12-11",
        "title": "关于沪深300、中证500、中证1000等指数定期调整结果的公告",
    },
    {
        "file": "bfcdac63888f3d85.pdf",
        "announce_date": "2024-05-31",
        "effective_date": "2024-06-17",
        "title": "关于沪深300、中证500、中证1000等指数定期调整结果的公告",
    },
    {
        "file": "e40f15343f472f08.pdf",
        "announce_date": "2024-11-29",
        "effective_date": "2024-12-16",
        "title": "关于沪深300、中证500、中证1000、中证A500等指数定期调整结果的公告",
    },
    {
        "file": "6a114671b42b9926.pdf",
        "announce_date": "2025-05-30",
        "effective_date": "2025-06-16",
        "title": "关于沪深300、中证500、中证1000、中证A500等指数定期调整结果的公告",
    },
    {
        "file": "e8d0279d40e5e351.pdf",
        "announce_date": "2025-11-28",
        "effective_date": "2025-12-15",
        "title": "关于沪深300、中证500、中证1000、中证A500等指数定期调整结果的公告",
    },
    {
        "file": "63301b60a2a2040c.pdf",
        "announce_date": "2026-05-29",
        "effective_date": "2026-06-15",
        "title": "关于沪深300、中证500、中证1000、中证A500等指数定期调整结果的公告",
    },
]

MANUAL_EVENTS = [
    {
        "source_url": "csindex-notice:15546:manual-temp",
        "announce_date": "2025-02-06",
        "effective_date": "2025-03-04",
        "adjustment_type": "temp",
        "events": [
            {"symbol": "600837", "name": "海通证券", "action_type": "delete"},
            {"symbol": "601058", "name": "赛轮轮胎", "action_type": "add"},
        ],
        "title": "关于调整沪深300等指数样本的公告",
        "note": "Official notice stated the change takes effect from Haitong Securities delisting date.",
    },
    {
        "source_url": "csindex-notice:1006022:manual-temp",
        "announce_date": "2025-07-25",
        "effective_date": "2025-09-05",
        "adjustment_type": "temp",
        "events": [
            {"symbol": "601989", "name": "中国重工", "action_type": "delete"},
            {"symbol": "601298", "name": "青岛港", "action_type": "add"},
        ],
        "title": "关于调整沪深300等指数样本的公告",
        "note": "Official notice stated the change takes effect from China Shipbuilding Industry delisting date.",
    },
]


def _parse_cached_sources(cache_dir: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    all_events: list[dict[str, Any]] = []
    source_records: list[dict[str, Any]] = []
    for source in CACHED_SOURCES:
        path = cache_dir / source["file"]
        if not path.exists():
            raise RuntimeError(f"Missing cached official source: {path}")
        content = path.read_bytes()
        parsed = parse_adjustment_notice(
            content,
            index_code=INDEX_CODE,
            source_url=f"csindex-cache:{source['file']}",
            announce_date=source["announce_date"],
            effective_date=source["effective_date"],
            content_type=path.suffix.lstrip("."),
            adjustment_type="regular",
        )
        if not parsed["events"]:
            raise RuntimeError(f"No CSI300 events parsed from official source: {path}")
        all_events.extend(parsed["events"])
        source_records.append(
            {
                **source,
                "url": f"csindex-cache:{source['file']}",
                "local_path": str(path),
                "hash": parsed["raw_file_hash"],
                "content_type": path.suffix.lstrip("."),
                "parse_status": parsed["parse_status"],
                "event_count": len(parsed["events"]),
                "warnings": parsed["warnings"],
            }
        )
    return all_events, source_records


def _manual_events() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    events: list[dict[str, Any]] = []
    sources: list[dict[str, Any]] = []
    for item in MANUAL_EVENTS:
        payload = json.dumps(item, ensure_ascii=False, sort_keys=True).encode("utf-8")
        raw_hash = content_hash(payload)
        for event in item["events"]:
            events.append(
                {
                    "index_code": INDEX_CODE,
                    "symbol": event["symbol"],
                    "name": event["name"],
                    "action_type": event["action_type"],
                    "adjustment_type": item["adjustment_type"],
                    "announce_date": item["announce_date"],
                    "effective_date": item["effective_date"],
                    "source_url": item["source_url"],
                    "raw_file_hash": raw_hash,
                    "parse_status": "manual_verified",
                }
            )
        sources.append(
            {
                "url": item["source_url"],
                "local_path": None,
                "hash": raw_hash,
                "content_type": "manual",
                "parse_status": "manual_verified",
                "event_count": len(item["events"]),
                "warnings": [],
                "announce_date": item["announce_date"],
                "effective_date": item["effective_date"],
                "title": item["title"],
                "note": item["note"],
            }
        )
    return events, sources


def _dedupe_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped = {(event["symbol"], event["action_type"], event["effective_date"]): event for event in events}
    return sorted(deduped.values(), key=lambda item: (item["effective_date"], item["action_type"], item["symbol"]))


def _cleanup_previous() -> None:
    with db() as connection:
        connection.execute("delete from universe_membership where universe_code = 'CSI300_DEMO'")
        connection.execute("delete from index_membership_events where index_code = 'CSI300_DEMO'")
        connection.execute("delete from index_source_artifacts where index_code = 'CSI300_DEMO'")
        connection.execute("delete from universe_membership where universe_code = ?", (INDEX_CODE,))
        connection.execute("delete from index_membership_events where index_code = ?", (INDEX_CODE,))
        connection.execute("delete from index_source_artifacts where index_code = ?", (INDEX_CODE,))


def _write_manifest(path: Path, *, source_records: list[dict[str, Any]], initial_members: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "index_code": INDEX_CODE,
        "source": SOURCE,
        "coverage_status": "partial_verified_from_official_cache",
        "coverage_start": COVERAGE_START,
        "coverage_note": COVERAGE_NOTE,
        "missing_history_before": COVERAGE_START,
        "initial_reconstruction": {
            "method": "reverse_events_from_current_membership",
            "member_count": len(initial_members),
            "as_of_date": COVERAGE_START,
        },
        "initial_members": initial_members,
        "sources": source_records,
        "manual_events": MANUAL_EVENTS,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Import CSI300 PIT membership from cached official CSIndex files.")
    parser.add_argument("--cache-dir", default=str(ROOT / "web" / "runtime" / "source-cache" / "csi300-official"))
    parser.add_argument("--manifest-out", default=str(ROOT / "data_sources" / "csi300_pit_sources.json"))
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--acknowledge-partial-coverage",
        action="store_true",
        help="Required for writes because the cached official sources currently cover 2017-12-08 onward, not full 2005 history.",
    )
    args = parser.parse_args()

    init_db()
    final_members = current_csi300_members()
    if len(final_members) != 300:
        raise RuntimeError(f"Current CSI300 final membership must be 300 before reconstruction; got {len(final_members)}.")

    events, source_records = _parse_cached_sources(Path(args.cache_dir))
    manual_events, manual_sources = _manual_events()
    events = _dedupe_events(events + manual_events)
    source_records.extend(manual_sources)
    initial_members = derive_initial_members(final_members, events)
    if len(initial_members) != 300:
        raise RuntimeError(f"Derived initial CSI300 membership count must be 300; got {len(initial_members)}.")

    batch_id = str(uuid.uuid4())
    built = build_membership_intervals(
        index_code=INDEX_CODE,
        initial_members=initial_members,
        initial_announce_date="2017-11-27",
        initial_effective_date=COVERAGE_START,
        events=events,
        source=SOURCE,
        batch_id=batch_id,
        previous_trade_date_fn=_previous_trade_date,
    )
    if built["warnings"]:
        raise RuntimeError(f"CSI300 interval build warnings: {built['warnings'][:20]}")

    active = {item["symbol"] for item in built["intervals"] if item.get("end_date") is None}
    current = {item["symbol"] for item in final_members}
    if active != current:
        raise RuntimeError(
            "Final active CSI300 members do not match current membership: "
            f"missing={sorted(current - active)[:20]} extra={sorted(active - current)[:20]}"
        )

    if not args.dry_run:
        if not args.acknowledge_partial_coverage:
            raise RuntimeError("Refusing to write without --acknowledge-partial-coverage.")
        _cleanup_previous()
        for source in source_records:
            upsert_source_artifact(
                index_code=INDEX_CODE,
                source_url=source["url"],
                raw_file_hash=source["hash"],
                local_path=source.get("local_path"),
                content_type=source.get("content_type"),
                parse_status=source["parse_status"],
                metadata={
                    "title": source.get("title"),
                    "announce_date": source["announce_date"],
                    "effective_date": source["effective_date"],
                    "event_count": source["event_count"],
                    "warnings": source.get("warnings") or [],
                    "coverage_start": COVERAGE_START,
                    "coverage_status": "partial_verified_from_official_cache",
                    "note": source.get("note"),
                },
            )
        upsert_membership_events(events, batch_id=batch_id)
        materialize_membership_intervals(
            index_code=INDEX_CODE,
            intervals=built["intervals"],
            source=SOURCE,
            batch_id=batch_id,
            replace=True,
        )
        _write_manifest(Path(args.manifest_out), source_records=source_records, initial_members=initial_members)

    counts = Counter(event["action_type"] for event in events)
    print(f"database={json.dumps(database_descriptor(), ensure_ascii=False)}")
    print(
        f"coverage_start={COVERAGE_START} source={SOURCE} sources={len(source_records)} "
        f"events={len(events)} add={counts['add']} delete={counts['delete']} "
        f"intervals={len(built['intervals'])} initial_members={len(initial_members)} "
        f"final_members={len(final_members)} batch_id={batch_id} dry_run={args.dry_run}"
    )
    print(COVERAGE_NOTE)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
