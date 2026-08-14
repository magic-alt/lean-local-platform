from __future__ import annotations

import re
from pathlib import Path


GRANDFATHERED_ML_FILES = {
    "app/ml/__init__.py",
    "app/ml/cross_sectional.py",
    "app/ml/training.py",
    "app/research/__init__.py",
    "app/research/factor_pipeline.py",
    "app/research/factors.py",
    "app/services/ml_research.py",
}


def test_platform_ml_surface_is_frozen_to_the_declared_legacy_allowlist():
    backend = Path(__file__).resolve().parents[1]
    app = backend / "app"
    governed = {
        path.relative_to(backend).as_posix()
        for root in (app / "ml", app / "research")
        for path in root.glob("*.py")
    }
    governed.add("app/services/ml_research.py")
    assert governed == GRANDFATHERED_ML_FILES


def test_model_framework_imports_remain_inside_the_isolated_legacy_worker():
    backend = Path(__file__).resolve().parents[1]
    app = backend / "app"
    pattern = re.compile(r"(?:from|import)\s+(?:lightgbm|xgboost|torch|qlib)\b")
    offenders = {
        path.relative_to(backend).as_posix()
        for path in app.rglob("*.py")
        if pattern.search(path.read_text(encoding="utf-8"))
        and path.relative_to(backend).as_posix() not in GRANDFATHERED_ML_FILES
    }
    assert offenders == set()


def test_research_control_center_hides_and_refuses_new_legacy_ml_jobs():
    backend = Path(__file__).resolve().parents[1]
    analysis_source = (backend / "app" / "services" / "research_analysis.py").read_text(encoding="utf-8")
    run_source = (backend / "app" / "services" / "research_runs.py").read_text(encoding="utf-8")
    assert '"legacy": True' in analysis_source
    assert "def public_templates()" in analysis_source
    assert "if template.get(\"legacy\")" in run_source



def test_contract_v2_never_assigns_execution_artifacts_to_qlib():
    from app.services.artifact_registry import QLIB_TYPES
    assert QLIB_TYPES.isdisjoint({"ORDER_INTENT", "BROKER_ORDER", "FILL", "POSITION", "CASH_LEDGER"})
