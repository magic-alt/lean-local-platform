from __future__ import annotations

import re
from pathlib import Path


def _sql_writers(app_root: Path, table: str) -> set[str]:
    pattern = re.compile(rf"\b(?:insert\s+into|update|delete\s+from)\s+{re.escape(table)}\b", re.IGNORECASE)
    writers: set[str] = set()
    for path in app_root.rglob("*.py"):
        if pattern.search(path.read_text(encoding="utf-8")):
            writers.add(path.relative_to(app_root.parent).as_posix())
    return writers


def test_audit_critical_tables_have_exactly_one_declared_writer():
    from app.architecture.state_ownership import CANONICAL_TABLE_WRITERS

    app_root = Path(__file__).resolve().parents[1] / "app"
    for table, owner in CANONICAL_TABLE_WRITERS.items():
        assert _sql_writers(app_root, table) == {owner}, table


def test_api_and_task_entrypoints_do_not_write_orchestration_state_with_sql():
    from app.architecture.state_ownership import ORCHESTRATION_STATE_BOUNDARIES

    app_root = Path(__file__).resolve().parents[1] / "app"
    entrypoints = [app_root / "api", app_root / "tasks"]
    for table in ORCHESTRATION_STATE_BOUNDARIES:
        pattern = re.compile(
            rf"\b(?:insert\s+into|update|delete\s+from)\s+{re.escape(table)}\b",
            re.IGNORECASE,
        )
        offenders = [
            path.relative_to(app_root.parent).as_posix()
            for root in entrypoints
            for path in root.rglob("*.py")
            if pattern.search(path.read_text(encoding="utf-8"))
        ]
        assert offenders == [], f"{table}: {offenders}"


def test_paper_router_uses_command_and_query_boundaries():
    router = (Path(__file__).resolve().parents[1] / "app" / "api" / "paper_accounts.py").read_text(encoding="utf-8")
    assert "paper_account_commands as commands" in router
    assert "paper_account_queries as queries" in router
    assert "paper_accounts as service" not in router
