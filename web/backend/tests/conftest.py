import os
import sys
from pathlib import Path

import pytest


os.environ.setdefault("LEAN_API_AUTH_REQUIRED", "0")


BACKEND_DIR = Path(__file__).resolve().parents[1]
ROOT_DIR = Path(__file__).resolve().parents[3]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))


@pytest.fixture(autouse=True)
def use_sqlite_test_backend(tmp_path, monkeypatch, request):
    import app.db as db_module

    if (
        request.node.get_closest_marker("integration_postgres")
        and os.environ.get("RUN_POSTGRES_INTEGRATION") == "1"
    ):
        yield
        return

    db_path = tmp_path / "test.sqlite3"
    monkeypatch.setattr(db_module, "DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setattr(db_module, "DB_PATH", db_path)
    monkeypatch.setattr(db_module, "SQLITE_TEST_BACKEND_ENABLED", True)
    # Market time series are filesystem-owned. Every unit test receives an
    # isolated lake so it can never mutate the developer's configured Data dir.
    from app.services import market_lake
    from app.services import db_object_store
    from app.services import data_sync

    monkeypatch.setattr(market_lake, "PARQUET_DIR", tmp_path / "parquet")
    monkeypatch.setattr(db_object_store, "FILE_OBJECT_STORE_DIR", tmp_path / "object-store")
    monkeypatch.setattr(
        data_sync,
        "_disk_metrics",
        lambda: {
            "diskFreeBytes": 10 * 1024**3,
            "diskTotalBytes": 20 * 1024**3,
            "diskReserveBytes": 1024**3,
            "diskWritableBytes": 9 * 1024**3,
            "databaseBytes": 0,
            "databaseLimitBytes": 0,
            "databaseUsagePercent": 0.0,
            "databaseLimitEnforced": False,
            "onDemandDatabaseLimitBytes": 50 * 1024**3,
            "databaseSizeSource": "pytest_fixture",
        },
    )
    yield
