import sys
from pathlib import Path

import pytest


BACKEND_DIR = Path(__file__).resolve().parents[1]
ROOT_DIR = Path(__file__).resolve().parents[3]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))


@pytest.fixture(autouse=True)
def use_sqlite_test_backend(tmp_path, monkeypatch):
    import app.db as db_module

    monkeypatch.setattr(db_module, "DATABASE_URL", f"sqlite:///{tmp_path / 'test.sqlite3'}")
