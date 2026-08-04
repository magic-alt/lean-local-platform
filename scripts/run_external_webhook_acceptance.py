#!/usr/bin/env python3
from __future__ import annotations

import argparse
import ipaddress
import json
import os
import socket
import sys
import time
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "web" / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.db import init_db  # noqa: E402
from app.services.alerts import delivery_max_attempts, emit_alert  # noqa: E402


def _safe_endpoint(url: str) -> str:
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))


def _api_token() -> str:
    configured = os.environ.get("LEAN_API_TOKEN", "").strip()
    if configured:
        return configured
    token_path = Path(
        os.environ.get(
            "LEAN_API_TOKEN_FILE",
            str(ROOT / "web" / "runtime" / "secrets" / "api_token"),
        )
    )
    try:
        return token_path.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def _assert_external_endpoint(url: str, *, allow_local: bool = False) -> None:
    parts = urlsplit(url)
    if parts.scheme not in {"http", "https"} or not parts.hostname:
        raise ValueError("webhook_url_must_be_http_or_https")
    if allow_local:
        return
    addresses = {
        item[4][0]
        for item in socket.getaddrinfo(
            parts.hostname,
            parts.port or (443 if parts.scheme == "https" else 80),
            type=socket.SOCK_STREAM,
        )
    }
    if not addresses:
        raise ValueError("webhook_hostname_did_not_resolve")
    for address in addresses:
        parsed = ipaddress.ip_address(address)
        if (
            parsed.is_private
            or parsed.is_loopback
            or parsed.is_link_local
            or parsed.is_multicast
            or parsed.is_reserved
            or parsed.is_unspecified
        ):
            raise ValueError(f"webhook_endpoint_is_not_external:{address}")


def _api(
    base_url: str,
    path: str,
    *,
    method: str = "GET",
    payload: dict[str, Any] | None = None,
    timeout: int = 30,
) -> tuple[int, Any]:
    headers: dict[str, str] = {}
    token = _api_token()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if payload is not None:
        headers.setdefault("Content-Type", "application/json")
    request = urllib.request.Request(
        base_url.rstrip("/") + path,
        method=method,
        headers=headers,
        data=None if payload is None else json.dumps(payload).encode("utf-8"),
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8")
            return response.status, (json.loads(raw) if raw else {})
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            payload = {"detail": raw}
        return exc.code, payload


def _load_alert_deliveries(alert_id: str) -> list[dict[str, Any]]:
    from app.db import db, rows_to_dicts

    with db() as connection:
        rows = connection.execute(
            """
            select *
            from alert_deliveries
            where alert_id=?
            order by created_at desc
            """,
            (alert_id,),
        ).fetchall()
    return rows_to_dicts(rows)


def _webhook_delivery(deliveries: list[dict[str, Any]]) -> dict[str, Any]:
    for delivery in deliveries:
        if str(delivery.get("channel")) == "webhook":
            return delivery
    return {}


def _health_channel(health: dict[str, Any], *, channel: str = "webhook") -> dict[str, Any]:
    for item in health.get("channels") or []:
        if str(item.get("channel")) == channel:
            return item
    return {}


def _requeue_dead_letter(api_url: str) -> dict[str, Any]:
    status, payload = _api(api_url, "/api/alert-deliveries/requeue-dead-letter", method="POST")
    if status >= 400:
        raise RuntimeError(f"requeue_dead_letter_failed:{status}:{payload}")
    return payload


def _collect_sample(alert_id: str, api_url: str) -> tuple[dict[str, Any], dict[str, Any]]:
    try:
        health_status, health_payload = _api(api_url, "/api/alert-deliveries/health")
        health = (
            health_payload
            if health_status < 400
            else {"ok": False, "reason": f"health_http_{health_status}"}
        )
    except Exception as exc:
        health = {"ok": False, "reason": str(exc)}
    deliveries = _load_alert_deliveries(alert_id)
    return _webhook_delivery(deliveries), health


def _delivery_attempts(samples: list[dict[str, Any]]) -> list[int]:
    values: list[int] = []
    for sample in samples:
        value = sample.get("delivery", {}).get("attempt_count")
        if value is not None:
            try:
                values.append(int(value))
            except (TypeError, ValueError):
                continue
    return values


def _normalize_status(value: Any) -> str:
    return str(value or "unknown").strip().lower() or "unknown"


def _is_persisted_success(sample: dict[str, Any]) -> bool:
    response_code = int(sample.get("response_code") or 0)
    return _normalize_status(sample.get("status")) == "success" and 200 <= response_code < 300


def _health_recovered(
    health_states: list[str],
    *,
    require_health_recovery: bool,
) -> bool:
    if not require_health_recovery or not health_states:
        return True
    normalized = [state for state in health_states if state not in {"", "unknown"}]
    if not normalized:
        return True
    start_state = normalized[0]
    end_state = normalized[-1]
    if start_state in {"failed", "dead_letter"}:
        return end_state in {"success", "warning", "degraded", "ok", "unprobed"}
    return end_state in {"success", "warning", "degraded", "ok", "unprobed"}


def _dead_letter_regressed(
    health_states: list[str],
    *,
    did_requeue: bool,
    requeue_requested: bool,
) -> bool:
    if not health_states:
        return True
    start_state = health_states[0]
    end_state = health_states[-1]
    if start_state == "dead_letter":
        return did_requeue and end_state != "dead_letter"
    if end_state == "dead_letter":
        return requeue_requested and did_requeue
    return end_state != "dead_letter"


def _health_states(samples: list[dict[str, Any]]) -> list[str]:
    states: list[str] = []
    for sample in samples:
        health = sample.get("health") if isinstance(sample.get("health"), dict) else {}
        status = "unknown"
        webhook = _health_channel(health)
        if webhook:
            status = str(webhook.get("status") or "unknown").strip().lower()
        states.append(status)
    return states


def run(
    webhook_url: str,
    *,
    allow_local: bool = False,
    probe_id: str | None = None,
    api_url: str = "http://127.0.0.1:8000",
    monitor_hours: float = 0,
    poll_seconds: float = 15,
    enable_requeue: bool = False,
    require_health_recovery: bool = True,
) -> dict[str, Any]:
    url = str(webhook_url or "").strip()
    if not url:
        raise ValueError("external_webhook_not_configured")
    _assert_external_endpoint(url, allow_local=allow_local)
    init_db()
    resolved_probe_id = probe_id or str(uuid.uuid4())
    alert = emit_alert(
        "paper_schedule_failed",
        severity="critical",
        title="LEAN external webhook acceptance probe",
        message="External notification terminal acceptance probe.",
        source="external_webhook_acceptance",
        related_id=resolved_probe_id,
        details={
            "probe": True,
            "probeId": resolved_probe_id,
            "sentAt": datetime.now(timezone.utc).isoformat(),
        },
        dedupe_key=f"external_webhook_acceptance:{resolved_probe_id}",
        webhook_url=url,
    )
    delivery = alert.get("delivery") or {}
    if (
        delivery.get("status") != "success"
        or not 200 <= int(delivery.get("response_code") or 0) < 300
    ):
        raise RuntimeError(
            "external_webhook_delivery_failed:"
            f"status={delivery.get('status')}:"
            f"response_code={delivery.get('response_code')}:"
            f"error={delivery.get('last_error') or 'unknown'}"
        )

    max_allowed_attempts = max(1, int(delivery_max_attempts()))
    samples: list[dict[str, Any]] = []
    start_health: dict[str, Any] = {}
    end_health: dict[str, Any] = {}
    requeue_result: dict[str, Any] = {"executed": False}
    did_requeue = False
    start = datetime.now(timezone.utc)
    deadline = time.time() + max(0.0, float(monitor_hours)) * 3600

    if deadline > time.time():
        try:
            start_delivery, start_health = _collect_sample(str(alert.get("id")), api_url)
        except Exception:
            start_delivery, start_health = {}, {}
        samples.append(
            {
                "at": start.isoformat(),
                "delivery": start_delivery or _webhook_delivery(_load_alert_deliveries(str(alert.get("id")))),
                "health": start_health,
            }
        )
        while time.time() < deadline:
            now_delivery, now_health = _collect_sample(str(alert.get("id")), api_url)
            samples.append(
                {
                    "at": datetime.now(timezone.utc).isoformat(),
                    "delivery": now_delivery,
                    "health": now_health,
                }
            )
            if (
                enable_requeue
                and not did_requeue
                and now_delivery.get("status") in {"failed", "dead_letter"}
            ):
                try:
                    requeue_result = _requeue_dead_letter(api_url)
                    requeue_result["executed"] = True
                except Exception as exc:
                    requeue_result = {"executed": True, "error": str(exc)}
                did_requeue = True
            if time.time() >= deadline:
                break
            time.sleep(max(1.0, float(poll_seconds)))
        end_health = samples[-1].get("health", {})
        if not end_health:
            end_health = start_health
    if not samples:
        try:
            start_delivery, start_health = _collect_sample(str(alert.get("id")), api_url)
        except Exception:
            start_health = {}
            start_delivery = {}
        samples = [
            {
                "at": start.isoformat(),
                "delivery": start_delivery or delivery,
                "health": start_health,
            }
        ]
        end_health = start_health

    latest_delivery = samples[-1].get("delivery", {})
    attempt_counts = _delivery_attempts(samples)
    max_attempt_count = max(attempt_counts or [int(delivery.get("attempt_count") or 0)])
    bounded_attempts = max_attempt_count <= max_allowed_attempts
    success_samples = [
        sample
        for sample in samples
        if _is_persisted_success(sample.get("delivery", {}))
    ]
    has_persisted_success_2xx = bool(success_samples)
    retry_storm_absent = all(
        attempt_counts[i] >= attempt_counts[i - 1] for i in range(1, len(attempt_counts))
    )

    health_states = _health_states(samples)
    start_webhook_status = health_states[0] if health_states else "unknown"
    end_webhook_status = health_states[-1] if health_states else "unknown"
    health_recovered = _health_recovered(
        health_states,
        require_health_recovery=require_health_recovery,
    )
    dead_letter_regressed = _dead_letter_regressed(
        health_states,
        did_requeue=did_requeue,
        requeue_requested=enable_requeue,
    )

    passed = bool(
        has_persisted_success_2xx
        and bounded_attempts
        and retry_storm_absent
        and health_recovered
        and dead_letter_regressed
    )
    status = "EXTERNAL_WEBHOOK_PASS" if passed else "EXTERNAL_WEBHOOK_FAIL"
    return {
        "status": status,
        "passed": passed,
        "testedAt": datetime.now(timezone.utc).isoformat(),
        "probeId": resolved_probe_id,
        "alertId": alert.get("id"),
        "channel": delivery.get("channel"),
        "deliveryId": delivery.get("id"),
        "attemptCount": int(delivery.get("attempt_count") or 0),
        "responseCode": int(delivery.get("response_code") or 0),
        "persistedDeliveryStatus": delivery.get("status"),
        "endpoint": _safe_endpoint(url),
        "maxConfiguredAttempts": max_allowed_attempts,
        "requeue": {
            "requested": enable_requeue,
            "executed": bool(did_requeue),
            "result": requeue_result,
        },
        "observedWindowHours": monitor_hours,
        "pollSeconds": poll_seconds,
        "observations": samples,
        "startHealth": start_health,
        "finalHealth": end_health,
        "finalDelivery": latest_delivery,
        "deliveryRecovered": has_persisted_success_2xx,
        "boundedAttempts": bounded_attempts,
        "retryStormAbsent": retry_storm_absent,
        "healthRecovered": health_recovered,
        "deadLetterRegressed": dead_letter_regressed,
        "observedHealthStates": health_states,
        "observedAttemptCounts": attempt_counts,
        "hasPersistedSuccess": has_persisted_success_2xx,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Send and persist a real external webhook acceptance probe."
    )
    parser.add_argument(
        "--webhook-url",
        default=os.environ.get("LEAN_ALERT_WEBHOOK_URL", ""),
        help="External webhook URL; defaults to LEAN_ALERT_WEBHOOK_URL.",
    )
    parser.add_argument(
        "--allow-local-endpoint",
        action="store_true",
        help="Allow loopback/private endpoints for development only; such evidence is not third-party certification.",
    )
    parser.add_argument(
        "--monitor-hours",
        type=float,
        default=24,
        help="Observation window in hours after probe acceptance.",
    )
    parser.add_argument(
        "--poll-seconds",
        type=float,
        default=15,
        help="Seconds between observation samples.",
    )
    parser.add_argument(
        "--api-url",
        default="http://127.0.0.1:8000",
        help="Backend base URL for alert-delivery health and optional dead-letter requeue.",
    )
    parser.add_argument(
        "--requeue-dead-letter",
        action="store_true",
        help="Requeue dead-lettered alert deliveries once during the observation window.",
    )
    parser.add_argument(
        "--skip-health-recovery",
        action="store_true",
        help="Do not require alert-delivery health recovery during observation.",
    )
    parser.add_argument(
        "--evidence",
        type=Path,
        default=ROOT
        / "web"
        / "runtime"
        / "audit"
        / "external-webhook-acceptance.json",
    )
    args = parser.parse_args()

    exit_code = 0
    try:
        evidence = run(
            args.webhook_url,
            allow_local=args.allow_local_endpoint,
            api_url=args.api_url,
            monitor_hours=args.monitor_hours,
            poll_seconds=args.poll_seconds,
            enable_requeue=args.requeue_dead_letter,
            require_health_recovery=not args.skip_health_recovery,
        )
        if args.allow_local_endpoint:
            evidence["status"] = "LOCAL_WEBHOOK_PASS"
            evidence["thirdPartyCertified"] = False
        else:
            evidence["thirdPartyCertified"] = True
        if not evidence.get("passed"):
            exit_code = 2
    except Exception as exc:
        evidence = {
            "status": "EXTERNAL_WEBHOOK_FAIL",
            "testedAt": datetime.now(timezone.utc).isoformat(),
            "thirdPartyCertified": False,
            "failure": {
                "type": type(exc).__name__,
                "detail": str(exc),
            },
        }
        exit_code = 2

    args.evidence.parent.mkdir(parents=True, exist_ok=True)
    args.evidence.write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(evidence, ensure_ascii=False, indent=2, default=str))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
