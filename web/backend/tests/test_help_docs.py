from __future__ import annotations

import json
import subprocess
import sys

import pytest


def test_help_catalog_metadata_search_and_path_validation():
    from app.core.errors import NotFoundError
    from app.services import help_docs

    items = help_docs.list_articles("maxBatchRuns")
    assert items
    assert {"group", "category", "summary", "status", "snippet"} <= items[0].keys()
    assert help_docs.article("backtests")["title"] == "单次与批量回测"
    assert help_docs.article("history")["status"] == "historical"
    with pytest.raises(NotFoundError):
        help_docs.article("../configuration")
    with pytest.raises(NotFoundError):
        help_docs.asset("../index.md")


def test_help_catalog_refreshes_when_a_source_changes(tmp_path, monkeypatch):
    from app.services import help_docs

    docs_root = tmp_path / "docs"
    help_root = docs_root / "help"
    help_root.mkdir(parents=True)
    source = help_root / "index.md"
    source.write_text("# First title\n\nalpha", encoding="utf-8")
    catalog = [{"slug": "index", "source": "help/index.md", "group": "guide", "category": "test", "order": 1, "summary": "test"}]
    catalog_path = help_root / "catalog.json"
    catalog_path.write_text(json.dumps(catalog), encoding="utf-8")
    monkeypatch.setattr(help_docs, "DOCS_ROOT", docs_root.resolve())
    monkeypatch.setattr(help_docs, "DOCS_DIR", help_root.resolve())
    monkeypatch.setattr(help_docs, "CATALOG_PATH", catalog_path.resolve())
    monkeypatch.setattr(help_docs, "_CACHE_SIGNATURE", None)
    monkeypatch.setattr(help_docs, "_CACHE_ARTICLES", ())
    assert help_docs.article("index")["title"] == "First title"
    source.write_text("# Second title\n\nbeta with more bytes", encoding="utf-8")
    assert help_docs.article("index")["title"] == "Second title"


def test_generated_api_reference_is_current():
    from app.core.config import PLATFORM_DIR

    result = subprocess.run(
        [sys.executable, str(PLATFORM_DIR / "scripts" / "generate_help_api_reference.py"), "--check", "--json"],
        cwd=PLATFORM_DIR,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr or result.stdout
    assert json.loads(result.stdout)["ok"] is True
