from app.db import db, init_db
from app.services.settings import get_settings


def test_web_default_end_date_is_2026_07_13():
    init_db()
    assert get_settings()["defaultEnd"] == "2026-07-13"


def test_web_default_end_date_migration_advances_legacy_value():
    init_db()
    with db() as connection:
        connection.execute(
            "insert into settings (`key`, value_json, updated_at) values (?, ?, ?)",
            ("defaultEnd", '"2024-12-31"', "now"),
        )
        connection.execute("delete from schema_migrations where revision = ?", ("0007_web_end_date_default",))

    init_db()

    assert get_settings()["defaultEnd"] == "2026-07-13"
