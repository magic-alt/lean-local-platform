"""Declared canonical writers for audit-critical state.

Tests use this manifest to reject a second SQL writer. Command/query facades may
delegate to these owners but must not mutate their tables directly.
"""

CANONICAL_TABLE_WRITERS = {
    "dataset_releases": "app/services/dataset_releases.py",
    "data_releases": "app/services/data_releases.py",
    "data_release_components": "app/services/data_releases.py",
    "artifact_registry": "app/services/artifact_registry.py",
    "artifact_lineage_edges": "app/services/artifact_registry.py",
    "artifact_promotion_events": "app/services/artifact_registry.py",
    "paper_ledger_entries": "app/services/paper_order_pipeline.py",
    "paper_account_projections": "app/services/paper_accounts.py",
    "paper_account_position_projections": "app/services/paper_accounts.py",
    "paper_account_daily_reports": "app/services/paper_accounts.py",
}

ORCHESTRATION_STATE_BOUNDARIES = {
    "backtest_runs": "app/repositories/backtest_repository.py",
    "tasks": "app/services/tasks.py",
    "data_sync_runs": "app/services/data_sync.py",
}
