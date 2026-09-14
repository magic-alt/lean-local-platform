from datetime import datetime
from zoneinfo import ZoneInfo

from app.db import db, init_db
from app.services import settings as settings_service
from app.services.settings import get_settings, update_settings


def current_shanghai_date():
    return datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat()


def test_web_default_end_date_is_current_date():
    init_db()
    assert get_settings()["defaultEnd"] == current_shanghai_date()


def test_web_default_end_date_migration_advances_legacy_value():
    init_db()
    with db() as connection:
        connection.execute(
            "insert into settings (`key`, value_json, updated_at) values (?, ?, ?)",
            ("defaultEnd", '"2024-12-31"', "now"),
        )
        connection.execute("delete from schema_migrations where revision = ?", ("0007_web_end_date_default",))

    init_db()

    assert get_settings()["defaultEnd"] == current_shanghai_date()


def test_web_default_end_is_resolved_at_read_time(monkeypatch):
    init_db()
    monkeypatch.setattr(settings_service, "_current_shanghai_date", lambda: "2099-01-02")

    assert get_settings()["defaultEnd"] == "2099-01-02"


def test_explicit_default_end_remains_user_controlled(monkeypatch):
    init_db()
    update_settings({"defaultEnd": "2026-01-31"})
    monkeypatch.setattr(settings_service, "_current_shanghai_date", lambda: "2099-01-02")

    assert get_settings()["defaultEnd"] == "2026-01-31"
