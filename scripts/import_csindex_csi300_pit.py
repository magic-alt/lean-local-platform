#!/usr/bin/env python3
from __future__ import annotations

import argparse
import html
import http.client
import json
import re
import subprocess
import sys
import time
import urllib.parse
import urllib.request
import uuid
from datetime import date, timedelta
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError


ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT / "web" / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.db import DB_PATH, db, init_db  # noqa: E402
from app.services.csi300_pit import (  # noqa: E402
    build_membership_intervals,
    content_hash,
    materialize_membership_intervals,
    parse_adjustment_notice,
    upsert_membership_events,
    upsert_source_artifact,
)


BASE_URL = "https://www.csindex.com.cn/csindex-home"
OFFICIAL_SOURCE = "csindex:official"
INDEX_CODE = "CSI300"


def _json_request(path: str, *, method: str = "GET", payload: dict[str, Any] | None = None) -> dict[str, Any]:
    data = None
    headers = {
        "User-Agent": "Mozilla/5.0 lean-platform CSI300 PIT importer",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Origin": "https://www.csindex.com.cn",
        "Referer": "https://www.csindex.com.cn/",
    }
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(f"{BASE_URL}{path}", data=data, headers=headers, method=method)
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            last_error = exc
            if exc.code in {403, 404}:
                break
            time.sleep(1.0 + attempt)
        except (URLError, TimeoutError, http.client.RemoteDisconnected) as exc:
            last_error = exc
            time.sleep(1.0 + attempt)
    args = [
        "curl",
        "-L",
        "-s",
        "--fail",
        "--connect-timeout",
        "20",
        "--max-time",
        "90",
        "-H",
        "User-Agent: Mozilla/5.0 lean-platform CSI300 PIT importer",
        "-H",
        "Accept: application/json, text/plain, */*",
        "-H",
        "Accept-Language: zh-CN,zh;q=0.9,en;q=0.8",
        "-H",
        "Origin: https://www.csindex.com.cn",
        "-H",
        "Referer: https://www.csindex.com.cn/",
    ]
    if payload is not None:
        args.extend(["-H", "Content-Type: application/json", "-X", method, "-d", json.dumps(payload, ensure_ascii=False)])
    args.append(f"{BASE_URL}{path}")
    result = subprocess.run(args, check=True, capture_output=True)
    return json.loads(result.stdout.decode("utf-8"))


def _download(url: str, cache_dir: Path) -> tuple[bytes, Path]:
    cache_dir.mkdir(parents=True, exist_ok=True)
    safe_url = urllib.parse.quote(url, safe=":/?&=%.-_")
    request = urllib.request.Request(
        safe_url,
        headers={
            "User-Agent": "Mozilla/5.0 lean-platform CSI300 PIT importer",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Referer": "https://www.csindex.com.cn/",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            content = response.read()
    except (HTTPError, URLError, TimeoutError, http.client.RemoteDisconnected):
        result = subprocess.run(
            [
                "curl",
                "-L",
                "-s",
                "--fail",
                "--connect-timeout",
                "20",
                "--max-time",
                "120",
                "-H",
                "User-Agent: Mozilla/5.0 lean-platform CSI300 PIT importer",
                "-H",
                "Accept-Language: zh-CN,zh;q=0.9,en;q=0.8",
                "-H",
                "Referer: https://www.csindex.com.cn/",
                safe_url,
            ],
            check=True,
            capture_output=True,
        )
        content = result.stdout
    suffix = Path(urllib.parse.urlparse(url).path).suffix or ".bin"
    digest = content_hash(content)
    path = cache_dir / f"{digest[:16]}{suffix}"
    path.write_bytes(content)
    return content, path


def _strip_html(content: str) -> str:
    text = re.sub(r"<br\s*/?>", "\n", content or "", flags=re.I)
    text = re.sub(r"</p\s*>", "\n", text, flags=re.I)
    text = re.sub(r"<[^>]+>", "", text)
    return html.unescape(text)


def _next_weekday(day: date) -> str:
    current = day + timedelta(days=1)
    while current.weekday() >= 5:
        current += timedelta(days=1)
    return current.isoformat()


def _next_trade_date(after_date: str) -> str:
    with db() as connection:
        row = connection.execute(
            """
            select min(trade_date) as trade_date
            from (select distinct trade_date from ashare_daily_bars where trade_date > ?)
            """,
            (after_date,),
        ).fetchone()
    return row["trade_date"] if row and row["trade_date"] else _next_weekday(date.fromisoformat(after_date))


def _previous_trade_date(before_date: str) -> str:
    with db() as connection:
        row = connection.execute(
            """
            select max(trade_date) as trade_date
            from (select distinct trade_date from ashare_daily_bars where trade_date < ?)
            """,
            (before_date,),
        ).fetchone()
    if row and row["trade_date"]:
        return row["trade_date"]
    current = date.fromisoformat(before_date) - timedelta(days=1)
    while current.weekday() >= 5:
        current -= timedelta(days=1)
    return current.isoformat()


def _parse_date_parts(year: str | None, month: str, day: str, publish_date: str) -> str:
    return date(int(year or publish_date[:4]), int(month), int(day)).isoformat()


def effective_date_from_content(content: str, publish_date: str) -> str | None:
    text = _strip_html(content)
    patterns = [
        r"(?:于|将于)?\s*(?:(\d{4})年)?(\d{1,2})月(\d{1,2})日\s*收[市盘]后\s*(?:正式)?生效",
        r"(?:于|将于)?\s*(?:(\d{4})年)?(\d{1,2})月(\d{1,2})日\s*(?:正式)?生效",
        r"(?:于|将于)?\s*(?:(\d{4})年)?(\d{1,2})月(\d{1,2})日\s*起\s*(?:正式)?生效",
        r"决定于\s*(?:(\d{4})年)?(\d{1,2})月(\d{1,2})日\s*调整",
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if not match:
            continue
        anchor = _parse_date_parts(match.group(1), match.group(2), match.group(3), publish_date)
        if re.search(r"收[市盘]后", match.group(0)):
            return _next_trade_date(anchor)
        return anchor
    return None


def discover_announcements(*, rows: int = 100, sleep: float = 0.05) -> list[dict[str, Any]]:
    payload = {
        "lang": "cn",
        "classlist": [],
        "indexlist": [],
        "page": {"desc": "", "key": "", "page": 1, "rows": rows},
        "related_topics": [],
        "typelist": [],
    }
    first = _json_request("/announcement/queryAnnouncementByVo", method="POST", payload=payload)
    total_pages = int(first.get("size") or 1)
    items = list(first.get("data") or [])
    for page in range(2, total_pages + 1):
        payload["page"]["page"] = page
        response = _json_request("/announcement/queryAnnouncementByVo", method="POST", payload=payload)
        items.extend(response.get("data") or [])
        if sleep > 0:
            time.sleep(sleep)
    return items


def _is_csi300_adjustment(item: dict[str, Any]) -> bool:
    title = str(item.get("title") or "")
    theme = str(item.get("theme") or "")
    notice_type = str(item.get("noticeType") or "")
    if notice_type and notice_type != "announcement":
        return False
    if "沪深300" not in title:
        return False
    derivative_tokens = ("精明", "行业指数", "价值指数", "风格指数", "主题指数", "等权", "波动率", "相对风格")
    if any(token in title for token in derivative_tokens):
        return False
    if not any(token in title for token in ("样本", "调整", "调样")):
        return False
    return "调样" in theme or "调整" in title or "样本" in title


def notice_detail(notice_id: int, *, cache_dir: Path | None = None) -> dict[str, Any]:
    cache_path = None
    if cache_dir is not None:
        detail_dir = cache_dir / "details"
        detail_dir.mkdir(parents=True, exist_ok=True)
        cache_path = detail_dir / f"{notice_id}.json"
        if cache_path.exists():
            return json.loads(cache_path.read_text(encoding="utf-8")).get("data") or {}
    response = _json_request(f"/announcement/queryAnnouncementById?id={notice_id}")
    if response.get("code") != "200":
        raise RuntimeError(f"notice detail failed id={notice_id}: {response}")
    if cache_path is not None:
        cache_path.write_text(json.dumps(response, ensure_ascii=False, indent=2), encoding="utf-8")
    return response.get("data") or {}


def current_csi300_members() -> list[dict[str, Any]]:
    with db() as connection:
        rows = connection.execute(
            """
            select u.symbol, coalesce(s.name, u.symbol) as name, s.listed_date, s.delisted_date
            from universe_membership u
            left join securities s on s.symbol = u.symbol
            where u.universe_code = ?
              and (u.end_date is null or u.end_date >= date('now'))
            group by u.symbol
            order by u.symbol
            """,
            (INDEX_CODE,),
        ).fetchall()
    return [dict(row) for row in rows]


def derive_initial_members(final_members: list[dict[str, Any]], events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    members = {item["symbol"]: dict(item) for item in final_members}
    for event in sorted(events, key=lambda item: (item["effective_date"], item["symbol"]), reverse=True):
        if event["action_type"] == "add":
            members.pop(event["symbol"], None)
        elif event["action_type"] == "delete":
            members[event["symbol"]] = {
                "symbol": event["symbol"],
                "name": event.get("name") or event["symbol"],
                "listed_date": None,
            }
    return sorted(members.values(), key=lambda item: item["symbol"])


def cleanup_demo_and_previous_real() -> None:
    with db() as connection:
        connection.execute("delete from universe_membership where universe_code = 'CSI300_DEMO'")
        connection.execute("delete from index_membership_events where index_code = 'CSI300_DEMO'")
        connection.execute("delete from index_source_artifacts where index_code = 'CSI300_DEMO'")
        connection.execute("delete from index_membership_events where index_code = ?", (INDEX_CODE,))
        connection.execute("delete from index_source_artifacts where index_code = ?", (INDEX_CODE,))


def parse_notice_sources(detail: dict[str, Any], *, cache_dir: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    notice_id = detail["id"]
    publish_date = detail["publishDate"]
    effective_date = effective_date_from_content(detail.get("content") or "", publish_date)
    if not effective_date:
        return [], [{"notice_id": notice_id, "title": detail.get("title"), "reason": "effective_date_not_found"}]

    events: list[dict[str, Any]] = []
    sources: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    attachments = list(detail.get("enclosureList") or [])
    content_links = re.findall(r'href="(https://oss-ch\.csindex\.com\.cn/[^"]+\.(?:pdf|xls|xlsx))"', detail.get("content") or "", flags=re.I)
    seen_urls = {item.get("fileUrl") for item in attachments}
    for url in content_links:
        clean_url = html.unescape(url)
        if clean_url in seen_urls:
            continue
        seen_urls.add(clean_url)
        attachments.append({"fileName": Path(urllib.parse.urlparse(clean_url).path).name, "fileUrl": clean_url})
    if not attachments:
        content = (detail.get("content") or "").encode("utf-8")
        parsed = parse_adjustment_notice(
            content,
            index_code=INDEX_CODE,
            source_url=f"csindex-notice:{notice_id}:content",
            announce_date=publish_date,
            effective_date=effective_date,
            content_type="html",
            adjustment_type="regular",
        )
        events.extend(parsed["events"])
        sources.append(
            {
                "notice_id": notice_id,
                "title": detail.get("title"),
                "url": f"csindex-notice:{notice_id}:content",
                "hash": parsed["raw_file_hash"],
                "content_type": "html",
                "parse_status": parsed["parse_status"],
                "event_count": len(parsed["events"]),
                "warnings": parsed["warnings"],
                "announce_date": publish_date,
                "effective_date": effective_date,
            }
        )
        return events, sources

    for attachment in attachments:
        url = attachment.get("fileUrl")
        if not url:
            continue
        content, local_path = _download(url, cache_dir)
        content_type = Path(urllib.parse.urlparse(url).path).suffix.lower().lstrip(".") or None
        parsed = parse_adjustment_notice(
            content,
            index_code=INDEX_CODE,
            source_url=url,
            announce_date=publish_date,
            effective_date=effective_date,
            content_type=content_type,
            adjustment_type="regular",
        )
        events.extend(parsed["events"])
        source = {
            "notice_id": notice_id,
            "title": detail.get("title"),
            "url": url,
            "local_path": str(local_path),
            "hash": parsed["raw_file_hash"],
            "content_type": content_type,
            "parse_status": parsed["parse_status"],
            "event_count": len(parsed["events"]),
            "warnings": parsed["warnings"],
            "announce_date": publish_date,
            "effective_date": effective_date,
        }
        sources.append(source)
    if not events and detail.get("content"):
        content = (detail.get("content") or "").encode("utf-8")
        parsed = parse_adjustment_notice(
            content,
            index_code=INDEX_CODE,
            source_url=f"csindex-notice:{notice_id}:content",
            announce_date=publish_date,
            effective_date=effective_date,
            content_type="html",
            adjustment_type="regular",
        )
        if parsed["events"]:
            events.extend(parsed["events"])
            sources.append(
                {
                    "notice_id": notice_id,
                    "title": detail.get("title"),
                    "url": f"csindex-notice:{notice_id}:content",
                    "hash": parsed["raw_file_hash"],
                    "content_type": "html",
                    "parse_status": parsed["parse_status"],
                    "event_count": len(parsed["events"]),
                    "warnings": parsed["warnings"],
                    "announce_date": publish_date,
                    "effective_date": effective_date,
                }
            )
    return events, sources or warnings


def write_manifest(path: Path, *, sources: list[dict[str, Any]], initial_members: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "index_code": INDEX_CODE,
        "source": OFFICIAL_SOURCE,
        "initial_announce_date": "2005-04-08",
        "initial_effective_date": "2005-04-08",
        "initial_members": initial_members,
        "sources": sources,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _event_distribution(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    for event in events:
        key = event["effective_date"]
        item = grouped.setdefault(key, {"effective_date": key, "add": 0, "delete": 0})
        item[event["action_type"]] += 1
    return sorted(grouped.values(), key=lambda item: item["effective_date"])


def main() -> int:
    parser = argparse.ArgumentParser(description="Import real CSI300 PIT membership from official CSIndex announcements.")
    parser.add_argument("--cache-dir", default=str(ROOT / "web" / "runtime" / "source-cache" / "csi300-official"))
    parser.add_argument("--manifest-out", default=str(ROOT / "data_sources" / "csi300_pit_sources.json"))
    parser.add_argument("--rows", type=int, default=50)
    parser.add_argument("--sleep", type=float, default=0.05)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--min-events", type=int, default=200)
    parser.add_argument("--allow-incomplete", action="store_true", help="Print diagnostics without failing on incomplete reconstruction.")
    args = parser.parse_args()

    init_db()
    final_members = current_csi300_members()
    if len(final_members) != 300:
        raise RuntimeError(f"Current CSI300 final membership must be 300 before reconstruction; got {len(final_members)}.")

    announcements = discover_announcements(rows=args.rows, sleep=args.sleep)
    candidates = [item for item in announcements if _is_csi300_adjustment(item)]
    details = []
    all_events: list[dict[str, Any]] = []
    source_records: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    for item in candidates:
        try:
            detail = notice_detail(int(item["id"]), cache_dir=Path(args.cache_dir))
        except Exception as exc:
            skipped.append({"notice_id": item.get("id"), "title": item.get("title"), "reason": f"detail_failed:{exc}"})
            continue
        details.append(detail)
        events, sources_or_warnings = parse_notice_sources(detail, cache_dir=Path(args.cache_dir))
        if events:
            all_events.extend(events)
            source_records.extend(sources_or_warnings)
        else:
            skipped.extend(sources_or_warnings)
        if args.sleep > 0:
            time.sleep(args.sleep)

    deduped = {(event["symbol"], event["action_type"], event["effective_date"]): event for event in all_events}
    events = sorted(deduped.values(), key=lambda item: (item["effective_date"], item["action_type"], item["symbol"]))
    initial_members = derive_initial_members(final_members, events)
    diagnostics = {
        "announcements": len(announcements),
        "candidates": candidates,
        "details": len(details),
        "sources": source_records,
        "skipped": skipped,
        "events": len(events),
        "event_distribution": _event_distribution(events),
        "initial_members_count": len(initial_members),
        "final_members_count": len(final_members),
    }
    diagnostics_path = Path(args.cache_dir) / "diagnostics.json"
    diagnostics_path.parent.mkdir(parents=True, exist_ok=True)
    diagnostics_path.write_text(json.dumps(diagnostics, ensure_ascii=False, indent=2), encoding="utf-8")

    if len(events) < args.min_events and not args.allow_incomplete:
        print(f"diagnostics={diagnostics_path}")
        raise RuntimeError(f"Parsed too few CSI300 events: {len(events)} < {args.min_events}. Not writing database.")
    if len(initial_members) != 300 and not args.allow_incomplete:
        print(f"diagnostics={diagnostics_path}")
        raise RuntimeError(f"Derived initial CSI300 membership count must be 300; got {len(initial_members)}. Not writing database.")

    batch_id = str(uuid.uuid4())
    built = build_membership_intervals(
        index_code=INDEX_CODE,
        initial_members=initial_members,
        initial_announce_date="2005-04-08",
        initial_effective_date="2005-04-08",
        events=events,
        source=OFFICIAL_SOURCE,
        batch_id=batch_id,
        previous_trade_date_fn=_previous_trade_date,
    )

    if not args.dry_run:
        cleanup_demo_and_previous_real()
        for source in source_records:
            upsert_source_artifact(
                index_code=INDEX_CODE,
                source_url=source["url"],
                raw_file_hash=source["hash"],
                local_path=source.get("local_path"),
                content_type=source.get("content_type"),
                parse_status=source["parse_status"],
                metadata={
                    "notice_id": source["notice_id"],
                    "title": source["title"],
                    "announce_date": source["announce_date"],
                    "effective_date": source["effective_date"],
                    "event_count": source["event_count"],
                    "warnings": source.get("warnings") or [],
                },
            )
        upsert_membership_events(events, batch_id=batch_id)
        materialize_membership_intervals(
            index_code=INDEX_CODE,
            intervals=built["intervals"],
            source=OFFICIAL_SOURCE,
            batch_id=batch_id,
            replace=True,
        )
        write_manifest(Path(args.manifest_out), sources=source_records, initial_members=initial_members)

    print(f"database={DB_PATH}")
    print(
        f"announcements={len(announcements)} candidates={len(candidates)} details={len(details)} "
        f"sources={len(source_records)} events={len(events)} intervals={len(built['intervals'])} "
        f"initial_members={len(initial_members)} final_members={len(final_members)} batch_id={batch_id} dry_run={args.dry_run}"
    )
    if skipped:
        print(f"skipped={len(skipped)}")
        for item in skipped[:20]:
            print(f"skip notice_id={item.get('notice_id')} title={item.get('title')} reason={item.get('reason')}")
    if built["warnings"]:
        print(f"build_warnings={len(built['warnings'])}")
        for warning in built["warnings"][:30]:
            print(f"warning: {warning}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
