from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
from typing import Any
import uuid
from urllib import error as urllib_error
from urllib import request as urllib_request
from urllib.parse import parse_qsl, urlsplit, urlunsplit

from ..db import db, json_dump, row_to_dict, rows_to_dicts, utc_now


ALERT_TYPES = {
    "api_down",
    "worker_down",
    "mysql_down",
    "migration_mismatch",
    "provider_unavailable",
    "qa_critical",
    "warning_expired",
    "benchmark_missing",
    "cache_restore_failed",
    "paper_reject_spike",
    "nav_drawdown_warning",
    "report_write_failed",
    "paper_schedule_failed",
    "paper_walkforward_failed",
    "data_sync_failed",
    "scheduled_report_failed",
}

_SEVERITY_RANK = {
    "debug": 0,
    "info": 1,
    "warning": 2,
    "error": 3,
    "critical": 4,
}
_ALERT_NAMESPACE = uuid.UUID("86d16cc7-5c13-49c7-a151-7ab940f4cb81")
_DELIVERY_NAMESPACE = uuid.UUID("c3f681a1-03ad-4271-8579-760308a76a03")


def _env_int(name: str, default: int, minimum: int = 0) -> int:
    try:
        return max(minimum, int(os.environ.get(name, str(default))))
    except (TypeError, ValueError):
        return max(minimum, default)


def _parse_time(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _safe_endpoint(url: str) -> str:
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))


def _safe_delivery_error(exc: Exception, url: str) -> str:
    message = str(exc).replace(url, _safe_endpoint(url))
    for _, value in parse_qsl(urlsplit(url).query, keep_blank_values=True):
        if value:
            message = message.replace(value, "[redacted]")
    return f"{exc.__class__.__name__}:{message}"[:1000]


def _webhook_payload(alert: dict[str, Any]) -> dict[str, Any]:
    return {
        "schemaVersion": 1,
        "id": alert.get("id"),
        "eventType": alert.get("event_type") or alert.get("eventType"),
        "severity": alert.get("severity"),
        "status": alert.get("status"),
        "title": alert.get("title"),
        "message": alert.get("message"),
        "source": alert.get("source"),
        "relatedId": alert.get("related_id") or alert.get("relatedId"),
        "count": int(alert.get("count") or 1),
        "details": alert.get("details") or {},
        "firstSeenAt": alert.get("first_seen_at") or alert.get("firstSeenAt"),
        "lastSeenAt": alert.get("last_seen_at") or alert.get("lastSeenAt"),
    }


def _send_webhook(url: str, alert: dict[str, Any], *, timeout_seconds: int, bearer_token: str) -> int:
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "lean-local-platform-alerts/1",
    }
    if bearer_token:
        headers["Authorization"] = f"Bearer {bearer_token}"
    body = json.dumps(_webhook_payload(alert), ensure_ascii=False, default=str).encode("utf-8")
    webhook_request = urllib_request.Request(url, data=body, headers=headers, method="POST")
    with urllib_request.urlopen(webhook_request, timeout=timeout_seconds) as response:
        response_code = int(getattr(response, "status", response.getcode()))
    if response_code < 200 or response_code >= 300:
        raise RuntimeError(f"webhook_http_{response_code}")
    return response_code


def _record_delivery(
    alert_id: str,
    *,
    status: str,
    response_code: int | None,
    error: str | None,
    endpoint: str,
) -> dict[str, Any]:
    now = utc_now()
    delivery_id = str(uuid.uuid5(_DELIVERY_NAMESPACE, f"{alert_id}:webhook"))
    with db() as connection:
        existing = connection.execute(
            "select id,attempt_count,created_at from alert_deliveries where alert_id=? and channel='webhook'",
            (alert_id,),
        ).fetchone()
        if existing:
            connection.execute(
                """
                update alert_deliveries
                set status=?,attempt_count=?,last_attempt_at=?,last_success_at=?,next_retry_at=null,
                    last_error=?,response_code=?,metadata_json=?,updated_at=?
                where id=?
                """,
                (
                    status,
                    int(existing["attempt_count"] or 0) + 1,
                    now,
                    now if status == "success" else None,
                    error,
                    response_code,
                    json_dump({"endpoint": _safe_endpoint(endpoint)}),
                    now,
                    existing["id"],
                ),
            )
        else:
            connection.execute(
                """
                insert into alert_deliveries
                    (id,alert_id,channel,status,attempt_count,last_attempt_at,last_success_at,
                     next_retry_at,last_error,response_code,metadata_json,created_at,updated_at)
                values (?,?,'webhook',?,1,?,?,null,?,?,?,?,?)
                """,
                (
                    delivery_id,
                    alert_id,
                    status,
                    now,
                    now if status == "success" else None,
                    error,
                    response_code,
                    json_dump({"endpoint": _safe_endpoint(endpoint)}),
                    now,
                    now,
                ),
            )
        row = connection.execute(
            "select * from alert_deliveries where alert_id=? and channel='webhook'",
            (alert_id,),
        ).fetchone()
    return row_to_dict(row) or {}


def dispatch_alert(alert: dict[str, Any], *, webhook_url: str | None = None) -> dict[str, Any]:
    url = str(webhook_url if webhook_url is not None else os.environ.get("LEAN_ALERT_WEBHOOK_URL", "")).strip()
    if not url:
        return {"channel": "webhook", "status": "disabled"}
    severity = str(alert.get("severity") or "warning").lower()
    minimum = str(os.environ.get("LEAN_ALERT_MIN_SEVERITY", "critical")).strip().lower()
    if _SEVERITY_RANK.get(severity, 0) < _SEVERITY_RANK.get(minimum, 4):
        return {"channel": "webhook", "status": "below_threshold", "minimumSeverity": minimum}
    cooldown_until = _parse_time(alert.get("cooldown_until"))
    if cooldown_until and cooldown_until > datetime.now(timezone.utc):
        return {"channel": "webhook", "status": "cooldown", "cooldownUntil": cooldown_until.isoformat()}
    timeout_seconds = _env_int("LEAN_ALERT_WEBHOOK_TIMEOUT_SECONDS", 5, 1)
    bearer_token = str(os.environ.get("LEAN_ALERT_WEBHOOK_BEARER_TOKEN", "")).strip()
    response_code: int | None = None
    delivery_error: str | None = None
    try:
        response_code = _send_webhook(
            url,
            alert,
            timeout_seconds=timeout_seconds,
            bearer_token=bearer_token,
        )
        status = "success"
    except (OSError, RuntimeError, ValueError, urllib_error.URLError) as exc:
        status = "failed"
        delivery_error = _safe_delivery_error(exc, url)
    delivery = _record_delivery(
        str(alert["id"]),
        status=status,
        response_code=response_code,
        error=delivery_error,
        endpoint=url,
    )
    if status == "success":
        cooldown_seconds = _env_int("LEAN_ALERT_COOLDOWN_SECONDS", 900, 0)
        cooldown = (datetime.now(timezone.utc) + timedelta(seconds=cooldown_seconds)).isoformat()
        with db() as connection:
            connection.execute("update alert_events set cooldown_until=? where id=?", (cooldown, alert["id"]))
        delivery["cooldownUntil"] = cooldown
    return delivery


def emit_alert(
    event_type: str,
    *,
    severity: str = "warning",
    title: str | None = None,
    message: str | None = None,
    source: str | None = None,
    related_id: str | None = None,
    details: dict[str, Any] | None = None,
    dedupe_key: str | None = None,
    alert_file: str | Path | None = None,
    webhook_url: str | None = None,
) -> dict[str, Any]:
    if event_type not in ALERT_TYPES:
        raise ValueError(f"unsupported_alert_type:{event_type}")
    now = utc_now()
    key = dedupe_key or f"{event_type}:{source or ''}:{related_id or ''}:{json_dump(details or {})[:128]}"
    alert_id = str(uuid.uuid5(_ALERT_NAMESPACE, key))
    payload = {
        "id": alert_id,
        "eventType": event_type,
        "severity": severity,
        "status": "open",
        "dedupeKey": key,
        "title": title or event_type,
        "message": message or event_type,
        "source": source,
        "relatedId": related_id,
        "details": details or {},
        "firstSeenAt": now,
        "lastSeenAt": now,
    }
    with db() as connection:
        existing = connection.execute(
            "select id,status,count from alert_events where dedupe_key=? order by last_seen_at desc limit 1",
            (key,),
        ).fetchone()
        if existing and existing["status"] != "open":
            alert_id = str(existing["id"])
            connection.execute(
                """
                update alert_events
                set event_type=?,severity=?,status='open',title=?,message=?,source=?,related_id=?,
                    details_json=?,last_seen_at=?,count=?,cooldown_until=null,
                    acknowledged_at=null,acknowledged_by=null,resolved_at=null,resolved_by=null
                where id=?
                """,
                (
                    event_type,
                    severity,
                    payload["title"],
                    payload["message"],
                    source,
                    related_id,
                    json_dump(details or {}),
                    now,
                    int(existing["count"] or 0) + 1,
                    alert_id,
                ),
            )
        else:
            connection.execute(
                """
                insert into alert_events
                    (id, event_type, severity, status, dedupe_key, title, message, source,
                     related_id, details_json, first_seen_at, last_seen_at, count)
                values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                on conflict(dedupe_key, status) do update set
                    severity = excluded.severity,
                    title = excluded.title,
                    message = excluded.message,
                    source = excluded.source,
                    related_id = excluded.related_id,
                    details_json = excluded.details_json,
                    last_seen_at = excluded.last_seen_at,
                    count = alert_events.count + 1
                """,
                (
                    alert_id,
                    event_type,
                    severity,
                    "open",
                    key,
                    payload["title"],
                    payload["message"],
                    source,
                    related_id,
                    json_dump(details or {}),
                    now,
                    now,
                    1,
                ),
            )
        row = connection.execute(
            "select * from alert_events where dedupe_key = ? and status = 'open'",
            (key,),
        ).fetchone()
        count = int(row["count"] or 1) if row else 1
        escalate_after = _env_int("LEAN_ALERT_ESCALATE_AFTER", 3, 2)
        if severity.lower() in {"warning", "error"} and count >= escalate_after:
            connection.execute("update alert_events set severity='critical' where id=?", (alert_id,))
            row = connection.execute("select * from alert_events where id=?", (alert_id,)).fetchone()
    item = row_to_dict(row) or payload
    if alert_file:
        path = Path(alert_file)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(item, ensure_ascii=False, default=str) + "\n")
    item["delivery"] = dispatch_alert(item, webhook_url=webhook_url)
    return item


def list_alert_events(status: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
    clauses = []
    params: list[Any] = []
    if status:
        clauses.append("status = ?")
        params.append(status)
    sql = "select * from alert_events"
    if clauses:
        sql += " where " + " and ".join(clauses)
    sql += " order by last_seen_at desc limit ?"
    params.append(max(1, min(int(limit), 1000)))
    with db() as connection:
        rows = connection.execute(sql, params).fetchall()
        alert_items = rows_to_dicts(rows)
        alert_ids = [str(item["id"]) for item in alert_items]
        deliveries: dict[str, list[dict[str, Any]]] = {alert_id: [] for alert_id in alert_ids}
        if alert_ids:
            placeholders = ",".join("?" for _ in alert_ids)
            delivery_rows = rows_to_dicts(
                connection.execute(
                    f"select * from alert_deliveries where alert_id in ({placeholders}) order by updated_at desc",
                    alert_ids,
                ).fetchall()
            )
            for delivery in delivery_rows:
                deliveries.setdefault(str(delivery["alert_id"]), []).append(delivery)
    for item in alert_items:
        item["deliveries"] = deliveries.get(str(item["id"]), [])
    return alert_items


def update_alert_status(alert_id: str, status: str, *, actor: str = "api") -> dict[str, Any] | None:
    if status not in {"acknowledged", "resolved"}:
        raise ValueError("status must be acknowledged or resolved")
    now = utc_now()
    fields = (
        "acknowledged_at = ?, acknowledged_by = ?, status = ?"
        if status == "acknowledged"
        else "resolved_at = ?, resolved_by = ?, status = ?"
    )
    with db() as connection:
        connection.execute(f"update alert_events set {fields} where id = ?", (now, actor, status, alert_id))
        row = connection.execute("select * from alert_events where id = ?", (alert_id,)).fetchone()
    return row_to_dict(row)
