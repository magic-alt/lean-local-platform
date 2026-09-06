from __future__ import annotations

import pytest
from fastapi import HTTPException


def test_platform_contract_preserves_upstream_lean_and_external_research():
    from app.architecture.platform_contract import platform_capabilities

    capabilities = platform_capabilities()
    engine = capabilities["engine"]
    assert engine["engine"] == "QuantConnect LEAN"
    assert engine["upstreamRepository"] == "QuantConnect/Lean"
    assert engine["authority"] == "upstream"
    assert engine["integrationMode"] == "delegate"
    assert engine["coreForkPolicy"] == "no_local_core_fork"
    assert engine["capabilityPolicy"] == "preserve_upstream_engine_capabilities"

    research = capabilities["research"]
    assert research["owner"] == "qlib-platform"
    assert research["localExecutionEnabled"] is False
    assert research["localNotebookWorkspaceEnabled"] is False
    assert research["artifactContractVersion"] == "2.0"


def test_cn_hk_localization_profiles_are_explicit_and_fail_closed_at_execution():
    from app.architecture.platform_contract import platform_capabilities
    from app.lean_engine.config import base_config, validate_backtest_parameters
    from app.lean_engine.errors import LeanPlatformError
    from app.lean_engine.symbols import normalize_symbol

    markets = {
        item["key"]: item
        for item in platform_capabilities()["localization"]["markets"]
    }
    china = markets["china"]
    hongkong = markets["hongkong"]

    assert china["implementation_status"] == "implemented"
    assert china["execution_scope"] == "daily_localized"
    assert china["sessions"] == [
        ["09:30:00", "11:30:00"],
        ["13:00:00", "15:00:00"],
    ]
    assert china["currency"] == "CNY"
    assert normalize_symbol("600519.SH", "china") == "600519"
    china_parameters = validate_backtest_parameters(
        {
            "ticker": "600519",
            "assetClass": "equity",
            "market": "china",
            "resolution": "daily",
            "dataType": "trade",
            "start": "2025-01-02",
            "end": "2025-01-03",
            "cash": 100000,
        }
    )
    assert china_parameters["market"] == "china"

    assert hongkong["implementation_status"] == "partial"
    assert hongkong["execution_scope"] == "preview_only"
    assert hongkong["symbol_properties_required"] is True
    assert hongkong["lot_size_policy"] == "per_security_board_lot_required"
    assert hongkong["tick_size_policy"] == "per_security_price_tier_required"
    assert normalize_symbol("0700.HK", "hongkong") == "00700"

    hk_parameters = validate_backtest_parameters(
        {
            "ticker": "00700",
            "assetClass": "equity",
            "market": "hongkong",
            "resolution": "daily",
            "dataType": "trade",
            "start": "2025-01-02",
            "end": "2025-01-03",
            "cash": 100000,
        }
    )
    assert hk_parameters["market"] == "hongkong"
    assert hk_parameters["ticker"] == "00700"
    with pytest.raises(LeanPlatformError, match="market_execution_not_certified:hongkong"):
        base_config(
            "hk-preview-only",
            hk_parameters,
            algorithm_class="Algorithm",
            algorithm_location="/tmp/algorithm.py",
            language="Python",
        )


def test_local_research_examples_are_hidden_from_public_api():
    from app.api import examples as example_api

    assert example_api.catalog("research", None) == {"items": [], "count": 0}
    assert all(
        item["kind"] in {"backtest", "optimization"}
        for item in example_api.catalog(None, None)["items"]
    )
    with pytest.raises(HTTPException) as exc_info:
        example_api.detail("research", "stock-eda")
    assert exc_info.value.status_code == 404
    assert "qlib-platform" in str(exc_info.value.detail)
    with pytest.raises(HTTPException) as exc_info:
        example_api.instantiate(
            "research",
            "stock-eda",
            example_api.ExampleInstantiateRequest(),
        )
    assert exc_info.value.status_code == 404


def test_retired_local_research_execution_routes_return_not_found():
    from app.api import research

    with pytest.raises(HTTPException) as exc_info:
        research.retired_templates()
    assert exc_info.value.status_code == 404
    assert "qlib-platform" in str(exc_info.value.detail)


def test_experiment_batch_research_entrypoint_points_to_qlib_handoff():
    from app.api.experiment_batches import ExperimentBatchRequest, _payload
    from app.core.errors import LeanWebError

    with pytest.raises(LeanWebError, match="qlib-platform"):
        _payload(ExperimentBatchRequest(kind="research"))
