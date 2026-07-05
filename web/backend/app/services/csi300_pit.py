from __future__ import annotations

import hashlib
import json
import re
import uuid
from datetime import date, datetime, timedelta
from io import BytesIO, StringIO
from pathlib import Path
from typing import Any, Callable

from ..core.errors import LeanWebError
from ..db import db, json_dump, rows_to_dicts, utc_now
from ..lean import normalize_symbol
from .ashare_repository import infer_exchange, upsert_security, upsert_universe_membership


PARSER_VERSION = "csi300-pit-v1"
DEFAULT_SOURCE = "csi300_pit_public"

SYMBOL_COLUMNS = [
    "symbol",
    "code",
    "证券代码",
    "股票代码",
    "成分券代码",
    "品种代码",
    "样本代码",
]
NAME_COLUMNS = [
    "name",
    "证券名称",
    "股票名称",
    "成分券名称",
    "品种名称",
    "样本名称",
]
ACTION_COLUMNS = ["action_type", "action", "调整方向", "变动方向", "操作", "类别", "类型"]
ADD_SYMBOL_COLUMNS = [
    "调入证券代码",
    "调入股票代码",
    "调入代码",
    "调入成分券代码",
    "调入样本代码",
    "纳入证券代码",
    "纳入股票代码",
    "纳入代码",
    "新增证券代码",
    "新增股票代码",
    "新增代码",
    "加入证券代码",
    "加入股票代码",
    "加入代码",
]
ADD_NAME_COLUMNS = [
    "调入证券名称",
    "调入股票名称",
    "调入名称",
    "调入成分券名称",
    "调入样本名称",
    "纳入证券名称",
    "纳入股票名称",
    "纳入名称",
    "新增证券名称",
    "新增股票名称",
    "新增名称",
    "加入证券名称",
    "加入股票名称",
    "加入名称",
]
DELETE_SYMBOL_COLUMNS = [
    "调出证券代码",
    "调出股票代码",
    "调出代码",
    "调出成分券代码",
    "调出样本代码",
    "剔除证券代码",
    "剔除股票代码",
    "剔除代码",
    "删除证券代码",
    "删除股票代码",
    "删除代码",
]
DELETE_NAME_COLUMNS = [
    "调出证券名称",
    "调出股票名称",
    "调出名称",
    "调出成分券名称",
    "调出样本名称",
    "剔除证券名称",
    "剔除股票名称",
    "剔除名称",
    "删除证券名称",
    "删除股票名称",
    "删除名称",
]


def content_hash(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _is_missing(value: Any) -> bool:
    if value is None:
        return True
    try:
        if value != value:
            return True
    except Exception:
        pass
    text = str(value).strip()
    return text == "" or text.lower() in {"nan", "none", "null", "--", "-"}


def _date(value: Any, field: str) -> str:
    if _is_missing(value):
        raise LeanWebError(f"{field} is required.")
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    text = str(value).strip()
    text = text.replace("年", "-").replace("月", "-").replace("日", "")
    text = text.replace("/", "-").replace(".", "-")
    if re.fullmatch(r"\d{8}", text):
        return datetime.strptime(text, "%Y%m%d").date().isoformat()
    match = re.search(r"(\d{4})-(\d{1,2})-(\d{1,2})", text)
    if match:
        year, month, day = match.groups()
        return date(int(year), int(month), int(day)).isoformat()
    raise LeanWebError(f"Invalid {field}: {value!r}; expected YYYY-MM-DD or YYYYMMDD.")


def _optional_date(value: Any) -> str | None:
    if _is_missing(value):
        return None
    return _date(value, "date")


def _float(value: Any) -> float | None:
    if _is_missing(value):
        return None
    text = str(value).strip().replace("%", "")
    try:
        return float(text)
    except ValueError:
        return None


def _header(value: Any) -> str:
    if isinstance(value, tuple):
        text = "".join(str(item) for item in value if not _is_missing(item) and not str(item).startswith("Unnamed"))
    else:
        text = str(value)
    return re.sub(r"[\s:_：()（）/\\.-]+", "", text.strip()).lower()


def _record_value(record: dict[str, Any], candidates: list[str]) -> Any:
    normalized = {_header(key): value for key, value in record.items()}
    for candidate in candidates:
        value = normalized.get(_header(candidate))
        if not _is_missing(value):
            return value
    return None


def _clean_symbol(value: Any) -> str | None:
    if _is_missing(value):
        return None
    text = str(value).strip().upper()
    if re.fullmatch(r"\d+\.0", text):
        text = text.split(".")[0]
    text = text.replace(" ", "")
    if text.isdigit() and len(text) < 6:
        text = text.zfill(6)
    try:
        return normalize_symbol(text, "china")
    except Exception:
        return None


def _action(value: Any, default: str | None = None) -> str | None:
    raw = str(value if not _is_missing(value) else default or "").strip().lower()
    if not raw:
        return None
    if raw in {"add", "in", "include", "included"} or any(
        token in raw for token in ("调入", "纳入", "新增", "加入", "新进", "进入")
    ):
        return "add"
    if raw in {"delete", "del", "remove", "removed", "out", "exclude", "excluded"} or any(
        token in raw for token in ("调出", "剔除", "删除", "退出", "移出")
    ):
        return "delete"
    return None


def _content_type(source_url: str | None, content_type: str | None) -> str:
    if content_type:
        return content_type.lower()
    suffix = Path(str(source_url or "")).suffix.lower()
    return suffix.lstrip(".")


def _pandas():
    try:
        import pandas as pd  # type: ignore
    except ImportError as exc:
        raise LeanWebError("pandas is required to parse CSI300 public source tables.") from exc
    return pd


def pdf_text_from_content(content: bytes) -> str:
    try:
        from pypdf import PdfReader  # type: ignore
    except ImportError as exc:
        raise LeanWebError("pypdf is required to parse CSI300 official PDF adjustment notices.") from exc
    reader = PdfReader(BytesIO(content))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def tables_from_content(content: bytes, *, source_url: str | None = None, content_type: str | None = None) -> list[Any]:
    kind = _content_type(source_url, content_type)
    if kind in {"pdf", "application/pdf"}:
        return []
    pd = _pandas()
    if kind in {"xls", "xlsx", "excel", "application/vnd.ms-excel"}:
        sheets = pd.read_excel(BytesIO(content), sheet_name=None, dtype=str)
        frames = []
        for sheet_name, frame in sheets.items():
            if frame.empty:
                continue
            frame.attrs["sheet_name"] = str(sheet_name)
            frames.append(frame)
        return frames
    if kind in {"csv", "txt"}:
        return [pd.read_csv(BytesIO(content), dtype=str)]
    text = content.decode("utf-8", errors="ignore")
    if "<table" in text.lower() or kind in {"html", "htm", "text/html"}:
        return pd.read_html(StringIO(text))
    return []


def events_from_csi300_pdf_text(
    text: str,
    *,
    index_code: str,
    source_url: str,
    raw_file_hash: str,
    announce_date: str,
    effective_date: str,
    adjustment_type: str = "regular",
) -> list[dict[str, Any]]:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    in_section = False
    first_action = "delete"
    second_action = "add"
    events: list[dict[str, Any]] = []
    for line in lines:
        compact = re.sub(r"\s+", "", line)
        if not in_section:
            if "沪深300" in compact and "样本调整名单" in compact:
                in_section = True
            continue
        if "指数样本调整名单" in compact and "沪深300" not in compact:
            break
        if compact == "调入名单调出名单":
            first_action, second_action = "add", "delete"
            continue
        if compact == "调出名单调入名单":
            first_action, second_action = "delete", "add"
            continue
        if compact == "证券代码证券名称证券代码证券名称":
            continue
        match = re.match(r"^(\d{6})\s+(.+?)\s+(\d{6})\s+(.+?)$", line)
        if not match:
            continue
        first_symbol, first_name, second_symbol, second_name = match.groups()
        clean_first = _clean_symbol(first_symbol)
        clean_second = _clean_symbol(second_symbol)
        if clean_first:
            events.append(
                _event(
                    index_code=index_code,
                    symbol=clean_first,
                    name=first_name,
                    action_type=first_action,
                    announce_date=announce_date,
                    effective_date=effective_date,
                    adjustment_type=adjustment_type,
                    source_url=source_url,
                    raw_file_hash=raw_file_hash,
                )
            )
        if clean_second:
            events.append(
                _event(
                    index_code=index_code,
                    symbol=clean_second,
                    name=second_name,
                    action_type=second_action,
                    announce_date=announce_date,
                    effective_date=effective_date,
                    adjustment_type=adjustment_type,
                    source_url=source_url,
                    raw_file_hash=raw_file_hash,
                )
            )
    return events


def _event(
    *,
    index_code: str,
    symbol: str,
    name: Any,
    action_type: str,
    announce_date: str,
    effective_date: str,
    adjustment_type: str,
    source_url: str,
    raw_file_hash: str,
    weight: Any = None,
) -> dict[str, Any]:
    if effective_date < announce_date:
        raise LeanWebError("CSI300 event effective_date cannot be earlier than announce_date.")
    return {
        "index_code": index_code.upper(),
        "symbol": symbol,
        "name": None if _is_missing(name) else str(name).strip(),
        "action_type": action_type,
        "adjustment_type": adjustment_type,
        "announce_date": announce_date,
        "effective_date": effective_date,
        "source_url": source_url,
        "raw_file_hash": raw_file_hash,
        "weight": _float(weight),
        "parse_status": "parsed",
    }


def _events_from_manual_records(
    records: list[dict[str, Any]],
    *,
    index_code: str,
    source_url: str,
    raw_file_hash: str,
    announce_date: str,
    effective_date: str,
    adjustment_type: str,
) -> list[dict[str, Any]]:
    events = []
    for record in records:
        symbol = _clean_symbol(record.get("symbol") or record.get("code") or record.get("证券代码") or record.get("股票代码"))
        action_type = _action(record.get("action_type") or record.get("action"), record.get("default_action"))
        if not symbol or not action_type:
            continue
        event_announce = _optional_date(record.get("announce_date") or record.get("announceDate")) or announce_date
        event_effective = _optional_date(record.get("effective_date") or record.get("effectiveDate")) or effective_date
        events.append(
            _event(
                index_code=index_code,
                symbol=symbol,
                name=record.get("name") or record.get("证券名称") or record.get("股票名称"),
                action_type=action_type,
                announce_date=event_announce,
                effective_date=event_effective,
                adjustment_type=record.get("adjustment_type") or adjustment_type,
                source_url=source_url,
                raw_file_hash=raw_file_hash,
                weight=record.get("weight"),
            )
        )
    return events


def _events_from_row(
    record: dict[str, Any],
    *,
    index_code: str,
    source_url: str,
    raw_file_hash: str,
    announce_date: str,
    effective_date: str,
    adjustment_type: str,
    default_action: str | None,
) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    add_symbol = _clean_symbol(_record_value(record, ADD_SYMBOL_COLUMNS))
    if add_symbol:
        events.append(
            _event(
                index_code=index_code,
                symbol=add_symbol,
                name=_record_value(record, ADD_NAME_COLUMNS),
                action_type="add",
                announce_date=announce_date,
                effective_date=effective_date,
                adjustment_type=adjustment_type,
                source_url=source_url,
                raw_file_hash=raw_file_hash,
            )
        )
    delete_symbol = _clean_symbol(_record_value(record, DELETE_SYMBOL_COLUMNS))
    if delete_symbol:
        events.append(
            _event(
                index_code=index_code,
                symbol=delete_symbol,
                name=_record_value(record, DELETE_NAME_COLUMNS),
                action_type="delete",
                announce_date=announce_date,
                effective_date=effective_date,
                adjustment_type=adjustment_type,
                source_url=source_url,
                raw_file_hash=raw_file_hash,
            )
        )
    if events:
        return events

    symbol = _clean_symbol(_record_value(record, SYMBOL_COLUMNS))
    action_type = _action(_record_value(record, ACTION_COLUMNS), default_action)
    if symbol and action_type:
        events.append(
            _event(
                index_code=index_code,
                symbol=symbol,
                name=_record_value(record, NAME_COLUMNS),
                action_type=action_type,
                announce_date=announce_date,
                effective_date=effective_date,
                adjustment_type=adjustment_type,
                source_url=source_url,
                raw_file_hash=raw_file_hash,
                weight=_record_value(record, ["weight", "权重", "权重(%)", "权重%"]),
            )
        )
    return events


def events_from_table(
    frame: Any,
    *,
    index_code: str,
    source_url: str,
    raw_file_hash: str,
    announce_date: str,
    effective_date: str,
    adjustment_type: str = "regular",
    default_action: str | None = None,
) -> list[dict[str, Any]]:
    if frame is None or getattr(frame, "empty", True):
        return []
    records = frame.to_dict("records")
    events: list[dict[str, Any]] = []
    for record in records:
        events.extend(
            _events_from_row(
                record,
                index_code=index_code,
                source_url=source_url,
                raw_file_hash=raw_file_hash,
                announce_date=announce_date,
                effective_date=effective_date,
                adjustment_type=adjustment_type,
                default_action=default_action,
            )
        )
    return events


def events_from_csindex_adjustment_frame(
    frame: Any,
    *,
    index_code: str,
    source_url: str,
    raw_file_hash: str,
    announce_date: str,
    effective_date: str,
    adjustment_type: str = "regular",
    parse_four_column_table: bool = False,
) -> list[dict[str, Any]]:
    if frame is None or getattr(frame, "empty", True):
        return []
    events: list[dict[str, Any]] = []
    records = frame.to_dict("records")
    normalized_columns = [_header(column) for column in frame.columns]
    sheet_name = str(frame.attrs.get("sheet_name") or "")
    sheet_action = _action(sheet_name)
    if sheet_action and any(column == _header("指数代码") for column in normalized_columns):
        for record in records:
            row_index_code = _record_value(record, ["指数代码", "index_code", "indexCode"])
            row_name = _record_value(record, ["指数简称", "指数名称", "index_name", "indexName"])
            if str(row_index_code).strip() not in {"000300", "399300", "CSI300"} and "沪深300" not in str(row_name or ""):
                continue
            symbol = _clean_symbol(_record_value(record, ["证券代码", "股票代码", "成分券代码", "股票代码"]))
            name = _record_value(record, ["证券简称", "证券名称", "股票简称", "股票名称"])
            if not symbol:
                continue
            events.append(
                _event(
                    index_code=index_code,
                    symbol=symbol,
                    name=name,
                    action_type=sheet_action,
                    announce_date=announce_date,
                    effective_date=effective_date,
                    adjustment_type=adjustment_type,
                    source_url=source_url,
                    raw_file_hash=raw_file_hash,
                )
            )
        return events

    if any(column == _header("指数代码") for column in normalized_columns):
        for record in records:
            row_index_code = _record_value(record, ["指数代码", "index_code", "indexCode"])
            row_name = _record_value(record, ["指数简称", "指数名称", "index_name", "indexName"])
            if str(row_index_code).strip() not in {"000300", "399300", "CSI300"} and "沪深300" not in str(row_name or ""):
                continue
            delete_symbol = _clean_symbol(_record_value(record, ["调出", "调出证券代码", "调出代码"]))
            delete_name = _record_value(record, ["Unnamed: 3", "调出证券简称", "调出证券名称", "调出名称"])
            add_symbol = _clean_symbol(_record_value(record, ["调入", "调入证券代码", "调入代码"]))
            add_name = _record_value(record, ["Unnamed: 5", "调入证券简称", "调入证券名称", "调入名称"])
            if delete_symbol:
                events.append(
                    _event(
                        index_code=index_code,
                        symbol=delete_symbol,
                        name=delete_name,
                        action_type="delete",
                        announce_date=announce_date,
                        effective_date=effective_date,
                        adjustment_type=adjustment_type,
                        source_url=source_url,
                        raw_file_hash=raw_file_hash,
                    )
                )
            if add_symbol:
                events.append(
                    _event(
                        index_code=index_code,
                        symbol=add_symbol,
                        name=add_name,
                        action_type="add",
                        announce_date=announce_date,
                        effective_date=effective_date,
                        adjustment_type=adjustment_type,
                        source_url=source_url,
                        raw_file_hash=raw_file_hash,
                    )
                )
        return events

    if not parse_four_column_table or len(frame.columns) < 4 or len(frame) < 3:
        return []
    rows = frame.astype(str).values.tolist()
    first_header = "".join(rows[0][:4])
    second_header = "".join(rows[1][:4])
    if "调出" not in first_header or "调入" not in first_header or "证券代码" not in second_header:
        return []
    first_action, second_action = ("delete", "add")
    if first_header.find("调入") < first_header.find("调出"):
        first_action, second_action = ("add", "delete")
    for row in rows[2:]:
        first_symbol = _clean_symbol(row[0])
        second_symbol = _clean_symbol(row[2])
        if first_symbol:
            events.append(
                _event(
                    index_code=index_code,
                    symbol=first_symbol,
                    name=row[1],
                    action_type=first_action,
                    announce_date=announce_date,
                    effective_date=effective_date,
                    adjustment_type=adjustment_type,
                    source_url=source_url,
                    raw_file_hash=raw_file_hash,
                )
            )
        if second_symbol:
            events.append(
                _event(
                    index_code=index_code,
                    symbol=second_symbol,
                    name=row[3],
                    action_type=second_action,
                    announce_date=announce_date,
                    effective_date=effective_date,
                    adjustment_type=adjustment_type,
                    source_url=source_url,
                    raw_file_hash=raw_file_hash,
                )
            )
    return events


def parse_adjustment_notice(
    content: bytes,
    *,
    index_code: str,
    source_url: str,
    announce_date: str,
    effective_date: str,
    content_type: str | None = None,
    adjustment_type: str = "regular",
    default_action: str | None = None,
    manual_records: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    announce = _date(announce_date, "announce_date")
    effective = _date(effective_date, "effective_date")
    raw_hash = content_hash(content)
    events = _events_from_manual_records(
        manual_records or [],
        index_code=index_code,
        source_url=source_url,
        raw_file_hash=raw_hash,
        announce_date=announce,
        effective_date=effective,
        adjustment_type=adjustment_type,
    )
    warnings: list[str] = []
    kind = _content_type(source_url, content_type)
    if content and kind not in {"pdf", "application/pdf", "manual"}:
        try:
            for table_index, frame in enumerate(tables_from_content(content, source_url=source_url, content_type=content_type)):
                official_events = events_from_csindex_adjustment_frame(
                    frame,
                    index_code=index_code,
                    source_url=source_url,
                    raw_file_hash=raw_hash,
                    announce_date=announce,
                    effective_date=effective,
                    adjustment_type=adjustment_type,
                    parse_four_column_table=kind in {"html", "htm", "text/html"} and table_index == 0,
                )
                if official_events:
                    events.extend(official_events)
                    if kind in {"html", "htm", "text/html"}:
                        break
                    continue
                events.extend(
                    events_from_table(
                        frame,
                        index_code=index_code,
                        source_url=source_url,
                        raw_file_hash=raw_hash,
                        announce_date=announce,
                        effective_date=effective,
                        adjustment_type=adjustment_type,
                        default_action=default_action,
                    )
                )
        except Exception as exc:
            warnings.append(f"table_parse_failed:{exc}")
    elif kind in {"pdf", "application/pdf"} and not events:
        try:
            events.extend(
                events_from_csi300_pdf_text(
                    pdf_text_from_content(content),
                    index_code=index_code,
                    source_url=source_url,
                    raw_file_hash=raw_hash,
                    announce_date=announce,
                    effective_date=effective,
                    adjustment_type=adjustment_type,
                )
            )
        except Exception as exc:
            warnings.append(f"pdf_parse_failed:{exc}")

    deduped: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    for event in events:
        key = (event["symbol"], event["action_type"], event["effective_date"], event["source_url"])
        deduped[key] = event
    parse_status = "parsed" if deduped else "needs_review"
    if not deduped:
        warnings.append("no_membership_events_parsed")
    return {"events": list(deduped.values()), "parse_status": parse_status, "warnings": warnings, "raw_file_hash": raw_hash}


def upsert_source_artifact(
    *,
    index_code: str,
    source_url: str,
    raw_file_hash: str,
    local_path: str | None = None,
    content_type: str | None = None,
    parse_status: str = "parsed",
    metadata: dict[str, Any] | None = None,
    error: str | None = None,
) -> str:
    artifact_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{index_code}:{source_url}:{raw_file_hash}"))
    with db() as connection:
        connection.execute(
            """
            insert into index_source_artifacts
                (id, index_code, source_url, local_path, raw_file_hash, content_type,
                 parser_version, parse_status, error, metadata_json, fetched_at)
            values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            on conflict(index_code, source_url, raw_file_hash) do update set
                local_path = excluded.local_path,
                content_type = excluded.content_type,
                parser_version = excluded.parser_version,
                parse_status = excluded.parse_status,
                error = excluded.error,
                metadata_json = excluded.metadata_json,
                fetched_at = excluded.fetched_at
            """,
            (
                artifact_id,
                index_code.upper(),
                source_url,
                local_path,
                raw_file_hash,
                content_type,
                PARSER_VERSION,
                parse_status,
                error,
                json_dump(metadata or {}),
                utc_now(),
            ),
        )
    return artifact_id


def upsert_membership_events(events: list[dict[str, Any]], *, batch_id: str | None = None) -> int:
    batch = batch_id or str(uuid.uuid4())
    now = utc_now()
    with db() as connection:
        for event in events:
            event_id = str(
                uuid.uuid5(
                    uuid.NAMESPACE_URL,
                    ":".join(
                        [
                            event["index_code"],
                            event["symbol"],
                            event["action_type"],
                            event["effective_date"],
                            event.get("source_url") or "",
                        ]
                    ),
                )
            )
            connection.execute(
                """
                insert into index_membership_events
                    (id, index_code, symbol, name, action_type, adjustment_type, announce_date,
                     effective_date, source_url, raw_file_hash, batch_id, parse_status, updated_at)
                values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                on conflict(index_code, symbol, action_type, effective_date, source_url) do update set
                    name = excluded.name,
                    adjustment_type = excluded.adjustment_type,
                    announce_date = excluded.announce_date,
                    raw_file_hash = excluded.raw_file_hash,
                    batch_id = excluded.batch_id,
                    parse_status = excluded.parse_status,
                    updated_at = excluded.updated_at
                """,
                (
                    event_id,
                    event["index_code"],
                    event["symbol"],
                    event.get("name"),
                    event["action_type"],
                    event.get("adjustment_type"),
                    event["announce_date"],
                    event["effective_date"],
                    event.get("source_url"),
                    event.get("raw_file_hash"),
                    batch,
                    event.get("parse_status") or "parsed",
                    now,
                ),
            )
    return len(events)


def load_membership_events(index_code: str) -> list[dict[str, Any]]:
    with db() as connection:
        rows = connection.execute(
            """
            select * from index_membership_events
            where index_code = ?
            order by effective_date asc, case action_type when 'delete' then 0 else 1 end, symbol asc
            """,
            (index_code.upper(),),
        ).fetchall()
    return rows_to_dicts(rows)


def previous_trade_date(effective_date: str, market: str = "china") -> str:
    effective = _date(effective_date, "effective_date")
    with db() as connection:
        row = connection.execute(
            """
            select max(trade_date) as trade_date
            from trade_calendar
            where market = ? and is_open = 1 and trade_date < ?
            """,
            (market, effective),
        ).fetchone()
    if row and row["trade_date"]:
        candidate = date.fromisoformat(row["trade_date"])
        effective_day = date.fromisoformat(effective)
        if (effective_day - candidate).days <= 14:
            return row["trade_date"]
    return (date.fromisoformat(effective) - timedelta(days=1)).isoformat()


def _member_record(
    record: dict[str, Any],
    *,
    index_code: str,
    start_date: str,
    announce_date: str,
    source: str,
    batch_id: str,
) -> dict[str, Any] | None:
    symbol = _clean_symbol(record.get("symbol") or record.get("code") or record.get("证券代码") or record.get("股票代码"))
    if not symbol:
        return None
    member_start = _optional_date(record.get("start_date") or record.get("startDate")) or start_date
    member_announce = _optional_date(record.get("announce_date") or record.get("announceDate")) or announce_date
    return {
        "universe_code": index_code.upper(),
        "symbol": symbol,
        "name": record.get("name") or record.get("证券名称") or record.get("股票名称") or symbol,
        "start_date": member_start,
        "end_date": _optional_date(record.get("end_date") or record.get("endDate")),
        "announce_date": member_announce,
        "effective_date": _optional_date(record.get("effective_date") or record.get("effectiveDate")) or member_start,
        "weight": _float(record.get("weight")),
        "source": source,
        "batch_id": batch_id,
        "listed_date": _optional_date(record.get("listed_date") or record.get("listedDate")) or member_start,
        "delisted_date": _optional_date(record.get("delisted_date") or record.get("delistedDate")),
    }


def build_membership_intervals(
    *,
    index_code: str,
    initial_members: list[dict[str, Any]],
    initial_effective_date: str,
    initial_announce_date: str,
    events: list[dict[str, Any]],
    source: str = DEFAULT_SOURCE,
    batch_id: str | None = None,
    previous_trade_date_fn: Callable[[str], str] | None = None,
) -> dict[str, Any]:
    batch = batch_id or str(uuid.uuid4())
    start = _date(initial_effective_date, "initial_effective_date")
    announce = _date(initial_announce_date, "initial_announce_date")
    previous_fn = previous_trade_date_fn or previous_trade_date
    active: dict[str, dict[str, Any]] = {}
    intervals: list[dict[str, Any]] = []
    warnings: list[str] = []

    for record in initial_members:
        member = _member_record(record, index_code=index_code, start_date=start, announce_date=announce, source=source, batch_id=batch)
        if not member:
            warnings.append(f"initial_member_skipped:{json.dumps(record, ensure_ascii=False)}")
            continue
        if member["symbol"] in active:
            warnings.append(f"duplicate_initial_member:{member['symbol']}")
            continue
        active[member["symbol"]] = member
        intervals.append(member)

    sorted_events = sorted(
        events,
        key=lambda item: (
            _date(item["effective_date"], "effective_date"),
            0 if item["action_type"] == "delete" else 1,
            item["symbol"],
        ),
    )
    for event in sorted_events:
        symbol = _clean_symbol(event.get("symbol"))
        if not symbol:
            warnings.append(f"event_symbol_invalid:{event.get('symbol')}")
            continue
        action_type = _action(event.get("action_type"))
        effective = _date(event.get("effective_date"), "effective_date")
        event_announce = _date(event.get("announce_date"), "announce_date")
        if effective < event_announce:
            raise LeanWebError("CSI300 event effective_date cannot be earlier than announce_date.")
        if action_type == "delete":
            interval = active.pop(symbol, None)
            if not interval:
                warnings.append(f"delete_without_active_member:{symbol}:{effective}")
                continue
            end_date = previous_fn(effective)
            if end_date < interval["start_date"]:
                warnings.append(f"delete_before_interval_start:{symbol}:{effective}")
                end_date = interval["start_date"]
            interval["end_date"] = end_date
            continue
        if action_type == "add":
            if symbol in active:
                warnings.append(f"add_while_already_active:{symbol}:{effective}")
                continue
            interval = {
                "universe_code": index_code.upper(),
                "symbol": symbol,
                "name": event.get("name") or symbol,
                "start_date": effective,
                "end_date": None,
                "announce_date": event_announce,
                "effective_date": effective,
                "weight": _float(event.get("weight")),
                "source": source,
                "batch_id": batch,
                "listed_date": effective,
                "delisted_date": None,
            }
            active[symbol] = interval
            intervals.append(interval)
            continue
        warnings.append(f"unknown_action:{event.get('action_type')}:{symbol}:{effective}")

    return {"intervals": sorted(intervals, key=lambda item: (item["symbol"], item["start_date"])), "warnings": warnings, "batch_id": batch}


def materialize_membership_intervals(
    *,
    index_code: str,
    intervals: list[dict[str, Any]],
    source: str = DEFAULT_SOURCE,
    batch_id: str | None = None,
    replace: bool = False,
) -> int:
    batch = batch_id or str(uuid.uuid4())
    if replace:
        with db() as connection:
            connection.execute("delete from universe_membership where universe_code = ?", (index_code.upper(),))
    imported = 0
    for interval in intervals:
        symbol = interval["symbol"]
        upsert_security(
            symbol=symbol,
            name=interval.get("name") or symbol,
            exchange=infer_exchange(symbol),
            listed_date=interval.get("listed_date") or interval["start_date"],
            delisted_date=interval.get("delisted_date"),
            status="delisted" if interval.get("delisted_date") else "listed",
        )
        upsert_universe_membership(
            index_code.upper(),
            symbol,
            interval["start_date"],
            interval.get("end_date"),
            source=interval.get("source") or source,
            batch_id=interval.get("batch_id") or batch,
            weight=interval.get("weight"),
            announce_date=interval.get("announce_date"),
            effective_date=interval.get("effective_date") or interval["start_date"],
        )
        imported += 1
    return imported


def membership_counts(index_code: str, as_of_dates: list[str]) -> list[dict[str, Any]]:
    from .ashare_repository import universe_as_of

    result = []
    for as_of in as_of_dates:
        items = universe_as_of(index_code.upper(), _date(as_of, "as_of_date"))
        result.append({"as_of_date": _date(as_of, "as_of_date"), "count": len(items), "symbols": [item["symbol"] for item in items]})
    return result
