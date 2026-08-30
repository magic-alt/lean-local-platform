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


DATABASES = (
    ("lean_platform", "LEAN_POSTGRES_APP_USER", "lean_app", "LEAN_POSTGRES_APP_PASSWORD"),
    ("lean_celery", "LEAN_POSTGRES_CELERY_USER", "lean_celery", "LEAN_POSTGRES_CELERY_PASSWORD"),
    ("lean_mlflow", "LEAN_POSTGRES_MLFLOW_USER", "lean_mlflow", "LEAN_POSTGRES_MLFLOW_PASSWORD"),
)


def _identifier(value: str, label: str) -> str:
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", value):
        raise RuntimeError(f"unsafe_{label}")
    return value


def _secret(name: str) -> str:
    value = os.environ.get(name, "")
    if value:
        return value
    path_value = os.environ.get(f"{name}_FILE", "")
    if path_value:
        try:
            value = Path(path_value).read_text(encoding="utf-8").strip()
        except OSError as exc:
            raise RuntimeError(f"{name}_FILE_unreadable") from exc
        if value:
            return value
    raise RuntimeError(f"{name}_required")


def main() -> int:
    try:
        import psycopg
        from psycopg import sql
    except ImportError as exc:
        raise RuntimeError("psycopg_required_in_backend_environment") from exc

    admin_url = os.environ.get("LEAN_POSTGRES_ADMIN_URL", "").strip()
    if not admin_url:
        raise RuntimeError("LEAN_POSTGRES_ADMIN_URL_required")
    parsed = urlsplit(admin_url.replace("postgresql+psycopg://", "postgresql://", 1))
    if parsed.scheme not in {"postgres", "postgresql"} or not parsed.hostname:
        raise RuntimeError("LEAN_POSTGRES_ADMIN_URL_invalid")

    connection = psycopg.connect(
        host=parsed.hostname,
        port=int(parsed.port or 5432),
        dbname=(parsed.path or "/postgres").lstrip("/") or "postgres",
        user=unquote(parsed.username or "postgres"),
        password=unquote(parsed.password or ""),
        autocommit=True,
    )
    try:
        for default_database, user_env, default_user, password_env in DATABASES:
            database = _identifier(
                os.environ.get(f"LEAN_POSTGRES_{default_database.removeprefix('lean_').upper()}_DATABASE", default_database),
                "database_name",
            )
            user = _identifier(os.environ.get(user_env, default_user), "role_name")
            password = _secret(password_env)
            with connection.cursor() as cursor:
                cursor.execute("select 1 from pg_roles where rolname=%s", (user,))
                if cursor.fetchone():
                    cursor.execute(
                        sql.SQL("alter role {} login password {}").format(
                            sql.Identifier(user), sql.Literal(password)
                        )
                    )
                else:
                    cursor.execute(
                        sql.SQL("create role {} login password {}").format(
                            sql.Identifier(user), sql.Literal(password)
                        )
                    )
                cursor.execute("select 1 from pg_database where datname=%s", (database,))
                if not cursor.fetchone():
                    cursor.execute(
                        sql.SQL("create database {} owner {}").format(
                            sql.Identifier(database), sql.Identifier(user)
                        )
                    )
                cursor.execute(
                    sql.SQL("alter database {} owner to {}").format(
                        sql.Identifier(database), sql.Identifier(user)
                    )
                )
    finally:
        connection.close()
    print("PostgreSQL platform, Celery, and MLflow databases are ready.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
