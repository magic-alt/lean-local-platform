import os
import json

import pytest


def test_load_env_file_reads_tushare_token_without_overriding_existing_value(tmp_path, monkeypatch):
    from app.core.config import _load_env_file

    env_file = tmp_path / ".env"
    env_file.write_text(
        """
# local provider token
TUSHARE_TOKEN="from-file"
ALPHAVANTAGE_API_KEY=from-alpha
""",
        encoding="utf-8",
    )

    monkeypatch.delenv("TUSHARE_TOKEN", raising=False)
    monkeypatch.delenv("ALPHAVANTAGE_API_KEY", raising=False)
    _load_env_file(env_file)
    assert os.environ["TUSHARE_TOKEN"] == "from-file"
    assert os.environ["ALPHAVANTAGE_API_KEY"] == "from-alpha"

    monkeypatch.setenv("TUSHARE_TOKEN", "from-env")
    _load_env_file(env_file)
    assert os.environ["TUSHARE_TOKEN"] == "from-env"


def test_database_descriptor_defaults_to_mysql_without_sqlite_path(monkeypatch):
    import app.db as db_module

    monkeypatch.setattr(db_module, "DATABASE_URL", "mysql+pymysql://lean:lean@127.0.0.1:3306/lean_market")
    descriptor = db_module.database_descriptor()

    assert descriptor["engine"] == "mysql"
    assert descriptor["database"] == "lean_market"
    assert "path" not in descriptor
    assert "HS300.sqlite3" not in json.dumps(descriptor)


def test_sqlite_database_url_is_rejected_outside_test_gate(monkeypatch):
    import app.db as db_module

    monkeypatch.setattr(db_module, "DATABASE_URL", "sqlite:////tmp/lean-platform.sqlite3")
    monkeypatch.setattr(db_module, "SQLITE_TEST_BACKEND_ENABLED", False)

    with pytest.raises(RuntimeError, match="SQLite is disabled"):
        db_module.database_backend()
