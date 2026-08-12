# Current MySQL Schema

Generated at: 2026-08-12T11:42:53.295762+00:00

This is a read-only structure snapshot of the local `lean_market` database. Row counts are exact at generation time; no row contents or credentials are included.

## Tables and views

| Relation | Type | Exact rows |
| --- | --- | ---: |
| `adjustment_factors` | base table | 0 |
| `alert_deliveries` | base table | 179 |
| `alert_events` | base table | 199 |
| `all_factor_values` | view | — |
| `api_idempotency_keys` | base table | 183 |
| `ashare_daily_bars` | view | — |
| `ashare_tech_agent_profiles` | base table | 0 |
| `ashare_tech_agent_runs` | base table | 5 |
| `ashare_tech_agent_stages` | base table | 6 |
| `ashare_tech_candidate_signals` | base table | 0 |
| `ashare_tech_prediction_evaluations` | base table | 0 |
| `ashare_tech_predictions` | base table | 0 |
| `ashare_tech_prompt_templates` | base table | 0 |
| `ashare_tech_reports` | base table | 11 |
| `ashare_tech_watchlist_items` | base table | 26 |
| `ashare_trade_status` | view | — |
| `asset_capabilities` | base table | 8 |
| `backtest_results` | base table | 0 |
| `backtest_runs` | base table | 0 |
| `cbond_call_events` | base table | 0 |
| `cbond_daily_bars` | base table | 0 |
| `cbond_securities` | base table | 0 |
| `corporate_actions` | base table | 0 |
| `daily_basic_factor_values` | view | — |
| `daily_basic_values` | base table | 0 |
| `data_assets` | base table | 0 |
| `data_gap_resolutions` | base table | 582991 |
| `data_gaps` | base table | 0 |
| `data_import_batches` | base table | 0 |
| `data_quality_reports` | base table | 0 |
| `data_record_issues` | base table | 0 |
| `data_sync_items` | base table | 0 |
| `data_sync_runs` | base table | 0 |
| `data_sync_work_items` | base table | 0 |
| `dataset_releases` | base table | 3 |
| `dataset_versions` | base table | 0 |
| `derived_layer_watermarks` | base table | 0 |
| `derived_maintenance_runs` | base table | 1 |
| `experiment_batch_attempts` | base table | 0 |
| `experiment_batch_items` | base table | 0 |
| `experiment_batches` | base table | 0 |
| `experiments` | base table | 0 |
| `factor_evaluations` | base table | 0 |
| `factor_values` | base table | 0 |
| `feature_pipeline_fits` | base table | 0 |
| `financial_facts` | base table | 0 |
| `financial_statements` | base table | 0 |
| `futures_continuous_bars` | base table | 0 |
| `futures_continuous_builds` | base table | 0 |
| `futures_contracts` | base table | 0 |
| `futures_daily_bars` | base table | 0 |
| `futures_fee_schedules` | base table | 0 |
| `futures_main_mapping` | base table | 0 |
| `futures_main_rules` | base table | 0 |
| `futures_roll_events` | base table | 0 |
| `index_membership_events` | base table | 0 |
| `index_membership_pit` | view | — |
| `index_source_artifacts` | base table | 0 |
| `index_weights` | base table | 0 |
| `industry_membership` | base table | 0 |
| `instrument_identifiers` | base table | 0 |
| `instruments` | base table | 0 |
| `leakage_check_results` | base table | 0 |
| `market_daily_bars` | base table | 0 |
| `market_intraday_bars` | base table | 0 |
| `market_ticks` | base table | 0 |
| `market_trade_status` | base table | 0 |
| `ml_feature_files` | base table | 0 |
| `ml_feature_sets` | base table | 0 |
| `ml_prediction_files` | base table | 0 |
| `ml_training_runs` | base table | 0 |
| `ml_training_trials` | base table | 0 |
| `object_store_items` | base table | 0 |
| `oos_evaluations` | base table | 0 |
| `paper_account_checkpoints` | base table | 10 |
| `paper_account_daily_reports` | base table | 98 |
| `paper_account_daily_snapshots` | base table | 98 |
| `paper_account_generations` | base table | 4 |
| `paper_account_position_projections` | base table | 0 |
| `paper_account_projections` | base table | 4 |
| `paper_account_trust_certifications` | base table | 2 |
| `paper_accounts` | base table | 4 |
| `paper_certification_cohorts` | base table | 2 |
| `paper_certification_members` | base table | 4 |
| `paper_constraint_decisions` | base table | 26 |
| `paper_daily_job_events` | base table | 592 |
| `paper_daily_jobs` | base table | 143 |
| `paper_daily_reports` | base table | 582 |
| `paper_execution_cycle_events` | base table | 533 |
| `paper_execution_cycles` | base table | 104 |
| `paper_lean_order_events` | base table | 14 |
| `paper_ledger_entries` | base table | 25 |
| `paper_notification_outbox` | base table | 137 |
| `paper_order_fills` | base table | 6 |
| `paper_order_intents` | base table | 14 |
| `paper_order_transitions` | base table | 82 |
| `paper_orders` | base table | 130 |
| `paper_portfolio_snapshots` | base table | 582 |
| `paper_positions` | base table | 3 |
| `paper_reconciliation_records` | base table | 237 |
| `paper_risk_profiles` | base table | 4 |
| `paper_run_checkpoints` | base table | 588 |
| `paper_sessions` | base table | 48 |
| `paper_signals` | base table | 466 |
| `paper_strategy_deployments` | base table | 6 |
| `paper_strategy_signals` | base table | 98 |
| `paper_universe_certifications` | base table | 1 |
| `paper_universe_symbols` | base table | 51 |
| `paper_walkforward_runs` | base table | 103 |
| `parameter_candidates` | base table | 0 |
| `parameter_selection_events` | base table | 0 |
| `parquet_datasets` | base table | 7 |
| `parquet_files` | base table | 0 |
| `pipeline_runs` | base table | 27 |
| `pipeline_steps` | base table | 295 |
| `portfolio_optimization_runs` | base table | 0 |
| `projects` | base table | 5 |
| `provider_availability_log` | base table | 274 |
| `provider_dataset_catalog` | base table | 51 |
| `provider_dataset_watermarks` | base table | 0 |
| `provider_ingestion_manifests` | base table | 0 |
| `provider_raw_archive_issues` | base table | 0 |
| `provider_raw_archives` | base table | 0 |
| `provider_raw_records` | base table | 0 |
| `qa_warning_allowlist` | base table | 3 |
| `qlib_research_imports` | base table | 0 |
| `qlib_signal_snapshots` | base table | 0 |
| `recording_jobs` | base table | 0 |
| `recording_status` | base table | 0 |
| `reports` | base table | 0 |
| `reproducibility_certificates` | base table | 0 |
| `research_run_items` | base table | 7 |
| `research_runs` | base table | 4 |
| `research_sessions` | base table | 0 |
| `research_workspaces` | base table | 0 |
| `restricted_runner_jobs` | base table | 357 |
| `scheduler_leases` | base table | 0 |
| `schema_migrations` | base table | 45 |
| `securities` | base table | 0 |
| `security_name_history` | base table | 0 |
| `settings` | base table | 17 |
| `stored_object_chunks` | base table | 4 |
| `stored_objects` | base table | 4 |
| `strategy_admission_events` | base table | 0 |
| `strategy_admissions` | base table | 0 |
| `strategy_versions` | base table | 497 |
| `tasks` | base table | 24 |
| `trade_calendar` | base table | 0 |
| `universe_coverage_watermarks` | base table | 0 |
| `universe_membership` | base table | 0 |
| `verification_cases` | base table | 232 |
| `verification_runs` | base table | 4 |
| `walk_forward_runs` | base table | 0 |
| `walk_forward_windows` | base table | 0 |
| `workflow_events` | base table | 4880 |
| `workflow_lineage_edges` | base table | 0 |

## `adjustment_factors`

| Column | Type | Null | Key | Default | Extra |
| --- | --- | --- | --- | --- | --- |
| `symbol` | `varchar(96)` | NO | PRI |  |  |
| `trade_date` | `varchar(32)` | NO | PRI |  |  |
| `adj_factor` | `double` | NO |  |  |  |
| `source` | `varchar(96)` | NO | PRI |  |  |
| `batch_id` | `varchar(64)` | NO |  |  |  |

Indexes:
- `PRIMARY` (unique): `symbol`, `trade_date`, `source`

## `alert_deliveries`

| Column | Type | Null | Key | Default | Extra |
| --- | --- | --- | --- | --- | --- |
| `id` | `varchar(64)` | NO | PRI |  |  |
| `alert_id` | `varchar(64)` | NO | MUL |  |  |
| `channel` | `varchar(255)` | NO |  |  |  |
| `status` | `varchar(96)` | NO | MUL |  |  |
| `attempt_count` | `int` | NO |  | 0 |  |
| `last_attempt_at` | `varchar(32)` | YES |  |  |  |
| `last_success_at` | `varchar(32)` | YES |  |  |  |
| `next_retry_at` | `varchar(32)` | YES |  |  |  |
| `last_error` | `varchar(255)` | YES |  |  |  |
| `response_code` | `int` | YES |  |  |  |
| `metadata_json` | `longtext` | NO |  |  |  |
| `created_at` | `varchar(32)` | NO |  |  |  |
| `updated_at` | `varchar(32)` | NO |  |  |  |
| `terminal_at` | `varchar(64)` | YES |  |  |  |

Indexes:
- `alert_id` (unique): `alert_id`, `channel`
- `idx_alert_deliveries_alert` (non-unique): `alert_id`, `channel`
- `idx_alert_deliveries_retry` (non-unique): `status`, `next_retry_at`, `attempt_count`
- `idx_alert_deliveries_status` (non-unique): `status`, `updated_at`
- `PRIMARY` (unique): `id`

## `alert_events`

| Column | Type | Null | Key | Default | Extra |
| --- | --- | --- | --- | --- | --- |
| `id` | `varchar(64)` | NO | PRI |  |  |
| `event_type` | `varchar(255)` | NO |  |  |  |
| `severity` | `varchar(96)` | NO |  |  |  |
| `status` | `varchar(96)` | NO | MUL | open |  |
| `dedupe_key` | `varchar(255)` | NO | MUL |  |  |
| `title` | `varchar(255)` | NO |  |  |  |
| `message` | `varchar(255)` | NO |  |  |  |
| `source` | `varchar(96)` | YES |  |  |  |
| `related_id` | `varchar(64)` | YES |  |  |  |
| `details_json` | `longtext` | NO |  |  |  |
| `first_seen_at` | `varchar(32)` | NO |  |  |  |
| `last_seen_at` | `varchar(32)` | NO |  |  |  |
| `count` | `int` | NO |  | 1 |  |
| `cooldown_until` | `varchar(255)` | YES |  |  |  |
| `acknowledged_at` | `varchar(32)` | YES |  |  |  |
| `acknowledged_by` | `varchar(255)` | YES |  |  |  |
| `resolved_at` | `varchar(32)` | YES |  |  |  |
| `resolved_by` | `varchar(255)` | YES |  |  |  |

Indexes:
- `dedupe_key` (unique): `dedupe_key`, `status`
- `idx_alert_events_status` (non-unique): `status`, `event_type`, `last_seen_at`
- `PRIMARY` (unique): `id`

## `all_factor_values`

| Column | Type | Null | Key | Default | Extra |
| --- | --- | --- | --- | --- | --- |
| `symbol` | `varchar(96)` | NO |  |  |  |
| `trade_date` | `varchar(32)` | NO |  |  |  |
| `factor_name` | `varchar(96)` | NO |  |  |  |
| `value` | `double` | YES |  |  |  |
| `source` | `varchar(96)` | NO |  |  |  |
| `batch_id` | `varchar(64)` | YES |  |  |  |
| `created_at` | `varchar(32)` | NO |  |  |  |

## `api_idempotency_keys`

| Column | Type | Null | Key | Default | Extra |
| --- | --- | --- | --- | --- | --- |
| `id` | `varchar(64)` | NO | PRI |  |  |
| `idempotency_key` | `varchar(255)` | NO | MUL |  |  |
| `method` | `varchar(16)` | NO |  |  |  |
| `request_path` | `varchar(1024)` | NO |  |  |  |
| `request_path_sha256` | `varchar(64)` | NO |  |  |  |
| `request_sha256` | `varchar(64)` | NO |  |  |  |
| `status` | `varchar(32)` | NO | MUL |  |  |
| `response_status` | `int` | YES |  |  |  |
| `response_body` | `longtext` | YES |  |  |  |
| `response_content_type` | `varchar(255)` | YES |  |  |  |
| `trace_id` | `varchar(128)` | YES |  |  |  |
| `created_at` | `varchar(32)` | NO |  |  |  |
| `updated_at` | `varchar(32)` | NO |  |  |  |

Indexes:
- `idempotency_key` (unique): `idempotency_key`, `method`, `request_path_sha256`
- `idx_api_idempotency_status_updated` (non-unique): `status`, `updated_at`
- `PRIMARY` (unique): `id`

## `ashare_daily_bars`

| Column | Type | Null | Key | Default | Extra |
| --- | --- | --- | --- | --- | --- |
| `symbol` | `varchar(96)` | NO |  |  |  |
| `trade_date` | `varchar(32)` | NO |  |  |  |
| `open` | `double` | YES |  |  |  |
| `high` | `double` | YES |  |  |  |
| `low` | `double` | YES |  |  |  |
| `close` | `double` | YES |  |  |  |
| `volume` | `double` | YES |  |  |  |
| `amount` | `double` | YES |  |  |  |
| `turnover_rate` | `double` | YES |  |  |  |
| `prev_close` | `double` | YES |  |  |  |
| `pct_change` | `double` | YES |  |  |  |
| `adj_factor` | `double` | YES |  |  |  |
| `adjust` | `varchar(96)` | NO |  | raw |  |
| `source` | `varchar(96)` | NO |  |  |  |
| `batch_id` | `varchar(64)` | YES |  |  |  |
| `created_at` | `varchar(32)` | NO |  |  |  |

## `ashare_tech_agent_profiles`

| Column | Type | Null | Key | Default | Extra |
| --- | --- | --- | --- | --- | --- |
| `profile_key` | `varchar(255)` | NO | PRI |  |  |
| `provider` | `varchar(96)` | NO |  |  |  |
| `model` | `varchar(255)` | NO |  |  |  |
| `prompt_version_id` | `varchar(64)` | NO |  |  |  |
| `updated_at` | `varchar(32)` | NO |  |  |  |

Indexes:
- `PRIMARY` (unique): `profile_key`

## `ashare_tech_agent_runs`

| Column | Type | Null | Key | Default | Extra |
| --- | --- | --- | --- | --- | --- |
| `id` | `varchar(64)` | NO | PRI |  |  |
| `report_id` | `varchar(64)` | NO | MUL |  |  |
| `task_id` | `varchar(64)` | YES |  |  |  |
| `requested_date` | `varchar(32)` | NO |  |  |  |
| `analysis_date` | `varchar(32)` | NO |  |  |  |
| `analysis_mode` | `varchar(255)` | NO |  |  |  |
| `status` | `varchar(96)` | NO | MUL |  |  |
| `provider` | `varchar(96)` | YES |  |  |  |
| `requested_model` | `varchar(255)` | YES |  |  |  |
| `prompt_version` | `varchar(255)` | NO |  |  |  |
| `input_fingerprint` | `varchar(255)` | NO |  |  |  |
| `stage_summary_json` | `longtext` | NO |  |  |  |
| `usage_json` | `longtext` | NO |  |  |  |
| `fallback_reason` | `varchar(255)` | YES |  |  |  |
| `created_at` | `varchar(32)` | NO |  |  |  |
| `started_at` | `varchar(32)` | YES |  |  |  |
| `finished_at` | `varchar(32)` | YES |  |  |  |
| `updated_at` | `varchar(32)` | NO |  |  |  |
| `prompt_version_id` | `varchar(64)` | YES |  |  |  |
| `prompt_snapshot_json` | `longtext` | YES |  |  |  |
| `prompt_fingerprint` | `varchar(255)` | YES |  |  |  |

Indexes:
- `idx_ashare_tech_agent_runs_report` (non-unique): `report_id`, `created_at`
- `idx_ashare_tech_agent_runs_status` (non-unique): `status`, `updated_at`
- `PRIMARY` (unique): `id`

## `ashare_tech_agent_stages`

| Column | Type | Null | Key | Default | Extra |
| --- | --- | --- | --- | --- | --- |
| `id` | `varchar(64)` | NO | PRI |  |  |
| `run_id` | `varchar(64)` | NO | MUL |  |  |
| `stage_key` | `varchar(255)` | NO |  |  |  |
| `sequence_no` | `int` | NO |  |  |  |
| `status` | `varchar(96)` | NO |  |  |  |
| `provider` | `varchar(96)` | YES |  |  |  |
| `model` | `varchar(255)` | YES |  |  |  |
| `prompt_version` | `varchar(255)` | NO |  |  |  |
| `input_fingerprint` | `varchar(255)` | NO |  |  |  |
| `input_fact_ids_json` | `longtext` | NO |  |  |  |
| `output_json` | `longtext` | YES |  |  |  |
| `usage_json` | `longtext` | NO |  |  |  |
| `latency_ms` | `int` | YES |  |  |  |
| `attempt_count` | `int` | NO |  | 0 |  |
| `error_category` | `varchar(255)` | YES |  |  |  |
| `error` | `longtext` | YES |  |  |  |
| `started_at` | `varchar(32)` | YES |  |  |  |
| `finished_at` | `varchar(32)` | YES |  |  |  |
| `updated_at` | `varchar(32)` | NO |  |  |  |
| `prompt_version_id` | `varchar(64)` | YES |  |  |  |
| `system_prompt` | `varchar(255)` | YES |  |  |  |

Indexes:
- `idx_ashare_tech_agent_stages_run` (non-unique): `run_id`, `sequence_no`
- `PRIMARY` (unique): `id`
- `run_id` (unique): `run_id`, `stage_key`

## `ashare_tech_candidate_signals`

| Column | Type | Null | Key | Default | Extra |
| --- | --- | --- | --- | --- | --- |
| `id` | `varchar(64)` | NO | PRI |  |  |
| `run_id` | `varchar(64)` | NO | MUL |  |  |
| `report_id` | `varchar(64)` | NO | MUL |  |  |
| `symbol` | `varchar(96)` | NO |  |  |  |
| `provider` | `varchar(96)` | YES |  |  |  |
| `model` | `varchar(255)` | YES |  |  |  |
| `prompt_version` | `varchar(255)` | NO |  |  |  |
| `source_type` | `varchar(255)` | NO |  |  |  |
| `raw_signal_json` | `longtext` | NO |  |  |  |
| `final_signal_json` | `longtext` | NO |  |  |  |
| `guardrail_json` | `longtext` | NO |  |  |  |
| `status` | `varchar(96)` | NO |  |  |  |
| `created_at` | `varchar(32)` | NO |  |  |  |

Indexes:
- `idx_ashare_tech_candidate_signals_report` (non-unique): `report_id`, `symbol`
- `PRIMARY` (unique): `id`
- `run_id` (unique): `run_id`, `symbol`

## `ashare_tech_prediction_evaluations`

| Column | Type | Null | Key | Default | Extra |
| --- | --- | --- | --- | --- | --- |
| `id` | `varchar(64)` | NO | PRI |  |  |
| `prediction_id` | `varchar(64)` | NO | UNI |  |  |
| `run_id` | `varchar(64)` | NO |  |  |  |
| `report_id` | `varchar(64)` | NO |  |  |  |
| `symbol` | `varchar(96)` | NO |  |  |  |
| `horizon_days` | `int` | NO |  |  |  |
| `status` | `varchar(96)` | NO | MUL |  |  |
| `evaluated_date` | `varchar(32)` | YES |  |  |  |
| `entry_close` | `double` | NO |  |  |  |
| `exit_close` | `double` | YES |  |  |  |
| `benchmark_code` | `varchar(255)` | NO |  |  |  |
| `benchmark_entry_close` | `double` | YES |  |  |  |
| `benchmark_exit_close` | `double` | YES |  |  |  |
| `return_pct` | `double` | YES |  |  |  |
| `benchmark_return_pct` | `double` | YES |  |  |  |
| `excess_return_pct` | `double` | YES |  |  |  |
| `realized_direction` | `varchar(255)` | YES |  |  |  |
| `direction_hit` | `int` | YES |  |  |  |
| `brier_score` | `double` | YES |  |  |  |
| `source_manifest_json` | `longtext` | NO |  |  |  |
| `missing_reason` | `varchar(255)` | YES |  |  |  |
| `created_at` | `varchar(32)` | NO |  |  |  |
| `updated_at` | `varchar(32)` | NO |  |  |  |

Indexes:
- `idx_ashare_tech_prediction_eval_summary` (non-unique): `status`, `horizon_days`, `evaluated_date`
- `prediction_id` (unique): `prediction_id`
- `PRIMARY` (unique): `id`

## `ashare_tech_predictions`

| Column | Type | Null | Key | Default | Extra |
| --- | --- | --- | --- | --- | --- |
| `id` | `varchar(64)` | NO | PRI |  |  |
| `run_id` | `varchar(64)` | NO | MUL |  |  |
| `report_id` | `varchar(64)` | NO | MUL |  |  |
| `symbol` | `varchar(96)` | NO |  |  |  |
| `horizon_days` | `int` | NO |  |  |  |
| `predicted_direction` | `varchar(255)` | NO |  |  |  |
| `probabilities_json` | `longtext` | NO |  |  |  |
| `confidence` | `double` | NO |  |  |  |
| `trend_score` | `double` | NO |  |  |  |
| `rule_conclusion` | `varchar(255)` | YES |  |  |  |
| `selection_rank` | `int` | YES |  |  |  |
| `selection_tier` | `varchar(255)` | NO |  |  |  |
| `rationale` | `varchar(255)` | NO |  |  |  |
| `evidence_ids_json` | `longtext` | NO |  |  |  |
| `neutral_band_pct` | `double` | NO |  |  |  |
| `entry_date` | `varchar(32)` | NO |  |  |  |
| `entry_close` | `double` | NO |  |  |  |
| `target_date` | `varchar(32)` | YES | MUL |  |  |
| `benchmark_code` | `varchar(255)` | NO |  |  |  |
| `model` | `varchar(255)` | NO |  |  |  |
| `prompt_version` | `varchar(255)` | NO |  |  |  |
| `created_at` | `varchar(32)` | NO |  |  |  |
| `provider` | `varchar(96)` | YES |  |  |  |

Indexes:
- `idx_ashare_tech_predictions_pending` (non-unique): `target_date`, `horizon_days`
- `idx_ashare_tech_predictions_report` (non-unique): `report_id`, `symbol`
- `PRIMARY` (unique): `id`
- `run_id` (unique): `run_id`, `symbol`, `horizon_days`

## `ashare_tech_prompt_templates`

| Column | Type | Null | Key | Default | Extra |
| --- | --- | --- | --- | --- | --- |
| `id` | `varchar(64)` | NO | PRI |  |  |
| `template_key` | `varchar(255)` | NO | MUL |  |  |
| `name` | `varchar(255)` | NO |  |  |  |
| `description` | `varchar(255)` | YES |  |  |  |
| `version_no` | `int` | NO |  |  |  |
| `stage_prompts_json` | `longtext` | NO |  |  |  |
| `prompt_fingerprint` | `varchar(255)` | NO |  |  |  |
| `created_at` | `varchar(32)` | NO |  |  |  |

Indexes:
- `idx_ashare_tech_prompt_templates_key` (non-unique): `template_key`, `version_no`
- `PRIMARY` (unique): `id`
- `template_key` (unique): `template_key`, `version_no`

## `ashare_tech_reports`

| Column | Type | Null | Key | Default | Extra |
| --- | --- | --- | --- | --- | --- |
| `id` | `varchar(64)` | NO | PRI |  |  |
| `task_id` | `varchar(64)` | YES |  |  |  |
| `requested_date` | `varchar(32)` | NO | UNI |  |  |
| `analysis_date` | `varchar(32)` | YES | MUL |  |  |
| `market_status` | `varchar(255)` | NO |  |  |  |
| `status` | `varchar(96)` | NO | MUL |  |  |
| `attempt_count` | `int` | NO |  | 0 |  |
| `data_cutoff_at` | `varchar(32)` | YES |  |  |  |
| `primary_source` | `varchar(255)` | NO |  | tushare |  |
| `sector_source` | `varchar(255)` | YES |  |  |  |
| `data_completeness_json` | `longtext` | NO |  |  |  |
| `source_conflicts_json` | `longtext` | NO |  |  |  |
| `source_manifest_json` | `longtext` | NO |  |  |  |
| `context_json` | `longtext` | YES |  |  |  |
| `raw_response_json` | `longtext` | YES |  |  |  |
| `report_json` | `longtext` | YES |  |  |  |
| `model` | `varchar(255)` | YES |  |  |  |
| `prompt_version` | `varchar(255)` | NO |  |  |  |
| `previous_report_id` | `varchar(64)` | YES |  |  |  |
| `input_fingerprint` | `varchar(255)` | YES |  |  |  |
| `error` | `longtext` | YES |  |  |  |
| `created_at` | `varchar(32)` | NO | MUL |  |  |
| `started_at` | `varchar(32)` | YES |  |  |  |
| `finished_at` | `varchar(32)` | YES |  |  |  |
| `updated_at` | `varchar(32)` | NO |  |  |  |
| `pool_snapshot_json` | `text` | YES |  |  |  |
| `pool_fingerprint` | `text` | YES |  |  |  |
| `active_agent_run_id` | `varchar(64)` | YES |  |  |  |
| `analysis_mode` | `varchar(255)` | YES |  |  |  |
| `llm_status` | `varchar(255)` | YES |  |  |  |
| `agent_summary_json` | `longtext` | YES |  |  |  |
| `requested_provider` | `varchar(255)` | YES |  |  |  |
| `requested_model` | `varchar(255)` | YES |  |  |  |
| `prompt_version_id` | `varchar(64)` | YES |  |  |  |

Indexes:
- `idx_ashare_tech_reports_analysis_date` (non-unique): `analysis_date`
- `idx_ashare_tech_reports_created` (non-unique): `created_at`
- `idx_ashare_tech_reports_status` (non-unique): `status`, `updated_at`
- `PRIMARY` (unique): `id`
- `requested_date` (unique): `requested_date`

## `ashare_tech_watchlist_items`

| Column | Type | Null | Key | Default | Extra |
| --- | --- | --- | --- | --- | --- |
| `code` | `varchar(255)` | NO | PRI |  |  |
| `name` | `varchar(255)` | NO |  |  |  |
| `group_key` | `varchar(255)` | NO | MUL |  |  |
| `enabled` | `int` | NO |  | 1 |  |
| `rule_tags_json` | `longtext` | NO |  |  |  |
| `source` | `varchar(96)` | NO |  | tushare:stock_basic |  |
| `created_at` | `varchar(32)` | NO |  |  |  |
| `updated_at` | `varchar(32)` | NO |  |  |  |

Indexes:
- `idx_ashare_tech_watchlist_group` (non-unique): `group_key`, `enabled`, `code`
- `PRIMARY` (unique): `code`

## `ashare_trade_status`

| Column | Type | Null | Key | Default | Extra |
| --- | --- | --- | --- | --- | --- |
| `symbol` | `varchar(96)` | NO |  |  |  |
| `trade_date` | `varchar(32)` | NO |  |  |  |
| `is_suspended` | `int` | NO |  | 0 |  |
| `limit_up` | `double` | YES |  |  |  |
| `limit_down` | `double` | YES |  |  |  |
| `is_limit_up` | `int` | NO |  | 0 |  |
| `is_limit_down` | `int` | NO |  | 0 |  |
| `is_one_word_limit_up` | `int` | NO |  | 0 |  |
| `is_one_word_limit_down` | `int` | NO |  | 0 |  |
| `can_buy` | `int` | NO |  | 1 |  |
| `can_sell` | `int` | NO |  | 1 |  |
| `is_st` | `int` | NO |  | 0 |  |
| `source` | `varchar(96)` | NO |  |  |  |
| `batch_id` | `varchar(64)` | YES |  |  |  |

## `asset_capabilities`

| Column | Type | Null | Key | Default | Extra |
| --- | --- | --- | --- | --- | --- |
| `id` | `varchar(96)` | NO | PRI |  |  |
| `asset_class` | `varchar(64)` | NO | MUL |  |  |
| `market` | `varchar(64)` | NO |  |  |  |
| `venue` | `varchar(64)` | NO |  |  |  |
| `resolution` | `varchar(32)` | NO |  |  |  |
| `data_type` | `varchar(32)` | NO |  |  |  |
| `state` | `varchar(32)` | NO | MUL |  |  |
| `metadata_count` | `bigint` | NO |  | 0 |  |
| `canonical_row_count` | `bigint` | NO |  | 0 |  |
| `executable_reason` | `varchar(255)` | YES |  |  |  |
| `evidence_json` | `longtext` | NO |  |  |  |
| `refreshed_at` | `varchar(64)` | NO |  |  |  |

Indexes:
- `asset_class` (unique): `asset_class`, `market`, `venue`, `resolution`, `data_type`
- `idx_asset_capabilities_state` (non-unique): `state`, `asset_class`, `market`, `venue`, `resolution`
- `PRIMARY` (unique): `id`

## `backtest_results`

| Column | Type | Null | Key | Default | Extra |
| --- | --- | --- | --- | --- | --- |
| `id` | `varchar(64)` | NO | PRI |  |  |
| `job_id` | `varchar(64)` | NO | UNI |  |  |
| `summary_metrics_json` | `longtext` | NO |  |  |  |
| `equity_curve_json` | `longtext` | NO |  |  |  |
| `drawdown_curve_json` | `longtext` | NO |  |  |  |
| `orders_json` | `longtext` | NO |  |  |  |
| `trades_json` | `longtext` | NO |  |  |  |
| `holdings_json` | `longtext` | NO |  |  |  |
| `statistics_json` | `longtext` | NO |  |  |  |
| `performance_json` | `longtext` | YES |  |  |  |
| `raw_result_path` | `varchar(1024)` | YES |  |  |  |
| `raw_result_object_id` | `varchar(64)` | YES |  |  |  |
| `summary_object_id` | `varchar(64)` | YES |  |  |  |
| `created_at` | `varchar(32)` | NO |  |  |  |

Indexes:
- `idx_backtest_results_job` (non-unique): `job_id`
- `job_id` (unique): `job_id`
- `PRIMARY` (unique): `id`

## `backtest_runs`

| Column | Type | Null | Key | Default | Extra |
| --- | --- | --- | --- | --- | --- |
| `id` | `varchar(64)` | NO | PRI |  |  |
| `task_id` | `varchar(64)` | YES | MUL |  |  |
| `project_id` | `varchar(64)` | YES | MUL |  |  |
| `symbol` | `varchar(96)` | NO | MUL |  |  |
| `asset_class` | `varchar(96)` | NO | MUL | equity |  |
| `venue` | `varchar(96)` | YES |  |  |  |
| `resolution` | `varchar(96)` | NO |  | daily |  |
| `data_type` | `varchar(96)` | NO |  | trade |  |
| `parameters_json` | `longtext` | NO |  |  |  |
| `status` | `varchar(96)` | NO | MUL |  |  |
| `docker_image` | `varchar(255)` | NO |  |  |  |
| `name` | `varchar(255)` | YES |  |  |  |
| `container_name` | `varchar(255)` | YES |  |  |  |
| `work_dir` | `varchar(1024)` | YES |  |  |  |
| `results_dir` | `varchar(1024)` | NO |  |  |  |
| `result_json_path` | `varchar(1024)` | YES |  |  |  |
| `summary_json_path` | `varchar(1024)` | YES |  |  |  |
| `report_html_path` | `varchar(1024)` | YES |  |  |  |
| `log_path` | `varchar(1024)` | YES |  |  |  |
| `statistics_json` | `longtext` | YES |  |  |  |
| `exit_code` | `int` | YES |  |  |  |
| `error` | `longtext` | YES |  |  |  |
| `error_message` | `longtext` | YES |  |  |  |
| `created_at` | `varchar(32)` | NO | MUL |  |  |
| `queued_at` | `varchar(32)` | YES |  |  |  |
| `started_at` | `varchar(32)` | YES |  |  |  |
| `finished_at` | `varchar(32)` | YES |  |  |  |
| `duration_seconds` | `double` | YES |  |  |  |
| `fingerprint_json` | `longtext` | YES |  |  |  |
| `validation_json` | `longtext` | YES |  |  |  |
| `experiment_json` | `longtext` | YES |  |  |  |
| `failure_json` | `text` | YES |  |  |  |
| `batch_item_id` | `varchar(64)` | YES |  |  |  |
| `dataset_release_id` | `varchar(96)` | YES | MUL |  |  |
| `reproducibility_certificate_id` | `varchar(96)` | YES |  |  |  |
| `trust_status` | `varchar(32)` | NO |  | unverified |  |
| `trust_reason` | `varchar(255)` | YES |  |  |  |
| `trust_evaluated_at` | `varchar(64)` | YES |  |  |  |

Indexes:
- `idx_backtest_runs_asset` (non-unique): `asset_class`, `venue`, `symbol`
- `idx_backtest_runs_created_at` (non-unique): `created_at`
- `idx_backtest_runs_project_status_created` (non-unique): `project_id`, `status`, `created_at`
- `idx_backtest_runs_release` (non-unique): `dataset_release_id`
- `idx_backtest_runs_status` (non-unique): `status`
- `idx_backtest_runs_symbol` (non-unique): `symbol`
- `idx_backtest_runs_task_created` (non-unique): `task_id`, `created_at`
- `idx_backtest_runs_terminal_trust` (non-unique): `status`, `trust_status`, `finished_at`
- `PRIMARY` (unique): `id`

## `cbond_call_events`

| Column | Type | Null | Key | Default | Extra |
| --- | --- | --- | --- | --- | --- |
| `id` | `varchar(64)` | NO | PRI |  |  |
| `bond_code` | `varchar(96)` | NO |  |  |  |
| `announce_date` | `varchar(32)` | NO | MUL |  |  |
| `trigger_date` | `varchar(32)` | YES |  |  |  |
| `status` | `varchar(96)` | NO |  |  |  |
| `call_price` | `double` | YES |  |  |  |
| `last_trade_date` | `varchar(32)` | YES |  |  |  |
| `source` | `varchar(96)` | NO |  |  |  |
| `created_at` | `varchar(32)` | NO |  |  |  |

Indexes:
- `idx_cbond_call_events_date` (non-unique): `announce_date`, `last_trade_date`, `status`
- `PRIMARY` (unique): `id`

## `cbond_daily_bars`

| Column | Type | Null | Key | Default | Extra |
| --- | --- | --- | --- | --- | --- |
| `bond_code` | `varchar(96)` | NO | PRI |  |  |
| `trade_date` | `varchar(32)` | NO | PRI |  |  |
| `close` | `double` | NO |  |  |  |
| `stock_close` | `double` | YES |  |  |  |
| `conversion_price` | `double` | YES |  |  |  |
| `conversion_value` | `double` | YES |  |  |  |
| `premium_rate` | `double` | YES |  |  |  |
| `remaining_size` | `double` | YES |  |  |  |
| `double_low` | `double` | YES |  |  |  |
| `source` | `varchar(96)` | NO | PRI |  |  |
| `batch_id` | `varchar(64)` | YES |  |  |  |
| `created_at` | `varchar(32)` | NO |  |  |  |

Indexes:
- `idx_cbond_daily_date` (non-unique): `trade_date`, `bond_code`
- `PRIMARY` (unique): `bond_code`, `trade_date`, `source`

## `cbond_securities`

| Column | Type | Null | Key | Default | Extra |
| --- | --- | --- | --- | --- | --- |
| `bond_code` | `varchar(96)` | NO | PRI |  |  |
| `bond_name` | `varchar(255)` | NO |  |  |  |
| `stock_symbol` | `varchar(96)` | NO | MUL |  |  |
| `listed_date` | `varchar(32)` | YES |  |  |  |
| `delisted_date` | `varchar(32)` | YES |  |  |  |
| `maturity_date` | `varchar(32)` | YES |  |  |  |
| `rating` | `varchar(255)` | YES |  |  |  |
| `conversion_price` | `double` | YES |  |  |  |
| `issue_size` | `double` | YES |  |  |  |
| `remaining_size` | `double` | YES |  |  |  |
| `terms_json` | `longtext` | YES |  |  |  |
| `source` | `varchar(96)` | NO |  |  |  |
| `updated_at` | `varchar(32)` | NO |  |  |  |

Indexes:
- `idx_cbond_stock_symbol` (non-unique): `stock_symbol`
- `PRIMARY` (unique): `bond_code`

## `corporate_actions`

| Column | Type | Null | Key | Default | Extra |
| --- | --- | --- | --- | --- | --- |
| `symbol` | `varchar(96)` | NO | PRI |  |  |
| `ex_date` | `varchar(32)` | NO | PRI |  |  |
| `action_type` | `varchar(96)` | NO | PRI |  |  |
| `cash_dividend` | `double` | YES |  |  |  |
| `stock_dividend` | `double` | YES |  |  |  |
| `split_ratio` | `double` | YES |  |  |  |
| `allotment_ratio` | `double` | YES |  |  |  |
| `allotment_price` | `double` | YES |  |  |  |
| `source` | `varchar(96)` | NO | PRI |  |  |
| `batch_id` | `varchar(64)` | YES |  |  |  |
| `created_at` | `varchar(32)` | NO |  |  |  |

Indexes:
- `idx_corporate_actions_symbol_date` (non-unique): `symbol`, `ex_date`
- `PRIMARY` (unique): `symbol`, `ex_date`, `action_type`, `source`

## `daily_basic_factor_values`

| Column | Type | Null | Key | Default | Extra |
| --- | --- | --- | --- | --- | --- |
| `symbol` | `varchar(96)` | NO |  |  |  |
| `trade_date` | `varchar(32)` | NO |  |  |  |
| `factor_name` | `varchar(96)` | NO |  |  |  |
| `value` | `double` | YES |  |  |  |
| `source` | `varchar(96)` | NO |  |  |  |
| `batch_id` | `varchar(64)` | YES |  |  |  |
| `created_at` | `varchar(32)` | NO |  |  |  |

## `daily_basic_values`

| Column | Type | Null | Key | Default | Extra |
| --- | --- | --- | --- | --- | --- |
| `symbol` | `varchar(96)` | NO | PRI |  |  |
| `trade_date` | `varchar(32)` | NO | PRI |  |  |
| `turnover_rate` | `double` | YES |  |  |  |
| `turnover_rate_float` | `double` | YES |  |  |  |
| `volume_ratio` | `double` | YES |  |  |  |
| `pe` | `double` | YES |  |  |  |
| `pe_ttm` | `double` | YES |  |  |  |
| `pb` | `double` | YES |  |  |  |
| `ps` | `double` | YES |  |  |  |
| `ps_ttm` | `double` | YES |  |  |  |
| `dividend_yield` | `double` | YES |  |  |  |
| `dividend_yield_ttm` | `double` | YES |  |  |  |
| `total_share_shares` | `double` | YES |  |  |  |
| `float_share_shares` | `double` | YES |  |  |  |
| `free_share_shares` | `double` | YES |  |  |  |
| `total_mv_cny` | `double` | YES |  |  |  |
| `circ_mv_cny` | `double` | YES |  |  |  |
| `source` | `varchar(96)` | NO | PRI |  |  |
| `batch_id` | `varchar(64)` | YES |  |  |  |
| `created_at` | `varchar(32)` | NO |  |  |  |

Indexes:
- `idx_daily_basic_values_date_symbol` (non-unique): `trade_date`, `symbol`
- `PRIMARY` (unique): `symbol`, `trade_date`, `source`

## `data_assets`

| Column | Type | Null | Key | Default | Extra |
| --- | --- | --- | --- | --- | --- |
| `id` | `int` | NO | PRI |  | auto_increment |
| `symbol` | `varchar(96)` | NO | MUL |  |  |
| `asset_class` | `varchar(96)` | NO | MUL | equity |  |
| `venue` | `varchar(96)` | YES |  |  |  |
| `resolution` | `varchar(96)` | NO |  | daily |  |
| `data_type` | `varchar(96)` | NO |  | trade |  |
| `source` | `varchar(96)` | NO |  |  |  |
| `rows` | `int` | NO |  |  |  |
| `first_date` | `varchar(32)` | NO |  |  |  |
| `last_date` | `varchar(32)` | NO |  |  |  |
| `lean_file` | `varchar(1024)` | NO |  |  |  |
| `lean_object_id` | `varchar(64)` | YES |  |  |  |
| `factor_object_id` | `varchar(64)` | YES |  |  |  |
| `metadata_json` | `longtext` | NO |  |  |  |
| `created_at` | `varchar(32)` | NO |  |  |  |
| `status` | `varchar(96)` | NO | MUL | active |  |
| `superseded_by` | `int` | YES |  |  |  |
| `superseded_at` | `varchar(32)` | YES |  |  |  |
| `superseded_reason` | `varchar(255)` | YES |  |  |  |

Indexes:
- `idx_data_assets_asset` (non-unique): `asset_class`, `venue`, `symbol`
- `idx_data_assets_status_created` (non-unique): `status`, `created_at`
- `idx_data_assets_symbol` (non-unique): `symbol`
- `PRIMARY` (unique): `id`

## `data_gap_resolutions`

| Column | Type | Null | Key | Default | Extra |
| --- | --- | --- | --- | --- | --- |
| `id` | `varchar(64)` | NO | PRI |  |  |
| `market` | `varchar(96)` | NO | MUL |  |  |
| `symbol` | `varchar(96)` | NO |  |  |  |
| `trade_date` | `varchar(32)` | NO |  |  |  |
| `classification` | `varchar(255)` | NO |  |  |  |
| `status` | `varchar(96)` | NO |  |  |  |
| `evidence_source` | `varchar(255)` | YES |  |  |  |
| `evidence_json` | `longtext` | YES |  |  |  |
| `batch_id` | `varchar(64)` | YES |  |  |  |
| `created_at` | `varchar(32)` | NO |  |  |  |
| `updated_at` | `varchar(32)` | NO |  |  |  |

Indexes:
- `idx_data_gap_resolution_lookup` (non-unique): `market`, `symbol`, `status`, `trade_date`
- `market` (unique): `market`, `symbol`, `trade_date`
- `PRIMARY` (unique): `id`

## `data_gaps`

| Column | Type | Null | Key | Default | Extra |
| --- | --- | --- | --- | --- | --- |
| `id` | `varchar(64)` | NO | PRI |  |  |
| `dataset` | `varchar(255)` | NO | MUL |  |  |
| `asset_class` | `varchar(96)` | NO |  |  |  |
| `market` | `varchar(96)` | NO |  |  |  |
| `symbol` | `varchar(96)` | YES |  |  |  |
| `start_time` | `varchar(32)` | NO |  |  |  |
| `end_time` | `varchar(32)` | NO |  |  |  |
| `severity` | `varchar(255)` | NO |  |  |  |
| `source` | `varchar(96)` | NO |  |  |  |
| `details_json` | `longtext` | NO |  |  |  |
| `created_at` | `varchar(32)` | NO |  |  |  |

Indexes:
- `idx_data_gaps_lookup` (non-unique): `dataset`, `asset_class`, `market`, `symbol`
- `PRIMARY` (unique): `id`

## `data_import_batches`

| Column | Type | Null | Key | Default | Extra |
| --- | --- | --- | --- | --- | --- |
| `id` | `varchar(64)` | NO | PRI |  |  |
| `provider` | `varchar(96)` | NO |  |  |  |
| `market` | `varchar(96)` | NO |  |  |  |
| `asset_class` | `varchar(96)` | NO |  |  |  |
| `status` | `varchar(96)` | NO |  |  |  |
| `config_json` | `longtext` | NO |  |  |  |
| `qa_report_json` | `longtext` | YES |  |  |  |
| `error` | `longtext` | YES |  |  |  |
| `started_at` | `varchar(32)` | NO | MUL |  |  |
| `finished_at` | `varchar(32)` | YES |  |  |  |

Indexes:
- `idx_import_batches_started_at` (non-unique): `started_at`
- `PRIMARY` (unique): `id`

## `data_quality_reports`

| Column | Type | Null | Key | Default | Extra |
| --- | --- | --- | --- | --- | --- |
| `id` | `varchar(64)` | NO | PRI |  |  |
| `report_type` | `varchar(255)` | NO | MUL |  |  |
| `asset_class` | `varchar(96)` | NO |  |  |  |
| `market` | `varchar(96)` | NO |  |  |  |
| `symbol` | `varchar(96)` | YES |  |  |  |
| `start_date` | `varchar(32)` | YES |  |  |  |
| `end_date` | `varchar(32)` | YES |  |  |  |
| `sources_json` | `longtext` | NO |  |  |  |
| `severity` | `varchar(255)` | NO |  |  |  |
| `result_json` | `longtext` | NO |  |  |  |
| `created_at` | `varchar(32)` | NO |  |  |  |

Indexes:
- `idx_data_quality_reports_lookup` (non-unique): `report_type`, `asset_class`, `market`, `symbol`, `created_at`
- `PRIMARY` (unique): `id`

## `data_record_issues`

| Column | Type | Null | Key | Default | Extra |
| --- | --- | --- | --- | --- | --- |
| `id` | `varchar(64)` | NO | PRI |  |  |
| `dataset_key` | `varchar(255)` | NO |  |  |  |
| `source` | `varchar(96)` | YES |  |  |  |
| `instrument_code` | `varchar(255)` | YES |  |  |  |
| `start_date` | `varchar(32)` | YES |  |  |  |
| `end_date` | `varchar(32)` | YES |  |  |  |
| `issue_code` | `varchar(255)` | NO |  |  |  |
| `severity` | `varchar(96)` | NO |  |  |  |
| `status` | `varchar(96)` | NO | MUL |  |  |
| `details_json` | `longtext` | YES |  |  |  |
| `detected_at` | `varchar(32)` | NO |  |  |  |
| `resolved_at` | `varchar(32)` | YES |  |  |  |
| `resolution_batch_id` | `varchar(64)` | YES |  |  |  |

Indexes:
- `idx_data_record_issues_status` (non-unique): `status`, `dataset_key`
- `PRIMARY` (unique): `id`

## `data_sync_items`

| Column | Type | Null | Key | Default | Extra |
| --- | --- | --- | --- | --- | --- |
| `id` | `varchar(64)` | NO | PRI |  |  |
| `run_id` | `varchar(64)` | NO | MUL |  |  |
| `dataset_key` | `varchar(255)` | NO |  |  |  |
| `status` | `varchar(96)` | NO |  |  |  |
| `processed` | `int` | NO |  | 0 |  |
| `inserted` | `int` | NO |  | 0 |  |
| `updated` | `int` | NO |  | 0 |  |
| `failed` | `int` | NO |  | 0 |  |
| `checkpoint_json` | `longtext` | YES |  |  |  |
| `error` | `longtext` | YES |  |  |  |
| `started_at` | `varchar(32)` | YES |  |  |  |
| `finished_at` | `varchar(32)` | YES |  |  |  |
| `metrics_json` | `longtext` | YES |  |  |  |
| `canonical_status` | `varchar(255)` | YES |  |  |  |
| `derived_status_json` | `longtext` | YES |  |  |  |

Indexes:
- `idx_data_sync_items_run` (non-unique): `run_id`, `status`
- `PRIMARY` (unique): `id`
- `run_id` (unique): `run_id`, `dataset_key`

## `data_sync_runs`

| Column | Type | Null | Key | Default | Extra |
| --- | --- | --- | --- | --- | --- |
| `id` | `varchar(64)` | NO | PRI |  |  |
| `task_id` | `varchar(64)` | YES |  |  |  |
| `provider` | `varchar(96)` | NO |  |  |  |
| `mode` | `varchar(255)` | NO |  |  |  |
| `scope` | `varchar(255)` | NO |  |  |  |
| `status` | `varchar(96)` | NO | MUL |  |  |
| `requested_datasets_json` | `longtext` | YES |  |  |  |
| `summary_json` | `longtext` | YES |  |  |  |
| `error` | `longtext` | YES |  |  |  |
| `created_at` | `varchar(32)` | NO |  |  |  |
| `started_at` | `varchar(32)` | YES |  |  |  |
| `finished_at` | `varchar(32)` | YES |  |  |  |
| `cancel_requested` | `int` | NO |  | 0 |  |
| `canonical_status` | `varchar(255)` | YES |  |  |  |
| `canonical_ready_at` | `varchar(32)` | YES |  |  |  |
| `derived_status_json` | `longtext` | YES |  |  |  |
| `heartbeat_at` | `varchar(32)` | YES |  |  |  |
| `request_scope_json` | `longtext` | YES |  |  |  |

Indexes:
- `idx_data_sync_runs_heartbeat` (non-unique): `status`, `heartbeat_at`
- `idx_data_sync_runs_status` (non-unique): `status`, `created_at`
- `PRIMARY` (unique): `id`

## `data_sync_work_items`

| Column | Type | Null | Key | Default | Extra |
| --- | --- | --- | --- | --- | --- |
| `run_id` | `varchar(64)` | NO | PRI |  |  |
| `dataset_key` | `varchar(255)` | NO | PRI |  |  |
| `work_key` | `varchar(255)` | NO | PRI |  |  |
| `sequence_no` | `int` | NO |  |  |  |
| `status` | `varchar(96)` | NO |  | pending |  |
| `attempts` | `int` | NO |  | 0 |  |
| `row_count` | `int` | NO |  | 0 |  |
| `content_sha256` | `varchar(64)` | YES |  |  |  |
| `error` | `longtext` | YES |  |  |  |
| `started_at` | `varchar(32)` | YES |  |  |  |
| `fetched_at` | `varchar(32)` | YES |  |  |  |
| `committed_at` | `varchar(32)` | YES |  |  |  |

Indexes:
- `idx_data_sync_work_pending` (non-unique): `run_id`, `dataset_key`, `status`, `sequence_no`
- `PRIMARY` (unique): `run_id`, `dataset_key`, `work_key`

## `dataset_releases`

| Column | Type | Null | Key | Default | Extra |
| --- | --- | --- | --- | --- | --- |
| `id` | `varchar(96)` | NO | PRI |  |  |
| `dataset_key` | `varchar(191)` | NO | MUL |  |  |
| `dataset_version` | `varchar(191)` | NO |  |  |  |
| `source` | `varchar(64)` | NO |  |  |  |
| `asset_class` | `varchar(64)` | NO |  |  |  |
| `market` | `varchar(64)` | NO |  |  |  |
| `venue` | `varchar(64)` | YES |  |  |  |
| `resolution` | `varchar(32)` | NO |  |  |  |
| `data_type` | `varchar(32)` | NO |  |  |  |
| `adjust_mode` | `varchar(32)` | NO |  |  |  |
| `parquet_dataset_id` | `varchar(64)` | NO | MUL |  |  |
| `file_manifest_sha256` | `varchar(64)` | NO |  |  |  |
| `qa_report_id` | `varchar(64)` | NO |  |  |  |
| `status` | `varchar(32)` | NO | MUL |  |  |
| `is_production` | `int` | NO |  | 1 |  |
| `is_certified` | `int` | NO |  | 1 |  |
| `coverage_start` | `varchar(32)` | YES |  |  |  |
| `coverage_end` | `varchar(32)` | YES |  |  |  |
| `row_count` | `bigint` | NO |  | 0 |  |
| `file_count` | `int` | NO |  | 0 |  |
| `certified_by` | `varchar(96)` | NO |  |  |  |
| `certified_at` | `varchar(64)` | NO |  |  |  |
| `revoked_at` | `varchar(64)` | YES |  |  |  |
| `revoke_reason` | `varchar(255)` | YES |  |  |  |
| `metadata_json` | `longtext` | NO |  |  |  |
| `created_at` | `varchar(64)` | NO |  |  |  |

Indexes:
- `dataset_key` (unique): `dataset_key`, `dataset_version`
- `idx_dataset_releases_active_scope` (non-unique): `status`, `source`, `asset_class`, `market`, `venue`, `resolution`, `data_type`
- `parquet_dataset_id` (unique): `parquet_dataset_id`, `dataset_version`
- `PRIMARY` (unique): `id`

## `dataset_versions`

| Column | Type | Null | Key | Default | Extra |
| --- | --- | --- | --- | --- | --- |
| `id` | `varchar(64)` | NO | PRI |  |  |
| `dataset_key` | `varchar(255)` | NO |  |  |  |
| `asset_class` | `varchar(96)` | YES | MUL |  |  |
| `market` | `varchar(96)` | YES |  |  |  |
| `venue` | `varchar(96)` | YES |  |  |  |
| `resolution` | `varchar(96)` | YES |  |  |  |
| `data_type` | `varchar(96)` | YES |  |  |  |
| `adjust` | `varchar(96)` | YES |  |  |  |
| `symbol` | `varchar(96)` | YES |  |  |  |
| `start_date` | `varchar(32)` | YES |  |  |  |
| `end_date` | `varchar(32)` | YES |  |  |  |
| `row_count` | `int` | NO |  | 0 |  |
| `status_count` | `int` | NO |  | 0 |  |
| `benchmark_symbol` | `varchar(255)` | YES |  |  |  |
| `benchmark_row_count` | `int` | NO |  | 0 |  |
| `data_batch_id` | `varchar(64)` | YES |  |  |  |
| `lean_zip_sha256` | `varchar(255)` | YES |  |  |  |
| `factor_file_sha256` | `varchar(255)` | YES |  |  |  |
| `parquet_dataset_id` | `varchar(64)` | YES |  |  |  |
| `parquet_file_sha256` | `varchar(255)` | YES |  |  |  |
| `metadata_json` | `longtext` | NO |  |  |  |
| `created_at` | `varchar(32)` | NO |  |  |  |
| `dataset_version` | `varchar(96)` | YES |  |  |  |
| `environment` | `varchar(32)` | NO |  | research |  |
| `is_production` | `int` | NO | MUL | 0 |  |
| `is_certified` | `int` | NO |  | 0 |  |
| `certified_at` | `varchar(32)` | YES |  |  |  |
| `certified_by` | `varchar(96)` | YES |  |  |  |
| `coverage_start` | `varchar(32)` | YES |  |  |  |
| `coverage_end` | `varchar(32)` | YES |  |  |  |
| `qa_status` | `varchar(32)` | YES |  |  |  |
| `qa_report_id` | `varchar(64)` | YES |  |  |  |
| `dataset_release_id` | `varchar(96)` | YES | MUL |  |  |

Indexes:
- `idx_dataset_versions_certified_source` (non-unique): `is_production`, `is_certified`, `asset_class`, `market`, `venue`
- `idx_dataset_versions_lookup` (non-unique): `asset_class`, `market`, `symbol`, `start_date`, `end_date`
- `idx_dataset_versions_release` (non-unique): `dataset_release_id`
- `PRIMARY` (unique): `id`

## `derived_layer_watermarks`

| Column | Type | Null | Key | Default | Extra |
| --- | --- | --- | --- | --- | --- |
| `layer_key` | `varchar(255)` | NO | PRI |  |  |
| `scope_key` | `varchar(255)` | NO | PRI |  |  |
| `source` | `varchar(96)` | NO | PRI |  |  |
| `canonical_start` | `varchar(255)` | YES |  |  |  |
| `canonical_end` | `varchar(255)` | YES |  |  |  |
| `materialized_start` | `varchar(255)` | YES |  |  |  |
| `materialized_end` | `varchar(255)` | YES |  |  |  |
| `status` | `varchar(96)` | NO |  |  |  |
| `row_count` | `int` | NO |  | 0 |  |
| `dataset_id` | `varchar(64)` | YES |  |  |  |
| `content_sha256` | `varchar(64)` | YES |  |  |  |
| `last_canonical_run_id` | `varchar(64)` | YES |  |  |  |
| `last_maintenance_run_id` | `varchar(64)` | YES |  |  |  |
| `error` | `longtext` | YES |  |  |  |
| `details_json` | `longtext` | NO |  |  |  |
| `started_at` | `varchar(32)` | YES |  |  |  |
| `completed_at` | `varchar(32)` | YES |  |  |  |
| `updated_at` | `varchar(32)` | NO |  |  |  |

Indexes:
- `idx_derived_layer_watermarks_status` (non-unique): `layer_key`, `status`, `materialized_end`
- `PRIMARY` (unique): `layer_key`, `scope_key`, `source`

## `derived_maintenance_runs`

| Column | Type | Null | Key | Default | Extra |
| --- | --- | --- | --- | --- | --- |
| `id` | `varchar(64)` | NO | PRI |  |  |
| `trigger_type` | `varchar(255)` | NO |  |  |  |
| `status` | `varchar(96)` | NO | MUL |  |  |
| `requested_layers_json` | `longtext` | NO |  |  |  |
| `canonical_watermark` | `varchar(255)` | YES |  |  |  |
| `summary_json` | `longtext` | NO |  |  |  |
| `error` | `longtext` | YES |  |  |  |
| `created_at` | `varchar(32)` | NO |  |  |  |
| `started_at` | `varchar(32)` | YES |  |  |  |
| `finished_at` | `varchar(32)` | YES |  |  |  |
| `attempt_count` | `int` | NO |  | 0 |  |
| `max_attempts` | `int` | NO |  | 5 |  |
| `checkpoint_json` | `longtext` | YES |  |  |  |
| `checkpoint_at` | `varchar(64)` | YES |  |  |  |
| `heartbeat_at` | `varchar(64)` | YES |  |  |  |
| `next_retry_at` | `varchar(64)` | YES |  |  |  |
| `alert_sent_at` | `varchar(64)` | YES |  |  |  |
| `lease_owner` | `varchar(96)` | YES |  |  |  |

Indexes:
- `idx_derived_maintenance_retry` (non-unique): `status`, `next_retry_at`, `attempt_count`
- `idx_derived_maintenance_runs_status` (non-unique): `status`, `created_at`
- `PRIMARY` (unique): `id`

## `experiment_batch_attempts`

| Column | Type | Null | Key | Default | Extra |
| --- | --- | --- | --- | --- | --- |
| `id` | `varchar(64)` | NO | PRI |  |  |
| `item_id` | `varchar(64)` | NO | MUL |  |  |
| `attempt` | `int` | NO |  |  |  |
| `related_id` | `varchar(128)` | YES |  |  |  |
| `task_id` | `varchar(64)` | YES |  |  |  |
| `status` | `varchar(32)` | NO |  |  |  |
| `error` | `longtext` | YES |  |  |  |
| `created_at` | `varchar(64)` | NO |  |  |  |
| `finished_at` | `varchar(64)` | YES |  |  |  |

Indexes:
- `idx_experiment_batch_attempts_item` (non-unique): `item_id`, `attempt`
- `item_id` (unique): `item_id`, `attempt`
- `PRIMARY` (unique): `id`

## `experiment_batch_items`

| Column | Type | Null | Key | Default | Extra |
| --- | --- | --- | --- | --- | --- |
| `id` | `varchar(64)` | NO | PRI |  |  |
| `batch_id` | `varchar(64)` | NO | MUL |  |  |
| `item_index` | `int` | NO |  |  |  |
| `item_key` | `varchar(255)` | NO |  |  |  |
| `project_id` | `varchar(255)` | YES |  |  |  |
| `symbol` | `varchar(64)` | YES |  |  |  |
| `status` | `varchar(32)` | NO |  |  |  |
| `parameters_json` | `longtext` | NO |  |  |  |
| `related_id` | `varchar(128)` | YES | MUL |  |  |
| `task_id` | `varchar(64)` | YES |  |  |  |
| `attempt` | `int` | NO |  | 0 |  |
| `result_json` | `longtext` | YES |  |  |  |
| `error` | `longtext` | YES |  |  |  |
| `created_at` | `varchar(64)` | NO |  |  |  |
| `started_at` | `varchar(64)` | YES |  |  |  |
| `finished_at` | `varchar(64)` | YES |  |  |  |

Indexes:
- `batch_id` (unique): `batch_id`, `item_key`
- `idx_experiment_batch_items_batch_status` (non-unique): `batch_id`, `status`, `item_index`
- `idx_experiment_batch_items_related` (non-unique): `related_id`
- `PRIMARY` (unique): `id`

## `experiment_batches`

| Column | Type | Null | Key | Default | Extra |
| --- | --- | --- | --- | --- | --- |
| `id` | `varchar(64)` | NO | PRI |  |  |
| `kind` | `varchar(32)` | NO |  |  |  |
| `mode` | `varchar(64)` | NO |  |  |  |
| `name` | `varchar(255)` | NO |  |  |  |
| `example_key` | `varchar(128)` | YES |  |  |  |
| `status` | `varchar(32)` | NO | MUL |  |  |
| `config_json` | `longtext` | NO |  |  |  |
| `summary_json` | `longtext` | YES |  |  |  |
| `total` | `int` | NO |  | 0 |  |
| `queued` | `int` | NO |  | 0 |  |
| `running` | `int` | NO |  | 0 |  |
| `succeeded` | `int` | NO |  | 0 |  |
| `failed` | `int` | NO |  | 0 |  |
| `skipped` | `int` | NO |  | 0 |  |
| `cancelled` | `int` | NO |  | 0 |  |
| `cancel_requested` | `int` | NO |  | 0 |  |
| `created_at` | `varchar(64)` | NO | MUL |  |  |
| `started_at` | `varchar(64)` | YES |  |  |  |
| `finished_at` | `varchar(64)` | YES |  |  |  |
| `objective_metric` | `varchar(32)` | YES |  |  |  |
| `source_backtest_run_id` | `varchar(191)` | YES |  |  |  |
| `scope_hash` | `varchar(128)` | YES |  |  |  |
| `data_fingerprint` | `varchar(128)` | YES |  |  |  |
| `archived_at` | `varchar(64)` | YES |  |  |  |

Indexes:
- `idx_experiment_batches_created` (non-unique): `created_at`
- `idx_experiment_batches_status` (non-unique): `status`, `created_at`
- `PRIMARY` (unique): `id`

## `experiments`

| Column | Type | Null | Key | Default | Extra |
| --- | --- | --- | --- | --- | --- |
| `id` | `varchar(64)` | NO | PRI |  |  |
| `run_id` | `varchar(64)` | NO | UNI |  |  |
| `strategy_version_id` | `varchar(64)` | NO |  |  |  |
| `dataset_version_id` | `varchar(64)` | NO |  |  |  |
| `parameter_hash` | `varchar(128)` | YES |  |  |  |
| `docker_image` | `varchar(255)` | YES |  |  |  |
| `docker_image_digest` | `varchar(255)` | YES |  |  |  |
| `git_commit` | `varchar(255)` | YES |  |  |  |
| `fingerprint_json` | `longtext` | NO |  |  |  |
| `validation_json` | `longtext` | NO |  |  |  |
| `experiment_json` | `longtext` | NO |  |  |  |
| `created_at` | `varchar(32)` | NO |  |  |  |
| `updated_at` | `varchar(32)` | NO |  |  |  |

Indexes:
- `idx_experiments_run` (non-unique): `run_id`
- `PRIMARY` (unique): `id`
- `run_id` (unique): `run_id`

## `factor_evaluations`

| Column | Type | Null | Key | Default | Extra |
| --- | --- | --- | --- | --- | --- |
| `id` | `varchar(64)` | NO | PRI |  |  |
| `factor_name` | `varchar(96)` | NO |  |  |  |
| `universe_code` | `varchar(96)` | NO |  |  |  |
| `start_date` | `varchar(32)` | NO |  |  |  |
| `end_date` | `varchar(32)` | NO |  |  |  |
| `forward_days` | `int` | NO |  |  |  |
| `quantiles` | `int` | NO |  |  |  |
| `engine` | `varchar(255)` | NO |  |  |  |
| `result_json` | `longtext` | NO |  |  |  |
| `created_at` | `varchar(32)` | NO | MUL |  |  |

Indexes:
- `idx_factor_evaluations_created_at` (non-unique): `created_at`
- `PRIMARY` (unique): `id`

## `factor_values`

| Column | Type | Null | Key | Default | Extra |
| --- | --- | --- | --- | --- | --- |
| `symbol` | `varchar(96)` | NO | PRI |  |  |
| `trade_date` | `varchar(32)` | NO | PRI |  |  |
| `factor_name` | `varchar(96)` | NO | PRI |  |  |
| `value` | `double` | NO |  |  |  |
| `source` | `varchar(96)` | NO | PRI |  |  |
| `batch_id` | `varchar(64)` | YES |  |  |  |
| `created_at` | `varchar(32)` | NO |  |  |  |

Indexes:
- `idx_factor_values_name_date` (non-unique): `factor_name`, `trade_date`, `symbol`
- `idx_factor_values_symbol_date` (non-unique): `symbol`, `trade_date`
- `PRIMARY` (unique): `symbol`, `trade_date`, `factor_name`, `source`

## `feature_pipeline_fits`

| Column | Type | Null | Key | Default | Extra |
| --- | --- | --- | --- | --- | --- |
| `id` | `varchar(64)` | NO | PRI |  |  |
| `window_id` | `varchar(64)` | NO | MUL |  |  |
| `pipeline_version` | `varchar(255)` | NO |  |  |  |
| `fit_phase` | `varchar(32)` | NO |  |  |  |
| `fit_start` | `varchar(10)` | NO |  |  |  |
| `fit_end` | `varchar(10)` | NO |  |  |  |
| `fit_statistics_json` | `longtext` | NO |  |  |  |
| `fit_fingerprint` | `varchar(64)` | NO | UNI |  |  |
| `created_at` | `varchar(64)` | NO |  |  |  |

Indexes:
- `fit_fingerprint` (unique): `fit_fingerprint`
- `idx_feature_pipeline_fits_window` (non-unique): `window_id`, `fit_phase`
- `PRIMARY` (unique): `id`
- `window_id` (unique): `window_id`, `pipeline_version`, `fit_phase`

## `financial_facts`

| Column | Type | Null | Key | Default | Extra |
| --- | --- | --- | --- | --- | --- |
| `symbol` | `varchar(96)` | NO | PRI |  |  |
| `field_name` | `varchar(96)` | NO | PRI |  |  |
| `report_date` | `varchar(32)` | NO | PRI |  |  |
| `announce_date` | `varchar(32)` | NO | PRI |  |  |
| `effective_date` | `varchar(32)` | NO |  |  |  |
| `value` | `double` | YES |  |  |  |
| `unit` | `varchar(255)` | YES |  |  |  |
| `source` | `varchar(96)` | NO | PRI |  |  |
| `batch_id` | `varchar(64)` | YES |  |  |  |
| `created_at` | `varchar(32)` | NO |  |  |  |

Indexes:
- `idx_financial_facts_pit` (non-unique): `symbol`, `field_name`, `effective_date`, `announce_date`, `report_date`
- `PRIMARY` (unique): `symbol`, `field_name`, `report_date`, `announce_date`, `source`

## `financial_statements`

| Column | Type | Null | Key | Default | Extra |
| --- | --- | --- | --- | --- | --- |
| `symbol` | `varchar(96)` | NO | PRI |  |  |
| `statement_type` | `varchar(96)` | NO | PRI |  |  |
| `report_date` | `varchar(32)` | NO | PRI |  |  |
| `announce_date` | `varchar(32)` | NO | PRI |  |  |
| `effective_date` | `varchar(32)` | NO |  |  |  |
| `fiscal_period` | `varchar(32)` | YES |  |  |  |
| `currency` | `varchar(96)` | YES |  |  |  |
| `fields_json` | `longtext` | NO |  |  |  |
| `source` | `varchar(96)` | NO | PRI |  |  |
| `batch_id` | `varchar(64)` | YES |  |  |  |
| `created_at` | `varchar(32)` | NO |  |  |  |
| `report_type` | `varchar(32)` | YES |  |  |  |
| `update_flag` | `varchar(32)` | YES |  |  |  |
| `payload_hash` | `varchar(64)` | YES |  |  |  |

Indexes:
- `idx_financial_statements_pit` (non-unique): `symbol`, `statement_type`, `effective_date`, `announce_date`, `report_date`
- `PRIMARY` (unique): `symbol`, `statement_type`, `report_date`, `announce_date`, `source`

## `futures_continuous_bars`

| Column | Type | Null | Key | Default | Extra |
| --- | --- | --- | --- | --- | --- |
| `build_id` | `varchar(64)` | NO | PRI |  |  |
| `trade_date` | `varchar(16)` | NO | PRI |  |  |
| `contract_code` | `varchar(64)` | NO |  |  |  |
| `raw_open` | `double` | YES |  |  |  |
| `raw_close` | `double` | NO |  |  |  |
| `adjusted_close` | `double` | NO |  |  |  |
| `adjustment_factor` | `double` | NO |  |  |  |
| `multiplier` | `double` | NO |  |  |  |
| `margin_rate` | `double` | NO |  |  |  |
| `notional` | `double` | NO |  |  |  |
| `margin_required` | `double` | NO |  |  |  |
| `variation_pnl` | `double` | NO |  |  |  |
| `commission` | `double` | NO |  |  |  |
| `slippage` | `double` | NO |  |  |  |
| `net_pnl` | `double` | NO |  |  |  |
| `cumulative_net_pnl` | `double` | NO |  |  |  |
| `is_roll` | `int` | NO |  | 0 |  |
| `roll_gap` | `double` | YES |  |  |  |
| `roll_yield` | `double` | YES |  |  |  |

Indexes:
- `idx_futures_continuous_bars_build` (non-unique): `build_id`, `trade_date`
- `PRIMARY` (unique): `build_id`, `trade_date`

## `futures_continuous_builds`

| Column | Type | Null | Key | Default | Extra |
| --- | --- | --- | --- | --- | --- |
| `id` | `varchar(64)` | NO | PRI |  |  |
| `product` | `varchar(32)` | NO | MUL |  |  |
| `exchange` | `varchar(32)` | NO |  |  |  |
| `start_date` | `varchar(16)` | NO |  |  |  |
| `end_date` | `varchar(16)` | NO |  |  |  |
| `adjustment` | `varchar(32)` | NO |  |  |  |
| `contracts` | `double` | NO |  |  |  |
| `mapping_batch_id` | `varchar(64)` | NO |  |  |  |
| `fee_schedule_version` | `varchar(64)` | NO |  |  |  |
| `config_json` | `longtext` | NO |  |  |  |
| `summary_json` | `longtext` | NO |  |  |  |
| `created_at` | `varchar(64)` | NO |  |  |  |

Indexes:
- `idx_futures_continuous_builds_lookup` (non-unique): `product`, `exchange`, `created_at`
- `PRIMARY` (unique): `id`

## `futures_contracts`

| Column | Type | Null | Key | Default | Extra |
| --- | --- | --- | --- | --- | --- |
| `contract_code` | `varchar(96)` | NO | PRI |  |  |
| `product` | `varchar(96)` | NO | MUL |  |  |
| `exchange` | `varchar(96)` | NO |  |  |  |
| `name` | `varchar(255)` | YES |  |  |  |
| `multiplier` | `double` | YES |  |  |  |
| `margin_rate` | `double` | YES |  |  |  |
| `tick_size` | `double` | YES |  |  |  |
| `delivery_month` | `varchar(32)` | YES |  |  |  |
| `listed_date` | `varchar(32)` | YES |  |  |  |
| `last_trade_date` | `varchar(32)` | YES |  |  |  |
| `source` | `varchar(96)` | NO |  |  |  |
| `updated_at` | `varchar(32)` | NO |  |  |  |

Indexes:
- `idx_futures_contracts_product` (non-unique): `product`, `exchange`, `last_trade_date`
- `PRIMARY` (unique): `contract_code`

## `futures_daily_bars`

| Column | Type | Null | Key | Default | Extra |
| --- | --- | --- | --- | --- | --- |
| `contract_code` | `varchar(96)` | NO | PRI |  |  |
| `trade_date` | `varchar(32)` | NO | PRI |  |  |
| `open` | `double` | YES |  |  |  |
| `high` | `double` | YES |  |  |  |
| `low` | `double` | YES |  |  |  |
| `close` | `double` | YES |  |  |  |
| `volume` | `double` | YES |  |  |  |
| `open_interest` | `double` | YES |  |  |  |
| `source` | `varchar(96)` | NO | PRI |  |  |
| `batch_id` | `varchar(64)` | YES |  |  |  |
| `created_at` | `varchar(32)` | NO |  |  |  |

Indexes:
- `idx_futures_daily_date` (non-unique): `trade_date`, `contract_code`
- `PRIMARY` (unique): `contract_code`, `trade_date`, `source`

## `futures_fee_schedules`

| Column | Type | Null | Key | Default | Extra |
| --- | --- | --- | --- | --- | --- |
| `product` | `varchar(32)` | NO | PRI |  |  |
| `exchange` | `varchar(32)` | NO | PRI |  |  |
| `open_rate` | `double` | NO |  | 0 |  |
| `close_rate` | `double` | NO |  | 0 |  |
| `close_today_rate` | `double` | NO |  | 0 |  |
| `per_contract` | `double` | NO |  | 0 |  |
| `slippage_ticks` | `double` | NO |  | 0 |  |
| `currency` | `varchar(16)` | NO |  | CNY |  |
| `version` | `varchar(64)` | NO |  |  |  |
| `source` | `varchar(64)` | NO |  |  |  |
| `updated_at` | `varchar(64)` | NO |  |  |  |

Indexes:
- `PRIMARY` (unique): `product`, `exchange`

## `futures_main_mapping`

| Column | Type | Null | Key | Default | Extra |
| --- | --- | --- | --- | --- | --- |
| `product` | `varchar(96)` | NO | PRI |  |  |
| `exchange` | `varchar(96)` | NO | PRI |  |  |
| `trade_date` | `varchar(32)` | NO | PRI |  |  |
| `main_symbol` | `varchar(96)` | NO |  |  |  |
| `continuous_symbol` | `varchar(96)` | YES |  |  |  |
| `rule` | `varchar(255)` | NO |  |  |  |
| `source` | `varchar(96)` | NO | PRI |  |  |
| `batch_id` | `varchar(64)` | YES |  |  |  |
| `updated_at` | `varchar(32)` | NO |  |  |  |

Indexes:
- `idx_futures_main_mapping_date` (non-unique): `product`, `exchange`, `trade_date`
- `PRIMARY` (unique): `product`, `exchange`, `trade_date`, `source`

## `futures_main_rules`

| Column | Type | Null | Key | Default | Extra |
| --- | --- | --- | --- | --- | --- |
| `product` | `varchar(96)` | NO | PRI |  |  |
| `exchange` | `varchar(96)` | NO | PRI |  |  |
| `rule_type` | `varchar(96)` | NO |  |  |  |
| `roll_days_before_expiry` | `int` | NO |  | 0 |  |
| `min_open_interest_days` | `int` | NO |  | 1 |  |
| `source` | `varchar(96)` | NO |  |  |  |
| `updated_at` | `varchar(32)` | NO |  |  |  |

Indexes:
- `PRIMARY` (unique): `product`, `exchange`

## `futures_roll_events`

| Column | Type | Null | Key | Default | Extra |
| --- | --- | --- | --- | --- | --- |
| `id` | `varchar(64)` | NO | PRI |  |  |
| `build_id` | `varchar(64)` | NO | MUL |  |  |
| `trade_date` | `varchar(16)` | NO |  |  |  |
| `from_contract` | `varchar(64)` | NO |  |  |  |
| `to_contract` | `varchar(64)` | NO |  |  |  |
| `from_price` | `double` | NO |  |  |  |
| `to_price` | `double` | NO |  |  |  |
| `roll_gap` | `double` | NO |  |  |  |
| `roll_yield` | `double` | NO |  |  |  |
| `market_pnl` | `double` | NO |  |  |  |
| `commission` | `double` | NO |  |  |  |
| `slippage` | `double` | NO |  |  |  |
| `net_pnl` | `double` | NO |  |  |  |

Indexes:
- `idx_futures_roll_events_build` (non-unique): `build_id`, `trade_date`
- `PRIMARY` (unique): `id`

## `index_membership_events`

| Column | Type | Null | Key | Default | Extra |
| --- | --- | --- | --- | --- | --- |
| `id` | `varchar(64)` | NO | PRI |  |  |
| `index_code` | `varchar(96)` | NO | MUL |  |  |
| `symbol` | `varchar(96)` | NO |  |  |  |
| `name` | `varchar(255)` | YES |  |  |  |
| `action_type` | `varchar(96)` | NO |  |  |  |
| `adjustment_type` | `varchar(255)` | YES |  |  |  |
| `announce_date` | `varchar(32)` | NO |  |  |  |
| `effective_date` | `varchar(32)` | NO |  |  |  |
| `source_url` | `varchar(255)` | YES |  |  |  |
| `raw_file_hash` | `varchar(128)` | YES |  |  |  |
| `batch_id` | `varchar(64)` | NO |  |  |  |
| `parse_status` | `varchar(96)` | NO |  |  |  |
| `updated_at` | `varchar(32)` | NO |  |  |  |

Indexes:
- `idx_index_events_asof` (non-unique): `index_code`, `effective_date`, `announce_date`, `symbol`
- `index_code` (unique): `index_code`, `symbol`, `action_type`, `effective_date`, `source_url`
- `PRIMARY` (unique): `id`

## `index_membership_pit`

| Column | Type | Null | Key | Default | Extra |
| --- | --- | --- | --- | --- | --- |
| `index_code` | `varchar(96)` | NO |  |  |  |
| `symbol` | `varchar(96)` | NO |  |  |  |
| `announce_date` | `varchar(32)` | YES |  |  |  |
| `effective_date` | `varchar(32)` | YES |  |  |  |
| `start_date` | `varchar(32)` | NO |  |  |  |
| `end_date` | `varchar(32)` | YES |  |  |  |
| `weight` | `double` | YES |  |  |  |
| `source` | `varchar(96)` | NO |  |  |  |
| `batch_id` | `varchar(64)` | YES |  |  |  |

## `index_source_artifacts`

| Column | Type | Null | Key | Default | Extra |
| --- | --- | --- | --- | --- | --- |
| `id` | `varchar(64)` | NO | PRI |  |  |
| `index_code` | `varchar(96)` | NO | MUL |  |  |
| `source_url` | `varchar(255)` | NO |  |  |  |
| `local_path` | `varchar(1024)` | YES |  |  |  |
| `raw_file_hash` | `varchar(128)` | NO |  |  |  |
| `content_type` | `varchar(96)` | YES |  |  |  |
| `parser_version` | `varchar(96)` | NO |  |  |  |
| `parse_status` | `varchar(96)` | NO |  |  |  |
| `error` | `longtext` | YES |  |  |  |
| `metadata_json` | `longtext` | NO |  |  |  |
| `fetched_at` | `varchar(32)` | NO |  |  |  |

Indexes:
- `idx_index_artifacts_code` (non-unique): `index_code`, `fetched_at`
- `index_code` (unique): `index_code`, `source_url`, `raw_file_hash`
- `PRIMARY` (unique): `id`

## `index_weights`

| Column | Type | Null | Key | Default | Extra |
| --- | --- | --- | --- | --- | --- |
| `universe_code` | `varchar(96)` | NO | PRI |  |  |
| `symbol` | `varchar(96)` | NO | PRI |  |  |
| `trade_date` | `varchar(32)` | NO | PRI |  |  |
| `weight` | `double` | NO |  |  |  |
| `source` | `varchar(96)` | NO | PRI |  |  |
| `batch_id` | `varchar(64)` | YES |  |  |  |
| `created_at` | `varchar(32)` | NO |  |  |  |

Indexes:
- `idx_index_weights_date` (non-unique): `universe_code`, `trade_date`, `symbol`
- `PRIMARY` (unique): `universe_code`, `symbol`, `trade_date`, `source`

## `industry_membership`

| Column | Type | Null | Key | Default | Extra |
| --- | --- | --- | --- | --- | --- |
| `id` | `varchar(64)` | NO | PRI |  |  |
| `symbol` | `varchar(32)` | NO | MUL |  |  |
| `industry_code` | `varchar(32)` | NO |  |  |  |
| `industry_name` | `varchar(255)` | YES |  |  |  |
| `taxonomy` | `varchar(32)` | NO |  |  |  |
| `level_no` | `int` | NO |  |  |  |
| `in_date` | `varchar(16)` | NO |  |  |  |
| `out_date` | `varchar(16)` | YES |  |  |  |
| `source` | `varchar(32)` | NO |  |  |  |
| `payload_hash` | `varchar(64)` | NO |  |  |  |
| `created_at` | `varchar(64)` | NO |  |  |  |

Indexes:
- `idx_industry_membership_pit` (non-unique): `symbol`, `taxonomy`, `level_no`, `in_date`, `out_date`
- `PRIMARY` (unique): `id`
- `symbol` (unique): `symbol`, `industry_code`, `taxonomy`, `in_date`

## `instrument_identifiers`

| Column | Type | Null | Key | Default | Extra |
| --- | --- | --- | --- | --- | --- |
| `instrument_id` | `varchar(64)` | NO | PRI |  |  |
| `id_type` | `varchar(255)` | NO | PRI |  |  |
| `id_value` | `varchar(255)` | NO | PRI |  |  |
| `start_date` | `varchar(32)` | YES |  |  |  |
| `end_date` | `varchar(32)` | YES |  |  |  |
| `source` | `varchar(96)` | NO | PRI |  |  |
| `created_at` | `varchar(32)` | NO |  |  |  |
| `provider` | `varchar(96)` | YES | MUL |  |  |
| `identifier_type` | `varchar(96)` | YES |  |  |  |
| `identifier_value` | `varchar(96)` | YES |  |  |  |
| `exchange` | `varchar(32)` | YES |  |  |  |
| `market` | `varchar(32)` | YES |  |  |  |
| `valid_from` | `varchar(32)` | YES |  |  |  |
| `valid_to` | `varchar(32)` | YES |  |  |  |
| `is_primary` | `int` | NO |  | 0 |  |
| `batch_id` | `varchar(64)` | YES |  |  |  |
| `updated_at` | `varchar(32)` | YES |  |  |  |

Indexes:
- `idx_instrument_identifiers_instrument` (non-unique): `instrument_id`, `provider`, `identifier_type`
- `idx_instrument_identifiers_provider_value` (unique): `provider`, `identifier_type`, `identifier_value`, `valid_from`
- `PRIMARY` (unique): `instrument_id`, `id_type`, `id_value`, `source`

## `instruments`

| Column | Type | Null | Key | Default | Extra |
| --- | --- | --- | --- | --- | --- |
| `instrument_id` | `varchar(64)` | NO | PRI |  |  |
| `symbol` | `varchar(96)` | NO |  |  |  |
| `normalized_symbol` | `varchar(96)` | NO |  |  |  |
| `name` | `varchar(255)` | YES |  |  |  |
| `asset_class` | `varchar(96)` | NO | MUL |  |  |
| `market` | `varchar(96)` | NO |  |  |  |
| `exchange` | `varchar(96)` | YES |  |  |  |
| `venue` | `varchar(96)` | YES |  |  |  |
| `currency` | `varchar(96)` | YES |  |  |  |
| `base_currency` | `varchar(96)` | YES |  |  |  |
| `quote_currency` | `varchar(96)` | YES |  |  |  |
| `underlying_symbol` | `varchar(96)` | YES |  |  |  |
| `listed_date` | `varchar(32)` | YES |  |  |  |
| `delisted_date` | `varchar(32)` | YES |  |  |  |
| `expiry_date` | `varchar(32)` | YES |  |  |  |
| `status` | `varchar(96)` | NO |  | active |  |
| `lot_size` | `double` | YES |  |  |  |
| `tick_size` | `double` | YES |  |  |  |
| `contract_multiplier` | `double` | YES |  |  |  |
| `margin_rate` | `double` | YES |  |  |  |
| `metadata_json` | `longtext` | NO |  |  |  |
| `source` | `varchar(96)` | NO |  |  |  |
| `created_at` | `varchar(32)` | NO |  |  |  |
| `updated_at` | `varchar(32)` | NO |  |  |  |

Indexes:
- `asset_class` (unique): `asset_class`, `market`, `venue`, `symbol`
- `idx_instruments_status` (non-unique): `asset_class`, `market`, `status`, `listed_date`, `delisted_date`
- `idx_instruments_symbol` (non-unique): `asset_class`, `market`, `venue`, `symbol`
- `PRIMARY` (unique): `instrument_id`

## `leakage_check_results`

| Column | Type | Null | Key | Default | Extra |
| --- | --- | --- | --- | --- | --- |
| `id` | `varchar(64)` | NO | PRI |  |  |
| `window_id` | `varchar(64)` | NO | MUL |  |  |
| `decision` | `varchar(16)` | NO |  |  |  |
| `check_version` | `varchar(64)` | NO |  |  |  |
| `result_json` | `longtext` | NO |  |  |  |
| `checked_at` | `varchar(64)` | NO |  |  |  |

Indexes:
- `idx_leakage_checks_window` (non-unique): `window_id`, `decision`
- `PRIMARY` (unique): `id`
- `window_id` (unique): `window_id`, `check_version`

## `market_daily_bars`

| Column | Type | Null | Key | Default | Extra |
| --- | --- | --- | --- | --- | --- |
| `instrument_id` | `varchar(64)` | NO | PRI |  |  |
| `symbol` | `varchar(96)` | NO |  |  |  |
| `asset_class` | `varchar(96)` | NO | MUL |  |  |
| `market` | `varchar(96)` | NO |  |  |  |
| `venue` | `varchar(96)` | YES |  |  |  |
| `trade_date` | `varchar(32)` | NO | PRI |  |  |
| `resolution` | `varchar(96)` | NO | PRI | daily |  |
| `data_type` | `varchar(96)` | NO | PRI | trade |  |
| `open` | `double` | YES |  |  |  |
| `high` | `double` | YES |  |  |  |
| `low` | `double` | YES |  |  |  |
| `close` | `double` | YES |  |  |  |
| `settle` | `double` | YES |  |  |  |
| `volume` | `double` | YES |  |  |  |
| `amount` | `double` | YES |  |  |  |
| `turnover_rate` | `double` | YES |  |  |  |
| `open_interest` | `double` | YES |  |  |  |
| `prev_close` | `double` | YES |  |  |  |
| `pct_change` | `double` | YES |  |  |  |
| `adjust` | `varchar(96)` | NO | PRI | raw |  |
| `adj_factor` | `double` | YES |  |  |  |
| `source` | `varchar(96)` | NO | PRI |  |  |
| `batch_id` | `varchar(64)` | YES |  |  |  |
| `created_at` | `varchar(32)` | NO |  |  |  |

Indexes:
- `idx_market_daily_instrument_date` (non-unique): `instrument_id`, `trade_date`
- `idx_market_daily_lineage` (non-unique): `asset_class`, `market`, `source`, `batch_id`, `symbol`
- `idx_market_daily_symbol_date` (non-unique): `asset_class`, `market`, `symbol`, `trade_date`
- `PRIMARY` (unique): `instrument_id`, `trade_date`, `resolution`, `data_type`, `adjust`, `source`

## `market_intraday_bars`

| Column | Type | Null | Key | Default | Extra |
| --- | --- | --- | --- | --- | --- |
| `instrument_id` | `varchar(64)` | NO | PRI |  |  |
| `symbol` | `varchar(96)` | NO |  |  |  |
| `asset_class` | `varchar(96)` | NO | MUL |  |  |
| `market` | `varchar(96)` | NO |  |  |  |
| `venue` | `varchar(96)` | YES |  |  |  |
| `timestamp` | `varchar(32)` | NO | PRI |  |  |
| `frequency` | `varchar(96)` | NO | PRI |  |  |
| `data_type` | `varchar(96)` | NO | PRI | trade |  |
| `open` | `double` | YES |  |  |  |
| `high` | `double` | YES |  |  |  |
| `low` | `double` | YES |  |  |  |
| `close` | `double` | YES |  |  |  |
| `volume` | `double` | YES |  |  |  |
| `amount` | `double` | YES |  |  |  |
| `open_interest` | `double` | YES |  |  |  |
| `adjust` | `varchar(96)` | NO | PRI | raw |  |
| `source` | `varchar(96)` | NO | PRI |  |  |
| `batch_id` | `varchar(64)` | YES |  |  |  |
| `created_at` | `varchar(32)` | NO |  |  |  |

Indexes:
- `idx_market_intraday_symbol_time` (non-unique): `asset_class`, `market`, `symbol`, `frequency`, `timestamp`
- `PRIMARY` (unique): `instrument_id`, `timestamp`, `frequency`, `data_type`, `adjust`, `source`

## `market_ticks`

| Column | Type | Null | Key | Default | Extra |
| --- | --- | --- | --- | --- | --- |
| `id` | `varchar(64)` | NO | PRI |  |  |
| `instrument_id` | `varchar(64)` | NO |  |  |  |
| `symbol` | `varchar(96)` | NO |  |  |  |
| `asset_class` | `varchar(96)` | NO | MUL |  |  |
| `market` | `varchar(96)` | NO |  |  |  |
| `venue` | `varchar(96)` | YES |  |  |  |
| `timestamp` | `varchar(32)` | NO |  |  |  |
| `last_price` | `double` | YES |  |  |  |
| `bid_price` | `double` | YES |  |  |  |
| `ask_price` | `double` | YES |  |  |  |
| `bid_volume` | `double` | YES |  |  |  |
| `ask_volume` | `double` | YES |  |  |  |
| `volume` | `double` | YES |  |  |  |
| `open_interest` | `double` | YES |  |  |  |
| `source` | `varchar(96)` | NO |  |  |  |
| `batch_id` | `varchar(64)` | YES |  |  |  |
| `created_at` | `varchar(32)` | NO |  |  |  |

Indexes:
- `idx_market_ticks_symbol_time` (non-unique): `asset_class`, `market`, `symbol`, `timestamp`
- `PRIMARY` (unique): `id`

## `market_trade_status`

| Column | Type | Null | Key | Default | Extra |
| --- | --- | --- | --- | --- | --- |
| `instrument_id` | `varchar(64)` | NO | PRI |  |  |
| `symbol` | `varchar(96)` | NO |  |  |  |
| `asset_class` | `varchar(96)` | NO | MUL |  |  |
| `market` | `varchar(96)` | NO |  |  |  |
| `venue` | `varchar(96)` | YES |  |  |  |
| `trade_date` | `varchar(32)` | NO | PRI |  |  |
| `is_tradeable` | `int` | NO |  | 1 |  |
| `is_suspended` | `int` | NO |  | 0 |  |
| `can_buy` | `int` | NO |  | 1 |  |
| `can_sell` | `int` | NO |  | 1 |  |
| `limit_up` | `double` | YES |  |  |  |
| `limit_down` | `double` | YES |  |  |  |
| `status` | `varchar(96)` | YES |  |  |  |
| `reason` | `varchar(255)` | YES |  |  |  |
| `source` | `varchar(96)` | NO | PRI |  |  |
| `batch_id` | `varchar(64)` | YES |  |  |  |
| `updated_at` | `varchar(32)` | NO |  |  |  |
| `is_limit_up` | `int` | NO |  | 0 |  |
| `is_limit_down` | `int` | NO |  | 0 |  |
| `is_one_word_limit_up` | `int` | NO |  | 0 |  |
| `is_one_word_limit_down` | `int` | NO |  | 0 |  |
| `is_st` | `int` | NO |  | 0 |  |

Indexes:
- `idx_market_status_symbol_date` (non-unique): `asset_class`, `market`, `symbol`, `trade_date`
- `PRIMARY` (unique): `instrument_id`, `trade_date`, `source`

## `ml_feature_files`

| Column | Type | Null | Key | Default | Extra |
| --- | --- | --- | --- | --- | --- |
| `id` | `varchar(64)` | NO | PRI |  |  |
| `feature_set_id` | `varchar(64)` | NO | MUL |  |  |
| `relative_path` | `varchar(512)` | NO |  |  |  |
| `sha256` | `varchar(64)` | NO |  |  |  |
| `row_count` | `int` | NO |  |  |  |
| `min_date` | `varchar(16)` | YES |  |  |  |
| `max_date` | `varchar(16)` | YES |  |  |  |
| `size_bytes` | `int` | NO |  |  |  |
| `created_at` | `varchar(64)` | NO |  |  |  |

Indexes:
- `feature_set_id` (unique): `feature_set_id`, `relative_path`
- `idx_ml_feature_files_set` (non-unique): `feature_set_id`
- `PRIMARY` (unique): `id`

## `ml_feature_sets`

| Column | Type | Null | Key | Default | Extra |
| --- | --- | --- | --- | --- | --- |
| `id` | `varchar(64)` | NO | PRI |  |  |
| `fingerprint` | `varchar(64)` | NO | UNI |  |  |
| `universe_code` | `varchar(32)` | NO |  |  |  |
| `start_date` | `varchar(16)` | NO |  |  |  |
| `end_date` | `varchar(16)` | NO |  |  |  |
| `feature_version` | `varchar(64)` | NO |  |  |  |
| `status` | `varchar(32)` | NO |  |  |  |
| `row_count` | `int` | NO |  | 0 |  |
| `symbol_count` | `int` | NO |  | 0 |  |
| `feature_count` | `int` | NO |  | 0 |  |
| `manifest_json` | `longtext` | NO |  |  |  |
| `coverage_json` | `longtext` | NO |  |  |  |
| `created_at` | `varchar(64)` | NO | MUL |  |  |
| `completed_at` | `varchar(64)` | YES |  |  |  |

Indexes:
- `fingerprint` (unique): `fingerprint`
- `idx_ml_feature_sets_created` (non-unique): `created_at`
- `PRIMARY` (unique): `id`

## `ml_prediction_files`

| Column | Type | Null | Key | Default | Extra |
| --- | --- | --- | --- | --- | --- |
| `id` | `varchar(64)` | NO | PRI |  |  |
| `training_run_id` | `varchar(64)` | NO | MUL |  |  |
| `split_key` | `varchar(64)` | NO |  |  |  |
| `relative_path` | `varchar(1024)` | NO |  |  |  |
| `sha256` | `varchar(64)` | NO |  |  |  |
| `row_count` | `int` | NO |  |  |  |
| `metrics_json` | `longtext` | NO |  |  |  |
| `created_at` | `varchar(64)` | NO |  |  |  |

Indexes:
- `idx_ml_prediction_files_run` (non-unique): `training_run_id`
- `PRIMARY` (unique): `id`
- `training_run_id` (unique): `training_run_id`, `split_key`

## `ml_training_runs`

| Column | Type | Null | Key | Default | Extra |
| --- | --- | --- | --- | --- | --- |
| `id` | `varchar(64)` | NO | PRI |  |  |
| `research_run_id` | `varchar(64)` | NO | UNI |  |  |
| `feature_set_id` | `varchar(64)` | YES |  |  |  |
| `status` | `varchar(32)` | NO | MUL |  |  |
| `stage` | `varchar(64)` | NO |  |  |  |
| `progress` | `double` | NO |  | 0 |  |
| `mlflow_run_id` | `varchar(128)` | YES |  |  |  |
| `mlflow_experiment` | `varchar(255)` | YES |  |  |  |
| `registered_model_name` | `varchar(255)` | YES |  |  |  |
| `registered_model_version` | `varchar(64)` | YES |  |  |  |
| `selected_trial_id` | `varchar(64)` | YES |  |  |  |
| `metrics_json` | `longtext` | NO |  |  |  |
| `quality_json` | `longtext` | NO |  |  |  |
| `fold_plan_json` | `longtext` | NO |  |  |  |
| `artifacts_json` | `longtext` | NO |  |  |  |
| `error` | `longtext` | YES |  |  |  |
| `created_at` | `varchar(64)` | NO |  |  |  |
| `started_at` | `varchar(64)` | YES |  |  |  |
| `finished_at` | `varchar(64)` | YES |  |  |  |
| `updated_at` | `varchar(64)` | NO |  |  |  |

Indexes:
- `idx_ml_training_runs_status` (non-unique): `status`, `updated_at`
- `PRIMARY` (unique): `id`
- `research_run_id` (unique): `research_run_id`

## `ml_training_trials`

| Column | Type | Null | Key | Default | Extra |
| --- | --- | --- | --- | --- | --- |
| `id` | `varchar(64)` | NO | PRI |  |  |
| `training_run_id` | `varchar(64)` | NO | MUL |  |  |
| `fold_index` | `int` | NO |  |  |  |
| `candidate_index` | `int` | NO |  |  |  |
| `status` | `varchar(32)` | NO |  |  |  |
| `parameters_json` | `longtext` | NO |  |  |  |
| `metrics_json` | `longtext` | NO |  |  |  |
| `best_iteration` | `int` | YES |  |  |  |
| `mlflow_run_id` | `varchar(128)` | YES |  |  |  |
| `selected` | `int` | NO |  | 0 |  |
| `created_at` | `varchar(64)` | NO |  |  |  |
| `finished_at` | `varchar(64)` | YES |  |  |  |

Indexes:
- `idx_ml_training_trials_run` (non-unique): `training_run_id`, `fold_index`, `candidate_index`
- `PRIMARY` (unique): `id`
- `training_run_id` (unique): `training_run_id`, `fold_index`, `candidate_index`

## `object_store_items`

| Column | Type | Null | Key | Default | Extra |
| --- | --- | --- | --- | --- | --- |
| `key` | `varchar(191)` | NO | PRI |  |  |
| `file_path` | `varchar(1024)` | NO |  |  |  |
| `stored_object_id` | `varchar(64)` | YES |  |  |  |
| `size` | `int` | NO |  |  |  |
| `updated_at` | `varchar(32)` | NO |  |  |  |

Indexes:
- `PRIMARY` (unique): `key`

## `oos_evaluations`

| Column | Type | Null | Key | Default | Extra |
| --- | --- | --- | --- | --- | --- |
| `id` | `varchar(64)` | NO | PRI |  |  |
| `window_id` | `varchar(64)` | NO | UNI |  |  |
| `selected_candidate_id` | `varchar(64)` | NO |  |  |  |
| `oos_item_id` | `varchar(64)` | NO | UNI |  |  |
| `oos_run_id` | `varchar(128)` | YES |  |  |  |
| `input_fingerprint` | `varchar(64)` | NO |  |  |  |
| `result_digest` | `varchar(64)` | YES |  |  |  |
| `metrics_json` | `longtext` | YES |  |  |  |
| `status` | `varchar(32)` | NO |  |  |  |
| `created_at` | `varchar(64)` | NO |  |  |  |
| `completed_at` | `varchar(64)` | YES |  |  |  |

Indexes:
- `idx_oos_evaluations_window` (non-unique): `window_id`, `status`
- `oos_item_id` (unique): `oos_item_id`
- `PRIMARY` (unique): `id`
- `window_id` (unique): `window_id`

## `paper_account_checkpoints`

| Column | Type | Null | Key | Default | Extra |
| --- | --- | --- | --- | --- | --- |
| `id` | `varchar(64)` | NO | PRI |  |  |
| `paper_account_id` | `varchar(64)` | NO | MUL |  |  |
| `generation` | `int` | NO |  |  |  |
| `cycle_id` | `varchar(64)` | YES |  |  |  |
| `source_ledger_sequence` | `int` | NO |  |  |  |
| `digest` | `varchar(128)` | NO | UNI |  |  |
| `checkpoint_json` | `longtext` | NO |  |  |  |
| `created_at` | `varchar(64)` | NO |  |  |  |

Indexes:
- `digest` (unique): `digest`
- `paper_account_id` (unique): `paper_account_id`, `generation`, `source_ledger_sequence`
- `PRIMARY` (unique): `id`

## `paper_account_daily_reports`

| Column | Type | Null | Key | Default | Extra |
| --- | --- | --- | --- | --- | --- |
| `id` | `varchar(64)` | NO | PRI |  |  |
| `paper_account_id` | `varchar(64)` | NO | MUL |  |  |
| `deployment_id` | `varchar(64)` | NO | MUL |  |  |
| `cycle_id` | `varchar(64)` | NO | UNI |  |  |
| `trading_date` | `varchar(32)` | NO |  |  |  |
| `report_json` | `longtext` | NO |  |  |  |
| `result_digest` | `varchar(128)` | NO | UNI |  |  |
| `created_at` | `varchar(64)` | NO |  |  |  |

Indexes:
- `cycle_id` (unique): `cycle_id`
- `deployment_id` (non-unique): `deployment_id`
- `paper_account_id` (non-unique): `paper_account_id`
- `PRIMARY` (unique): `id`
- `result_digest` (unique): `result_digest`

## `paper_account_daily_snapshots`

| Column | Type | Null | Key | Default | Extra |
| --- | --- | --- | --- | --- | --- |
| `id` | `varchar(64)` | NO | PRI |  |  |
| `paper_account_id` | `varchar(64)` | NO | MUL |  |  |
| `generation` | `int` | NO |  |  |  |
| `trading_date` | `varchar(32)` | NO |  |  |  |
| `projection_json` | `longtext` | NO |  |  |  |
| `benchmark_symbol` | `varchar(64)` | NO |  |  |  |
| `benchmark_return` | `decimal(20,12)` | NO |  |  |  |
| `source_ledger_sequence` | `int` | NO |  |  |  |
| `source_checkpoint_digest` | `varchar(128)` | NO |  |  |  |
| `created_at` | `varchar(64)` | NO |  |  |  |

Indexes:
- `paper_account_id` (unique): `paper_account_id`, `generation`, `trading_date`
- `PRIMARY` (unique): `id`

## `paper_account_generations`

| Column | Type | Null | Key | Default | Extra |
| --- | --- | --- | --- | --- | --- |
| `id` | `varchar(64)` | NO | PRI |  |  |
| `paper_account_id` | `varchar(64)` | NO | MUL |  |  |
| `generation` | `int` | NO |  |  |  |
| `opening_cash` | `decimal(28,8)` | NO |  |  |  |
| `opening_ledger_entry_id` | `varchar(64)` | NO | UNI |  |  |
| `opening_checkpoint_digest` | `varchar(128)` | NO |  |  |  |
| `reason` | `varchar(255)` | NO |  |  |  |
| `created_at` | `varchar(64)` | NO |  |  |  |

Indexes:
- `opening_ledger_entry_id` (unique): `opening_ledger_entry_id`
- `paper_account_id` (unique): `paper_account_id`, `generation`
- `PRIMARY` (unique): `id`

## `paper_account_position_projections`

| Column | Type | Null | Key | Default | Extra |
| --- | --- | --- | --- | --- | --- |
| `paper_account_id` | `varchar(64)` | NO | PRI |  |  |
| `generation` | `int` | NO | PRI |  |  |
| `symbol` | `varchar(64)` | NO | PRI |  |  |
| `security_name` | `varchar(191)` | YES |  |  |  |
| `market` | `varchar(32)` | NO |  |  |  |
| `quantity` | `decimal(28,8)` | NO |  |  |  |
| `sellable_quantity` | `decimal(28,8)` | NO |  |  |  |
| `frozen_quantity` | `decimal(28,8)` | NO |  |  |  |
| `average_cost` | `decimal(28,8)` | NO |  |  |  |
| `certified_price` | `decimal(28,8)` | YES |  |  |  |
| `market_value` | `decimal(28,8)` | NO |  |  |  |
| `account_weight` | `decimal(20,12)` | NO |  |  |  |
| `daily_pnl` | `decimal(28,8)` | NO |  |  |  |
| `unrealized_pnl` | `decimal(28,8)` | NO |  |  |  |
| `realized_pnl` | `decimal(28,8)` | NO |  |  |  |
| `last_buy_date` | `varchar(32)` | YES |  |  |  |
| `quote_data_timestamp` | `varchar(64)` | YES |  |  |  |
| `data_status` | `varchar(32)` | NO |  |  |  |
| `updated_at` | `varchar(64)` | NO |  |  |  |

Indexes:
- `PRIMARY` (unique): `paper_account_id`, `generation`, `symbol`

## `paper_account_projections`

| Column | Type | Null | Key | Default | Extra |
| --- | --- | --- | --- | --- | --- |
| `paper_account_id` | `varchar(64)` | NO | PRI |  |  |
| `generation` | `int` | NO |  |  |  |
| `cash` | `decimal(28,8)` | NO |  |  |  |
| `available_cash` | `decimal(28,8)` | NO |  |  |  |
| `frozen_cash` | `decimal(28,8)` | NO |  |  |  |
| `market_value` | `decimal(28,8)` | NO |  |  |  |
| `total_equity` | `decimal(28,8)` | NO |  |  |  |
| `realized_pnl` | `decimal(28,8)` | NO |  |  |  |
| `unrealized_pnl` | `decimal(28,8)` | NO |  |  |  |
| `daily_pnl` | `decimal(28,8)` | NO |  |  |  |
| `cumulative_return` | `decimal(20,12)` | NO |  |  |  |
| `benchmark_return` | `decimal(20,12)` | NO |  |  |  |
| `excess_return` | `decimal(20,12)` | NO |  |  |  |
| `position_count` | `int` | NO |  |  |  |
| `gross_exposure` | `decimal(20,12)` | NO |  |  |  |
| `net_exposure` | `decimal(20,12)` | NO |  |  |  |
| `turnover` | `decimal(20,12)` | NO |  |  |  |
| `last_valuation_at` | `varchar(64)` | YES |  |  |  |
| `quote_data_timestamp` | `varchar(64)` | YES |  |  |  |
| `source_ledger_sequence` | `int` | NO |  |  |  |
| `source_checkpoint_digest` | `varchar(128)` | NO |  |  |  |
| `health_status` | `varchar(32)` | NO |  |  |  |
| `updated_at` | `varchar(64)` | NO |  |  |  |

Indexes:
- `PRIMARY` (unique): `paper_account_id`

## `paper_account_trust_certifications`

| Column | Type | Null | Key | Default | Extra |
| --- | --- | --- | --- | --- | --- |
| `id` | `varchar(96)` | NO | PRI |  |  |
| `paper_account_id` | `varchar(64)` | NO | MUL |  |  |
| `account_generation` | `int` | NO |  |  |  |
| `dataset_release_id` | `varchar(96)` | NO | MUL |  |  |
| `status` | `varchar(32)` | NO |  |  |  |
| `checkpoint_count` | `int` | NO |  | 0 |  |
| `result_count` | `int` | NO |  | 0 |  |
| `evidence_json` | `longtext` | NO |  |  |  |
| `certified_at` | `varchar(64)` | NO |  |  |  |
| `expires_at` | `varchar(64)` | NO |  |  |  |
| `revoked_at` | `varchar(64)` | YES |  |  |  |
| `revoke_reason` | `varchar(255)` | YES |  |  |  |

Indexes:
- `dataset_release_id` (non-unique): `dataset_release_id`
- `idx_paper_account_trust_active` (non-unique): `paper_account_id`, `account_generation`, `status`, `expires_at`
- `paper_account_id` (unique): `paper_account_id`, `account_generation`, `dataset_release_id`
- `PRIMARY` (unique): `id`

## `paper_accounts`

| Column | Type | Null | Key | Default | Extra |
| --- | --- | --- | --- | --- | --- |
| `id` | `varchar(64)` | NO | PRI |  |  |
| `shadow_session_id` | `varchar(64)` | NO | UNI |  |  |
| `name` | `varchar(191)` | NO |  |  |  |
| `description` | `varchar(1024)` | YES |  |  |  |
| `status` | `varchar(32)` | NO | MUL |  |  |
| `market_scope` | `varchar(32)` | NO |  |  |  |
| `base_currency` | `varchar(16)` | NO |  |  |  |
| `initial_cash` | `decimal(28,8)` | NO |  |  |  |
| `benchmark_symbol` | `varchar(64)` | NO |  |  |  |
| `execution_mode` | `varchar(32)` | NO |  |  |  |
| `current_generation` | `int` | NO |  | 1 |  |
| `active_risk_profile_id` | `varchar(64)` | YES |  |  |  |
| `version` | `int` | NO |  | 1 |  |
| `metadata_json` | `longtext` | NO |  |  |  |
| `created_at` | `varchar(64)` | NO |  |  |  |
| `updated_at` | `varchar(64)` | NO |  |  |  |
| `activated_at` | `varchar(64)` | YES |  |  |  |
| `paused_at` | `varchar(64)` | YES |  |  |  |
| `archived_at` | `varchar(64)` | YES |  |  |  |

Indexes:
- `idx_paper_accounts_status_market` (non-unique): `status`, `market_scope`, `updated_at`
- `PRIMARY` (unique): `id`
- `shadow_session_id` (unique): `shadow_session_id`

## `paper_certification_cohorts`

| Column | Type | Null | Key | Default | Extra |
| --- | --- | --- | --- | --- | --- |
| `id` | `varchar(64)` | NO | PRI |  |  |
| `name` | `varchar(191)` | NO |  |  |  |
| `status` | `varchar(32)` | NO | MUL |  |  |
| `required_accounts` | `int` | NO |  | 2 |  |
| `required_sessions` | `int` | NO |  | 21 |  |
| `contract_json` | `longtext` | NO |  |  |  |
| `evidence_digest` | `varchar(64)` | YES |  |  |  |
| `created_at` | `varchar(64)` | NO |  |  |  |
| `refreshed_at` | `varchar(64)` | YES |  |  |  |
| `certified_at` | `varchar(64)` | YES |  |  |  |

Indexes:
- `idx_paper_certification_cohorts_status` (non-unique): `status`, `created_at`
- `PRIMARY` (unique): `id`

## `paper_certification_members`

| Column | Type | Null | Key | Default | Extra |
| --- | --- | --- | --- | --- | --- |
| `id` | `varchar(64)` | NO | PRI |  |  |
| `cohort_id` | `varchar(64)` | NO | MUL |  |  |
| `paper_account_id` | `varchar(64)` | NO | MUL |  |  |
| `account_generation` | `int` | NO |  |  |  |
| `opening_cash` | `decimal(28,8)` | NO |  |  |  |
| `risk_profile_id` | `varchar(64)` | YES |  |  |  |
| `deployment_id` | `varchar(64)` | YES |  |  |  |
| `strategy_fingerprint` | `varchar(128)` | YES |  |  |  |
| `dataset_fingerprint` | `varchar(128)` | YES |  |  |  |
| `execution_mode` | `varchar(32)` | NO |  |  |  |
| `evidence_json` | `longtext` | YES |  |  |  |
| `evidence_digest` | `varchar(64)` | YES |  |  |  |
| `certified_sessions` | `int` | NO |  | 0 |  |
| `status` | `varchar(32)` | NO |  | collecting |  |
| `added_at` | `varchar(64)` | NO |  |  |  |
| `refreshed_at` | `varchar(64)` | YES |  |  |  |

Indexes:
- `cohort_id` (unique): `cohort_id`, `paper_account_id`
- `idx_paper_certification_members_account` (non-unique): `paper_account_id`, `cohort_id`
- `PRIMARY` (unique): `id`

## `paper_constraint_decisions`

| Column | Type | Null | Key | Default | Extra |
| --- | --- | --- | --- | --- | --- |
| `id` | `varchar(64)` | NO | PRI |  |  |
| `intent_id` | `varchar(64)` | NO | UNI |  |  |
| `decision` | `varchar(16)` | NO |  |  |  |
| `constraint_version` | `varchar(64)` | NO |  |  |  |
| `rule_code` | `varchar(64)` | YES |  |  |  |
| `rule_inputs_json` | `longtext` | NO |  |  |  |
| `portfolio_snapshot_json` | `longtext` | NO |  |  |  |
| `reference_data_version` | `varchar(255)` | NO |  |  |  |
| `rules_json` | `longtext` | NO |  |  |  |
| `decision_digest` | `varchar(64)` | NO | UNI |  |  |
| `decision_timestamp` | `varchar(64)` | NO |  |  |  |

Indexes:
- `decision_digest` (unique): `decision_digest`
- `idx_paper_constraint_intent` (non-unique): `intent_id`, `decision`
- `intent_id` (unique): `intent_id`
- `PRIMARY` (unique): `id`

## `paper_daily_job_events`

| Column | Type | Null | Key | Default | Extra |
| --- | --- | --- | --- | --- | --- |
| `id` | `varchar(64)` | NO | PRI |  |  |
| `job_id` | `varchar(64)` | NO | MUL |  |  |
| `sequence` | `int` | NO |  |  |  |
| `from_state` | `varchar(48)` | YES |  |  |  |
| `to_state` | `varchar(48)` | NO |  |  |  |
| `event_type` | `varchar(64)` | NO |  |  |  |
| `payload_json` | `longtext` | NO |  |  |  |
| `correlation_id` | `varchar(128)` | NO |  |  |  |
| `created_at` | `varchar(64)` | NO |  |  |  |

Indexes:
- `idx_paper_daily_job_events_job` (non-unique): `job_id`, `sequence`
- `job_id` (unique): `job_id`, `sequence`
- `PRIMARY` (unique): `id`

## `paper_daily_jobs`

| Column | Type | Null | Key | Default | Extra |
| --- | --- | --- | --- | --- | --- |
| `id` | `varchar(64)` | NO | PRI |  |  |
| `session_id` | `varchar(64)` | NO | MUL |  |  |
| `trade_date` | `varchar(32)` | NO |  |  |  |
| `state` | `varchar(48)` | NO | MUL |  |  |
| `attempt` | `int` | NO |  | 0 |  |
| `max_attempts` | `int` | NO |  | 3 |  |
| `version` | `int` | NO |  | 1 |  |
| `paper_run_id` | `varchar(64)` | YES |  |  |  |
| `task_id` | `varchar(64)` | YES |  |  |  |
| `lease_holder` | `varchar(128)` | YES |  |  |  |
| `lease_expires_at` | `varchar(64)` | YES |  |  |  |
| `completion_marker` | `varchar(128)` | YES | UNI |  |  |
| `correlation_id` | `varchar(128)` | NO |  |  |  |
| `last_error` | `longtext` | YES |  |  |  |
| `scheduled_at` | `varchar(64)` | NO |  |  |  |
| `started_at` | `varchar(64)` | YES |  |  |  |
| `completed_at` | `varchar(64)` | YES |  |  |  |
| `updated_at` | `varchar(64)` | NO |  |  |  |
| `quarantined_at` | `varchar(64)` | YES |  |  |  |
| `quarantine_reason` | `varchar(255)` | YES |  |  |  |

Indexes:
- `completion_marker` (unique): `completion_marker`
- `idx_paper_daily_jobs_session_date` (non-unique): `session_id`, `trade_date`
- `idx_paper_daily_jobs_state_date` (non-unique): `state`, `trade_date`, `scheduled_at`
- `PRIMARY` (unique): `id`
- `session_id` (unique): `session_id`, `trade_date`

## `paper_daily_reports`

| Column | Type | Null | Key | Default | Extra |
| --- | --- | --- | --- | --- | --- |
| `id` | `varchar(64)` | NO | PRI |  |  |
| `session_id` | `varchar(64)` | NO | MUL |  |  |
| `trade_date` | `varchar(32)` | NO |  |  |  |
| `report_json` | `longtext` | NO |  |  |  |
| `signals_json` | `longtext` | NO |  |  |  |
| `orders_json` | `longtext` | NO |  |  |  |
| `trades_json` | `longtext` | NO |  |  |  |
| `rejects_json` | `longtext` | NO |  |  |  |
| `positions_json` | `longtext` | NO |  |  |  |
| `snapshot_json` | `longtext` | NO |  |  |  |
| `benchmark_json` | `longtext` | NO |  |  |  |
| `qa_json` | `longtext` | NO |  |  |  |
| `created_at` | `varchar(32)` | NO |  |  |  |

Indexes:
- `idx_paper_reports_session_date` (non-unique): `session_id`, `trade_date`
- `PRIMARY` (unique): `id`
- `session_id` (unique): `session_id`, `trade_date`

## `paper_execution_cycle_events`

| Column | Type | Null | Key | Default | Extra |
| --- | --- | --- | --- | --- | --- |
| `id` | `varchar(64)` | NO | PRI |  |  |
| `cycle_id` | `varchar(64)` | NO | MUL |  |  |
| `sequence` | `int` | NO |  |  |  |
| `from_status` | `varchar(48)` | YES |  |  |  |
| `to_status` | `varchar(48)` | NO |  |  |  |
| `event_type` | `varchar(64)` | NO |  |  |  |
| `payload_json` | `longtext` | NO |  |  |  |
| `created_at` | `varchar(64)` | NO |  |  |  |

Indexes:
- `cycle_id` (unique): `cycle_id`, `sequence`
- `PRIMARY` (unique): `id`

## `paper_execution_cycles`

| Column | Type | Null | Key | Default | Extra |
| --- | --- | --- | --- | --- | --- |
| `id` | `varchar(64)` | NO | PRI |  |  |
| `paper_account_id` | `varchar(64)` | NO | MUL |  |  |
| `account_generation` | `int` | NO |  |  |  |
| `deployment_id` | `varchar(64)` | NO | MUL |  |  |
| `trading_date` | `varchar(32)` | NO |  |  |  |
| `scheduled_at` | `varchar(64)` | NO |  |  |  |
| `started_at` | `varchar(64)` | YES |  |  |  |
| `finished_at` | `varchar(64)` | YES |  |  |  |
| `status` | `varchar(48)` | NO | MUL |  |  |
| `attempt` | `int` | NO |  | 0 |  |
| `idempotency_key` | `varchar(255)` | NO | UNI |  |  |
| `input_fingerprint` | `varchar(128)` | NO |  |  |  |
| `account_checkpoint_digest` | `varchar(128)` | NO |  |  |  |
| `strategy_fingerprint` | `varchar(128)` | NO |  |  |  |
| `dataset_fingerprint` | `varchar(128)` | NO |  |  |  |
| `result_digest` | `varchar(128)` | YES |  |  |  |
| `signal_count` | `int` | NO |  | 0 |  |
| `intent_count` | `int` | NO |  | 0 |  |
| `order_count` | `int` | NO |  | 0 |  |
| `fill_count` | `int` | NO |  | 0 |  |
| `rejected_count` | `int` | NO |  | 0 |  |
| `skip_reason` | `varchar(128)` | YES |  |  |  |
| `failure_code` | `varchar(128)` | YES |  |  |  |
| `failure_detail` | `longtext` | YES |  |  |  |
| `lean_run_id` | `varchar(128)` | YES |  |  |  |
| `paper_run_id` | `varchar(64)` | YES |  |  |  |
| `daily_report_id` | `varchar(64)` | YES |  |  |  |
| `lease_holder` | `varchar(128)` | YES |  |  |  |
| `lease_expires_at` | `varchar(64)` | YES |  |  |  |
| `version` | `int` | NO |  | 1 |  |
| `created_at` | `varchar(64)` | NO |  |  |  |
| `updated_at` | `varchar(64)` | NO |  |  |  |

Indexes:
- `deployment_id` (unique): `deployment_id`, `trading_date`
- `idempotency_key` (unique): `idempotency_key`
- `idx_paper_cycles_account_date` (non-unique): `paper_account_id`, `trading_date`, `status`
- `idx_paper_cycles_due` (non-unique): `status`, `scheduled_at`, `trading_date`
- `PRIMARY` (unique): `id`

## `paper_lean_order_events`

| Column | Type | Null | Key | Default | Extra |
| --- | --- | --- | --- | --- | --- |
| `id` | `varchar(64)` | NO | PRI |  |  |
| `session_id` | `varchar(64)` | NO | MUL |  |  |
| `paper_run_id` | `varchar(64)` | NO |  |  |  |
| `backtest_run_id` | `varchar(64)` | NO |  |  |  |
| `event_key` | `varchar(255)` | NO |  |  |  |
| `trade_date` | `varchar(32)` | NO |  |  |  |
| `event_json` | `longtext` | NO |  |  |  |
| `created_at` | `varchar(32)` | NO |  |  |  |

Indexes:
- `idx_paper_lean_events_session_date` (non-unique): `session_id`, `trade_date`
- `PRIMARY` (unique): `id`
- `session_id` (unique): `session_id`, `event_key`

## `paper_ledger_entries`

| Column | Type | Null | Key | Default | Extra |
| --- | --- | --- | --- | --- | --- |
| `id` | `varchar(64)` | NO | PRI |  |  |
| `session_id` | `varchar(64)` | NO | MUL |  |  |
| `intent_id` | `varchar(64)` | NO |  |  |  |
| `fill_id` | `varchar(64)` | YES |  |  |  |
| `entry_type` | `varchar(32)` | NO |  |  |  |
| `asset` | `varchar(32)` | NO |  |  |  |
| `symbol` | `varchar(64)` | YES |  |  |  |
| `quantity` | `double` | NO |  | 0 |  |
| `amount` | `double` | NO |  | 0 |  |
| `currency` | `varchar(16)` | NO |  |  |  |
| `idempotency_key` | `varchar(255)` | NO |  |  |  |
| `created_at` | `varchar(64)` | NO |  |  |  |
| `event_id` | `varchar(64)` | YES |  |  |  |
| `trade_date` | `varchar(32)` | YES |  |  |  |
| `debit_account` | `varchar(128)` | YES |  |  |  |
| `credit_account` | `varchar(128)` | YES |  |  |  |
| `correction_entry_id` | `varchar(64)` | YES |  |  |  |
| `reversal_entry_id` | `varchar(64)` | YES |  |  |  |
| `paper_account_id` | `varchar(64)` | YES | MUL |  |  |
| `account_generation` | `int` | YES |  |  |  |
| `execution_cycle_id` | `varchar(64)` | YES |  |  |  |
| `ledger_sequence` | `int` | YES |  |  |  |
| `precise_quantity` | `decimal(28,8)` | YES |  |  |  |
| `precise_amount` | `decimal(28,8)` | YES |  |  |  |

Indexes:
- `idx_paper_account_ledger_sequence` (non-unique): `paper_account_id`, `account_generation`, `ledger_sequence`
- `idx_paper_ledger_session_created` (non-unique): `session_id`, `created_at`
- `idx_paper_ledger_trade_date` (non-unique): `session_id`, `trade_date`, `entry_type`
- `PRIMARY` (unique): `id`
- `session_id` (unique): `session_id`, `idempotency_key`
- `uq_paper_account_ledger_sequence` (unique): `paper_account_id`, `account_generation`, `ledger_sequence`

## `paper_notification_outbox`

| Column | Type | Null | Key | Default | Extra |
| --- | --- | --- | --- | --- | --- |
| `id` | `varchar(64)` | NO | PRI |  |  |
| `paper_account_id` | `varchar(64)` | NO | MUL |  |  |
| `deployment_id` | `varchar(64)` | YES |  |  |  |
| `cycle_id` | `varchar(64)` | YES |  |  |  |
| `event_type` | `varchar(64)` | NO |  |  |  |
| `dedupe_key` | `varchar(255)` | NO | UNI |  |  |
| `payload_json` | `longtext` | NO |  |  |  |
| `status` | `varchar(32)` | NO | MUL |  |  |
| `attempt` | `int` | NO |  | 0 |  |
| `next_attempt_at` | `varchar(64)` | YES |  |  |  |
| `delivered_at` | `varchar(64)` | YES |  |  |  |
| `last_error` | `longtext` | YES |  |  |  |
| `created_at` | `varchar(64)` | NO |  |  |  |
| `updated_at` | `varchar(64)` | NO |  |  |  |
| `terminal_at` | `varchar(64)` | YES |  |  |  |

Indexes:
- `dedupe_key` (unique): `dedupe_key`
- `idx_paper_outbox_delivery` (non-unique): `status`, `next_attempt_at`, `created_at`
- `idx_paper_outbox_terminal` (non-unique): `status`, `next_attempt_at`, `attempt`
- `paper_account_id` (non-unique): `paper_account_id`
- `PRIMARY` (unique): `id`

## `paper_order_fills`

| Column | Type | Null | Key | Default | Extra |
| --- | --- | --- | --- | --- | --- |
| `id` | `varchar(64)` | NO | PRI |  |  |
| `intent_id` | `varchar(64)` | NO | MUL |  |  |
| `external_fill_key` | `varchar(255)` | NO |  |  |  |
| `trade_date` | `varchar(32)` | NO |  |  |  |
| `quantity` | `double` | NO |  |  |  |
| `price` | `double` | NO |  |  |  |
| `fee` | `double` | NO |  | 0 |  |
| `payload_json` | `longtext` | NO |  |  |  |
| `created_at` | `varchar(64)` | NO |  |  |  |
| `tax` | `double` | NO |  | 0 |  |
| `slippage` | `double` | NO |  | 0 |  |
| `fee_model_version` | `varchar(64)` | YES |  |  |  |
| `matching_contract` | `varchar(64)` | YES |  |  |  |
| `fill_fingerprint` | `varchar(64)` | YES | UNI |  |  |
| `paper_account_id` | `varchar(64)` | YES | MUL |  |  |
| `execution_cycle_id` | `varchar(64)` | YES |  |  |  |
| `precise_quantity` | `decimal(28,8)` | YES |  |  |  |
| `precise_price` | `decimal(28,8)` | YES |  |  |  |
| `commission` | `decimal(28,8)` | YES |  |  |  |
| `stamp_duty` | `decimal(28,8)` | YES |  |  |  |
| `transfer_fee` | `decimal(28,8)` | YES |  |  |  |
| `precise_slippage` | `decimal(28,8)` | YES |  |  |  |

Indexes:
- `idx_paper_account_fills` (non-unique): `paper_account_id`, `execution_cycle_id`
- `idx_paper_fills_fingerprint` (unique): `fill_fingerprint`
- `idx_paper_fills_intent` (non-unique): `intent_id`
- `intent_id` (unique): `intent_id`, `external_fill_key`
- `PRIMARY` (unique): `id`

## `paper_order_intents`

| Column | Type | Null | Key | Default | Extra |
| --- | --- | --- | --- | --- | --- |
| `id` | `varchar(64)` | NO | PRI |  |  |
| `session_id` | `varchar(64)` | NO | MUL |  |  |
| `paper_run_id` | `varchar(64)` | NO |  |  |  |
| `backtest_run_id` | `varchar(128)` | NO |  |  |  |
| `event_key` | `varchar(128)` | NO |  |  |  |
| `idempotency_key` | `varchar(255)` | NO |  |  |  |
| `correlation_id` | `varchar(128)` | NO |  |  |  |
| `version` | `int` | NO |  | 1 |  |
| `attempt` | `int` | NO |  | 1 |  |
| `trade_date` | `varchar(32)` | NO |  |  |  |
| `symbol` | `varchar(64)` | NO |  |  |  |
| `side` | `varchar(16)` | NO |  |  |  |
| `quantity` | `double` | NO |  |  |  |
| `requested_price` | `double` | YES |  |  |  |
| `raw_intent_json` | `longtext` | NO |  |  |  |
| `created_at` | `varchar(64)` | NO |  |  |  |
| `lean_run_id` | `varchar(128)` | YES |  |  |  |
| `lean_order_id` | `varchar(128)` | YES |  |  |  |
| `project_snapshot_id` | `varchar(128)` | YES |  |  |  |
| `project_snapshot_hash` | `varchar(128)` | YES |  |  |  |
| `strategy_fingerprint` | `varchar(128)` | YES |  |  |  |
| `order_type` | `varchar(32)` | YES |  |  |  |
| `limit_price` | `double` | YES |  |  |  |
| `stop_price` | `double` | YES |  |  |  |
| `signal_time` | `varchar(64)` | YES |  |  |  |
| `requested_execution_time` | `varchar(64)` | YES |  |  |  |
| `dataset_version` | `varchar(255)` | YES |  |  |  |
| `universe_version` | `varchar(255)` | YES |  |  |  |
| `constraint_version` | `varchar(64)` | YES |  |  |  |
| `paper_account_id` | `varchar(64)` | YES |  |  |  |
| `deployment_id` | `varchar(64)` | YES |  |  |  |
| `execution_cycle_id` | `varchar(64)` | YES |  |  |  |
| `account_generation` | `int` | YES |  |  |  |
| `precise_quantity` | `decimal(28,8)` | YES |  |  |  |
| `precise_requested_price` | `decimal(28,8)` | YES |  |  |  |

Indexes:
- `idx_paper_intents_session_date` (non-unique): `session_id`, `trade_date`
- `PRIMARY` (unique): `id`
- `session_id` (unique): `session_id`, `idempotency_key`
- `session_id_2` (unique): `session_id`, `event_key`

## `paper_order_transitions`

| Column | Type | Null | Key | Default | Extra |
| --- | --- | --- | --- | --- | --- |
| `id` | `varchar(64)` | NO | PRI |  |  |
| `intent_id` | `varchar(64)` | NO | MUL |  |  |
| `sequence` | `int` | NO |  |  |  |
| `from_state` | `varchar(32)` | YES |  |  |  |
| `to_state` | `varchar(32)` | NO |  |  |  |
| `event_type` | `varchar(64)` | NO |  |  |  |
| `idempotency_key` | `varchar(255)` | NO |  |  |  |
| `correlation_id` | `varchar(128)` | NO |  |  |  |
| `version` | `int` | NO |  | 1 |  |
| `attempt` | `int` | NO |  | 1 |  |
| `payload_json` | `longtext` | NO |  |  |  |
| `created_at` | `varchar(64)` | NO |  |  |  |

Indexes:
- `idx_paper_transitions_intent_sequence` (non-unique): `intent_id`, `sequence`
- `intent_id` (unique): `intent_id`, `sequence`
- `intent_id_2` (unique): `intent_id`, `idempotency_key`
- `PRIMARY` (unique): `id`

## `paper_orders`

| Column | Type | Null | Key | Default | Extra |
| --- | --- | --- | --- | --- | --- |
| `id` | `varchar(64)` | NO | PRI |  |  |
| `session_id` | `varchar(64)` | NO | MUL |  |  |
| `signal_id` | `varchar(64)` | YES |  |  |  |
| `trade_date` | `varchar(32)` | NO |  |  |  |
| `symbol` | `varchar(96)` | NO |  |  |  |
| `side` | `varchar(96)` | NO |  |  |  |
| `quantity` | `double` | NO |  |  |  |
| `order_price` | `double` | YES |  |  |  |
| `fill_price` | `double` | YES |  |  |  |
| `fee` | `double` | NO |  | 0 |  |
| `status` | `varchar(96)` | NO |  |  |  |
| `reason` | `varchar(255)` | YES |  |  |  |
| `created_at` | `varchar(32)` | NO |  |  |  |
| `filled_at` | `varchar(32)` | YES |  |  |  |

Indexes:
- `idx_paper_orders_session_date` (non-unique): `session_id`, `trade_date`
- `PRIMARY` (unique): `id`

## `paper_portfolio_snapshots`

| Column | Type | Null | Key | Default | Extra |
| --- | --- | --- | --- | --- | --- |
| `id` | `varchar(64)` | NO | PRI |  |  |
| `session_id` | `varchar(64)` | NO | MUL |  |  |
| `trade_date` | `varchar(32)` | NO |  |  |  |
| `cash` | `double` | NO |  |  |  |
| `market_value` | `double` | NO |  |  |  |
| `equity` | `double` | NO |  |  |  |
| `positions_json` | `longtext` | NO |  |  |  |
| `created_at` | `varchar(32)` | NO |  |  |  |
| `benchmark_symbol` | `varchar(255)` | YES |  |  |  |
| `benchmark_close` | `double` | YES |  |  |  |
| `benchmark_return` | `double` | YES |  |  |  |

Indexes:
- `idx_paper_snapshots_session_date` (non-unique): `session_id`, `trade_date`
- `PRIMARY` (unique): `id`
- `session_id` (unique): `session_id`, `trade_date`

## `paper_positions`

| Column | Type | Null | Key | Default | Extra |
| --- | --- | --- | --- | --- | --- |
| `session_id` | `varchar(64)` | NO | PRI |  |  |
| `symbol` | `varchar(96)` | NO | PRI |  |  |
| `quantity` | `double` | NO |  |  |  |
| `average_price` | `double` | NO |  |  |  |
| `market_price` | `double` | YES |  |  |  |
| `market_value` | `double` | YES |  |  |  |
| `last_buy_date` | `varchar(32)` | YES |  |  |  |
| `updated_at` | `varchar(32)` | NO |  |  |  |

Indexes:
- `PRIMARY` (unique): `session_id`, `symbol`

## `paper_reconciliation_records`

| Column | Type | Null | Key | Default | Extra |
| --- | --- | --- | --- | --- | --- |
| `id` | `varchar(64)` | NO | PRI |  |  |
| `session_id` | `varchar(64)` | NO | MUL |  |  |
| `paper_run_id` | `varchar(64)` | NO | UNI |  |  |
| `trade_date` | `varchar(32)` | NO |  |  |  |
| `status` | `varchar(32)` | NO |  |  |  |
| `opening_cash` | `double` | NO |  |  |  |
| `ledger_cash_movement` | `double` | NO |  |  |  |
| `closing_cash` | `double` | NO |  |  |  |
| `cash_drift` | `double` | NO |  |  |  |
| `position_drift` | `double` | NO |  |  |  |
| `order_fill_ok` | `int` | NO |  |  |  |
| `fill_ledger_ok` | `int` | NO |  |  |  |
| `ledger_cash_ok` | `int` | NO |  |  |  |
| `ledger_positions_ok` | `int` | NO |  |  |  |
| `snapshot_ok` | `int` | NO |  |  |  |
| `daily_report_ok` | `int` | NO |  |  |  |
| `invariants_json` | `longtext` | NO |  |  |  |
| `result_digest` | `varchar(64)` | NO | UNI |  |  |
| `created_at` | `varchar(64)` | NO |  |  |  |
| `quarantined_at` | `varchar(64)` | YES |  |  |  |
| `quarantine_reason` | `varchar(255)` | YES |  |  |  |

Indexes:
- `idx_paper_reconciliation_session_date` (non-unique): `session_id`, `trade_date`, `status`
- `paper_run_id` (unique): `paper_run_id`
- `PRIMARY` (unique): `id`
- `result_digest` (unique): `result_digest`
- `session_id` (unique): `session_id`, `trade_date`

## `paper_risk_profiles`

| Column | Type | Null | Key | Default | Extra |
| --- | --- | --- | --- | --- | --- |
| `id` | `varchar(64)` | NO | PRI |  |  |
| `paper_account_id` | `varchar(64)` | NO | MUL |  |  |
| `version` | `int` | NO |  |  |  |
| `status` | `varchar(32)` | NO |  |  |  |
| `max_positions` | `int` | YES |  |  |  |
| `max_position_weight` | `decimal(20,12)` | YES |  |  |  |
| `cash_floor` | `decimal(28,8)` | YES |  |  |  |
| `max_order_amount` | `decimal(28,8)` | YES |  |  |  |
| `max_daily_turnover` | `decimal(20,12)` | YES |  |  |  |
| `config_json` | `longtext` | NO |  |  |  |
| `config_fingerprint` | `varchar(128)` | NO | UNI |  |  |
| `created_at` | `varchar(64)` | NO |  |  |  |
| `superseded_at` | `varchar(64)` | YES |  |  |  |

Indexes:
- `config_fingerprint` (unique): `config_fingerprint`
- `paper_account_id` (unique): `paper_account_id`, `version`
- `PRIMARY` (unique): `id`

## `paper_run_checkpoints`

| Column | Type | Null | Key | Default | Extra |
| --- | --- | --- | --- | --- | --- |
| `id` | `varchar(64)` | NO | PRI |  |  |
| `paper_run_id` | `varchar(64)` | NO | MUL |  |  |
| `phase` | `varchar(64)` | NO |  |  |  |
| `status` | `varchar(32)` | NO |  |  |  |
| `digest` | `varchar(128)` | YES |  |  |  |
| `payload_json` | `longtext` | NO |  |  |  |
| `created_at` | `varchar(64)` | NO |  |  |  |
| `completed_at` | `varchar(64)` | YES |  |  |  |

Indexes:
- `idx_paper_checkpoints_run` (non-unique): `paper_run_id`, `phase`
- `paper_run_id` (unique): `paper_run_id`, `phase`
- `PRIMARY` (unique): `id`

## `paper_sessions`

| Column | Type | Null | Key | Default | Extra |
| --- | --- | --- | --- | --- | --- |
| `id` | `varchar(64)` | NO | PRI |  |  |
| `project_id` | `varchar(64)` | YES |  |  |  |
| `name` | `varchar(255)` | NO |  |  |  |
| `status` | `varchar(96)` | NO |  |  |  |
| `symbol` | `varchar(96)` | NO |  |  |  |
| `asset_class` | `varchar(96)` | NO |  |  |  |
| `venue` | `varchar(96)` | NO |  |  |  |
| `resolution` | `varchar(96)` | NO |  |  |  |
| `cash` | `double` | NO |  |  |  |
| `equity` | `double` | NO |  |  |  |
| `parameters_json` | `longtext` | NO |  |  |  |
| `created_at` | `varchar(32)` | NO | MUL |  |  |
| `updated_at` | `varchar(32)` | NO |  |  |  |
| `finished_at` | `varchar(32)` | YES |  |  |  |
| `mode` | `varchar(255)` | NO |  | legacy_replay |  |
| `legacy_read_only` | `int` | NO |  | 1 |  |
| `source_backtest_id` | `varchar(64)` | YES |  |  |  |
| `strategy_version_id` | `varchar(64)` | YES |  |  |  |
| `parameter_hash` | `varchar(128)` | YES |  |  |  |
| `start_date` | `varchar(32)` | YES |  |  |  |
| `last_processed_date` | `varchar(32)` | YES |  |  |  |
| `auto_advance` | `int` | NO |  | 0 |  |
| `failure_json` | `longtext` | YES |  |  |  |
| `pipeline_version` | `int` | NO |  | 1 |  |

Indexes:
- `idx_paper_sessions_created_at` (non-unique): `created_at`
- `PRIMARY` (unique): `id`

## `paper_signals`

| Column | Type | Null | Key | Default | Extra |
| --- | --- | --- | --- | --- | --- |
| `id` | `varchar(64)` | NO | PRI |  |  |
| `session_id` | `varchar(64)` | NO | MUL |  |  |
| `trade_date` | `varchar(32)` | NO |  |  |  |
| `symbol` | `varchar(96)` | NO |  |  |  |
| `side` | `varchar(96)` | NO |  |  |  |
| `target_percent` | `double` | YES |  |  |  |
| `strength` | `double` | YES |  |  |  |
| `reason` | `varchar(255)` | YES |  |  |  |
| `status` | `varchar(96)` | NO |  |  |  |
| `source` | `varchar(96)` | NO |  |  |  |
| `created_at` | `varchar(32)` | NO |  |  |  |

Indexes:
- `idx_paper_signals_session_date` (non-unique): `session_id`, `trade_date`
- `PRIMARY` (unique): `id`

## `paper_strategy_deployments`

| Column | Type | Null | Key | Default | Extra |
| --- | --- | --- | --- | --- | --- |
| `id` | `varchar(64)` | NO | PRI |  |  |
| `paper_account_id` | `varchar(64)` | NO | MUL |  |  |
| `generation` | `int` | NO |  |  |  |
| `supersedes_deployment_id` | `varchar(64)` | YES |  |  |  |
| `version` | `int` | NO |  |  |  |
| `name` | `varchar(191)` | NO |  |  |  |
| `status` | `varchar(32)` | NO |  |  |  |
| `is_primary` | `int` | NO |  | 0 |  |
| `project_id` | `varchar(64)` | NO |  |  |  |
| `source_backtest_id` | `varchar(64)` | NO |  |  |  |
| `strategy_version_id` | `varchar(128)` | YES |  |  |  |
| `project_snapshot_id` | `varchar(128)` | NO |  |  |  |
| `dataset_version_id` | `varchar(255)` | NO |  |  |  |
| `experiment_version_id` | `varchar(128)` | YES |  |  |  |
| `schedule_type` | `varchar(32)` | NO |  |  |  |
| `schedule_expression` | `varchar(128)` | NO |  |  |  |
| `market_timezone` | `varchar(64)` | NO |  |  |  |
| `run_after_market_close` | `int` | NO |  | 1 |  |
| `execution_timing` | `varchar(32)` | NO |  |  |  |
| `signal_mode` | `varchar(32)` | NO |  |  |  |
| `parameters_json` | `longtext` | NO |  |  |  |
| `universe_config_json` | `longtext` | NO |  |  |  |
| `risk_config_version` | `int` | NO |  |  |  |
| `strategy_fingerprint` | `varchar(128)` | NO |  |  |  |
| `dataset_fingerprint` | `varchar(128)` | NO |  |  |  |
| `deployment_fingerprint` | `varchar(128)` | NO | UNI |  |  |
| `last_successful_trading_date` | `varchar(32)` | YES |  |  |  |
| `next_scheduled_at` | `varchar(64)` | YES |  |  |  |
| `consecutive_failures` | `int` | NO |  | 0 |  |
| `created_at` | `varchar(64)` | NO |  |  |  |
| `updated_at` | `varchar(64)` | NO |  |  |  |
| `paused_at` | `varchar(64)` | YES |  |  |  |
| `disabled_at` | `varchar(64)` | YES |  |  |  |

Indexes:
- `deployment_fingerprint` (unique): `deployment_fingerprint`
- `idx_paper_deployments_account_status` (non-unique): `paper_account_id`, `status`, `is_primary`
- `paper_account_id` (unique): `paper_account_id`, `version`
- `PRIMARY` (unique): `id`

## `paper_strategy_signals`

| Column | Type | Null | Key | Default | Extra |
| --- | --- | --- | --- | --- | --- |
| `id` | `varchar(64)` | NO | PRI |  |  |
| `paper_account_id` | `varchar(64)` | NO | MUL |  |  |
| `deployment_id` | `varchar(64)` | NO | MUL |  |  |
| `cycle_id` | `varchar(64)` | NO | MUL |  |  |
| `signal_key` | `varchar(255)` | NO |  |  |  |
| `signal_type` | `varchar(32)` | NO |  |  |  |
| `symbol` | `varchar(64)` | YES |  |  |  |
| `signal_timestamp` | `varchar(64)` | NO |  |  |  |
| `intended_execution_date` | `varchar(32)` | YES |  |  |  |
| `target_quantity` | `decimal(28,8)` | YES |  |  |  |
| `target_weight` | `decimal(20,12)` | YES |  |  |  |
| `previous_quantity` | `decimal(28,8)` | YES |  |  |  |
| `previous_weight` | `decimal(20,12)` | YES |  |  |  |
| `confidence` | `decimal(20,12)` | YES |  |  |  |
| `evidence_json` | `longtext` | NO |  |  |  |
| `disposition` | `varchar(64)` | NO |  |  |  |
| `no_trade_reason` | `varchar(128)` | YES |  |  |  |
| `intent_id` | `varchar(64)` | YES |  |  |  |
| `constraint_decision_id` | `varchar(64)` | YES |  |  |  |
| `lean_run_id` | `varchar(128)` | YES |  |  |  |
| `data_timestamp` | `varchar(64)` | YES |  |  |  |
| `created_at` | `varchar(64)` | NO |  |  |  |

Indexes:
- `cycle_id` (non-unique): `cycle_id`
- `deployment_id` (unique): `deployment_id`, `signal_key`
- `idx_paper_signals_account_time` (non-unique): `paper_account_id`, `signal_timestamp`, `disposition`
- `PRIMARY` (unique): `id`

## `paper_universe_certifications`

| Column | Type | Null | Key | Default | Extra |
| --- | --- | --- | --- | --- | --- |
| `id` | `varchar(64)` | NO | PRI |  |  |
| `universe_code` | `varchar(96)` | NO | MUL |  |  |
| `source` | `varchar(96)` | NO |  |  |  |
| `benchmark_symbol` | `varchar(255)` | NO |  |  |  |
| `certification_status` | `varchar(255)` | NO |  |  |  |
| `certification_date` | `varchar(32)` | NO |  |  |  |
| `start_date` | `varchar(32)` | NO |  |  |  |
| `end_date` | `varchar(32)` | NO |  |  |  |
| `target_size` | `int` | NO |  |  |  |
| `min_size` | `int` | NO |  |  |  |
| `symbol_count` | `int` | NO |  | 0 |  |
| `coverage_report_id` | `varchar(64)` | YES |  |  |  |
| `qa_report_id` | `varchar(64)` | YES |  |  |  |
| `valid_from` | `varchar(255)` | NO |  |  |  |
| `valid_to` | `varchar(255)` | YES |  |  |  |
| `coverage_json` | `longtext` | NO |  |  |  |
| `qa_report_json` | `longtext` | NO |  |  |  |
| `warnings_json` | `longtext` | NO |  |  |  |
| `errors_json` | `longtext` | NO |  |  |  |
| `created_at` | `varchar(32)` | NO |  |  |  |
| `updated_at` | `varchar(32)` | NO |  |  |  |

Indexes:
- `idx_paper_universe_cert_status` (non-unique): `universe_code`, `certification_status`, `certification_date`
- `PRIMARY` (unique): `id`
- `universe_code` (unique): `universe_code`, `source`, `start_date`, `end_date`

## `paper_universe_symbols`

| Column | Type | Null | Key | Default | Extra |
| --- | --- | --- | --- | --- | --- |
| `id` | `varchar(64)` | NO | PRI |  |  |
| `universe_code` | `varchar(96)` | NO | MUL |  |  |
| `symbol` | `varchar(96)` | NO |  |  |  |
| `source` | `varchar(96)` | NO |  |  |  |
| `certification_status` | `varchar(255)` | NO |  |  |  |
| `certification_date` | `varchar(32)` | NO |  |  |  |
| `coverage_report_id` | `varchar(64)` | YES |  |  |  |
| `qa_report_id` | `varchar(64)` | YES |  |  |  |
| `valid_from` | `varchar(255)` | NO |  |  |  |
| `valid_to` | `varchar(255)` | YES |  |  |  |
| `coverage_json` | `longtext` | NO |  |  |  |
| `qa_json` | `longtext` | NO |  |  |  |
| `warnings_json` | `longtext` | NO |  |  |  |
| `errors_json` | `longtext` | NO |  |  |  |
| `created_at` | `varchar(32)` | NO |  |  |  |
| `updated_at` | `varchar(32)` | NO |  |  |  |

Indexes:
- `idx_paper_universe_symbols_status` (non-unique): `universe_code`, `certification_status`, `symbol`
- `PRIMARY` (unique): `id`
- `universe_code` (unique): `universe_code`, `symbol`, `valid_from`

## `paper_walkforward_runs`

| Column | Type | Null | Key | Default | Extra |
| --- | --- | --- | --- | --- | --- |
| `id` | `varchar(64)` | NO | PRI |  |  |
| `session_id` | `varchar(64)` | NO | MUL |  |  |
| `trade_date` | `varchar(32)` | NO |  |  |  |
| `backtest_run_id` | `varchar(64)` | YES |  |  |  |
| `task_id` | `varchar(64)` | YES |  |  |  |
| `status` | `varchar(96)` | NO |  |  |  |
| `order_fingerprint` | `varchar(255)` | YES |  |  |  |
| `reconciliation_json` | `longtext` | YES |  |  |  |
| `failure_json` | `longtext` | YES |  |  |  |
| `created_at` | `varchar(32)` | NO |  |  |  |
| `started_at` | `varchar(32)` | YES |  |  |  |
| `finished_at` | `varchar(32)` | YES |  |  |  |

Indexes:
- `idx_paper_walkforward_session_date` (non-unique): `session_id`, `trade_date`
- `PRIMARY` (unique): `id`
- `session_id` (unique): `session_id`, `trade_date`

## `parameter_candidates`

| Column | Type | Null | Key | Default | Extra |
| --- | --- | --- | --- | --- | --- |
| `id` | `varchar(64)` | NO | PRI |  |  |
| `window_id` | `varchar(64)` | NO | MUL |  |  |
| `candidate_key` | `varchar(255)` | NO |  |  |  |
| `parameters_json` | `longtext` | NO |  |  |  |
| `train_item_id` | `varchar(64)` | YES |  |  |  |
| `validation_item_id` | `varchar(64)` | YES |  |  |  |
| `validation_return` | `double` | YES |  |  |  |
| `validation_sharpe` | `double` | YES |  |  |  |
| `validation_max_drawdown` | `double` | YES |  |  |  |
| `validation_trade_count` | `int` | YES |  |  |  |
| `validation_turnover` | `double` | YES |  |  |  |
| `constraint_violations` | `int` | NO |  | 0 |  |
| `selected` | `int` | NO |  | 0 |  |
| `not_selected_reason` | `varchar(255)` | YES |  |  |  |
| `created_at` | `varchar(64)` | NO |  |  |  |
| `updated_at` | `varchar(64)` | NO |  |  |  |

Indexes:
- `idx_parameter_candidates_window` (non-unique): `window_id`, `selected`, `candidate_key`
- `PRIMARY` (unique): `id`
- `window_id` (unique): `window_id`, `candidate_key`

## `parameter_selection_events`

| Column | Type | Null | Key | Default | Extra |
| --- | --- | --- | --- | --- | --- |
| `id` | `varchar(64)` | NO | PRI |  |  |
| `window_id` | `varchar(64)` | NO | UNI |  |  |
| `selected_candidate_id` | `varchar(64)` | NO |  |  |  |
| `selection_metric` | `varchar(64)` | NO |  |  |  |
| `tie_break_rule` | `varchar(255)` | NO |  |  |  |
| `selected_parameters_json` | `longtext` | NO |  |  |  |
| `candidate_ranking_json` | `longtext` | NO |  |  |  |
| `selection_timestamp` | `varchar(64)` | NO |  |  |  |
| `selection_fingerprint` | `varchar(64)` | NO | UNI |  |  |

Indexes:
- `idx_parameter_selection_window` (non-unique): `window_id`, `selection_timestamp`
- `PRIMARY` (unique): `id`
- `selection_fingerprint` (unique): `selection_fingerprint`
- `window_id` (unique): `window_id`

## `parquet_datasets`

| Column | Type | Null | Key | Default | Extra |
| --- | --- | --- | --- | --- | --- |
| `id` | `varchar(64)` | NO | PRI |  |  |
| `dataset_key` | `varchar(255)` | NO | UNI |  |  |
| `asset_class` | `varchar(96)` | NO | MUL |  |  |
| `market` | `varchar(96)` | NO |  |  |  |
| `venue` | `varchar(96)` | YES |  |  |  |
| `resolution` | `varchar(96)` | NO |  |  |  |
| `data_type` | `varchar(96)` | NO |  | trade |  |
| `adjust` | `varchar(96)` | NO |  | raw |  |
| `source` | `varchar(96)` | NO |  |  |  |
| `root_path` | `varchar(1024)` | NO |  |  |  |
| `schema_version` | `int` | NO |  | 1 |  |
| `start_date` | `varchar(32)` | YES |  |  |  |
| `end_date` | `varchar(32)` | YES |  |  |  |
| `row_count` | `int` | NO |  | 0 |  |
| `file_count` | `int` | NO |  | 0 |  |
| `metadata_json` | `longtext` | NO |  |  |  |
| `created_at` | `varchar(32)` | NO |  |  |  |
| `updated_at` | `varchar(32)` | NO |  |  |  |
| `dataset_version` | `varchar(96)` | YES |  |  |  |
| `environment` | `varchar(32)` | NO |  | research |  |
| `is_production` | `int` | NO | MUL | 0 |  |
| `is_certified` | `int` | NO |  | 0 |  |
| `certified_at` | `varchar(32)` | YES |  |  |  |
| `certified_by` | `varchar(96)` | YES |  |  |  |
| `coverage_start` | `varchar(32)` | YES |  |  |  |
| `coverage_end` | `varchar(32)` | YES |  |  |  |
| `qa_status` | `varchar(32)` | YES |  |  |  |
| `qa_report_id` | `varchar(64)` | YES |  |  |  |
| `dataset_release_id` | `varchar(96)` | YES | MUL |  |  |

Indexes:
- `dataset_key` (unique): `dataset_key`
- `idx_parquet_datasets_certified_source` (non-unique): `is_production`, `is_certified`, `source`, `asset_class`, `market`, `venue`
- `idx_parquet_datasets_lookup` (non-unique): `asset_class`, `market`, `venue`, `resolution`, `data_type`, `adjust`, `source`
- `idx_parquet_datasets_release` (non-unique): `dataset_release_id`
- `PRIMARY` (unique): `id`

## `parquet_files`

| Column | Type | Null | Key | Default | Extra |
| --- | --- | --- | --- | --- | --- |
| `id` | `varchar(64)` | NO | PRI |  |  |
| `dataset_id` | `varchar(64)` | NO | MUL |  |  |
| `file_path` | `varchar(1024)` | NO |  |  |  |
| `partition_json` | `longtext` | NO |  |  |  |
| `row_count` | `int` | NO |  |  |  |
| `first_timestamp` | `varchar(255)` | YES |  |  |  |
| `last_timestamp` | `varchar(255)` | YES |  |  |  |
| `sha256` | `varchar(255)` | NO |  |  |  |
| `size` | `int` | NO |  |  |  |
| `created_at` | `varchar(32)` | NO |  |  |  |

Indexes:
- `idx_parquet_files_dataset` (non-unique): `dataset_id`, `first_timestamp`, `last_timestamp`
- `PRIMARY` (unique): `id`

## `pipeline_runs`

| Column | Type | Null | Key | Default | Extra |
| --- | --- | --- | --- | --- | --- |
| `id` | `varchar(64)` | NO | PRI |  |  |
| `universe_code` | `varchar(96)` | YES |  |  |  |
| `source` | `varchar(96)` | NO |  |  |  |
| `benchmark_symbol` | `varchar(255)` | YES |  |  |  |
| `status` | `varchar(96)` | NO |  |  |  |
| `severity` | `varchar(96)` | NO |  |  |  |
| `decision` | `varchar(255)` | YES |  |  |  |
| `started_at` | `varchar(32)` | NO | MUL |  |  |
| `finished_at` | `varchar(32)` | YES |  |  |  |
| `duration_seconds` | `double` | YES |  |  |  |
| `artifact_dir` | `varchar(255)` | YES |  |  |  |
| `artifact_object_id` | `varchar(64)` | YES |  |  |  |
| `summary_json` | `longtext` | NO |  |  |  |
| `warnings_json` | `longtext` | NO |  |  |  |
| `errors_json` | `longtext` | NO |  |  |  |

Indexes:
- `idx_pipeline_runs_created` (non-unique): `started_at`, `status`
- `PRIMARY` (unique): `id`

## `pipeline_steps`

| Column | Type | Null | Key | Default | Extra |
| --- | --- | --- | --- | --- | --- |
| `id` | `varchar(64)` | NO | PRI |  |  |
| `run_id` | `varchar(64)` | NO | MUL |  |  |
| `step_name` | `varchar(255)` | NO |  |  |  |
| `status` | `varchar(96)` | NO |  |  |  |
| `started_at` | `varchar(32)` | NO |  |  |  |
| `finished_at` | `varchar(32)` | YES |  |  |  |
| `duration_seconds` | `double` | YES |  |  |  |
| `warnings_json` | `longtext` | NO |  |  |  |
| `errors_json` | `longtext` | NO |  |  |  |
| `details_json` | `longtext` | NO |  |  |  |

Indexes:
- `idx_pipeline_steps_run` (non-unique): `run_id`, `step_name`
- `PRIMARY` (unique): `id`

## `portfolio_optimization_runs`

| Column | Type | Null | Key | Default | Extra |
| --- | --- | --- | --- | --- | --- |
| `id` | `varchar(64)` | NO | PRI |  |  |
| `name` | `varchar(255)` | NO |  |  |  |
| `status` | `varchar(32)` | NO | MUL |  |  |
| `objective` | `varchar(32)` | NO |  |  |  |
| `run_ids_json` | `longtext` | NO |  |  |  |
| `constraints_json` | `longtext` | NO |  |  |  |
| `input_fingerprints_json` | `longtext` | NO |  |  |  |
| `result_json` | `longtext` | YES |  |  |  |
| `base_currency` | `varchar(16)` | YES |  |  |  |
| `resolution` | `varchar(32)` | YES |  |  |  |
| `error` | `longtext` | YES |  |  |  |
| `archived_at` | `varchar(64)` | YES |  |  |  |
| `created_at` | `varchar(64)` | NO | MUL |  |  |
| `started_at` | `varchar(64)` | YES |  |  |  |
| `finished_at` | `varchar(64)` | YES |  |  |  |

Indexes:
- `idx_portfolio_optimization_created` (non-unique): `created_at`
- `idx_portfolio_optimization_status` (non-unique): `status`, `created_at`
- `PRIMARY` (unique): `id`

## `projects`

| Column | Type | Null | Key | Default | Extra |
| --- | --- | --- | --- | --- | --- |
| `id` | `varchar(64)` | NO | PRI |  |  |
| `name` | `varchar(255)` | NO | MUL |  |  |
| `language` | `varchar(255)` | NO |  |  |  |
| `algorithm_class` | `varchar(255)` | NO |  |  |  |
| `project_path` | `varchar(1024)` | NO |  |  |  |
| `main_file` | `varchar(1024)` | NO |  |  |  |
| `config_json` | `longtext` | NO |  |  |  |
| `created_at` | `varchar(32)` | NO |  |  |  |
| `updated_at` | `varchar(32)` | NO |  |  |  |

Indexes:
- `idx_projects_name` (non-unique): `name`
- `PRIMARY` (unique): `id`

## `provider_availability_log`

| Column | Type | Null | Key | Default | Extra |
| --- | --- | --- | --- | --- | --- |
| `id` | `varchar(64)` | NO | PRI |  |  |
| `provider` | `varchar(96)` | NO | MUL |  |  |
| `status` | `varchar(96)` | NO |  |  |  |
| `installed` | `int` | NO |  | 0 |  |
| `configured` | `int` | NO |  | 0 |  |
| `credentials_status` | `varchar(255)` | NO |  |  |  |
| `unavailable_reason` | `varchar(255)` | YES |  |  |  |
| `supported_endpoints_json` | `longtext` | NO |  |  |  |
| `coverage_json` | `longtext` | NO |  |  |  |
| `production_certified` | `int` | NO |  | 0 |  |
| `checked_at` | `varchar(32)` | NO |  |  |  |
| `metadata_json` | `longtext` | NO |  |  |  |

Indexes:
- `idx_provider_availability_checked` (non-unique): `provider`, `checked_at`
- `PRIMARY` (unique): `id`

## `provider_dataset_catalog`

| Column | Type | Null | Key | Default | Extra |
| --- | --- | --- | --- | --- | --- |
| `provider` | `varchar(96)` | NO | PRI |  |  |
| `dataset_key` | `varchar(255)` | NO | PRI |  |  |
| `api_name` | `varchar(255)` | NO |  |  |  |
| `category` | `varchar(255)` | NO |  |  |  |
| `scope_type` | `varchar(255)` | NO |  |  |  |
| `cadence` | `varchar(255)` | NO |  |  |  |
| `permission_status` | `varchar(255)` | NO |  | unknown |  |
| `permission_reason` | `varchar(255)` | YES |  |  |  |
| `row_count` | `int` | NO |  | 0 |  |
| `first_data_date` | `varchar(32)` | YES |  |  |  |
| `last_data_date` | `varchar(32)` | YES |  |  |  |
| `last_checked_at` | `varchar(32)` | YES |  |  |  |
| `last_synced_at` | `varchar(32)` | YES |  |  |  |
| `checkpoint_json` | `longtext` | YES |  |  |  |
| `metadata_json` | `longtext` | YES |  |  |  |
| `sync_policy` | `varchar(255)` | YES |  |  |  |
| `skip_reason` | `varchar(255)` | YES |  |  |  |
| `rate_limit_per_hour` | `int` | YES |  |  |  |
| `next_allowed_at` | `varchar(32)` | YES |  |  |  |

Indexes:
- `PRIMARY` (unique): `provider`, `dataset_key`

## `provider_dataset_watermarks`

| Column | Type | Null | Key | Default | Extra |
| --- | --- | --- | --- | --- | --- |
| `provider` | `varchar(96)` | NO | PRI |  |  |
| `dataset_key` | `varchar(255)` | NO | PRI |  |  |
| `scope_key` | `varchar(255)` | NO | PRI |  |  |
| `coverage_start` | `varchar(255)` | YES |  |  |  |
| `coverage_end` | `varchar(255)` | YES |  |  |  |
| `last_data_date` | `varchar(32)` | YES |  |  |  |
| `last_run_id` | `varchar(64)` | YES | MUL |  |  |
| `empty_result` | `int` | NO |  | 0 |  |
| `validation_status` | `varchar(255)` | NO |  | unknown |  |
| `updated_at` | `varchar(32)` | NO |  |  |  |

Indexes:
- `idx_provider_dataset_watermark_run` (non-unique): `last_run_id`, `dataset_key`
- `PRIMARY` (unique): `provider`, `dataset_key`, `scope_key`

## `provider_ingestion_manifests`

| Column | Type | Null | Key | Default | Extra |
| --- | --- | --- | --- | --- | --- |
| `id` | `varchar(64)` | NO | PRI |  |  |
| `run_id` | `varchar(64)` | NO | MUL |  |  |
| `provider` | `varchar(96)` | NO |  |  |  |
| `dataset_key` | `varchar(255)` | NO |  |  |  |
| `scope_key` | `varchar(255)` | NO |  |  |  |
| `request_json` | `longtext` | NO |  |  |  |
| `response_rows` | `int` | NO |  | 0 |  |
| `normalized_rows` | `int` | NO |  | 0 |  |
| `rejected_rows` | `int` | NO |  | 0 |  |
| `payload_sha256` | `varchar(64)` | NO |  |  |  |
| `keys_sha256` | `varchar(64)` | NO |  |  |  |
| `coverage_start` | `varchar(255)` | YES |  |  |  |
| `coverage_end` | `varchar(255)` | YES |  |  |  |
| `status` | `varchar(96)` | NO |  |  |  |
| `validation_json` | `longtext` | NO |  |  |  |
| `endpoint_counts_json` | `longtext` | NO |  |  |  |
| `created_at` | `varchar(32)` | NO |  |  |  |

Indexes:
- `idx_provider_ingestion_manifest_run` (non-unique): `run_id`, `dataset_key`, `scope_key`
- `PRIMARY` (unique): `id`

## `provider_raw_archive_issues`

| Column | Type | Null | Key | Default | Extra |
| --- | --- | --- | --- | --- | --- |
| `archive_id` | `varchar(64)` | NO | PRI |  |  |
| `provider` | `varchar(96)` | NO |  |  |  |
| `dataset_key` | `varchar(255)` | NO |  |  |  |
| `run_id` | `varchar(64)` | NO | MUL |  |  |
| `object_id` | `varchar(64)` | NO |  |  |  |
| `row_count` | `int` | NO |  |  |  |
| `payload_sha256` | `varchar(64)` | NO |  |  |  |
| `archive_sha256` | `varchar(64)` | NO |  |  |  |
| `uncompressed_size` | `int` | NO |  |  |  |
| `compressed_size` | `int` | NO |  |  |  |
| `compression` | `varchar(255)` | NO |  |  |  |
| `archive_created_at` | `varchar(32)` | NO |  |  |  |
| `issue_code` | `varchar(255)` | NO |  |  |  |
| `detected_at` | `varchar(32)` | NO |  |  |  |
| `status` | `varchar(96)` | NO | MUL | open |  |
| `resolution_code` | `varchar(255)` | YES |  |  |  |
| `resolution_run_id` | `varchar(64)` | YES |  |  |  |
| `resolution_evidence_json` | `longtext` | YES |  |  |  |
| `resolved_at` | `varchar(32)` | YES |  |  |  |

Indexes:
- `idx_provider_raw_archive_issues_run` (non-unique): `run_id`, `dataset_key`, `detected_at`
- `idx_provider_raw_archive_issues_status` (non-unique): `status`, `dataset_key`, `detected_at`
- `PRIMARY` (unique): `archive_id`

## `provider_raw_archives`

| Column | Type | Null | Key | Default | Extra |
| --- | --- | --- | --- | --- | --- |
| `id` | `varchar(64)` | NO | PRI |  |  |
| `provider` | `varchar(96)` | NO | MUL |  |  |
| `dataset_key` | `varchar(255)` | NO |  |  |  |
| `run_id` | `varchar(64)` | NO | MUL |  |  |
| `object_id` | `varchar(64)` | NO | MUL |  |  |
| `row_count` | `int` | NO |  |  |  |
| `payload_sha256` | `varchar(64)` | NO |  |  |  |
| `archive_sha256` | `varchar(64)` | NO |  |  |  |
| `uncompressed_size` | `int` | NO |  |  |  |
| `compressed_size` | `int` | NO |  |  |  |
| `compression` | `varchar(255)` | NO |  |  |  |
| `created_at` | `varchar(32)` | NO |  |  |  |

Indexes:
- `idx_provider_raw_archives_object` (non-unique): `object_id`, `created_at`
- `idx_provider_raw_archives_payload` (non-unique): `provider`, `dataset_key`, `payload_sha256`
- `idx_provider_raw_archives_run` (non-unique): `run_id`, `dataset_key`, `created_at`
- `PRIMARY` (unique): `id`
- `provider` (unique): `provider`, `dataset_key`, `run_id`, `payload_sha256`

## `provider_raw_records`

| Column | Type | Null | Key | Default | Extra |
| --- | --- | --- | --- | --- | --- |
| `provider` | `varchar(96)` | NO | PRI |  |  |
| `dataset_key` | `varchar(255)` | NO | PRI |  |  |
| `record_key` | `varchar(255)` | NO | PRI |  |  |
| `business_date` | `varchar(32)` | YES |  |  |  |
| `instrument_code` | `varchar(255)` | YES |  |  |  |
| `payload_json` | `longtext` | NO |  |  |  |
| `content_sha256` | `varchar(64)` | NO |  |  |  |
| `batch_id` | `varchar(64)` | YES |  |  |  |
| `source_updated_at` | `varchar(32)` | YES |  |  |  |
| `ingested_at` | `varchar(32)` | NO |  |  |  |

Indexes:
- `idx_provider_raw_dataset_date` (non-unique): `provider`, `dataset_key`, `business_date`
- `idx_provider_raw_dataset_instrument_date` (non-unique): `dataset_key`, `instrument_code`, `business_date`
- `PRIMARY` (unique): `provider`, `dataset_key`, `record_key`

## `qa_warning_allowlist`

| Column | Type | Null | Key | Default | Extra |
| --- | --- | --- | --- | --- | --- |
| `id` | `varchar(64)` | NO | PRI |  |  |
| `warning_code` | `varchar(255)` | NO | MUL |  |  |
| `reason` | `varchar(255)` | NO |  |  |  |
| `valid_until` | `varchar(255)` | NO |  |  |  |
| `approved_by` | `varchar(255)` | NO |  |  |  |
| `affected_symbols_json` | `longtext` | NO |  |  |  |
| `scope_json` | `longtext` | NO |  |  |  |
| `status` | `varchar(96)` | NO |  | active |  |
| `created_at` | `varchar(32)` | NO |  |  |  |
| `updated_at` | `varchar(32)` | NO |  |  |  |

Indexes:
- `idx_qa_warning_allowlist_code` (non-unique): `warning_code`, `status`, `valid_until`
- `PRIMARY` (unique): `id`

## `qlib_research_imports`

| Column | Type | Null | Key | Default | Extra |
| --- | --- | --- | --- | --- | --- |
| `id` | `varchar(64)` | NO | PRI |  |  |
| `research_run_id` | `varchar(64)` | NO | UNI |  |  |
| `external_run_id` | `varchar(128)` | NO | UNI |  |  |
| `schema_version` | `varchar(32)` | NO |  |  |  |
| `run_kind` | `varchar(64)` | NO |  |  |  |
| `dataset_fingerprint` | `varchar(128)` | NO | MUL |  |  |
| `model_fingerprint` | `varchar(128)` | NO |  |  |  |
| `manifest_sha256` | `varchar(64)` | NO |  |  |  |
| `manifest_json` | `longtext` | NO |  |  |  |
| `object_keys_json` | `longtext` | NO |  |  |  |
| `created_at` | `varchar(64)` | NO |  |  |  |

Indexes:
- `external_run_id` (unique): `external_run_id`
- `idx_qlib_import_dataset` (non-unique): `dataset_fingerprint`, `created_at`
- `PRIMARY` (unique): `id`
- `research_run_id` (unique): `research_run_id`

## `qlib_signal_snapshots`

| Column | Type | Null | Key | Default | Extra |
| --- | --- | --- | --- | --- | --- |
| `id` | `varchar(64)` | NO | PRI |  |  |
| `import_id` | `varchar(64)` | NO |  |  |  |
| `research_run_id` | `varchar(64)` | NO |  |  |  |
| `model_fingerprint` | `varchar(128)` | NO | MUL |  |  |
| `dataset_fingerprint` | `varchar(128)` | NO |  |  |  |
| `signal_date` | `varchar(16)` | NO |  |  |  |
| `trade_date` | `varchar(16)` | NO | MUL |  |  |
| `targets_sha256` | `varchar(64)` | NO |  |  |  |
| `target_count` | `int` | NO |  |  |  |
| `gross_exposure` | `double` | NO |  |  |  |
| `targets_json` | `longtext` | NO |  |  |  |
| `created_at` | `varchar(64)` | NO |  |  |  |

Indexes:
- `idx_qlib_signal_trade_date` (non-unique): `trade_date`, `created_at`
- `model_fingerprint` (unique): `model_fingerprint`, `dataset_fingerprint`, `signal_date`
- `PRIMARY` (unique): `id`

## `recording_jobs`

| Column | Type | Null | Key | Default | Extra |
| --- | --- | --- | --- | --- | --- |
| `id` | `varchar(64)` | NO | PRI |  |  |
| `name` | `varchar(255)` | NO |  |  |  |
| `asset_class` | `varchar(96)` | NO |  |  |  |
| `market` | `varchar(96)` | NO |  |  |  |
| `venue` | `varchar(96)` | YES |  |  |  |
| `symbols_json` | `longtext` | NO |  |  |  |
| `frequency` | `varchar(96)` | YES |  |  |  |
| `status` | `varchar(96)` | NO |  |  |  |
| `source` | `varchar(96)` | NO |  |  |  |
| `parameters_json` | `longtext` | NO |  |  |  |
| `created_at` | `varchar(32)` | NO |  |  |  |
| `updated_at` | `varchar(32)` | NO |  |  |  |

Indexes:
- `PRIMARY` (unique): `id`

## `recording_status`

| Column | Type | Null | Key | Default | Extra |
| --- | --- | --- | --- | --- | --- |
| `job_id` | `varchar(64)` | NO | PRI |  |  |
| `status` | `varchar(96)` | NO |  |  |  |
| `last_event_at` | `varchar(32)` | YES |  |  |  |
| `last_bar_at` | `varchar(32)` | YES |  |  |  |
| `last_error` | `varchar(255)` | YES |  |  |  |
| `updated_at` | `varchar(32)` | NO |  |  |  |

Indexes:
- `PRIMARY` (unique): `job_id`

## `reports`

| Column | Type | Null | Key | Default | Extra |
| --- | --- | --- | --- | --- | --- |
| `id` | `varchar(64)` | NO | PRI |  |  |
| `task_id` | `varchar(64)` | YES |  |  |  |
| `run_id` | `varchar(64)` | NO | MUL |  |  |
| `status` | `varchar(96)` | NO | MUL |  |  |
| `report_path` | `varchar(1024)` | YES |  |  |  |
| `error` | `longtext` | YES |  |  |  |
| `created_at` | `varchar(32)` | NO |  |  |  |
| `finished_at` | `varchar(32)` | YES |  |  |  |

Indexes:
- `idx_reports_run_created` (non-unique): `run_id`, `created_at`
- `idx_reports_status_created` (non-unique): `status`, `created_at`
- `PRIMARY` (unique): `id`

## `reproducibility_certificates`

| Column | Type | Null | Key | Default | Extra |
| --- | --- | --- | --- | --- | --- |
| `id` | `varchar(96)` | NO | PRI |  |  |
| `run_id` | `varchar(191)` | NO | UNI |  |  |
| `dataset_release_id` | `varchar(96)` | NO | MUL |  |  |
| `input_fingerprint` | `varchar(64)` | NO | MUL |  |  |
| `equivalence_digest` | `varchar(64)` | NO |  |  |  |
| `certificate_sha256` | `varchar(64)` | NO | UNI |  |  |
| `canonical_result_sha256` | `varchar(64)` | NO |  |  |  |
| `orders_sha256` | `varchar(64)` | NO |  |  |  |
| `fills_sha256` | `varchar(64)` | NO |  |  |  |
| `equity_sha256` | `varchar(64)` | NO |  |  |  |
| `artifact_manifest_sha256` | `varchar(64)` | NO |  |  |  |
| `stored_object_id` | `varchar(64)` | YES | MUL |  |  |
| `status` | `varchar(32)` | NO |  |  |  |
| `certificate_json` | `longtext` | NO |  |  |  |
| `created_at` | `varchar(64)` | NO |  |  |  |

Indexes:
- `certificate_sha256` (unique): `certificate_sha256`
- `dataset_release_id` (non-unique): `dataset_release_id`
- `idx_reproducibility_golden_pair` (non-unique): `input_fingerprint`, `equivalence_digest`, `status`, `created_at`
- `PRIMARY` (unique): `id`
- `run_id` (unique): `run_id`
- `stored_object_id` (non-unique): `stored_object_id`

## `research_run_items`

| Column | Type | Null | Key | Default | Extra |
| --- | --- | --- | --- | --- | --- |
| `id` | `varchar(64)` | NO | PRI |  |  |
| `run_id` | `varchar(64)` | NO | MUL |  |  |
| `item_index` | `int` | NO |  |  |  |
| `item_key` | `varchar(255)` | NO |  |  |  |
| `status` | `varchar(96)` | NO |  |  |  |
| `parameters_json` | `longtext` | NO |  |  |  |
| `result_json` | `longtext` | YES |  |  |  |
| `error` | `longtext` | YES |  |  |  |
| `created_at` | `varchar(32)` | NO |  |  |  |
| `started_at` | `varchar(32)` | YES |  |  |  |
| `finished_at` | `varchar(32)` | YES |  |  |  |

Indexes:
- `idx_research_run_items_run` (non-unique): `run_id`, `item_index`
- `PRIMARY` (unique): `id`
- `run_id` (unique): `run_id`, `item_key`

## `research_runs`

| Column | Type | Null | Key | Default | Extra |
| --- | --- | --- | --- | --- | --- |
| `id` | `varchar(64)` | NO | PRI |  |  |
| `task_id` | `varchar(64)` | YES |  |  |  |
| `template_key` | `varchar(255)` | NO |  |  |  |
| `name` | `varchar(255)` | NO |  |  |  |
| `status` | `varchar(96)` | NO | MUL |  |  |
| `scope_json` | `longtext` | NO |  |  |  |
| `parameters_json` | `longtext` | NO |  |  |  |
| `result_json` | `longtext` | YES |  |  |  |
| `summary_json` | `longtext` | YES |  |  |  |
| `data_fingerprint` | `varchar(255)` | YES |  |  |  |
| `source_research_run_id` | `varchar(64)` | YES |  |  |  |
| `error` | `longtext` | YES |  |  |  |
| `cancel_requested` | `int` | NO |  | 0 |  |
| `created_at` | `varchar(32)` | NO | MUL |  |  |
| `started_at` | `varchar(32)` | YES |  |  |  |
| `finished_at` | `varchar(32)` | YES |  |  |  |
| `owner_heartbeat_at` | `varchar(64)` | YES |  |  |  |
| `recovery_reason` | `varchar(255)` | YES |  |  |  |

Indexes:
- `idx_research_runs_created` (non-unique): `created_at`
- `idx_research_runs_status` (non-unique): `status`, `created_at`
- `PRIMARY` (unique): `id`

## `research_sessions`

| Column | Type | Null | Key | Default | Extra |
| --- | --- | --- | --- | --- | --- |
| `id` | `varchar(64)` | NO | PRI |  |  |
| `task_id` | `varchar(64)` | YES |  |  |  |
| `project_id` | `varchar(64)` | YES |  |  |  |
| `status` | `varchar(96)` | NO |  |  |  |
| `port` | `int` | NO |  |  |  |
| `container_id` | `varchar(64)` | YES |  |  |  |
| `url` | `varchar(255)` | YES |  |  |  |
| `log_path` | `varchar(1024)` | YES |  |  |  |
| `error` | `longtext` | YES |  |  |  |
| `created_at` | `varchar(32)` | NO |  |  |  |
| `started_at` | `varchar(32)` | YES |  |  |  |
| `finished_at` | `varchar(32)` | YES |  |  |  |
| `readiness_status` | `varchar(255)` | YES |  |  |  |
| `container_status` | `varchar(255)` | YES |  |  |  |
| `workspace_path` | `varchar(1024)` | YES |  |  |  |
| `last_checked_at` | `varchar(32)` | YES |  |  |  |
| `project_name` | `varchar(255)` | YES |  |  |  |

Indexes:
- `PRIMARY` (unique): `id`

## `research_workspaces`

| Column | Type | Null | Key | Default | Extra |
| --- | --- | --- | --- | --- | --- |
| `id` | `varchar(64)` | NO | PRI |  |  |
| `task_id` | `varchar(64)` | YES |  |  |  |
| `project_id` | `varchar(64)` | YES |  |  |  |
| `status` | `varchar(96)` | NO |  |  |  |
| `port` | `int` | NO |  |  |  |
| `container_id` | `varchar(64)` | YES |  |  |  |
| `url` | `varchar(255)` | YES |  |  |  |
| `log_path` | `varchar(1024)` | YES |  |  |  |
| `error` | `longtext` | YES |  |  |  |
| `created_at` | `varchar(32)` | NO | MUL |  |  |
| `started_at` | `varchar(32)` | YES |  |  |  |
| `finished_at` | `varchar(32)` | YES |  |  |  |
| `readiness_status` | `varchar(255)` | YES |  |  |  |
| `container_status` | `varchar(255)` | YES |  |  |  |
| `workspace_path` | `varchar(1024)` | YES |  |  |  |
| `last_checked_at` | `varchar(32)` | YES |  |  |  |
| `project_name` | `varchar(255)` | YES |  |  |  |
| `snapshot_id` | `varchar(64)` | YES |  |  |  |

Indexes:
- `idx_research_workspaces_created` (non-unique): `created_at`
- `PRIMARY` (unique): `id`

## `restricted_runner_jobs`

| Column | Type | Null | Key | Default | Extra |
| --- | --- | --- | --- | --- | --- |
| `id` | `varchar(64)` | NO | PRI |  |  |
| `run_id` | `varchar(128)` | NO | UNI |  |  |
| `spec_digest` | `varchar(64)` | NO | UNI |  |  |
| `image_digest` | `varchar(255)` | NO |  |  |  |
| `command_json` | `longtext` | NO |  |  |  |
| `mounts_json` | `longtext` | NO |  |  |  |
| `resource_limits_json` | `longtext` | NO |  |  |  |
| `network_policy` | `varchar(32)` | NO |  |  |  |
| `status` | `varchar(32)` | NO | MUL |  |  |
| `exit_code` | `int` | YES |  |  |  |
| `timed_out` | `int` | NO |  | 0 |  |
| `error` | `longtext` | YES |  |  |  |
| `created_at` | `varchar(64)` | NO |  |  |  |
| `started_at` | `varchar(64)` | YES |  |  |  |
| `finished_at` | `varchar(64)` | YES |  |  |  |

Indexes:
- `idx_restricted_runner_jobs_status` (non-unique): `status`, `created_at`
- `PRIMARY` (unique): `id`
- `run_id` (unique): `run_id`
- `spec_digest` (unique): `spec_digest`

## `scheduler_leases`

| Column | Type | Null | Key | Default | Extra |
| --- | --- | --- | --- | --- | --- |
| `id` | `varchar(64)` | NO | PRI |  |  |
| `resource` | `varchar(255)` | NO | MUL |  |  |
| `slot_index` | `int` | NO |  |  |  |
| `holder_id` | `varchar(64)` | NO |  |  |  |
| `limit_count` | `int` | NO |  |  |  |
| `acquired_at` | `varchar(32)` | NO |  |  |  |
| `expires_at` | `varchar(32)` | NO |  |  |  |
| `metadata_json` | `longtext` | NO |  |  |  |

Indexes:
- `idx_scheduler_leases_resource` (non-unique): `resource`, `expires_at`
- `PRIMARY` (unique): `id`
- `resource` (unique): `resource`, `holder_id`
- `resource_2` (unique): `resource`, `slot_index`

## `schema_migrations`

| Column | Type | Null | Key | Default | Extra |
| --- | --- | --- | --- | --- | --- |
| `revision` | `varchar(255)` | NO | PRI |  |  |
| `description` | `varchar(255)` | NO |  |  |  |
| `applied_at` | `varchar(32)` | NO |  |  |  |
| `checksum` | `text` | YES |  |  |  |
| `execution_time_ms` | `int` | YES |  |  |  |

Indexes:
- `PRIMARY` (unique): `revision`

## `securities`

| Column | Type | Null | Key | Default | Extra |
| --- | --- | --- | --- | --- | --- |
| `symbol` | `varchar(96)` | NO | PRI |  |  |
| `name` | `varchar(255)` | NO |  |  |  |
| `exchange` | `varchar(96)` | NO |  |  |  |
| `market` | `varchar(96)` | NO | MUL | china |  |
| `listed_date` | `varchar(32)` | NO |  |  |  |
| `delisted_date` | `varchar(32)` | YES |  |  |  |
| `status` | `varchar(96)` | NO |  | listed |  |
| `is_st` | `int` | NO |  | 0 |  |
| `industry` | `varchar(255)` | YES |  |  |  |
| `concepts_json` | `longtext` | YES |  |  |  |
| `created_at` | `varchar(32)` | NO |  |  |  |
| `updated_at` | `varchar(32)` | NO |  |  |  |

Indexes:
- `idx_securities_market_status` (non-unique): `market`, `status`
- `PRIMARY` (unique): `symbol`

## `security_name_history`

| Column | Type | Null | Key | Default | Extra |
| --- | --- | --- | --- | --- | --- |
| `id` | `varchar(64)` | NO | PRI |  |  |
| `symbol` | `varchar(32)` | NO | MUL |  |  |
| `name` | `varchar(255)` | NO |  |  |  |
| `start_date` | `varchar(16)` | NO |  |  |  |
| `end_date` | `varchar(16)` | YES |  |  |  |
| `is_st` | `int` | NO |  | 0 |  |
| `source` | `varchar(32)` | NO |  |  |  |
| `payload_hash` | `varchar(64)` | NO |  |  |  |
| `created_at` | `varchar(64)` | NO |  |  |  |

Indexes:
- `idx_security_name_history_pit` (non-unique): `symbol`, `start_date`, `end_date`
- `PRIMARY` (unique): `id`
- `symbol` (unique): `symbol`, `start_date`, `name`

## `settings`

| Column | Type | Null | Key | Default | Extra |
| --- | --- | --- | --- | --- | --- |
| `key` | `varchar(191)` | NO | PRI |  |  |
| `value_json` | `longtext` | NO |  |  |  |
| `updated_at` | `varchar(32)` | NO |  |  |  |

Indexes:
- `PRIMARY` (unique): `key`

## `stored_object_chunks`

| Column | Type | Null | Key | Default | Extra |
| --- | --- | --- | --- | --- | --- |
| `object_id` | `varchar(64)` | NO | PRI |  |  |
| `chunk_index` | `int` | NO | PRI |  |  |
| `data` | `longblob` | NO |  |  |  |
| `size` | `int` | NO |  |  |  |
| `sha256` | `varchar(255)` | NO |  |  |  |

Indexes:
- `PRIMARY` (unique): `object_id`, `chunk_index`

## `stored_objects`

| Column | Type | Null | Key | Default | Extra |
| --- | --- | --- | --- | --- | --- |
| `id` | `varchar(64)` | NO | PRI |  |  |
| `namespace` | `varchar(255)` | NO | MUL |  |  |
| `object_key` | `varchar(255)` | NO | MUL |  |  |
| `content_type` | `varchar(96)` | YES |  |  |  |
| `encoding` | `varchar(96)` | NO |  | binary |  |
| `size` | `int` | NO |  |  |  |
| `sha256` | `varchar(255)` | NO | MUL |  |  |
| `storage_mode` | `varchar(96)` | NO |  | database |  |
| `source_path` | `varchar(1024)` | YES |  |  |  |
| `metadata_json` | `longtext` | NO |  |  |  |
| `created_at` | `varchar(32)` | NO |  |  |  |
| `updated_at` | `varchar(32)` | NO |  |  |  |

Indexes:
- `idx_stored_objects_hash` (non-unique): `sha256`
- `idx_stored_objects_key_updated` (non-unique): `object_key`, `updated_at`
- `idx_stored_objects_lookup` (non-unique): `namespace`, `object_key`, `updated_at`
- `idx_stored_objects_namespace_updated` (non-unique): `namespace`, `updated_at`
- `namespace` (unique): `namespace`, `object_key`, `sha256`
- `PRIMARY` (unique): `id`

## `strategy_admission_events`

| Column | Type | Null | Key | Default | Extra |
| --- | --- | --- | --- | --- | --- |
| `id` | `varchar(64)` | NO | PRI |  |  |
| `admission_id` | `varchar(64)` | NO | MUL |  |  |
| `stage` | `varchar(64)` | NO |  |  |  |
| `source_id` | `varchar(64)` | YES |  |  |  |
| `payload_json` | `longtext` | NO |  |  |  |
| `created_at` | `varchar(32)` | NO |  |  |  |

Indexes:
- `idx_strategy_admission_events` (non-unique): `admission_id`, `created_at`
- `PRIMARY` (unique): `id`

## `strategy_admissions`

| Column | Type | Null | Key | Default | Extra |
| --- | --- | --- | --- | --- | --- |
| `id` | `varchar(64)` | NO | PRI |  |  |
| `strategy_id` | `varchar(64)` | NO | MUL |  |  |
| `strategy_version_id` | `varchar(64)` | YES |  |  |  |
| `parameters_sha256` | `varchar(64)` | NO |  |  |  |
| `profile_name` | `varchar(64)` | NO |  |  |  |
| `profile_version` | `varchar(64)` | NO |  |  |  |
| `sample_set` | `varchar(64)` | NO |  |  |  |
| `current_stage` | `varchar(64)` | NO |  |  |  |
| `baseline_snapshot_json` | `longtext` | NO |  |  |  |
| `evaluation_json` | `longtext` | NO |  |  |  |
| `created_at` | `varchar(32)` | NO |  |  |  |
| `updated_at` | `varchar(32)` | NO |  |  |  |

Indexes:
- `idx_strategy_admissions_lookup` (non-unique): `strategy_id`, `parameters_sha256`, `updated_at`
- `PRIMARY` (unique): `id`
- `strategy_id` (unique): `strategy_id`, `parameters_sha256`, `profile_name`, `profile_version`

## `strategy_versions`

| Column | Type | Null | Key | Default | Extra |
| --- | --- | --- | --- | --- | --- |
| `id` | `varchar(64)` | NO | PRI |  |  |
| `project_id` | `varchar(64)` | YES | MUL |  |  |
| `strategy_path` | `varchar(1024)` | YES |  |  |  |
| `source_sha256` | `varchar(255)` | YES |  |  |  |
| `git_commit` | `varchar(255)` | YES |  |  |  |
| `git_branch` | `varchar(255)` | YES |  |  |  |
| `git_dirty` | `int` | NO |  | 0 |  |
| `git_status_hash` | `varchar(128)` | YES |  |  |  |
| `metadata_json` | `longtext` | NO |  |  |  |
| `created_at` | `varchar(32)` | NO |  |  |  |

Indexes:
- `idx_strategy_versions_project` (non-unique): `project_id`, `created_at`
- `PRIMARY` (unique): `id`

## `tasks`

| Column | Type | Null | Key | Default | Extra |
| --- | --- | --- | --- | --- | --- |
| `id` | `varchar(64)` | NO | PRI |  |  |
| `celery_task_id` | `varchar(64)` | YES |  |  |  |
| `kind` | `varchar(96)` | NO |  |  |  |
| `status` | `varchar(96)` | NO |  |  |  |
| `title` | `varchar(255)` | NO |  |  |  |
| `project_id` | `varchar(64)` | YES |  |  |  |
| `related_id` | `varchar(64)` | YES |  |  |  |
| `parameters_json` | `longtext` | NO |  |  |  |
| `log_path` | `varchar(1024)` | NO |  |  |  |
| `artifacts_json` | `longtext` | YES |  |  |  |
| `error` | `longtext` | YES |  |  |  |
| `created_at` | `varchar(32)` | NO | MUL |  |  |
| `started_at` | `varchar(32)` | YES |  |  |  |
| `finished_at` | `varchar(32)` | YES |  |  |  |

Indexes:
- `idx_tasks_created_at` (non-unique): `created_at`
- `PRIMARY` (unique): `id`

## `trade_calendar`

| Column | Type | Null | Key | Default | Extra |
| --- | --- | --- | --- | --- | --- |
| `market` | `varchar(96)` | NO | PRI |  |  |
| `trade_date` | `varchar(32)` | NO | PRI |  |  |
| `is_open` | `int` | NO |  |  |  |
| `prev_trade_date` | `varchar(32)` | YES |  |  |  |
| `next_trade_date` | `varchar(32)` | YES |  |  |  |
| `source` | `varchar(96)` | YES |  |  |  |
| `batch_id` | `varchar(64)` | YES |  |  |  |

Indexes:
- `PRIMARY` (unique): `market`, `trade_date`

## `universe_coverage_watermarks`

| Column | Type | Null | Key | Default | Extra |
| --- | --- | --- | --- | --- | --- |
| `universe_code` | `varchar(96)` | NO | PRI |  |  |
| `launch_date` | `varchar(32)` | NO |  |  |  |
| `coverage_start` | `varchar(255)` | YES |  |  |  |
| `coverage_end` | `varchar(255)` | YES |  |  |  |
| `coverage_status` | `varchar(255)` | NO | MUL | missing |  |
| `source` | `varchar(96)` | YES |  |  |  |
| `expected_members` | `int` | YES |  |  |  |
| `observed_snapshots` | `int` | NO |  | 0 |  |
| `membership_rows` | `int` | NO |  | 0 |  |
| `bundle_sha256` | `varchar(64)` | YES |  |  |  |
| `last_batch_id` | `varchar(64)` | YES |  |  |  |
| `validation_json` | `longtext` | NO |  |  |  |
| `validated_at` | `varchar(32)` | NO |  |  |  |
| `updated_at` | `varchar(32)` | NO |  |  |  |

Indexes:
- `idx_universe_coverage_status` (non-unique): `coverage_status`, `coverage_end`
- `PRIMARY` (unique): `universe_code`

## `universe_membership`

| Column | Type | Null | Key | Default | Extra |
| --- | --- | --- | --- | --- | --- |
| `universe_code` | `varchar(96)` | NO | PRI |  |  |
| `symbol` | `varchar(96)` | NO | PRI |  |  |
| `start_date` | `varchar(32)` | NO | PRI |  |  |
| `end_date` | `varchar(32)` | YES |  |  |  |
| `announce_date` | `varchar(32)` | YES |  |  |  |
| `effective_date` | `varchar(32)` | YES |  |  |  |
| `weight` | `double` | YES |  |  |  |
| `source` | `varchar(96)` | NO |  |  |  |
| `batch_id` | `varchar(64)` | YES |  |  |  |

Indexes:
- `idx_universe_asof` (non-unique): `universe_code`, `start_date`, `end_date`
- `PRIMARY` (unique): `universe_code`, `symbol`, `start_date`

## `verification_cases`

| Column | Type | Null | Key | Default | Extra |
| --- | --- | --- | --- | --- | --- |
| `id` | `varchar(64)` | NO | PRI |  |  |
| `verification_run_id` | `varchar(64)` | NO | MUL |  |  |
| `case_key` | `varchar(255)` | NO |  |  |  |
| `market` | `varchar(96)` | YES |  |  |  |
| `symbol` | `varchar(96)` | YES |  |  |  |
| `stage` | `varchar(64)` | NO |  |  |  |
| `status` | `varchar(96)` | NO |  |  |  |
| `trace_id` | `varchar(64)` | YES |  |  |  |
| `resource_type` | `varchar(255)` | YES |  |  |  |
| `resource_id` | `varchar(64)` | YES |  |  |  |
| `error_code` | `varchar(255)` | YES |  |  |  |
| `details_json` | `longtext` | YES |  |  |  |
| `artifact_path` | `varchar(255)` | YES |  |  |  |
| `started_at` | `varchar(32)` | YES |  |  |  |
| `finished_at` | `varchar(32)` | YES |  |  |  |

Indexes:
- `idx_verification_cases_run` (non-unique): `verification_run_id`, `stage`, `status`
- `PRIMARY` (unique): `id`
- `verification_run_id` (unique): `verification_run_id`, `case_key`

## `verification_runs`

| Column | Type | Null | Key | Default | Extra |
| --- | --- | --- | --- | --- | --- |
| `id` | `varchar(64)` | NO | PRI |  |  |
| `name` | `varchar(255)` | NO |  |  |  |
| `status` | `varchar(96)` | NO |  |  |  |
| `git_commit` | `varchar(255)` | YES |  |  |  |
| `environment_json` | `longtext` | YES |  |  |  |
| `manifest_json` | `longtext` | YES |  |  |  |
| `summary_json` | `longtext` | YES |  |  |  |
| `artifact_path` | `varchar(255)` | YES |  |  |  |
| `created_at` | `varchar(32)` | NO | MUL |  |  |
| `started_at` | `varchar(32)` | YES |  |  |  |
| `finished_at` | `varchar(32)` | YES |  |  |  |

Indexes:
- `idx_verification_runs_created` (non-unique): `created_at`
- `PRIMARY` (unique): `id`

## `walk_forward_runs`

| Column | Type | Null | Key | Default | Extra |
| --- | --- | --- | --- | --- | --- |
| `id` | `varchar(64)` | NO | PRI |  |  |
| `batch_id` | `varchar(64)` | NO | UNI |  |  |
| `status` | `varchar(32)` | NO | MUL |  |  |
| `dataset_version` | `varchar(255)` | NO |  |  |  |
| `universe_version` | `varchar(255)` | NO |  |  |  |
| `adjustment_contract` | `varchar(255)` | NO |  |  |  |
| `feature_pipeline_version` | `varchar(255)` | NO |  |  |  |
| `selection_metric` | `varchar(64)` | NO |  |  |  |
| `selection_rule` | `varchar(255)` | NO |  |  |  |
| `created_at` | `varchar(64)` | NO |  |  |  |
| `completed_at` | `varchar(64)` | YES |  |  |  |
| `lineage_status` | `varchar(32)` | NO |  | complete |  |
| `lineage_reason` | `varchar(255)` | YES |  |  |  |
| `batch_snapshot_json` | `longtext` | YES |  |  |  |
| `certificate_json` | `longtext` | YES |  |  |  |
| `certificate_digest` | `varchar(64)` | YES | UNI |  |  |
| `certified_at` | `varchar(64)` | YES |  |  |  |

Indexes:
- `batch_id` (unique): `batch_id`
- `idx_walk_forward_certificate_digest` (unique): `certificate_digest`
- `idx_walk_forward_runs_status` (non-unique): `status`, `created_at`
- `PRIMARY` (unique): `id`

## `walk_forward_windows`

| Column | Type | Null | Key | Default | Extra |
| --- | --- | --- | --- | --- | --- |
| `id` | `varchar(64)` | NO | PRI |  |  |
| `walk_forward_run_id` | `varchar(64)` | NO | MUL |  |  |
| `batch_id` | `varchar(64)` | NO | MUL |  |  |
| `project_id` | `varchar(255)` | NO |  |  |  |
| `symbol` | `varchar(64)` | NO |  |  |  |
| `fold` | `int` | NO |  |  |  |
| `train_start` | `varchar(10)` | NO |  |  |  |
| `train_end` | `varchar(10)` | NO |  |  |  |
| `validation_start` | `varchar(10)` | NO |  |  |  |
| `validation_end` | `varchar(10)` | NO |  |  |  |
| `oos_start` | `varchar(10)` | NO |  |  |  |
| `oos_end` | `varchar(10)` | NO |  |  |  |
| `universe_version` | `varchar(255)` | NO |  |  |  |
| `dataset_version` | `varchar(255)` | NO |  |  |  |
| `adjustment_contract` | `varchar(255)` | NO |  |  |  |
| `feature_pipeline_version` | `varchar(255)` | NO |  |  |  |
| `fold_fingerprint` | `varchar(64)` | NO |  |  |  |
| `oos_input_fingerprint` | `varchar(64)` | NO |  |  |  |
| `status` | `varchar(32)` | NO |  |  |  |
| `created_at` | `varchar(64)` | NO |  |  |  |
| `completed_at` | `varchar(64)` | YES |  |  |  |
| `project_snapshot_json` | `longtext` | YES |  |  |  |
| `selection_inputs_json` | `longtext` | YES |  |  |  |
| `selection_outputs_json` | `longtext` | YES |  |  |  |

Indexes:
- `batch_id` (unique): `batch_id`, `project_id`, `symbol`, `fold`
- `idx_walk_forward_windows_batch` (non-unique): `batch_id`, `project_id`, `symbol`, `fold`
- `idx_walk_forward_windows_run` (non-unique): `walk_forward_run_id`, `fold`
- `PRIMARY` (unique): `id`

## `workflow_events`

| Column | Type | Null | Key | Default | Extra |
| --- | --- | --- | --- | --- | --- |
| `id` | `varchar(64)` | NO | PRI |  |  |
| `workflow_id` | `varchar(64)` | NO | MUL |  |  |
| `trace_id` | `varchar(64)` | NO | MUL |  |  |
| `stage` | `varchar(64)` | NO |  |  |  |
| `action` | `varchar(255)` | NO |  |  |  |
| `resource_type` | `varchar(255)` | YES |  |  |  |
| `resource_id` | `varchar(64)` | YES |  |  |  |
| `status` | `varchar(96)` | NO |  |  |  |
| `error_code` | `varchar(255)` | YES |  |  |  |
| `message` | `varchar(255)` | YES |  |  |  |
| `details_json` | `longtext` | YES |  |  |  |
| `created_at` | `varchar(32)` | NO |  |  |  |

Indexes:
- `idx_workflow_events_lookup` (non-unique): `workflow_id`, `created_at`
- `idx_workflow_events_trace` (non-unique): `trace_id`, `created_at`
- `PRIMARY` (unique): `id`

## `workflow_lineage_edges`

| Column | Type | Null | Key | Default | Extra |
| --- | --- | --- | --- | --- | --- |
| `id` | `varchar(191)` | NO | PRI |  |  |
| `parent_type` | `varchar(64)` | NO | MUL |  |  |
| `parent_id` | `varchar(191)` | NO |  |  |  |
| `child_type` | `varchar(64)` | NO | MUL |  |  |
| `child_id` | `varchar(191)` | NO |  |  |  |
| `relation` | `varchar(64)` | NO |  |  |  |
| `contract_digest` | `varchar(128)` | YES |  |  |  |
| `details_json` | `longtext` | YES |  |  |  |
| `created_at` | `varchar(64)` | NO |  |  |  |

Indexes:
- `idx_workflow_lineage_child` (non-unique): `child_type`, `child_id`, `created_at`
- `idx_workflow_lineage_parent` (non-unique): `parent_type`, `parent_id`, `created_at`
- `parent_type` (unique): `parent_type`, `parent_id`, `child_type`, `child_id`, `relation`
- `PRIMARY` (unique): `id`
