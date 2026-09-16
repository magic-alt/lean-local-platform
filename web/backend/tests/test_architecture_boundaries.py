from __future__ import annotations

from pathlib import Path

from app.architecture.module_boundaries import (
    architecture_violations,
    domain_import_violations,
    entrypoint_sql_write_violations,
    ownership_violations,
    sql_writers,
)
from app.architecture.state_ownership import (
    CANONICAL_TABLE_WRITERS,
    ORCHESTRATION_STATE_BOUNDARIES,
)


def _current_app_root() -> Path:
    return Path(__file__).resolve().parents[1] / "app"


def test_audit_critical_tables_have_exactly_one_declared_writer():
    app_root = _current_app_root()
    for table, owner in CANONICAL_TABLE_WRITERS.items():
        assert sql_writers(app_root, table) == {owner}, table


def test_api_and_task_entrypoints_do_not_write_protected_state_with_sql():
    app_root = _current_app_root()
    protected = set(CANONICAL_TABLE_WRITERS) | set(ORCHESTRATION_STATE_BOUNDARIES)
    assert entrypoint_sql_write_violations(app_root, protected) == []


def test_current_domain_and_writer_boundaries_are_clean():
    assert architecture_violations(_current_app_root()) == []


def test_domain_boundary_rejects_framework_vendor_and_upward_imports(tmp_path: Path):
    app_root = tmp_path / "app"
    domain = app_root / "domain"
    domain.mkdir(parents=True)
    (domain / "bad.py").write_text(
        "import tushare\n"
        "from fastapi import APIRouter\n"
        "from ..services import data_sync\n",
        encoding="utf-8",
    )

    violations = domain_import_violations(app_root)

    assert len(violations) == 3
    assert any("tushare" in item for item in violations)
    assert any("fastapi" in item for item in violations)
    assert any("..services" in item for item in violations)


def test_entrypoint_boundary_rejects_direct_canonical_ledger_sql(tmp_path: Path):
    app_root = tmp_path / "app"
    api = app_root / "api"
    api.mkdir(parents=True)
    (api / "bad.py").write_text(
        'SQL = "insert into paper_ledger_entries (id) values (?)"\n',
        encoding="utf-8",
    )

    violations = entrypoint_sql_write_violations(
        app_root,
        {"paper_ledger_entries"},
    )

    assert violations == [
        "app/api/bad.py: entrypoint performs direct SQL write to paper_ledger_entries"
    ]


def test_canonical_writer_boundary_rejects_second_writer(tmp_path: Path):
    app_root = tmp_path / "app"
    services = app_root / "services"
    services.mkdir(parents=True)
    (services / "owner.py").write_text(
        'SQL = "insert into artifact_registry (artifact_id) values (?)"\n',
        encoding="utf-8",
    )
    (services / "shadow.py").write_text(
        'SQL = "update artifact_registry set artifact_id=?"\n',
        encoding="utf-8",
    )

    violations = ownership_violations(
        app_root,
        {"artifact_registry": "app/services/owner.py"},
    )

    assert violations == [
        "artifact_registry: canonical writer mismatch; expected=app/services/owner.py; "
        "actual=['app/services/owner.py', 'app/services/shadow.py']"
    ]


def test_paper_router_uses_command_and_query_boundaries():
    router = (_current_app_root() / "api" / "paper_accounts.py").read_text(encoding="utf-8")
    assert "paper_account_commands as commands" in router
    assert "paper_account_queries as queries" in router
    assert "paper_accounts as service" not in router
