#!/usr/bin/env python3
from __future__ import annotations

import argparse
import ipaddress
import json
import os
import socket
import sys
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
from app.services.alerts import emit_alert  # noqa: E402


def _safe_endpoint(url: str) -> str:
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))


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


def run(
    webhook_url: str,
    *,
    allow_local: bool = False,
    probe_id: str | None = None,
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
    return {
        "status": "EXTERNAL_WEBHOOK_PASS",
        "testedAt": datetime.now(timezone.utc).isoformat(),
        "probeId": resolved_probe_id,
        "alertId": alert.get("id"),
        "channel": delivery.get("channel"),
        "deliveryId": delivery.get("id"),
        "attemptCount": delivery.get("attempt_count"),
        "responseCode": delivery.get("response_code"),
        "persistedDeliveryStatus": delivery.get("status"),
        "endpoint": _safe_endpoint(url),
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
        )
        if args.allow_local_endpoint:
            evidence["status"] = "LOCAL_WEBHOOK_PASS"
            evidence["thirdPartyCertified"] = False
        else:
            evidence["thirdPartyCertified"] = True
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
