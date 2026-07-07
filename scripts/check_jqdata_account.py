#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]


def _load_env(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        text = line.strip()
        if not text or text.startswith("#") or "=" not in text:
            continue
        key, value = text.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def _jsonable(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_jsonable(item) for item in value]
    if hasattr(value, "to_dict"):
        try:
            return value.to_dict()
        except Exception:
            pass
    return str(value)


def main() -> int:
    parser = argparse.ArgumentParser(description="Check JQData account authentication, account info, and query quota.")
    parser.add_argument("--username", help="JQData username. Defaults to JQDATA_USERNAME.")
    parser.add_argument("--password", help="JQData password. Defaults to JQDATA_PASSWORD.")
    parser.add_argument("--token", help="JQData auth token. Defaults to JQDATA_TOKEN.")
    parser.add_argument("--env-file", default=str(ROOT / ".env"))
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    _load_env(Path(args.env_file))
    token = args.token or os.environ.get("JQDATA_TOKEN")
    username = args.username or os.environ.get("JQDATA_USERNAME")
    password = args.password or os.environ.get("JQDATA_PASSWORD")
    if not token and not (username and password):
        payload = {
            "provider": "jqdata",
            "status": "unavailable",
            "reason": "credential_missing",
            "credentials": {
                "JQDATA_TOKEN": bool(token),
                "JQDATA_USERNAME": bool(username),
                "JQDATA_PASSWORD": bool(password),
            },
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 3

    try:
        import jqdatasdk as jq  # type: ignore
    except ImportError as exc:
        payload = {"provider": "jqdata", "status": "unavailable", "reason": "dependency_missing:jqdatasdk", "error": str(exc)}
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 3

    try:
        if token:
            jq.auth_by_token(token)
            auth_method = "token"
        else:
            jq.auth(username, password)
            auth_method = "username_password"
        is_auth = bool(jq.is_auth())
        account_info = jq.get_account_info() if hasattr(jq, "get_account_info") else None
        query_count = jq.get_query_count() if hasattr(jq, "get_query_count") else None
    except Exception as exc:
        payload = {
            "provider": "jqdata",
            "status": "unavailable",
            "reason": "login_or_permission_query_failed",
            "error": str(exc),
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
        return 2

    payload = {
        "provider": "jqdata",
        "status": "available" if is_auth else "unavailable",
        "authMethod": auth_method,
        "isAuth": is_auth,
        "accountInfo": _jsonable(account_info),
        "queryCount": _jsonable(query_count),
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
    return 0 if is_auth else 2


if __name__ == "__main__":
    raise SystemExit(main())
