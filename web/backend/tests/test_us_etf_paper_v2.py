from __future__ import annotations

from pathlib import Path

import pytest

from app.services import us_etf_paper_certification as probe
from app.services import us_etf_paper_v2


def _trusted_source(snapshot_dir: Path) -> dict:
    return {
        "id": "bt-1",
        "project_id": "project-1",
        "status": "success",
        "trust_status": "trusted",
        "validation": {"passed": True, "data": {"truncated": False}},
        "asset_class": "equity",
        "venue": "usa",
        "resolution": "daily",
        "symbol": "SPY",
        "fingerprint": {
            "datasetCertification": {
                "isProduction": True,
                "isCertified": True,
                "environment": "production",
                "qaStatus": "ok",
                "datasetVersion": "us-bars-v1",
            }
        },
        "parameters": {
            "strategyTemplateKey": "etf_rotation",
            "market": "usa",
            "venue": "usa",
            "resolution": "daily",
            "end": "2025-12-31",
            "cash": 100000,
            "commissionPerOrder": 1.0,
            "strategySnapshotDir": str(snapshot_dir),
            "strategySnapshotMainFile": "main.py",
            "strategySnapshotAlgorithmClass": "EtfRotationCertifiedAlgorithm",
            "strategySnapshotLanguage": "Python",
        },
    }


def test_us_etf_source_context_requires_trusted_certified_daily_etf(monkeypatch, tmp_path):
    snapshot = tmp_path / "strategy"
    snapshot.mkdir()
    source = _trusted_source(snapshot)
    monkeypatch.setattr(us_etf_paper_v2, "get_backtest", lambda _run_id: source)
    monkeypatch.setattr(us_etf_paper_v2, "get_result", lambda _run_id: {"holdings": []})
    monkeypatch.setattr(us_etf_paper_v2, "run_directory", lambda *_args, **_kwargs: snapshot)
    run, result, parameters, path = us_etf_paper_v2._source_context("bt-1", "project-1")
    assert run["id"] == "bt-1"
    assert result == {"holdings": []}
    assert parameters["strategyTemplateKey"] == "etf_rotation"
    assert path == snapshot

    source["parameters"] = {**source["parameters"], "strategyTemplateKey": "buy_hold"}
    with pytest.raises(ValueError, match="etf_rotation"):
        us_etf_paper_v2._source_context("bt-1", "project-1")


def test_us_etf_source_context_rejects_research_or_non_us_scope(monkeypatch, tmp_path):
    snapshot = tmp_path / "strategy"
    snapshot.mkdir()
    source = _trusted_source(snapshot)
    monkeypatch.setattr(us_etf_paper_v2, "get_backtest", lambda _run_id: source)
    monkeypatch.setattr(us_etf_paper_v2, "get_result", lambda _run_id: {"holdings": []})
    monkeypatch.setattr(us_etf_paper_v2, "run_directory", lambda *_args, **_kwargs: snapshot)

    source["parameters"] = {**source["parameters"], "allowResearchSource": True}
    with pytest.raises(ValueError, match="Research-source"):
        us_etf_paper_v2._source_context("bt-1", "project-1")

    source["parameters"] = {**source["parameters"], "allowResearchSource": False}
    source["venue"] = "china"
    with pytest.raises(ValueError, match="market=usa"):
        us_etf_paper_v2._source_context("bt-1", "project-1")


def test_us_etf_constant_commission_is_frozen_in_worker_risk_semantics():
    session = {
        "parameters": {
            "commissionPerOrder": 1.25,
            "commissionRate": 0.0,
            "minCommission": 1.25,
            "stampTaxSell": 0.0,
            "transferFeeRate": 0.0,
        }
    }
    assert us_etf_paper_v2._commission(session) == pytest.approx(1.25)
    assert session["parameters"]["commissionRate"] == 0.0
    assert session["parameters"]["minCommission"] == pytest.approx(1.25)
    assert session["parameters"]["stampTaxSell"] == 0.0
    assert session["parameters"]["transferFeeRate"] == 0.0


def test_risk_probe_is_guaranteed_to_exceed_usable_cash_and_order_limit():
    quantity, inputs = probe._oversized_buy(
        {
            "cash": 1000.0,
            "parameters": {
                "minCash": 100.0,
                "commissionPerOrder": 1.0,
                "maxOrderAmount": 750.0,
            },
        },
        50.0,
    )
    principal = quantity * 50.0
    assert principal > 1000.0 - 100.0 + 1.0
    assert principal > 750.0
    assert inputs["requestedPrincipal"] == pytest.approx(principal)


def test_risk_probe_refuses_to_fabricate_reject(monkeypatch):
    paper_run = {
        "id": "paper-run-1",
        "session_id": "session-1",
        "backtest_run_id": "child-1",
        "trade_date": "2026-01-05",
    }
    session = {
        "id": "session-1",
        "symbol": "SPY",
        "cash": 1000.0,
        "equity": 1000.0,
        "parameters": {
            "paperMarketPolicy": us_etf_paper_v2.POLICY_VERSION,
            "datasetVersion": "us-bars-v1",
            "strategySnapshotDir": "/managed/strategy",
            "strategySnapshotHash": "snapshot-sha",
            "commissionPerOrder": 1.0,
        },
    }
    child = {"id": "child-1", "status": "success", "validation": {"passed": True}}
    monkeypatch.setattr(probe, "_paper_context", lambda _run_id: (paper_run, session, child))
    monkeypatch.setattr(probe, "_probe_price", lambda *_args: 100.0)
    monkeypatch.setattr(
        probe.paper_order_pipeline,
        "record_intent",
        lambda **_kwargs: {
            "id": "probe-intent",
            "trade_date": "2026-01-05",
            "dataset_version": "us-bars-v1",
        },
    )
    monkeypatch.setattr(probe.paper_order_pipeline, "current_state", lambda _intent_id: "INTENT_CREATED")
    transitions = []
    monkeypatch.setattr(
        probe.paper_order_pipeline,
        "append_transition",
        lambda intent_id, state, **kwargs: transitions.append((intent_id, state, kwargs)) or {},
    )
    monkeypatch.setattr(probe.paper_service, "get_session", lambda _session_id: session)
    monkeypatch.setattr(probe.paper_service, "list_positions", lambda _session_id: [])
    monkeypatch.setattr(probe.paper_service, "_strategy_fingerprint", lambda _child: "strategy-fp")
    monkeypatch.setattr(probe.paper_service, "_lean_intent_rejection", lambda *_args: None)

    with pytest.raises(ValueError, match="was not rejected"):
        probe.record_worker_rejection_probe("paper-run-1")
    assert transitions[0][1] == "VALIDATION_PENDING"
    assert all(state != "FILLED" for _, state, _ in transitions)


def test_us_etf_walkforward_creation_is_policy_guarded(monkeypatch):
    monkeypatch.setattr(
        us_etf_paper_v2.paper_service,
        "get_session",
        lambda _session_id: {
            "id": "session-1",
            "parameters": {"paperMarketPolicy": us_etf_paper_v2.POLICY_VERSION},
        },
    )
    monkeypatch.setattr(
        us_etf_paper_v2.paper_service,
        "create_walkforward_run",
        lambda session_id, trade_date: {
            "id": "paper-run-1",
            "session_id": session_id,
            "trade_date": trade_date,
        },
    )
    created = us_etf_paper_v2.create_walkforward_run("session-1", "2026-01-05")
    assert created["id"] == "paper-run-1"

    monkeypatch.setattr(
        us_etf_paper_v2.paper_service,
        "get_session",
        lambda _session_id: {"id": "session-1", "parameters": {}},
    )
    with pytest.raises(ValueError, match="not a U.S. ETF"):
        us_etf_paper_v2.create_walkforward_run("session-1", "2026-01-05")
