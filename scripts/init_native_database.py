#!/usr/bin/env python3
from __future__ import annotations

import os
import re
import sys
from pathlib import Path
from urllib.parse import unquote, urlsplit


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "web" / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))


def _name(value: str, label: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9_]+", value):
        raise RuntimeError(f"unsafe_{label}")
    return value


def _password(name: str, file_name: str) -> str:
    value = os.environ.get(name, "")
    if value:
        return value
    path_value = os.environ.get(file_name, "")
    if path_value:
        try:
            return Path(path_value).read_text(encoding="utf-8").strip()
        except OSError as exc:
            raise RuntimeError(f"{file_name}_unreadable") from exc
    raise RuntimeError(f"{name}_required")


def main() -> int:
    try:
        import pymysql
    except ImportError as exc:
        raise RuntimeError("pymysql_required_in_backend_environment") from exc
    admin_url = os.environ.get("LEAN_MYSQL_ADMIN_URL", "").strip()
    if not admin_url:
        raise RuntimeError("LEAN_MYSQL_ADMIN_URL_required")
    parsed = urlsplit(admin_url.replace("mysql+pymysql://", "mysql://", 1))
    if parsed.scheme != "mysql" or not parsed.hostname:
        raise RuntimeError("LEAN_MYSQL_ADMIN_URL_invalid")
    database = _name(os.environ.get("LEAN_MYSQL_DATABASE", "lean_market"), "database_name")
    user = _name(os.environ.get("LEAN_MYSQL_USER", "lean"), "user_name")
    loader = _name(os.environ.get("LEAN_MYSQL_LOADER_USER", "lean_loader"), "loader_user_name")
    password = _password("LEAN_MYSQL_PASSWORD", "LEAN_MYSQL_PASSWORD_FILE")
    loader_password = _password("LEAN_MYSQL_LOADER_PASSWORD", "LEAN_MYSQL_LOADER_PASSWORD_FILE")
    profile = os.environ.get("LEAN_DEPLOYMENT_PROFILE", "core").strip().lower()
    connection = pymysql.connect(
        host=parsed.hostname,
        port=int(parsed.port or 3306),
        user=unquote(parsed.username or "root"),
        password=unquote(parsed.password or ""),
        autocommit=True,
    )
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                f"create database if not exists `{database}` character set utf8mb4 collate utf8mb4_0900_ai_ci"
            )
            cursor.execute("create user if not exists %s@%s identified by %s", (user, "localhost", password))
            cursor.execute("create user if not exists %s@%s identified by %s", (loader, "localhost", loader_password))
            cursor.execute(f"grant all privileges on `{database}`.* to %s@%s", (user, "localhost"))
            cursor.execute(
                f"grant select,insert,update,delete,create,alter,index on `{database}`.* to %s@%s",
                (loader, "localhost"),
            )
            if profile in {"ml", "full"}:
                cursor.execute(
                    "create database if not exists lean_mlflow character set utf8mb4 collate utf8mb4_0900_ai_ci"
                )
                cursor.execute("grant all privileges on `lean_mlflow`.* to %s@%s", (user, "localhost"))
            cursor.execute("show variables like 'local_infile'")
            row = cursor.fetchone()
            if not row or str(row[1]).lower() not in {"on", "1"}:
                raise RuntimeError("mysql_local_infile_must_be_enabled")
    finally:
        connection.close()
    print("Native MySQL databases, users, and loader grants are ready.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
