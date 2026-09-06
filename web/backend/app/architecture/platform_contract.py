"""Machine-readable platform ownership and compatibility contract."""

from __future__ import annotations

from typing import Any

from ..localization import public_market_profiles


UPSTREAM_LEAN_CONTRACT: dict[str, Any] = {
    "engine": "QuantConnect LEAN",
    "upstreamRepository": "QuantConnect/Lean",
    "authority": "upstream",
    "integrationMode": "delegate",
    "coreForkPolicy": "no_local_core_fork",
    "capabilityPolicy": "preserve_upstream_engine_capabilities",
    "uiPolicy": "curated_control_plane_not_feature_reimplementation",
    "extensionBoundary": [
        "market_data_adapters",
        "market_hours_and_symbol_properties",
        "broker_adapters",
        "local_orchestration",
        "validation_and_governance",
        "web_control_plane",
    ],
    "nonGoals": [
        "replace_lean_algorithm_engine",
        "replace_lean_order_engine",
        "replace_lean_portfolio_engine",
        "replace_lean_brokerage_model",
        "maintain_a_divergent_lean_core_fork",
    ],
}


RESEARCH_PLANE_CONTRACT: dict[str, Any] = {
    "owner": "qlib-platform",
    "localExecutionEnabled": False,
    "localNotebookWorkspaceEnabled": False,
    "artifactContractVersion": "2.0",
    "importType": "QLIB_RESEARCH_BUNDLE",
    "handoff": {
        "import": "POST /api/research/imports/qlib",
        "preview": "GET /api/research/imports",
        "previewDetail": "GET /api/research/imports/{import_id}",
        "leanValidation": "POST /api/research/runs/{run_id}/lean-validation",
    },
    "platformResponsibilities": [
        "immutable_data_release",
        "artifact_lineage_and_hash_verification",
        "imported_result_preview",
        "authoritative_lean_execution_validation",
        "portfolio_and_execution_control",
    ],
    "externalResponsibilities": [
        "feature_engineering",
        "factor_research",
        "model_training",
        "walk_forward_research",
        "research_selection",
        "research_diagnostics",
    ],
}


def platform_capabilities() -> dict[str, Any]:
    """Single source of truth for engine, localization and research ownership."""
    markets = public_market_profiles()
    return {
        "schemaVersion": "1.0",
        "engine": dict(UPSTREAM_LEAN_CONTRACT),
        "localization": {
            "priority": ["china", "hongkong"],
            "strategy": "adapter_layer_over_upstream_lean",
            "markets": markets,
            "productionCertificationSource": "docs/release-status.md",
        },
        "research": dict(RESEARCH_PLANE_CONTRACT),
    }
