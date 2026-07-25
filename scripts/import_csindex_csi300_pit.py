#!/usr/bin/env python3
from __future__ import annotations

import argparse
import calendar
import hashlib
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
from functools import lru_cache
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError


ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT / "web" / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.db import database_descriptor, db, init_db  # noqa: E402
from app.services.csi300_pit import (  # noqa: E402
    build_membership_intervals,
    content_hash,
    materialize_membership_intervals,
    parse_adjustment_notice,
    tables_from_content,
    upsert_membership_events,
    upsert_source_artifact,
)


BASE_URL = "https://www.csindex.com.cn/csindex-home"
OFFICIAL_SOURCE = "csindex:official"
INDEX_CODE = "CSI300"
INITIAL_EFFECTIVE_DATE = "2005-04-08"
INITIAL_SNAPSHOT_EFFECTIVE_DATE = "2005-07-01"
OFFICIAL_DETAIL_URL = f"{BASE_URL}/announcement/queryAnnouncementById?id={{notice_id}}"
# The current announcement listing no longer returns this still-fetchable
# official notice.  Retain its immutable identifier so clean bundle rebuilds
# do not lose the 600472 -> 600380 corporate-action interval.
RETIRED_OFFICIAL_NOTICES = (
    {
        "id": 47,
        "title": "关于调整沪深300和中证200等指数样本股的公告",
        "theme": "指数调样",
        "publishDate": "2007-12-25",
        "noticeType": "announcement",
    },
)


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


def _download(url: str, cache_dir: Path, *, offline: bool = False) -> tuple[bytes, Path]:
    cache_dir.mkdir(parents=True, exist_ok=True)
    download_index_path = cache_dir / "download-index.json"
    download_index: dict[str, Any] = {}
    if download_index_path.exists():
        try:
            download_index = json.loads(download_index_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            download_index = {}
    cached = download_index.get(url) or {}
    cached_path = cache_dir / str(cached.get("file") or "")
    if cached_path.is_file():
        content = cached_path.read_bytes()
        if content_hash(content) == cached.get("sha256"):
            return content, cached_path
    diagnostics_path = cache_dir / "diagnostics.json"
    if diagnostics_path.exists():
        try:
            diagnostics = json.loads(diagnostics_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            diagnostics = {}
        prior = next(
            (item for item in diagnostics.get("sources") or [] if item.get("url") == url and item.get("hash")),
            None,
        )
        if prior:
            suffix = Path(urllib.parse.urlparse(url).path).suffix or ".bin"
            prior_path = cache_dir / f"{str(prior['hash'])[:16]}{suffix}"
            if prior_path.is_file() and content_hash(prior_path.read_bytes()) == prior["hash"]:
                download_index[url] = {"file": prior_path.name, "sha256": prior["hash"]}
                download_index_path.write_text(
                    json.dumps(download_index, ensure_ascii=False, indent=2, sort_keys=True),
                    encoding="utf-8",
                )
                return prior_path.read_bytes(), prior_path
    if offline:
        raise RuntimeError(f"Official attachment is absent from the immutable offline bundle: {url}")
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
    download_index[url] = {"file": path.name, "sha256": digest}
    download_index_path.write_text(
        json.dumps(download_index, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
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


@lru_cache(maxsize=256)
def _next_trade_date(after_date: str) -> str:
    with db() as connection:
        row = connection.execute(
            """
            select min(trade_date) as trade_date
            from (select distinct trade_date from ashare_daily_bars where trade_date > ?) as trade_dates
            """,
            (after_date,),
        ).fetchone()
    return row["trade_date"] if row and row["trade_date"] else _next_weekday(date.fromisoformat(after_date))


@lru_cache(maxsize=256)
def _previous_trade_date(before_date: str) -> str:
    with db() as connection:
        row = connection.execute(
            """
            select max(trade_date) as trade_date
            from (select distinct trade_date from ashare_daily_bars where trade_date < ?) as trade_dates
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
    publish = date.fromisoformat(publish_date)
    candidate = date(int(year or publish.year), int(month), int(day))
    if year is None and candidate < publish - timedelta(days=31):
        candidate = date(publish.year + 1, int(month), int(day))
    return candidate.isoformat()


def _first_trade_date(year: int, month: int) -> str:
    start = date(year, month, 1)
    end = date(year, month, calendar.monthrange(year, month)[1])
    with db() as connection:
        row = connection.execute(
            """
            select min(trade_date) as trade_date
            from (select distinct trade_date from ashare_daily_bars
                  where trade_date between ? and ?) as trade_dates
            """,
            (start.isoformat(), end.isoformat()),
        ).fetchone()
    if row and row["trade_date"]:
        return str(row["trade_date"])
    current = start
    while current.weekday() >= 5:
        current += timedelta(days=1)
    return current.isoformat()


def _delisting_date_from_content(content: str, publish_date: str) -> str | None:
    text = _strip_html(content)
    if not re.search(r"(?:退市|终止上市).{0,8}(?:之日|日起|生效)", text):
        return None
    symbols = sorted(set(re.findall(r"(?<!\d)([036]\d{5})(?!\d)", text)))
    if not symbols:
        return None
    placeholders = ",".join("?" for _ in symbols)
    with db() as connection:
        rows = connection.execute(
            f"""
            select distinct delisted_date
            from securities
            where symbol in ({placeholders}) and delisted_date is not null
              and delisted_date >= ?
            order by delisted_date
            """,
            (*symbols, publish_date),
        ).fetchall()
    dates = [str(row["delisted_date"]) for row in rows if row["delisted_date"]]
    return dates[0] if len(set(dates)) == 1 else None


def effective_date_from_content(content: str, publish_date: str) -> str | None:
    text = re.sub(r"\s+", "", _strip_html(content))
    patterns = [
        r"(?:于|将于)?\s*(?:(\d{4})年)?(\d{1,2})月(\d{1,2})日\s*收[市盘]后\s*(?:正式)?生效",
        r"(?:于|将于)?\s*(?:(\d{4})年)?(\d{1,2})月(\d{1,2})日\s*(?:正式)?生效",
        r"(?:于|将于)?\s*(?:(\d{4})年)?(\d{1,2})月(\d{1,2})日\s*起\s*(?:正式)?生效",
        r"决定于\s*(?:(\d{4})年)?(\d{1,2})月(\d{1,2})日\s*调整",
        r"(?:决定)?自\s*(?:(\d{4})年)?(\d{1,2})月(\d{1,2})日\s*起",
        r"(?:将于|决定于)\s*(?:(\d{4})年)?(\d{1,2})月(\d{1,2})日\s*调整",
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if not match:
            continue
        anchor = _parse_date_parts(match.group(1), match.group(2), match.group(3), publish_date)
        if re.search(r"收[市盘]后", match.group(0)):
            return _next_trade_date(anchor)
        return anchor
    first_trade = re.search(
        r"(?:决定于|将于)\s*(?:(\d{4})年)?(\d{1,2})月第一个交易日\s*调整",
        text,
    )
    if first_trade:
        publish = date.fromisoformat(publish_date)
        year = int(first_trade.group(1) or publish.year)
        month = int(first_trade.group(2))
        if first_trade.group(1) is None and month < publish.month:
            year += 1
        return _first_trade_date(year, month)
    return _delisting_date_from_content(content, publish_date)


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
    if (
        "调样" in theme
        and "指数调整" in title
        and any(token in title for token in ("退市", "退巿", "上市", "合并", "私有化"))
    ):
        # Some corporate-action notices name only the security in the title;
        # the official attachment carries the affected index-code rows.
        return True
    if "沪深300" not in title:
        return False
    derivative_tokens = ("精明", "行业指数", "价值指数", "风格指数", "主题指数", "等权", "波动率", "相对风格")
    if any(token in title for token in derivative_tokens):
        return False
    if not any(token in title for token in ("样本", "调整", "调样")):
        return False
    return "调样" in theme or "调整" in title or "样本" in title


def notice_detail(
    notice_id: int,
    *,
    cache_dir: Path | None = None,
    offline: bool = False,
) -> dict[str, Any]:
    cache_path = None
    if cache_dir is not None:
        detail_dir = cache_dir / "details"
        detail_dir.mkdir(parents=True, exist_ok=True)
        cache_path = detail_dir / f"{notice_id}.json"
        if cache_path.exists():
            return json.loads(cache_path.read_text(encoding="utf-8")).get("data") or {}
    if offline:
        raise RuntimeError(f"Official notice {notice_id} is absent from the immutable offline bundle.")
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


def official_initial_members(
    details: list[dict[str, Any]],
    events: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    candidates = [
        detail
        for detail in details
        if str(detail.get("publishDate") or "").startswith("2005-")
        and "样本股名单" in str(detail.get("title") or "")
        and "7月1日"
        in re.sub(
            r"\s+",
            "",
            f"{detail.get('title') or ''} {_strip_html(str(detail.get('content') or ''))}",
        )
    ]
    snapshots: list[tuple[list[dict[str, Any]], dict[str, Any]]] = []
    for detail in candidates:
        content = str(detail.get("content") or "").encode("utf-8")
        members: dict[str, dict[str, Any]] = {}
        for frame in tables_from_content(
            content,
            source_url=OFFICIAL_DETAIL_URL.format(notice_id=detail["id"]),
            content_type="html",
        ):
            rows = frame.astype(str).values.tolist()
            for row in rows:
                for index, value in enumerate(row[:-1]):
                    text = str(value).strip()
                    if not re.fullmatch(r"\d{6}(?:\.0)?", text):
                        continue
                    symbol = text.split(".", 1)[0].zfill(6)
                    name = str(row[index + 1]).strip()
                    if name and name.lower() not in {"nan", "none"}:
                        members[symbol] = {"symbol": symbol, "name": name}
        if len(members) == 300:
            snapshots.append(
                (
                    sorted(members.values(), key=lambda item: item["symbol"]),
                    {
                        "notice_id": detail["id"],
                        "title": detail.get("title"),
                        "publish_date": detail.get("publishDate"),
                        "announce_date": detail.get("publishDate"),
                        "effective_date": INITIAL_SNAPSHOT_EFFECTIVE_DATE,
                        "url": OFFICIAL_DETAIL_URL.format(notice_id=detail["id"]),
                        "hash": content_hash(content),
                        "content_type": "html",
                        "parse_status": "snapshot_verified",
                        "event_count": 0,
                        "warnings": [],
                    },
                )
            )
    if not snapshots:
        raise RuntimeError("Official CSI300 2005-07-01 300-member snapshot was not found in the source bundle.")
    snapshot, source = snapshots[0]
    early_events = [
        event
        for event in events
        if INITIAL_EFFECTIVE_DATE < event["effective_date"] <= INITIAL_SNAPSHOT_EFFECTIVE_DATE
    ]
    initial_members = derive_initial_members(snapshot, early_events)
    if len(initial_members) != 300:
        raise RuntimeError(
            "Official CSI300 initial membership reconstruction must contain 300 members; "
            f"got {len(initial_members)}."
        )
    source["reconstruction"] = {
        "method": "reverse_official_2005_07_01_snapshot_with_official_2005_07_01_adjustment",
        "snapshotMemberCount": len(snapshot),
        "reversedEventCount": len(early_events),
        "initialEffectiveDate": INITIAL_EFFECTIVE_DATE,
    }
    return initial_members, source


def _variable_termination_events(detail: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    text = re.sub(r"\s+", "", _strip_html(str(detail.get("content") or "")))
    if "终止上市生效日起" not in text or "依次调入" not in text:
        return [], None
    before, after = text.split("依次调入", 1)
    company_pattern = r"([^，。、；：和]{1,24})（([036]\d{5})）"
    outgoing = re.findall(company_pattern, before)
    incoming = re.findall(company_pattern, after.split("。", 1)[0])
    outgoing = [(re.sub(r"^.*(?:鉴于|及)", "", name), symbol) for name, symbol in outgoing]
    if not outgoing or len(outgoing) != len(incoming):
        return [], None
    symbols = [symbol for _, symbol in outgoing]
    placeholders = ",".join("?" for _ in symbols)
    with db() as connection:
        rows = connection.execute(
            f"select symbol,delisted_date from securities where symbol in ({placeholders})",
            symbols,
        ).fetchall()
    delisted = {str(row["symbol"]): str(row["delisted_date"] or "") for row in rows}
    if any(not delisted.get(symbol) for symbol in symbols):
        return [], None
    source_url = OFFICIAL_DETAIL_URL.format(notice_id=detail["id"])
    payload = str(detail.get("content") or "").encode("utf-8")
    raw_hash = content_hash(payload)
    events: list[dict[str, Any]] = []
    for delete_name, delete_symbol in outgoing:
        events.append(
            {
                "index_code": INDEX_CODE,
                "symbol": delete_symbol,
                "name": delete_name,
                "action_type": "delete",
                "adjustment_type": "temporary_delisting",
                "announce_date": detail["publishDate"],
                "effective_date": delisted[delete_symbol],
                "source_url": source_url,
                "raw_file_hash": raw_hash,
                "parse_status": "parsed",
            }
        )
    # The notice assigns replacements "依次" by termination time rather than
    # pairing them with the outgoing companies in prose order.
    for (add_name, add_symbol), effective_date in zip(incoming, sorted(delisted.values())):
        events.append(
            {
                "index_code": INDEX_CODE,
                "symbol": add_symbol,
                "name": add_name,
                "action_type": "add",
                "adjustment_type": "temporary_delisting",
                "announce_date": detail["publishDate"],
                "effective_date": effective_date,
                "source_url": source_url,
                "raw_file_hash": raw_hash,
                "parse_status": "parsed",
            }
        )
    return events, {
        "notice_id": detail["id"],
        "title": detail.get("title"),
        "url": source_url,
        "hash": raw_hash,
        "content_type": "html",
        "parse_status": "parsed_variable_effective_dates",
        "event_count": len(events),
        "warnings": [],
        "announce_date": detail["publishDate"],
        "effective_date": None,
    }


def _listing_merger_events(detail: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    text = re.sub(r"\s+", "", _strip_html(str(detail.get("content") or "")))
    if "吸收合并" not in text or "上市之日起" not in text:
        return [], None
    outgoing_match = re.search(r"([^，。；：()（）]{1,20})[（(]([036]\d{5})[）)]即将被", text)
    incoming_match = re.search(r"即将被([^，。；：()（）]{1,20})吸收合并", text)
    if not outgoing_match or not incoming_match:
        return [], None
    outgoing_name, outgoing_symbol = outgoing_match.groups()
    incoming_name = incoming_match.group(1)
    with db() as connection:
        rows = connection.execute(
            """
            select symbol,name,listed_date
            from securities
            where name = ? and listed_date >= ?
            order by listed_date,symbol
            """,
            (incoming_name, detail["publishDate"]),
        ).fetchall()
    if len(rows) != 1 or not rows[0]["listed_date"]:
        return [], None
    incoming = dict(rows[0])
    effective_date = str(incoming["listed_date"])
    source_url = OFFICIAL_DETAIL_URL.format(notice_id=detail["id"])
    payload = str(detail.get("content") or "").encode("utf-8")
    raw_hash = content_hash(payload)
    common = {
        "index_code": INDEX_CODE,
        "adjustment_type": "merger_listing",
        "announce_date": detail["publishDate"],
        "effective_date": effective_date,
        "source_url": source_url,
        "raw_file_hash": raw_hash,
        "parse_status": "parsed",
    }
    events = [
        {**common, "symbol": outgoing_symbol, "name": outgoing_name, "action_type": "delete"},
        {**common, "symbol": incoming["symbol"], "name": incoming["name"], "action_type": "add"},
    ]
    return events, {
        "notice_id": detail["id"],
        "title": detail.get("title"),
        "url": source_url,
        "hash": raw_hash,
        "content_type": "html",
        "parse_status": "parsed_merger_security_master_resolution",
        "event_count": len(events),
        "warnings": [],
        "announce_date": detail["publishDate"],
        "effective_date": effective_date,
        "resolution": {
            "incomingName": incoming_name,
            "incomingSymbol": incoming["symbol"],
            "effectiveDateField": "securities.listed_date",
        },
    }


def cleanup_demo_and_previous_real() -> None:
    with db() as connection:
        connection.execute("delete from universe_membership where universe_code = 'CSI300_DEMO'")
        connection.execute("delete from index_membership_events where index_code = 'CSI300_DEMO'")
        connection.execute("delete from index_source_artifacts where index_code = 'CSI300_DEMO'")
        connection.execute("delete from index_membership_events where index_code = ?", (INDEX_CODE,))
        connection.execute("delete from index_source_artifacts where index_code = ?", (INDEX_CODE,))


def parse_notice_sources(
    detail: dict[str, Any],
    *,
    cache_dir: Path,
    offline: bool = False,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    notice_id = detail["id"]
    publish_date = detail["publishDate"]
    effective_date = effective_date_from_content(detail.get("content") or "", publish_date)
    if not effective_date:
        merger_events, merger_source = _listing_merger_events(detail)
        if merger_events and merger_source:
            return merger_events, [merger_source]
        variable_events, variable_source = _variable_termination_events(detail)
        if variable_events and variable_source:
            return variable_events, [variable_source]
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
    explicit_csi300 = "沪深300" in (
        f"{detail.get('title') or ''} {_strip_html(str(detail.get('content') or ''))}"
    )
    if not explicit_csi300 and not attachments:
        return [], [
            {
                "notice_id": notice_id,
                "title": detail.get("title"),
                "reason": "corporate_action_does_not_reference_csi300",
            }
        ]
    if not attachments:
        content = (detail.get("content") or "").encode("utf-8")
        detail_url = OFFICIAL_DETAIL_URL.format(notice_id=notice_id)
        parsed = parse_adjustment_notice(
            content,
            index_code=INDEX_CODE,
            source_url=detail_url,
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
                "url": detail_url,
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
        content, local_path = _download(url, cache_dir, offline=offline)
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
        detail_url = OFFICIAL_DETAIL_URL.format(notice_id=notice_id)
        parsed = parse_adjustment_notice(
            content,
            index_code=INDEX_CODE,
            source_url=detail_url,
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
                    "url": detail_url,
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


def write_bundle_manifest(cache_dir: Path) -> dict[str, Any]:
    inventory = []
    for path in sorted(cache_dir.rglob("*")):
        if not path.is_file() or path.name in {"bundle-manifest.json", "diagnostics.json"}:
            continue
        payload = path.read_bytes()
        inventory.append(
            {
                "path": path.relative_to(cache_dir).as_posix(),
                "size": len(payload),
                "sha256": hashlib.sha256(payload).hexdigest(),
            }
        )
    encoded = json.dumps(inventory, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    manifest = {
        "schemaVersion": 1,
        "indexCode": INDEX_CODE,
        "source": OFFICIAL_SOURCE,
        "coverageStart": INITIAL_EFFECTIVE_DATE,
        "fileCount": len(inventory),
        "bundleSha256": hashlib.sha256(encoded).hexdigest(),
        "files": inventory,
    }
    (cache_dir / "bundle-manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return manifest


def write_manifest(
    path: Path,
    *,
    sources: list[dict[str, Any]],
    initial_members: list[dict[str, Any]],
    bundle: dict[str, Any],
    event_count: int,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "index_code": INDEX_CODE,
        "source": OFFICIAL_SOURCE,
        "coverage_status": "full_verified_official_bundle",
        "coverage_start": INITIAL_EFFECTIVE_DATE,
        "coverage_end": None,
        "missing_history_before": None,
        "coverage_note": (
            "Official CSIndex announcement detail responses and immutable attachments reconstruct "
            "CSI300 membership from launch without using current constituents as the historical seed."
        ),
        "initial_announce_date": INITIAL_EFFECTIVE_DATE,
        "initial_effective_date": INITIAL_EFFECTIVE_DATE,
        "initial_reconstruction": {
            "method": "official_2005_snapshot_and_adjustment",
            "member_count": len(initial_members),
            "current_constituent_substitution": False,
        },
        "event_count": event_count,
        "bundle": {
            "cache_path": "web/runtime/source-cache/csi300-official",
            "manifest": "web/runtime/source-cache/csi300-official/bundle-manifest.json",
            "file_count": bundle["fileCount"],
            "sha256": bundle["bundleSha256"],
            "fetch_command": (
                "web/backend/.venv/bin/python scripts/import_csindex_csi300_pit.py "
                "--dry-run"
            ),
            "offline_verify_command": (
                "web/backend/.venv/bin/python scripts/import_csindex_csi300_pit.py "
                "--offline --dry-run"
            ),
        },
        "initial_members": initial_members,
        "sources": [{key: value for key, value in source.items() if key != "local_path"} for source in sources],
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
    parser.add_argument("--manifest-out", default=str(ROOT / "config" / "data-sources" / "csi300_pit_sources.json"))
    parser.add_argument("--rows", type=int, default=50)
    parser.add_argument("--sleep", type=float, default=0.05)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--min-events", type=int, default=200)
    parser.add_argument("--offline", action="store_true", help="Use only the cached immutable announcement bundle.")
    parser.add_argument("--allow-incomplete", action="store_true", help="Print diagnostics without failing on incomplete reconstruction.")
    args = parser.parse_args()

    init_db()
    cache_dir = Path(args.cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    announcements_path = cache_dir / "announcements.json"
    if args.offline:
        if not announcements_path.exists():
            raise RuntimeError(f"Cached official announcement index is missing: {announcements_path}")
        announcements = json.loads(announcements_path.read_text(encoding="utf-8"))
    else:
        announcements = discover_announcements(rows=args.rows, sleep=args.sleep)
        announcements_path.write_text(
            json.dumps(announcements, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    announcement_ids = {int(item["id"]) for item in announcements if item.get("id") is not None}
    discovery_items = list(announcements) + [
        dict(item) for item in RETIRED_OFFICIAL_NOTICES if int(item["id"]) not in announcement_ids
    ]
    candidates = [item for item in discovery_items if _is_csi300_adjustment(item)]
    details = []
    all_events: list[dict[str, Any]] = []
    source_records: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    for item in candidates:
        try:
            detail = notice_detail(int(item["id"]), cache_dir=cache_dir, offline=args.offline)
        except Exception as exc:
            skipped.append({"notice_id": item.get("id"), "title": item.get("title"), "reason": f"detail_failed:{exc}"})
            continue
        details.append(detail)
        events, sources_or_warnings = parse_notice_sources(
            detail,
            cache_dir=cache_dir,
            offline=args.offline,
        )
        if events:
            all_events.extend(events)
            source_records.extend(sources_or_warnings)
        else:
            skipped.extend(sources_or_warnings)
        if args.sleep > 0:
            time.sleep(args.sleep)

    deduped = {(event["symbol"], event["action_type"], event["effective_date"]): event for event in all_events}
    events = sorted(deduped.values(), key=lambda item: (item["effective_date"], item["action_type"], item["symbol"]))
    initial_members, initial_source = official_initial_members(details, events)
    source_records.insert(0, initial_source)
    final_members = current_csi300_members()
    bundle = write_bundle_manifest(cache_dir)
    diagnostics = {
        "announcements": len(announcements),
        "candidates": candidates,
        "details": len(details),
        "sources": source_records,
        "skipped": skipped,
        "events": len(events),
        "event_distribution": _event_distribution(events),
        "membership_events": events,
        "initial_members_count": len(initial_members),
        "final_members_count": len(final_members),
        "bundle": bundle,
    }
    diagnostics_path = cache_dir / "diagnostics.json"
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
        initial_announce_date=INITIAL_EFFECTIVE_DATE,
        initial_effective_date=INITIAL_EFFECTIVE_DATE,
        events=events,
        source=OFFICIAL_SOURCE,
        batch_id=batch_id,
        previous_trade_date_fn=_previous_trade_date,
    )
    derived_final = sorted(
        interval["symbol"]
        for interval in built["intervals"]
        if interval.get("end_date") is None
    )
    current_final = sorted(item["symbol"] for item in final_members)
    if len(derived_final) != 300:
        built["warnings"].append(f"derived_final_member_count:{len(derived_final)}")
    if len(current_final) == 300 and derived_final != current_final:
        built["warnings"].append(
            "derived_final_members_mismatch:"
            f"missing={sorted(set(current_final) - set(derived_final))}:"
            f"extra={sorted(set(derived_final) - set(current_final))}"
        )
    if built["warnings"] and not args.allow_incomplete:
        raise RuntimeError(f"CSI300 interval build warnings: {built['warnings'][:20]}")

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
        write_manifest(
            Path(args.manifest_out),
            sources=source_records,
            initial_members=initial_members,
            bundle=bundle,
            event_count=len(events),
        )

    print(f"database={json.dumps(database_descriptor(), ensure_ascii=False)}")
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
