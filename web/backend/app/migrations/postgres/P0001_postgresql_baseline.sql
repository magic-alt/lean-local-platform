-- description: PostgreSQL baseline equivalent to the certified legacy 0056 schema
-- compatibility: fresh PostgreSQL initialization only; no MySQL data migration or legacy replay
-- rollback: restore an isolated pg_dump or recreate the empty database from this baseline
-- data migration: none
-- affected tests: PostgreSQL baseline, schema contract, market time-series relation guard

create table if not exists alert_deliveries (
                id text primary key,
                alert_id text not null,
                channel text not null,
                status text not null,
                attempt_count integer not null default 0,
                last_attempt_at text,
                last_success_at text,
                next_retry_at text,
                last_error text,
                response_code integer,
                metadata_json text not null,
                created_at text not null,
                updated_at text not null, terminal_at varchar(64),
                unique(alert_id, channel)
            );

create table if not exists alert_events (
                id text primary key,
                event_type text not null,
                severity text not null,
                status text not null default 'open',
                dedupe_key text not null,
                title text not null,
                message text not null,
                source text,
                related_id text,
                details_json text not null,
                first_seen_at text not null,
                last_seen_at text not null,
                count integer not null default 1,
                cooldown_until text,
                acknowledged_at text,
                acknowledged_by text,
                resolved_at text,
                resolved_by text,
                unique(dedupe_key, status)
            );

create table if not exists api_idempotency_keys (
    id varchar(64) primary key,
    idempotency_key varchar(255) not null,
    method varchar(16) not null,
    request_path varchar(1024) not null,
    request_path_sha256 varchar(64) not null,
    request_sha256 varchar(64) not null,
    status varchar(32) not null,
    response_status integer,
    response_body text,
    response_content_type varchar(255),
    trace_id varchar(128),
    created_at text not null,
    updated_at text not null,
    unique(idempotency_key, method, request_path_sha256)
);

create table if not exists artifact_registry (
    artifact_id varchar(128) primary key,
    schema_version varchar(32) not null,
    artifact_type varchar(64) not null,
    owner varchar(32) not null,
    promotion_status varchar(32) not null,
    data_release_id varchar(96) not null,
    universe_release_id varchar(128),
    model_release_id varchar(128),
    strategy_policy_id varchar(128),
    git_commit varchar(128) not null,
    container_digest varchar(255) not null,
    as_of_time varchar(64) not null,
    signal_date varchar(32),
    trade_date varchar(32),
    timezone varchar(64) not null,
    currency varchar(16) not null,
    payload_sha256 varchar(64) not null,
    object_key varchar(1024),
    media_type varchar(128),
    row_count bigint,
    metadata_json text not null,
    created_at varchar(64) not null
);

create table if not exists ashare_tech_agent_profiles (
    profile_key text primary key,
    provider text not null,
    model text not null,
    prompt_version_id text not null,
    updated_at text not null
);

create table if not exists ashare_tech_agent_runs (
    id text primary key,
    report_id text not null,
    task_id text,
    requested_date text not null,
    analysis_date text not null,
    analysis_mode text not null,
    status text not null,
    provider text,
    requested_model text,
    prompt_version text not null,
    input_fingerprint text not null,
    stage_summary_json text not null,
    usage_json text not null,
    fallback_reason text,
    created_at text not null,
    started_at text,
    finished_at text,
    updated_at text not null
, prompt_version_id text, prompt_snapshot_json text, prompt_fingerprint text);

create table if not exists ashare_tech_agent_stages (
    id text primary key,
    run_id text not null,
    stage_key text not null,
    sequence_no integer not null,
    status text not null,
    provider text,
    model text,
    prompt_version text not null,
    input_fingerprint text not null,
    input_fact_ids_json text not null,
    output_json text,
    usage_json text not null,
    latency_ms integer,
    attempt_count integer not null default 0,
    error_category text,
    error text,
    started_at text,
    finished_at text,
    updated_at text not null, prompt_version_id text, system_prompt text,
    unique(run_id, stage_key)
);

create table if not exists ashare_tech_candidate_signals (
    id text primary key,
    run_id text not null,
    report_id text not null,
    symbol text not null,
    provider text,
    model text,
    prompt_version text not null,
    source_type text not null,
    raw_signal_json text not null,
    final_signal_json text not null,
    guardrail_json text not null,
    status text not null,
    created_at text not null,
    unique(run_id, symbol)
);

create table if not exists ashare_tech_prediction_evaluations (
    id text primary key,
    prediction_id text not null,
    run_id text not null,
    report_id text not null,
    symbol text not null,
    horizon_days integer not null,
    status text not null,
    evaluated_date text,
    entry_close double precision not null,
    exit_close double precision,
    benchmark_code text not null,
    benchmark_entry_close double precision,
    benchmark_exit_close double precision,
    return_pct double precision,
    benchmark_return_pct double precision,
    excess_return_pct double precision,
    realized_direction text,
    direction_hit integer,
    brier_score double precision,
    source_manifest_json text not null,
    missing_reason text,
    created_at text not null,
    updated_at text not null,
    unique(prediction_id)
);

create table if not exists ashare_tech_predictions (
    id text primary key,
    run_id text not null,
    report_id text not null,
    symbol text not null,
    horizon_days integer not null,
    predicted_direction text not null,
    probabilities_json text not null,
    confidence double precision not null,
    trend_score double precision not null,
    rule_conclusion text,
    selection_rank integer,
    selection_tier text not null,
    rationale text not null,
    evidence_ids_json text not null,
    neutral_band_pct double precision not null,
    entry_date text not null,
    entry_close double precision not null,
    target_date text,
    benchmark_code text not null,
    model text not null,
    prompt_version text not null,
    created_at text not null, provider text,
    unique(run_id, symbol, horizon_days)
);

create table if not exists ashare_tech_prompt_templates (
    id text primary key,
    template_key text not null,
    name text not null,
    description text,
    version_no integer not null,
    stage_prompts_json text not null,
    prompt_fingerprint text not null,
    created_at text not null,
    unique(template_key, version_no)
);

create table if not exists ashare_tech_reports (
    id text primary key,
    task_id text,
    requested_date text not null,
    analysis_date text,
    market_status text not null,
    status text not null,
    attempt_count integer not null default 0,
    data_cutoff_at text,
    primary_source text not null default 'tushare',
    sector_source text,
    data_completeness_json text not null,
    source_conflicts_json text not null,
    source_manifest_json text not null,
    context_json text,
    raw_response_json text,
    report_json text,
    model text,
    prompt_version text not null,
    previous_report_id text,
    input_fingerprint text,
    error text,
    created_at text not null,
    started_at text,
    finished_at text,
    updated_at text not null, pool_snapshot_json text, pool_fingerprint text, active_agent_run_id text, analysis_mode text, llm_status text, agent_summary_json text, requested_provider text, requested_model text, prompt_version_id text,
    unique(requested_date)
);

create table if not exists ashare_tech_watchlist_items (
    code text primary key,
    name text not null,
    group_key text not null,
    enabled integer not null default 1,
    rule_tags_json text not null,
    source text not null default 'tushare:stock_basic',
    created_at text not null,
    updated_at text not null
);

create table if not exists asset_capabilities (
    id varchar(96) primary key,
    asset_class varchar(64) not null,
    market varchar(64) not null,
    venue varchar(64) not null,
    resolution varchar(32) not null,
    data_type varchar(32) not null,
    state varchar(32) not null,
    metadata_count bigint not null default 0,
    canonical_row_count bigint not null default 0,
    executable_reason varchar(255),
    evidence_json text not null,
    refreshed_at varchar(64) not null,
    unique(asset_class, market, venue, resolution, data_type)
);

create table if not exists backtest_results (
                id text primary key,
                job_id text not null unique,
                summary_metrics_json text not null,
                equity_curve_json text not null,
                drawdown_curve_json text not null,
                orders_json text not null,
                trades_json text not null,
                holdings_json text not null,
                statistics_json text not null,
                performance_json text,
                raw_result_path text,
                raw_result_object_id text,
                summary_object_id text,
                created_at text not null
            );

create table if not exists backtest_runs (
                id text primary key,
                task_id text,
                project_id text,
                symbol text not null,
                asset_class text not null default 'equity',
                venue text,
                resolution text not null default 'daily',
                data_type text not null default 'trade',
                parameters_json text not null,
                status text not null,
                docker_image text not null,
                name text,
                container_name text,
                work_dir text,
                results_dir text not null,
                result_json_path text,
                summary_json_path text,
                report_html_path text,
                log_path text,
                statistics_json text,
                exit_code integer,
                error text,
                error_message text,
                created_at text not null,
                queued_at text,
                started_at text,
                finished_at text,
                duration_seconds double precision,
                fingerprint_json text,
                validation_json text,
                experiment_json text
            , failure_json text, batch_item_id varchar(64), dataset_release_id varchar(96), reproducibility_certificate_id varchar(96), trust_status varchar(32) not null default 'unverified', trust_reason varchar(255), trust_evaluated_at varchar(64), data_release_id varchar(96), execution_backend varchar(32), execution_id varchar(128), runtime_identity_json text, canonical_config_sha256 varchar(64));

create table if not exists cbond_call_events (
                id text primary key,
                bond_code text not null,
                announce_date text not null,
                trigger_date text,
                status text not null,
                call_price double precision,
                last_trade_date text,
                source text not null,
                created_at text not null
            );

create table if not exists cbond_securities (
                bond_code text primary key,
                bond_name text not null,
                stock_symbol text not null,
                listed_date text,
                delisted_date text,
                maturity_date text,
                rating text,
                conversion_price double precision,
                issue_size double precision,
                remaining_size double precision,
                terms_json text,
                source text not null,
                updated_at text not null
            );

create table if not exists corporate_actions (
                symbol text not null,
                ex_date text not null,
                action_type text not null,
                cash_dividend double precision,
                stock_dividend double precision,
                split_ratio double precision,
                allotment_ratio double precision,
                allotment_price double precision,
                source text not null,
                batch_id text,
                created_at text not null,
                primary key (symbol, ex_date, action_type, source)
            );

create table if not exists data_assets (
                id bigserial primary key,
                symbol text not null,
                asset_class text not null default 'equity',
                venue text,
                resolution text not null default 'daily',
                data_type text not null default 'trade',
                source text not null,
                "rows" integer not null,
                first_date text not null,
                last_date text not null,
                lean_file text not null,
                lean_object_id text,
                factor_object_id text,
                status text not null default 'active',
                superseded_by integer,
                superseded_at text,
                superseded_reason text,
                metadata_json text not null,
                created_at text not null
            );

create table if not exists data_gap_resolutions (
    id text primary key,
    market text not null,
    symbol text not null,
    trade_date text not null,
    classification text not null,
    status text not null,
    evidence_source text,
    evidence_json text,
    batch_id text,
    created_at text not null,
    updated_at text not null,
    unique(market, symbol, trade_date)
);

create table if not exists data_gaps (
                id text primary key,
                dataset text not null,
                asset_class text not null,
                market text not null,
                symbol text,
                start_time text not null,
                end_time text not null,
                severity text not null,
                source text not null,
                details_json text not null,
                created_at text not null
            );

create table if not exists data_import_batches (
                id text primary key,
                provider text not null,
                market text not null,
                asset_class text not null,
                status text not null,
                config_json text not null,
                qa_report_json text,
                error text,
                started_at text not null,
                finished_at text
            );

create table if not exists data_providers_v2 (
    id text primary key,
    provider_key text not null unique,
    display_name text not null,
    priority integer not null default 100,
    status text not null default 'active',
    metadata_json json not null,
    created_at text not null,
    updated_at text not null,
    check (priority >= 0),
    check (status in ('active','disabled','retired'))
);

create table if not exists data_quality_reports (
                id text primary key,
                report_type text not null,
                asset_class text not null,
                market text not null,
                symbol text,
                start_date text,
                end_date text,
                sources_json text not null,
                severity text not null,
                result_json text not null,
                created_at text not null
            );

create table if not exists data_record_issues (
    id text primary key,
    dataset_key text not null,
    source text,
    instrument_code text,
    start_date text,
    end_date text,
    issue_code text not null,
    severity text not null,
    status text not null,
    details_json text,
    detected_at text not null,
    resolved_at text,
    resolution_batch_id text
);

create table if not exists data_releases (
    id varchar(96) primary key,
    schema_version varchar(32) not null,
    profile varchar(96) not null,
    asset_class varchar(64) not null,
    market varchar(64) not null,
    universe varchar(96) not null,
    benchmark varchar(32) not null,
    coverage_start varchar(32) not null,
    coverage_end varchar(32) not null,
    as_of_time varchar(64) not null,
    identity_sha256 varchar(64) not null unique,
    manifest_sha256 varchar(64) not null unique,
    manifest_path varchar(1024) not null,
    status varchar(32) not null,
    created_at varchar(64) not null,
    revoked_at varchar(64),
    revoke_reason varchar(255)
);

create table if not exists data_sync_items (
    id text primary key,
    run_id text not null,
    dataset_key text not null,
    status text not null,
    processed integer not null default 0,
    inserted integer not null default 0,
    updated integer not null default 0,
    failed integer not null default 0,
    checkpoint_json text,
    error text,
    started_at text,
    finished_at text, metrics_json text, canonical_status text, derived_status_json text,
    unique(run_id, dataset_key)
);

create table if not exists data_sync_lineage_jobs (
    id varchar(64) primary key,
    run_id varchar(64) not null,
    dataset_key varchar(255) not null,
    object_id varchar(64) not null,
    row_count integer not null default 0,
    status varchar(32) not null default 'pending',
    attempts integer not null default 0,
    error text,
    created_at varchar(32) not null,
    started_at varchar(32),
    finished_at varchar(32),
    unique(run_id,dataset_key,object_id)
);

create table if not exists data_sync_runs (
    id text primary key,
    task_id text,
    provider text not null,
    mode text not null,
    scope text not null,
    status text not null,
    requested_datasets_json text,
    summary_json text,
    error text,
    created_at text not null,
    started_at text,
    finished_at text,
    cancel_requested integer not null default 0
, canonical_status text, canonical_ready_at text, derived_status_json text, heartbeat_at text, request_scope_json text);

create table if not exists data_sync_work_items (
    run_id text not null,
    dataset_key text not null,
    work_key text not null,
    sequence_no integer not null,
    status text not null default 'pending',
    attempts integer not null default 0,
    row_count integer not null default 0,
    content_sha256 text,
    error text,
    started_at text,
    fetched_at text,
    committed_at text,
    primary key (run_id, dataset_key, work_key)
);

create table if not exists dataset_versions (
                id text primary key,
                dataset_key text not null,
                asset_class text,
                market text,
                venue text,
                resolution text,
                data_type text,
                adjust text,
                symbol text,
                start_date text,
                end_date text,
                row_count integer not null default 0,
                status_count integer not null default 0,
                benchmark_symbol text,
                benchmark_row_count integer not null default 0,
                data_batch_id text,
                lean_zip_sha256 text,
                factor_file_sha256 text,
                parquet_dataset_id text,
                parquet_file_sha256 text,
                metadata_json text not null,
                created_at text not null
            , dataset_version varchar(96), environment varchar(32) not null default 'research', is_production integer not null default 0, is_certified integer not null default 0, certified_at varchar(32), certified_by varchar(96), coverage_start varchar(32), coverage_end varchar(32), qa_status varchar(32), qa_report_id varchar(64), dataset_release_id varchar(96));

create table if not exists derived_layer_watermarks (
    layer_key text not null,
    scope_key text not null,
    source text not null,
    canonical_start text,
    canonical_end text,
    materialized_start text,
    materialized_end text,
    status text not null,
    row_count integer not null default 0,
    dataset_id text,
    content_sha256 text,
    last_canonical_run_id text,
    last_maintenance_run_id text,
    error text,
    details_json text not null,
    started_at text,
    completed_at text,
    updated_at text not null,
    primary key (layer_key, scope_key, source)
);

create table if not exists derived_maintenance_runs (
    id text primary key,
    trigger_type text not null,
    status text not null,
    requested_layers_json text not null,
    canonical_watermark text,
    summary_json text not null,
    error text,
    created_at text not null,
    started_at text,
    finished_at text
, attempt_count integer not null default 0, max_attempts integer not null default 5, checkpoint_json text, checkpoint_at varchar(64), heartbeat_at varchar(64), next_retry_at varchar(64), alert_sent_at varchar(64), lease_owner varchar(96));

create table if not exists equity_issuers_v2 (
    id text primary key,
    legal_name text not null,
    unified_credit_code text,
    country_code text not null default 'CN',
    province text,
    city text,
    registered_capital decimal(28,4),
    established_date date,
    metadata_json json not null,
    created_at text not null,
    updated_at text not null,
    unique(unified_credit_code)
);

create table if not exists experiment_batch_attempts (
    id varchar(64) primary key,
    item_id varchar(64) not null,
    attempt integer not null,
    related_id varchar(128),
    task_id varchar(64),
    status varchar(32) not null,
    error text,
    created_at varchar(64) not null,
    finished_at varchar(64),
    unique(item_id, attempt)
);

create table if not exists experiment_batch_items (
    id varchar(64) primary key,
    batch_id varchar(64) not null,
    item_index integer not null,
    item_key varchar(255) not null,
    project_id varchar(255),
    symbol varchar(64),
    status varchar(32) not null,
    parameters_json text not null,
    related_id varchar(128),
    task_id varchar(64),
    attempt integer not null default 0,
    result_json text,
    error text,
    created_at varchar(64) not null,
    started_at varchar(64),
    finished_at varchar(64),
    unique(batch_id, item_key)
);

create table if not exists experiment_batches (
    id varchar(64) primary key,
    kind varchar(32) not null,
    mode varchar(64) not null,
    name varchar(255) not null,
    example_key varchar(128),
    status varchar(32) not null,
    config_json text not null,
    summary_json text,
    total integer not null default 0,
    queued integer not null default 0,
    running integer not null default 0,
    succeeded integer not null default 0,
    failed integer not null default 0,
    skipped integer not null default 0,
    cancelled integer not null default 0,
    cancel_requested integer not null default 0,
    created_at varchar(64) not null,
    started_at varchar(64),
    finished_at varchar(64)
, objective_metric varchar(32), source_backtest_run_id varchar(191), scope_hash varchar(128), data_fingerprint varchar(128), archived_at varchar(64));

create table if not exists experiments (
                id text primary key,
                run_id text not null unique,
                strategy_version_id text not null,
                dataset_version_id text not null,
                parameter_hash text,
                docker_image text,
                docker_image_digest text,
                git_commit text,
                fingerprint_json text not null,
                validation_json text not null,
                experiment_json text not null,
                created_at text not null,
                updated_at text not null
            , execution_backend varchar(32), runtime_identity_json text, canonical_config_sha256 varchar(64));

create table if not exists factor_evaluations (
                id text primary key,
                factor_name text not null,
                universe_code text not null,
                start_date text not null,
                end_date text not null,
                forward_days integer not null,
                quantiles integer not null,
                engine text not null,
                result_json text not null,
                created_at text not null
            );

create table if not exists factor_values (
                symbol text not null,
                trade_date text not null,
                factor_name text not null,
                value double precision not null,
                source text not null,
                batch_id text,
                created_at text not null,
                primary key (symbol, trade_date, factor_name, source)
            );

create table if not exists feature_pipeline_fits (
    id varchar(64) primary key,
    window_id varchar(64) not null,
    pipeline_version varchar(255) not null,
    fit_phase varchar(32) not null,
    fit_start varchar(10) not null,
    fit_end varchar(10) not null,
    fit_statistics_json text not null,
    fit_fingerprint varchar(64) not null,
    created_at varchar(64) not null,
    unique(window_id, pipeline_version, fit_phase),
    unique(fit_fingerprint)
);

create table if not exists financial_facts (
                symbol text not null,
                field_name text not null,
                report_date text not null,
                announce_date text not null,
                effective_date text not null,
                value double precision,
                unit text,
                source text not null,
                batch_id text,
                created_at text not null,
                primary key (symbol, field_name, report_date, announce_date, source)
            );

create table if not exists financial_statements (
                symbol text not null,
                statement_type text not null,
                report_date text not null,
                announce_date text not null,
                effective_date text not null,
                fiscal_period text,
                currency text,
                fields_json text not null,
                source text not null,
                batch_id text,
                created_at text not null, report_type varchar(32), update_flag varchar(32), payload_hash varchar(64),
                primary key (symbol, statement_type, report_date, announce_date, source)
            );

create table if not exists futures_continuous_builds (
    id varchar(64) primary key,
    product varchar(32) not null,
    exchange varchar(32) not null,
    start_date varchar(16) not null,
    end_date varchar(16) not null,
    adjustment varchar(32) not null,
    contracts double precision not null,
    mapping_batch_id varchar(64) not null,
    fee_schedule_version varchar(64) not null,
    config_json text not null,
    summary_json text not null,
    created_at varchar(64) not null
);

create table if not exists futures_contracts (
                contract_code text primary key,
                product text not null,
                exchange text not null,
                name text,
                multiplier double precision,
                margin_rate double precision,
                tick_size double precision,
                delivery_month text,
                listed_date text,
                last_trade_date text,
                source text not null,
                updated_at text not null
            );

create table if not exists futures_fee_schedules (
    product varchar(32) not null,
    exchange varchar(32) not null,
    open_rate double precision not null default 0,
    close_rate double precision not null default 0,
    close_today_rate double precision not null default 0,
    per_contract double precision not null default 0,
    slippage_ticks double precision not null default 0,
    currency varchar(16) not null default 'CNY',
    version varchar(64) not null,
    source varchar(64) not null,
    updated_at varchar(64) not null,
    primary key (product, exchange)
);

create table if not exists futures_main_mapping (
                product text not null,
                exchange text not null,
                trade_date text not null,
                main_symbol text not null,
                continuous_symbol text,
                rule text not null,
                source text not null,
                batch_id text,
                updated_at text not null,
                primary key (product, exchange, trade_date, source)
            );

create table if not exists futures_main_rules (
                product text not null,
                exchange text not null,
                rule_type text not null,
                roll_days_before_expiry integer not null default 0,
                min_open_interest_days integer not null default 1,
                source text not null,
                updated_at text not null,
                primary key (product, exchange)
            );

create table if not exists futures_roll_events (
    id varchar(64) primary key,
    build_id varchar(64) not null,
    trade_date varchar(16) not null,
    from_contract varchar(64) not null,
    to_contract varchar(64) not null,
    from_price double precision not null,
    to_price double precision not null,
    roll_gap double precision not null,
    roll_yield double precision not null,
    market_pnl double precision not null,
    commission double precision not null,
    slippage double precision not null,
    net_pnl double precision not null
);

create table if not exists index_membership_events (
                id text primary key,
                index_code text not null,
                symbol text not null,
                name text,
                action_type text not null,
                adjustment_type text,
                announce_date text not null,
                effective_date text not null,
                source_url text,
                raw_file_hash text,
                batch_id text not null,
                parse_status text not null,
                updated_at text not null,
                unique(index_code, symbol, action_type, effective_date, source_url)
            );

create table if not exists index_source_artifacts (
                id text primary key,
                index_code text not null,
                source_url text not null,
                local_path text,
                raw_file_hash text not null,
                content_type text,
                parser_version text not null,
                parse_status text not null,
                error text,
                metadata_json text not null,
                fetched_at text not null,
                unique(index_code, source_url, raw_file_hash)
            );

create table if not exists index_weights (
                universe_code text not null,
                symbol text not null,
                trade_date text not null,
                weight double precision not null,
                source text not null,
                batch_id text,
                created_at text not null,
                primary key (universe_code, symbol, trade_date, source)
            );

create table if not exists industry_membership (
    id varchar(64) primary key,
    symbol varchar(32) not null,
    industry_code varchar(32) not null,
    industry_name varchar(255),
    taxonomy varchar(32) not null,
    level_no integer not null,
    in_date varchar(16) not null,
    out_date varchar(16),
    source varchar(32) not null,
    payload_hash varchar(64) not null,
    created_at varchar(64) not null,
    unique(symbol, industry_code, taxonomy, in_date)
);

create table if not exists instrument_identifiers (
                instrument_id text not null,
                id_type text not null,
                id_value text not null,
                start_date text,
                end_date text,
                source text not null,
                created_at text not null, provider varchar(96), identifier_type varchar(96), identifier_value varchar(96), exchange varchar(32), market varchar(32), valid_from varchar(32), valid_to varchar(32), is_primary integer not null default 0, batch_id varchar(64), updated_at varchar(32),
                primary key (instrument_id, id_type, id_value, source)
            );

create table if not exists instruments (
                instrument_id text primary key,
                symbol text not null,
                normalized_symbol text not null,
                name text,
                asset_class text not null,
                market text not null,
                exchange text,
                venue text,
                currency text,
                base_currency text,
                quote_currency text,
                underlying_symbol text,
                listed_date text,
                delisted_date text,
                expiry_date text,
                status text not null default 'active',
                lot_size double precision,
                tick_size double precision,
                contract_multiplier double precision,
                margin_rate double precision,
                metadata_json text not null,
                source text not null,
                created_at text not null,
                updated_at text not null,
                unique(asset_class, market, venue, symbol)
            );

create table if not exists leakage_check_results (
    id varchar(64) primary key,
    window_id varchar(64) not null,
    decision varchar(16) not null,
    check_version varchar(64) not null,
    result_json text not null,
    checked_at varchar(64) not null,
    unique(window_id, check_version)
);

create table if not exists market_lake_cutovers (
    id varchar(64) primary key,
    status varchar(32) not null,
    parquet_root text not null,
    verification_json text not null,
    dropped_tables_json text not null,
    created_at varchar(64) not null
);

create table if not exists market_schema_versions_v2 (
    version text primary key,
    contract_version text not null,
    state text not null,
    prepared_at text not null,
    activated_at text,
    preparation_report_json json not null,
    check (state in ('prepared','active','retired'))
);

create table if not exists market_venues_v2 (
    id text primary key,
    venue_code text not null unique,
    name text not null,
    country_code text not null,
    timezone text not null,
    currency text,
    status text not null default 'active',
    created_at text not null,
    updated_at text not null,
    check (status in ('active','inactive','retired'))
);

create table if not exists ml_feature_files (
    id varchar(64) primary key,
    feature_set_id varchar(64) not null,
    relative_path varchar(512) not null,
    sha256 varchar(64) not null,
    row_count integer not null,
    min_date varchar(16),
    max_date varchar(16),
    size_bytes integer not null,
    created_at varchar(64) not null,
    unique(feature_set_id, relative_path)
);

create table if not exists ml_feature_sets (
    id varchar(64) primary key,
    fingerprint varchar(64) not null unique,
    universe_code varchar(32) not null,
    start_date varchar(16) not null,
    end_date varchar(16) not null,
    feature_version varchar(64) not null,
    status varchar(32) not null,
    row_count integer not null default 0,
    symbol_count integer not null default 0,
    feature_count integer not null default 0,
    manifest_json text not null,
    coverage_json text not null,
    created_at varchar(64) not null,
    completed_at varchar(64)
);

create table if not exists ml_prediction_files (
    id varchar(64) primary key,
    training_run_id varchar(64) not null,
    split_key varchar(64) not null,
    relative_path varchar(1024) not null,
    sha256 varchar(64) not null,
    row_count integer not null,
    metrics_json text not null,
    created_at varchar(64) not null,
    unique(training_run_id, split_key)
);

create table if not exists ml_training_runs (
    id varchar(64) primary key,
    research_run_id varchar(64) not null unique,
    feature_set_id varchar(64),
    status varchar(32) not null,
    stage varchar(64) not null,
    progress double precision not null default 0,
    mlflow_run_id varchar(128),
    mlflow_experiment varchar(255),
    registered_model_name varchar(255),
    registered_model_version varchar(64),
    selected_trial_id varchar(64),
    metrics_json text not null,
    quality_json text not null,
    fold_plan_json text not null,
    artifacts_json text not null,
    error text,
    created_at varchar(64) not null,
    started_at varchar(64),
    finished_at varchar(64),
    updated_at varchar(64) not null
);

create table if not exists ml_training_trials (
    id varchar(64) primary key,
    training_run_id varchar(64) not null,
    fold_index integer not null,
    candidate_index integer not null,
    status varchar(32) not null,
    parameters_json text not null,
    metrics_json text not null,
    best_iteration integer,
    mlflow_run_id varchar(128),
    selected integer not null default 0,
    created_at varchar(64) not null,
    finished_at varchar(64),
    unique(training_run_id, fold_index, candidate_index)
);

create table if not exists object_store_items (
                "key" text primary key,
                file_path text not null,
                stored_object_id text,
                size integer not null,
                updated_at text not null
            );

create table if not exists oos_evaluations (
    id varchar(64) primary key,
    window_id varchar(64) not null,
    selected_candidate_id varchar(64) not null,
    oos_item_id varchar(64) not null,
    oos_run_id varchar(128),
    input_fingerprint varchar(64) not null,
    result_digest varchar(64),
    metrics_json text,
    status varchar(32) not null,
    created_at varchar(64) not null,
    completed_at varchar(64),
    unique(window_id),
    unique(oos_item_id)
);

create table if not exists paper_accounts (
    id varchar(64) primary key,
    shadow_session_id varchar(64) not null,
    name varchar(191) not null,
    description varchar(1024),
    status varchar(32) not null,
    market_scope varchar(32) not null,
    base_currency varchar(16) not null,
    initial_cash decimal(28,8) not null,
    benchmark_symbol varchar(64) not null,
    execution_mode varchar(32) not null,
    current_generation integer not null default 1,
    active_risk_profile_id varchar(64),
    version integer not null default 1,
    metadata_json text not null,
    created_at varchar(64) not null,
    updated_at varchar(64) not null,
    activated_at varchar(64),
    paused_at varchar(64),
    archived_at varchar(64),
    unique(shadow_session_id)
);

create table if not exists paper_certification_cohorts (
    id varchar(64) primary key,
    name varchar(191) not null,
    status varchar(32) not null,
    required_accounts integer not null default 2,
    required_sessions integer not null default 21,
    contract_json text not null,
    evidence_digest varchar(64),
    created_at varchar(64) not null,
    refreshed_at varchar(64),
    certified_at varchar(64)
);

create table if not exists paper_certification_members (
    id varchar(64) primary key,
    cohort_id varchar(64) not null,
    paper_account_id varchar(64) not null,
    account_generation integer not null,
    opening_cash decimal(28,8) not null,
    risk_profile_id varchar(64),
    deployment_id varchar(64),
    strategy_fingerprint varchar(128),
    dataset_fingerprint varchar(128),
    execution_mode varchar(32) not null,
    evidence_json text,
    evidence_digest varchar(64),
    certified_sessions integer not null default 0,
    status varchar(32) not null default 'collecting',
    added_at varchar(64) not null,
    refreshed_at varchar(64),
    unique(cohort_id, paper_account_id)
);

create table if not exists paper_constraint_decisions (
    id varchar(64) primary key,
    intent_id varchar(64) not null,
    decision varchar(16) not null,
    constraint_version varchar(64) not null,
    rule_code varchar(64),
    rule_inputs_json text not null,
    portfolio_snapshot_json text not null,
    reference_data_version varchar(255) not null,
    rules_json text not null,
    decision_digest varchar(64) not null,
    decision_timestamp varchar(64) not null,
    unique(intent_id),
    unique(decision_digest)
);

create table if not exists paper_daily_job_events (
    id varchar(64) primary key,
    job_id varchar(64) not null,
    sequence integer not null,
    from_state varchar(48),
    to_state varchar(48) not null,
    event_type varchar(64) not null,
    payload_json text not null,
    correlation_id varchar(128) not null,
    created_at varchar(64) not null,
    unique(job_id, sequence)
);

create table if not exists paper_daily_jobs (
    id varchar(64) primary key,
    session_id varchar(64) not null,
    trade_date varchar(32) not null,
    state varchar(48) not null,
    attempt integer not null default 0,
    max_attempts integer not null default 3,
    version integer not null default 1,
    paper_run_id varchar(64),
    task_id varchar(64),
    lease_holder varchar(128),
    lease_expires_at varchar(64),
    completion_marker varchar(128),
    correlation_id varchar(128) not null,
    last_error text,
    scheduled_at varchar(64) not null,
    started_at varchar(64),
    completed_at varchar(64),
    updated_at varchar(64) not null, quarantined_at varchar(64), quarantine_reason varchar(255),
    unique(session_id, trade_date),
    unique(completion_marker)
);

create table if not exists paper_daily_reports (
                id text primary key,
                session_id text not null,
                trade_date text not null,
                report_json text not null,
                signals_json text not null,
                orders_json text not null,
                trades_json text not null,
                rejects_json text not null,
                positions_json text not null,
                snapshot_json text not null,
                benchmark_json text not null,
                qa_json text not null,
                created_at text not null,
                unique(session_id, trade_date)
            );

create table if not exists paper_lean_order_events (
    id text primary key,
    session_id text not null,
    paper_run_id text not null,
    backtest_run_id text not null,
    event_key text not null,
    trade_date text not null,
    event_json text not null,
    created_at text not null,
    unique(session_id, event_key)
);

create table if not exists paper_ledger_entries (
    id varchar(64) primary key,
    session_id varchar(64) not null,
    intent_id varchar(64) not null,
    fill_id varchar(64),
    entry_type varchar(32) not null,
    asset varchar(32) not null,
    symbol varchar(64),
    quantity double precision not null default 0,
    amount double precision not null default 0,
    currency varchar(16) not null,
    idempotency_key varchar(255) not null,
    created_at varchar(64) not null, event_id varchar(64), trade_date varchar(32), debit_account varchar(128), credit_account varchar(128), correction_entry_id varchar(64), reversal_entry_id varchar(64), paper_account_id varchar(64), account_generation integer, execution_cycle_id varchar(64), ledger_sequence integer, precise_quantity decimal(28,8), precise_amount decimal(28,8),
    unique(session_id, idempotency_key)
);

create table if not exists paper_order_fills (
    id varchar(64) primary key,
    intent_id varchar(64) not null,
    external_fill_key varchar(255) not null,
    trade_date varchar(32) not null,
    quantity double precision not null,
    price double precision not null,
    fee double precision not null default 0,
    payload_json text not null,
    created_at varchar(64) not null, tax double precision not null default 0, slippage double precision not null default 0, fee_model_version varchar(64), matching_contract varchar(64), fill_fingerprint varchar(64), paper_account_id varchar(64), execution_cycle_id varchar(64), precise_quantity decimal(28,8), precise_price decimal(28,8), commission decimal(28,8), stamp_duty decimal(28,8), transfer_fee decimal(28,8), precise_slippage decimal(28,8),
    unique(intent_id, external_fill_key)
);

create table if not exists paper_order_intents (
    id varchar(64) primary key,
    session_id varchar(64) not null,
    paper_run_id varchar(64) not null,
    backtest_run_id varchar(128) not null,
    event_key varchar(128) not null,
    idempotency_key varchar(255) not null,
    correlation_id varchar(128) not null,
    version integer not null default 1,
    attempt integer not null default 1,
    trade_date varchar(32) not null,
    symbol varchar(64) not null,
    side varchar(16) not null,
    quantity double precision not null,
    requested_price double precision,
    raw_intent_json text not null,
    created_at varchar(64) not null, lean_run_id varchar(128), lean_order_id varchar(128), project_snapshot_id varchar(128), project_snapshot_hash varchar(128), strategy_fingerprint varchar(128), order_type varchar(32), limit_price double precision, stop_price double precision, signal_time varchar(64), requested_execution_time varchar(64), dataset_version varchar(255), universe_version varchar(255), constraint_version varchar(64), paper_account_id varchar(64), deployment_id varchar(64), execution_cycle_id varchar(64), account_generation integer, precise_quantity decimal(28,8), precise_requested_price decimal(28,8),
    unique(session_id, idempotency_key),
    unique(session_id, event_key)
);

create table if not exists paper_order_transitions (
    id varchar(64) primary key,
    intent_id varchar(64) not null,
    sequence integer not null,
    from_state varchar(32),
    to_state varchar(32) not null,
    event_type varchar(64) not null,
    idempotency_key varchar(255) not null,
    correlation_id varchar(128) not null,
    version integer not null default 1,
    attempt integer not null default 1,
    payload_json text not null,
    created_at varchar(64) not null,
    unique(intent_id, sequence),
    unique(intent_id, idempotency_key)
);

create table if not exists paper_orders (
                id text primary key,
                session_id text not null,
                signal_id text,
                trade_date text not null,
                symbol text not null,
                side text not null,
                quantity double precision not null,
                order_price double precision,
                fill_price double precision,
                fee double precision not null default 0,
                status text not null,
                reason text,
                created_at text not null,
                filled_at text
            );

create table if not exists paper_portfolio_snapshots (
                id text primary key,
                session_id text not null,
                trade_date text not null,
                cash double precision not null,
                market_value double precision not null,
                equity double precision not null,
                positions_json text not null,
                benchmark_symbol text,
                benchmark_close double precision,
                benchmark_return double precision,
                created_at text not null,
                unique(session_id, trade_date)
            );

create table if not exists paper_positions (
                session_id text not null,
                symbol text not null,
                quantity double precision not null,
                average_price double precision not null,
                market_price double precision,
                market_value double precision,
                last_buy_date text,
                updated_at text not null,
                primary key (session_id, symbol)
            );

create table if not exists paper_reconciliation_records (
    id varchar(64) primary key,
    session_id varchar(64) not null,
    paper_run_id varchar(64) not null,
    trade_date varchar(32) not null,
    status varchar(32) not null,
    opening_cash double precision not null,
    ledger_cash_movement double precision not null,
    closing_cash double precision not null,
    cash_drift double precision not null,
    position_drift double precision not null,
    order_fill_ok integer not null,
    fill_ledger_ok integer not null,
    ledger_cash_ok integer not null,
    ledger_positions_ok integer not null,
    snapshot_ok integer not null,
    daily_report_ok integer not null,
    invariants_json text not null,
    result_digest varchar(64) not null,
    created_at varchar(64) not null, quarantined_at varchar(64), quarantine_reason varchar(255),
    unique(session_id, trade_date),
    unique(paper_run_id),
    unique(result_digest)
);

create table if not exists paper_run_checkpoints (
    id varchar(64) primary key,
    paper_run_id varchar(64) not null,
    phase varchar(64) not null,
    status varchar(32) not null,
    digest varchar(128),
    payload_json text not null,
    created_at varchar(64) not null,
    completed_at varchar(64),
    unique(paper_run_id, phase)
);

create table if not exists paper_sessions (
                id text primary key,
                project_id text,
                name text not null,
                status text not null,
                symbol text not null,
                asset_class text not null,
                venue text not null,
                resolution text not null,
                cash double precision not null,
                equity double precision not null,
                parameters_json text not null,
                created_at text not null,
                updated_at text not null,
                finished_at text
            , mode text not null default 'legacy_replay', legacy_read_only integer not null default 1, source_backtest_id text, strategy_version_id text, parameter_hash text, start_date text, last_processed_date text, auto_advance integer not null default 0, failure_json text, pipeline_version integer not null default 1);

create table if not exists paper_signals (
                id text primary key,
                session_id text not null,
                trade_date text not null,
                symbol text not null,
                side text not null,
                target_percent double precision,
                strength double precision,
                reason text,
                status text not null,
                source text not null,
                created_at text not null
            );

create table if not exists paper_universe_certifications (
                id text primary key,
                universe_code text not null,
                source text not null,
                benchmark_symbol text not null,
                certification_status text not null,
                certification_date text not null,
                start_date text not null,
                end_date text not null,
                target_size integer not null,
                min_size integer not null,
                symbol_count integer not null default 0,
                coverage_report_id text,
                qa_report_id text,
                valid_from text not null,
                valid_to text,
                coverage_json text not null,
                qa_report_json text not null,
                warnings_json text not null,
                errors_json text not null,
                created_at text not null,
                updated_at text not null,
                unique(universe_code, source, start_date, end_date)
            );

create table if not exists paper_universe_symbols (
                id text primary key,
                universe_code text not null,
                symbol text not null,
                source text not null,
                certification_status text not null,
                certification_date text not null,
                coverage_report_id text,
                qa_report_id text,
                valid_from text not null,
                valid_to text,
                coverage_json text not null,
                qa_json text not null,
                warnings_json text not null,
                errors_json text not null,
                created_at text not null,
                updated_at text not null,
                unique(universe_code, symbol, valid_from)
            );

create table if not exists paper_walkforward_runs (
    id text primary key,
    session_id text not null,
    trade_date text not null,
    backtest_run_id text,
    task_id text,
    status text not null,
    order_fingerprint text,
    reconciliation_json text,
    failure_json text,
    created_at text not null,
    started_at text,
    finished_at text,
    unique(session_id, trade_date)
);

create table if not exists parameter_candidates (
    id varchar(64) primary key,
    window_id varchar(64) not null,
    candidate_key varchar(255) not null,
    parameters_json text not null,
    train_item_id varchar(64),
    validation_item_id varchar(64),
    validation_return double,
    validation_sharpe double,
    validation_max_drawdown double,
    validation_trade_count integer,
    validation_turnover double,
    constraint_violations integer not null default 0,
    selected integer not null default 0,
    not_selected_reason varchar(255),
    created_at varchar(64) not null,
    updated_at varchar(64) not null,
    unique(window_id, candidate_key)
);

create table if not exists parameter_selection_events (
    id varchar(64) primary key,
    window_id varchar(64) not null,
    selected_candidate_id varchar(64) not null,
    selection_metric varchar(64) not null,
    tie_break_rule varchar(255) not null,
    selected_parameters_json text not null,
    candidate_ranking_json text not null,
    selection_timestamp varchar(64) not null,
    selection_fingerprint varchar(64) not null,
    unique(window_id),
    unique(selection_fingerprint)
);

create table if not exists parquet_datasets (
                id text primary key,
                dataset_key text not null unique,
                asset_class text not null,
                market text not null,
                venue text,
                resolution text not null,
                data_type text not null default 'trade',
                adjust text not null default 'raw',
                source text not null,
                root_path text not null,
                schema_version integer not null default 1,
                start_date text,
                end_date text,
                row_count integer not null default 0,
                file_count integer not null default 0,
                metadata_json text not null,
                created_at text not null,
                updated_at text not null
            , dataset_version varchar(96), environment varchar(32) not null default 'research', is_production integer not null default 0, is_certified integer not null default 0, certified_at varchar(32), certified_by varchar(96), coverage_start varchar(32), coverage_end varchar(32), qa_status varchar(32), qa_report_id varchar(64), dataset_release_id varchar(96));

create table if not exists parquet_files (
                id text primary key,
                dataset_id text not null,
                file_path text not null,
                partition_json text not null,
                row_count integer not null,
                first_timestamp text,
                last_timestamp text,
                sha256 text not null,
                size integer not null,
                created_at text not null
            );

create table if not exists pipeline_runs (
                id text primary key,
                universe_code text,
                source text not null,
                benchmark_symbol text,
                status text not null,
                severity text not null,
                decision text,
                started_at text not null,
                finished_at text,
                duration_seconds double precision,
                artifact_dir text,
                artifact_object_id text,
                summary_json text not null,
                warnings_json text not null,
                errors_json text not null
            );

create table if not exists pipeline_steps (
                id text primary key,
                run_id text not null,
                step_name text not null,
                status text not null,
                started_at text not null,
                finished_at text,
                duration_seconds double precision,
                warnings_json text not null,
                errors_json text not null,
                details_json text not null
            );

create table if not exists portfolio_optimization_runs (
    id varchar(64) primary key,
    name varchar(255) not null,
    status varchar(32) not null,
    objective varchar(32) not null,
    run_ids_json text not null,
    constraints_json text not null,
    input_fingerprints_json text not null,
    result_json text,
    base_currency varchar(16),
    resolution varchar(32),
    error text,
    archived_at varchar(64),
    created_at varchar(64) not null,
    started_at varchar(64),
    finished_at varchar(64)
);

create table if not exists projects (
                id text primary key,
                name text not null,
                language text not null,
                algorithm_class text not null,
                project_path text not null,
                main_file text not null,
                config_json text not null,
                created_at text not null,
                updated_at text not null
            , archived_at varchar(64));

create table if not exists provider_availability_log (
                id text primary key,
                provider text not null,
                status text not null,
                installed integer not null default 0,
                configured integer not null default 0,
                credentials_status text not null,
                unavailable_reason text,
                supported_endpoints_json text not null,
                coverage_json text not null,
                production_certified integer not null default 0,
                checked_at text not null,
                metadata_json text not null
            );

create table if not exists provider_dataset_catalog (
    provider text not null,
    dataset_key text not null,
    api_name text not null,
    category text not null,
    scope_type text not null,
    cadence text not null,
    permission_status text not null default 'unknown',
    permission_reason text,
    row_count integer not null default 0,
    first_data_date text,
    last_data_date text,
    last_checked_at text,
    last_synced_at text,
    checkpoint_json text,
    metadata_json text, sync_policy text, skip_reason text, rate_limit_per_hour integer, next_allowed_at text,
    primary key (provider, dataset_key)
);

create table if not exists provider_dataset_watermarks (
    provider text not null,
    dataset_key text not null,
    scope_key text not null,
    coverage_start text,
    coverage_end text,
    last_data_date text,
    last_run_id text,
    empty_result integer not null default 0,
    validation_status text not null default 'unknown',
    updated_at text not null,
    primary key (provider, dataset_key, scope_key)
);

create table if not exists provider_ingestion_manifests (
    id text primary key,
    run_id text not null,
    provider text not null,
    dataset_key text not null,
    scope_key text not null,
    request_json text not null,
    response_rows integer not null default 0,
    normalized_rows integer not null default 0,
    rejected_rows integer not null default 0,
    payload_sha256 text not null,
    keys_sha256 text not null,
    coverage_start text,
    coverage_end text,
    status text not null,
    validation_json text not null,
    endpoint_counts_json text not null,
    created_at text not null
);

create table if not exists provider_raw_archive_issues (
    archive_id text primary key,
    provider text not null,
    dataset_key text not null,
    run_id text not null,
    object_id text not null,
    row_count integer not null,
    payload_sha256 text not null,
    archive_sha256 text not null,
    uncompressed_size integer not null,
    compressed_size integer not null,
    compression text not null,
    archive_created_at text not null,
    issue_code text not null,
    detected_at text not null
, status text not null default 'open', resolution_code text, resolution_run_id text, resolution_evidence_json text, resolved_at text);

create table if not exists provider_raw_archives (
    id text primary key,
    provider text not null,
    dataset_key text not null,
    run_id text not null,
    object_id text not null,
    row_count integer not null,
    payload_sha256 text not null,
    archive_sha256 text not null,
    uncompressed_size integer not null,
    compressed_size integer not null,
    compression text not null,
    created_at text not null,
    unique(provider, dataset_key, run_id, payload_sha256)
);

create table if not exists provider_raw_records (
    provider text not null,
    dataset_key text not null,
    record_key text not null,
    business_date text,
    instrument_code text,
    payload_json text not null,
    content_sha256 text not null,
    batch_id text,
    source_updated_at text,
    ingested_at text not null,
    primary key (provider, dataset_key, record_key)
);

create table if not exists qa_warning_allowlist (
                id text primary key,
                warning_code text not null,
                reason text not null,
                valid_until text not null,
                approved_by text not null,
                affected_symbols_json text not null,
                scope_json text not null,
                status text not null default 'active',
                created_at text not null,
                updated_at text not null
            );

create table if not exists qlib_research_imports (
    id varchar(64) primary key,
    research_run_id varchar(64) not null unique,
    external_run_id varchar(128) not null unique,
    schema_version varchar(32) not null,
    run_kind varchar(64) not null,
    dataset_fingerprint varchar(128) not null,
    model_fingerprint varchar(128) not null,
    manifest_sha256 varchar(64) not null,
    manifest_json text not null,
    object_keys_json text not null,
    created_at varchar(64) not null
, data_release_id varchar(96), root_artifact_ids_json text);

create table if not exists qlib_signal_snapshots (
    id varchar(64) primary key,
    import_id varchar(64) not null,
    research_run_id varchar(64) not null,
    model_fingerprint varchar(128) not null,
    dataset_fingerprint varchar(128) not null,
    signal_date varchar(16) not null,
    trade_date varchar(16) not null,
    targets_sha256 varchar(64) not null,
    target_count integer not null,
    gross_exposure double precision not null,
    targets_json text not null,
    created_at varchar(64) not null, target_artifact_id varchar(128),
    unique(model_fingerprint, dataset_fingerprint, signal_date)
);

create table if not exists recording_jobs (
                id text primary key,
                name text not null,
                asset_class text not null,
                market text not null,
                venue text,
                symbols_json text not null,
                frequency text,
                status text not null,
                source text not null,
                parameters_json text not null,
                created_at text not null,
                updated_at text not null
            );

create table if not exists recording_status (
                job_id text primary key,
                status text not null,
                last_event_at text,
                last_bar_at text,
                last_error text,
                updated_at text not null
            );

create table if not exists reports (
                id text primary key,
                task_id text,
                run_id text not null,
                status text not null,
                report_path text,
                error text,
                created_at text not null,
                finished_at text
            );

create table if not exists research_run_items (
                id text primary key,
                run_id text not null,
                item_index integer not null,
                item_key text not null,
                status text not null,
                parameters_json text not null,
                result_json text,
                error text,
                created_at text not null,
                started_at text,
                finished_at text,
                unique(run_id, item_key)
            );

create table if not exists research_runs (
                id text primary key,
                task_id text,
                template_key text not null,
                name text not null,
                status text not null,
                scope_json text not null,
                parameters_json text not null,
                result_json text,
                summary_json text,
                data_fingerprint text,
                source_research_run_id text,
                error text,
                cancel_requested integer not null default 0,
                created_at text not null,
                started_at text,
                finished_at text
            , owner_heartbeat_at varchar(64), recovery_reason varchar(255));

create table if not exists research_sessions (
                id text primary key,
                task_id text,
                project_id text,
                status text not null,
                port integer not null,
                container_id text,
                url text,
                log_path text,
                error text,
                created_at text not null,
                started_at text,
                finished_at text
            , readiness_status text, container_status text, workspace_path text, last_checked_at text, project_name text);

create table if not exists research_workspaces (
                id text primary key,
                task_id text,
                project_id text,
                status text not null,
                port integer not null,
                container_id text,
                url text,
                log_path text,
                error text,
                created_at text not null,
                started_at text,
                finished_at text,
                readiness_status text,
                container_status text,
                workspace_path text,
                last_checked_at text,
                project_name text,
                snapshot_id text
            , execution_backend varchar(32), execution_id varchar(128), runtime_identity_json text);

create table if not exists restricted_runner_jobs (
    id varchar(64) primary key,
    run_id varchar(128) not null,
    spec_digest varchar(64) not null,
    image_digest varchar(255) not null,
    command_json text not null,
    mounts_json text not null,
    resource_limits_json text not null,
    network_policy varchar(32) not null,
    status varchar(32) not null,
    exit_code integer,
    timed_out integer not null default 0,
    error text,
    created_at varchar(64) not null,
    started_at varchar(64),
    finished_at varchar(64), execution_backend varchar(32), execution_id varchar(128), runtime_ref varchar(512), runtime_digest varchar(64), runtime_identity_json text, sandbox_json text,
    unique(run_id),
    unique(spec_digest)
);

create table if not exists scheduler_leases (
                id text primary key,
                resource text not null,
                slot_index integer not null,
                holder_id text not null,
                limit_count integer not null,
                acquired_at text not null,
                expires_at text not null,
                metadata_json text not null,
                unique(resource, holder_id),
                unique(resource, slot_index)
            );

create table if not exists securities (
                symbol text primary key,
                name text not null,
                exchange text not null,
                market text not null default 'china',
                listed_date text not null,
                delisted_date text,
                status text not null default 'listed',
                is_st integer not null default 0,
                industry text,
                concepts_json text,
                created_at text not null,
                updated_at text not null
            );

create table if not exists security_name_history (
    id varchar(64) primary key,
    symbol varchar(32) not null,
    name varchar(255) not null,
    start_date varchar(16) not null,
    end_date varchar(16),
    is_st integer not null default 0,
    source varchar(32) not null,
    payload_hash varchar(64) not null,
    created_at varchar(64) not null,
    unique(symbol, start_date, name)
);

create table if not exists settings (
                "key" text primary key,
                value_json text not null,
                updated_at text not null
            );

create table if not exists "src_tushare_bak_basic" (
    "_observation_id" varchar(64) primary key,
    "_batch_id" varchar(64) not null,
    "_natural_key_hash" varchar(64) not null,
    "_revision_no" integer not null,
    "_is_current" integer not null default 1,
    "_current_natural_key_hash" varchar(64) generated always as (case when "_is_current" = 1 then "_natural_key_hash" else null end) stored,
    "_published_at" text,
    "_source_updated_at" text,
    "_observed_at" text not null,
    "_valid_from" text,
    "_valid_to" text,
    "_payload_hash" varchar(64) not null,
    "trade_date" date,
    "ts_code" text,
    "name" text,
    "industry" text,
    "area" text,
    "pe" decimal(38,8),
    "float_share" decimal(38,8),
    "total_share" decimal(38,8),
    "total_assets" decimal(38,8),
    "liquid_assets" decimal(38,8),
    "fixed_assets" decimal(38,8),
    "reserved" decimal(38,8),
    "reserved_pershare" decimal(38,8),
    "eps" decimal(38,8),
    "bvps" decimal(38,8),
    "pb" decimal(38,8),
    "list_date" date,
    "undp" decimal(38,8),
    "per_undp" decimal(38,8),
    "rev_yoy" decimal(38,8),
    "profit_yoy" decimal(38,8),
    "gpr" decimal(38,8),
    "npr" decimal(38,8),
    "holder_num" bigint,
    unique("_natural_key_hash","_revision_no"),
    unique("_current_natural_key_hash"),
    check ("_revision_no" > 0),
    check ("_is_current" in (0,1)),
    check ("_valid_to" is null or "_valid_from" is null or "_valid_to" >= "_valid_from")
);

create table if not exists "src_tushare_balancesheet" (
    "_observation_id" varchar(64) primary key,
    "_batch_id" varchar(64) not null,
    "_natural_key_hash" varchar(64) not null,
    "_revision_no" integer not null,
    "_is_current" integer not null default 1,
    "_current_natural_key_hash" varchar(64) generated always as (case when "_is_current" = 1 then "_natural_key_hash" else null end) stored,
    "_published_at" text,
    "_source_updated_at" text,
    "_observed_at" text not null,
    "_valid_from" text,
    "_valid_to" text,
    "_payload_hash" varchar(64) not null,
    "ts_code" text,
    "ann_date" date,
    "f_ann_date" date,
    "end_date" date,
    "report_type" text,
    "comp_type" text,
    "end_type" text,
    "total_share" decimal(38,8),
    "cap_rese" decimal(38,8),
    "undistr_porfit" decimal(38,8),
    "surplus_rese" decimal(38,8),
    "special_rese" decimal(38,8),
    "money_cap" decimal(38,8),
    "trad_asset" decimal(38,8),
    "notes_receiv" decimal(38,8),
    "accounts_receiv" decimal(38,8),
    "oth_receiv" decimal(38,8),
    "prepayment" decimal(38,8),
    "div_receiv" decimal(38,8),
    "int_receiv" decimal(38,8),
    "inventories" decimal(38,8),
    "amor_exp" decimal(38,8),
    "nca_within_1y" decimal(38,8),
    "sett_rsrv" decimal(38,8),
    "loanto_oth_bank_fi" decimal(38,8),
    "premium_receiv" decimal(38,8),
    "reinsur_receiv" decimal(38,8),
    "reinsur_res_receiv" decimal(38,8),
    "pur_resale_fa" decimal(38,8),
    "oth_cur_assets" decimal(38,8),
    "total_cur_assets" decimal(38,8),
    "fa_avail_for_sale" decimal(38,8),
    "htm_invest" decimal(38,8),
    "lt_eqt_invest" decimal(38,8),
    "invest_real_estate" decimal(38,8),
    "time_deposits" text,
    "oth_assets" decimal(38,8),
    "lt_rec" decimal(38,8),
    "fix_assets" decimal(38,8),
    "cip" decimal(38,8),
    "const_materials" decimal(38,8),
    "fixed_assets_disp" decimal(38,8),
    "produc_bio_assets" decimal(38,8),
    "oil_and_gas_assets" decimal(38,8),
    "intan_assets" decimal(38,8),
    "r_and_d" decimal(38,8),
    "goodwill" decimal(38,8),
    "lt_amor_exp" decimal(38,8),
    "defer_tax_assets" decimal(38,8),
    "decr_in_disbur" decimal(38,8),
    "oth_nca" decimal(38,8),
    "total_nca" decimal(38,8),
    "cash_reser_cb" decimal(38,8),
    "depos_in_oth_bfi" decimal(38,8),
    "prec_metals" decimal(38,8),
    "deriv_assets" decimal(38,8),
    "rr_reins_une_prem" decimal(38,8),
    "rr_reins_outstd_cla" decimal(38,8),
    "rr_reins_lins_liab" decimal(38,8),
    "rr_reins_lthins_liab" decimal(38,8),
    "refund_depos" decimal(38,8),
    "ph_pledge_loans" decimal(38,8),
    "refund_cap_depos" decimal(38,8),
    "indep_acct_assets" decimal(38,8),
    "client_depos" decimal(38,8),
    "client_prov" decimal(38,8),
    "transac_seat_fee" decimal(38,8),
    "invest_as_receiv" decimal(38,8),
    "total_assets" decimal(38,8),
    "lt_borr" decimal(38,8),
    "st_borr" decimal(38,8),
    "cb_borr" decimal(38,8),
    "depos_ib_deposits" decimal(38,8),
    "loan_oth_bank" decimal(38,8),
    "trading_fl" decimal(38,8),
    "notes_payable" decimal(38,8),
    "acct_payable" decimal(38,8),
    "adv_receipts" decimal(38,8),
    "sold_for_repur_fa" decimal(38,8),
    "comm_payable" decimal(38,8),
    "payroll_payable" decimal(38,8),
    "taxes_payable" decimal(38,8),
    "int_payable" decimal(38,8),
    "div_payable" decimal(38,8),
    "oth_payable" decimal(38,8),
    "acc_exp" decimal(38,8),
    "deferred_inc" decimal(38,8),
    "st_bonds_payable" decimal(38,8),
    "payable_to_reinsurer" decimal(38,8),
    "rsrv_insur_cont" decimal(38,8),
    "acting_trading_sec" decimal(38,8),
    "acting_uw_sec" decimal(38,8),
    "non_cur_liab_due_1y" decimal(38,8),
    "oth_cur_liab" decimal(38,8),
    "total_cur_liab" decimal(38,8),
    "bond_payable" decimal(38,8),
    "lt_payable" decimal(38,8),
    "specific_payables" decimal(38,8),
    "estimated_liab" decimal(38,8),
    "defer_tax_liab" decimal(38,8),
    "defer_inc_non_cur_liab" decimal(38,8),
    "oth_ncl" decimal(38,8),
    "total_ncl" decimal(38,8),
    "depos_oth_bfi" decimal(38,8),
    "deriv_liab" decimal(38,8),
    "depos" decimal(38,8),
    "agency_bus_liab" decimal(38,8),
    "oth_liab" decimal(38,8),
    "prem_receiv_adva" decimal(38,8),
    "depos_received" decimal(38,8),
    "ph_invest" decimal(38,8),
    "reser_une_prem" decimal(38,8),
    "reser_outstd_claims" decimal(38,8),
    "reser_lins_liab" decimal(38,8),
    "reser_lthins_liab" decimal(38,8),
    "indept_acc_liab" decimal(38,8),
    "pledge_borr" decimal(38,8),
    "indem_payable" decimal(38,8),
    "policy_div_payable" decimal(38,8),
    "total_liab" decimal(38,8),
    "treasury_share" decimal(38,8),
    "ordin_risk_reser" decimal(38,8),
    "forex_differ" decimal(38,8),
    "invest_loss_unconf" decimal(38,8),
    "minority_int" decimal(38,8),
    "total_hldr_eqy_exc_min_int" decimal(38,8),
    "total_hldr_eqy_inc_min_int" decimal(38,8),
    "total_liab_hldr_eqy" decimal(38,8),
    "lt_payroll_payable" decimal(38,8),
    "oth_comp_income" decimal(38,8),
    "oth_eqt_tools" decimal(38,8),
    "oth_eqt_tools_p_shr" decimal(38,8),
    "lending_funds" decimal(38,8),
    "acc_receivable" decimal(38,8),
    "st_fin_payable" decimal(38,8),
    "payables" decimal(38,8),
    "hfs_assets" decimal(38,8),
    "hfs_sales" decimal(38,8),
    "cost_fin_assets" decimal(38,8),
    "fair_value_fin_assets" decimal(38,8),
    "cip_total" decimal(38,8),
    "oth_pay_total" decimal(38,8),
    "long_pay_total" decimal(38,8),
    "debt_invest" decimal(38,8),
    "oth_debt_invest" decimal(38,8),
    "oth_eq_invest" decimal(38,8),
    "oth_illiq_fin_assets" decimal(38,8),
    "oth_eq_ppbond" decimal(38,8),
    "receiv_financing" decimal(38,8),
    "use_right_assets" decimal(38,8),
    "lease_liab" decimal(38,8),
    "contract_assets" decimal(38,8),
    "contract_liab" decimal(38,8),
    "accounts_receiv_bill" decimal(38,8),
    "accounts_pay" decimal(38,8),
    "oth_rcv_total" decimal(38,8),
    "fix_assets_total" decimal(38,8),
    "update_flag" text,
    unique("_natural_key_hash","_revision_no"),
    unique("_current_natural_key_hash"),
    check ("_revision_no" > 0),
    check ("_is_current" in (0,1)),
    check ("_valid_to" is null or "_valid_from" is null or "_valid_to" >= "_valid_from")
);

create table if not exists "src_tushare_block_trade" (
    "_observation_id" varchar(64) primary key,
    "_batch_id" varchar(64) not null,
    "_natural_key_hash" varchar(64) not null,
    "_revision_no" integer not null,
    "_is_current" integer not null default 1,
    "_current_natural_key_hash" varchar(64) generated always as (case when "_is_current" = 1 then "_natural_key_hash" else null end) stored,
    "_published_at" text,
    "_source_updated_at" text,
    "_observed_at" text not null,
    "_valid_from" text,
    "_valid_to" text,
    "_payload_hash" varchar(64) not null,
    "ts_code" text,
    "trade_date" date,
    "price" decimal(38,8),
    "vol" decimal(38,8),
    "amount" decimal(38,8),
    "buyer" text,
    "seller" text,
    unique("_natural_key_hash","_revision_no"),
    unique("_current_natural_key_hash"),
    check ("_revision_no" > 0),
    check ("_is_current" in (0,1)),
    check ("_valid_to" is null or "_valid_from" is null or "_valid_to" >= "_valid_from")
);

create table if not exists "src_tushare_broker_recommend" (
    "_observation_id" varchar(64) primary key,
    "_batch_id" varchar(64) not null,
    "_natural_key_hash" varchar(64) not null,
    "_revision_no" integer not null,
    "_is_current" integer not null default 1,
    "_current_natural_key_hash" varchar(64) generated always as (case when "_is_current" = 1 then "_natural_key_hash" else null end) stored,
    "_published_at" text,
    "_source_updated_at" text,
    "_observed_at" text not null,
    "_valid_from" text,
    "_valid_to" text,
    "_payload_hash" varchar(64) not null,
    "month" text,
    "broker" text,
    "ts_code" text,
    "name" text,
    unique("_natural_key_hash","_revision_no"),
    unique("_current_natural_key_hash"),
    check ("_revision_no" > 0),
    check ("_is_current" in (0,1)),
    check ("_valid_to" is null or "_valid_from" is null or "_valid_to" >= "_valid_from")
);

create table if not exists "src_tushare_bse_mapping" (
    "_observation_id" varchar(64) primary key,
    "_batch_id" varchar(64) not null,
    "_natural_key_hash" varchar(64) not null,
    "_revision_no" integer not null,
    "_is_current" integer not null default 1,
    "_current_natural_key_hash" varchar(64) generated always as (case when "_is_current" = 1 then "_natural_key_hash" else null end) stored,
    "_published_at" text,
    "_source_updated_at" text,
    "_observed_at" text not null,
    "_valid_from" text,
    "_valid_to" text,
    "_payload_hash" varchar(64) not null,
    "name" text,
    "o_code" text,
    "n_code" text,
    "list_date" date,
    unique("_natural_key_hash","_revision_no"),
    unique("_current_natural_key_hash"),
    check ("_revision_no" > 0),
    check ("_is_current" in (0,1)),
    check ("_valid_to" is null or "_valid_from" is null or "_valid_to" >= "_valid_from")
);

create table if not exists "src_tushare_cashflow" (
    "_observation_id" varchar(64) primary key,
    "_batch_id" varchar(64) not null,
    "_natural_key_hash" varchar(64) not null,
    "_revision_no" integer not null,
    "_is_current" integer not null default 1,
    "_current_natural_key_hash" varchar(64) generated always as (case when "_is_current" = 1 then "_natural_key_hash" else null end) stored,
    "_published_at" text,
    "_source_updated_at" text,
    "_observed_at" text not null,
    "_valid_from" text,
    "_valid_to" text,
    "_payload_hash" varchar(64) not null,
    "ts_code" text,
    "ann_date" date,
    "f_ann_date" date,
    "end_date" date,
    "comp_type" text,
    "report_type" text,
    "end_type" text,
    "net_profit" decimal(38,8),
    "finan_exp" decimal(38,8),
    "c_fr_sale_sg" decimal(38,8),
    "recp_tax_rends" decimal(38,8),
    "n_depos_incr_fi" decimal(38,8),
    "n_incr_loans_cb" decimal(38,8),
    "n_inc_borr_oth_fi" decimal(38,8),
    "prem_fr_orig_contr" decimal(38,8),
    "n_incr_insured_dep" decimal(38,8),
    "n_reinsur_prem" decimal(38,8),
    "n_incr_disp_tfa" decimal(38,8),
    "ifc_cash_incr" decimal(38,8),
    "n_incr_disp_faas" decimal(38,8),
    "n_incr_loans_oth_bank" decimal(38,8),
    "n_cap_incr_repur" decimal(38,8),
    "c_fr_oth_operate_a" decimal(38,8),
    "c_inf_fr_operate_a" decimal(38,8),
    "c_paid_goods_s" decimal(38,8),
    "c_paid_to_for_empl" decimal(38,8),
    "c_paid_for_taxes" decimal(38,8),
    "n_incr_clt_loan_adv" decimal(38,8),
    "n_incr_dep_cbob" decimal(38,8),
    "c_pay_claims_orig_inco" decimal(38,8),
    "pay_handling_chrg" decimal(38,8),
    "pay_comm_insur_plcy" decimal(38,8),
    "oth_cash_pay_oper_act" decimal(38,8),
    "st_cash_out_act" decimal(38,8),
    "n_cashflow_act" decimal(38,8),
    "oth_recp_ral_inv_act" decimal(38,8),
    "c_disp_withdrwl_invest" decimal(38,8),
    "c_recp_return_invest" decimal(38,8),
    "n_recp_disp_fiolta" decimal(38,8),
    "n_recp_disp_sobu" decimal(38,8),
    "stot_inflows_inv_act" decimal(38,8),
    "c_pay_acq_const_fiolta" decimal(38,8),
    "c_paid_invest" decimal(38,8),
    "n_disp_subs_oth_biz" decimal(38,8),
    "oth_pay_ral_inv_act" decimal(38,8),
    "n_incr_pledge_loan" decimal(38,8),
    "stot_out_inv_act" decimal(38,8),
    "n_cashflow_inv_act" decimal(38,8),
    "c_recp_borrow" decimal(38,8),
    "proc_issue_bonds" decimal(38,8),
    "oth_cash_recp_ral_fnc_act" decimal(38,8),
    "stot_cash_in_fnc_act" decimal(38,8),
    "free_cashflow" decimal(38,8),
    "c_prepay_amt_borr" decimal(38,8),
    "c_pay_dist_dpcp_int_exp" decimal(38,8),
    "incl_dvd_profit_paid_sc_ms" decimal(38,8),
    "oth_cashpay_ral_fnc_act" decimal(38,8),
    "stot_cashout_fnc_act" decimal(38,8),
    "n_cash_flows_fnc_act" decimal(38,8),
    "eff_fx_flu_cash" decimal(38,8),
    "n_incr_cash_cash_equ" decimal(38,8),
    "c_cash_equ_beg_period" decimal(38,8),
    "c_cash_equ_end_period" decimal(38,8),
    "c_recp_cap_contrib" decimal(38,8),
    "incl_cash_rec_saims" decimal(38,8),
    "uncon_invest_loss" decimal(38,8),
    "prov_depr_assets" decimal(38,8),
    "depr_fa_coga_dpba" decimal(38,8),
    "amort_intang_assets" decimal(38,8),
    "lt_amort_deferred_exp" decimal(38,8),
    "decr_deferred_exp" decimal(38,8),
    "incr_acc_exp" decimal(38,8),
    "loss_disp_fiolta" decimal(38,8),
    "loss_scr_fa" decimal(38,8),
    "loss_fv_chg" decimal(38,8),
    "invest_loss" decimal(38,8),
    "decr_def_inc_tax_assets" decimal(38,8),
    "incr_def_inc_tax_liab" decimal(38,8),
    "decr_inventories" decimal(38,8),
    "decr_oper_payable" decimal(38,8),
    "incr_oper_payable" decimal(38,8),
    "others" decimal(38,8),
    "im_net_cashflow_oper_act" decimal(38,8),
    "conv_debt_into_cap" decimal(38,8),
    "conv_copbonds_due_within_1y" decimal(38,8),
    "fa_fnc_leases" decimal(38,8),
    "im_n_incr_cash_equ" decimal(38,8),
    "net_dism_capital_add" decimal(38,8),
    "net_cash_rece_sec" decimal(38,8),
    "credit_impa_loss" decimal(38,8),
    "use_right_asset_dep" decimal(38,8),
    "oth_loss_asset" decimal(38,8),
    "end_bal_cash" decimal(38,8),
    "beg_bal_cash" decimal(38,8),
    "end_bal_cash_equ" decimal(38,8),
    "beg_bal_cash_equ" decimal(38,8),
    "update_flag" text,
    unique("_natural_key_hash","_revision_no"),
    unique("_current_natural_key_hash"),
    check ("_revision_no" > 0),
    check ("_is_current" in (0,1)),
    check ("_valid_to" is null or "_valid_from" is null or "_valid_to" >= "_valid_from")
);

create table if not exists "src_tushare_ci_index_member" (
    "_observation_id" varchar(64) primary key,
    "_batch_id" varchar(64) not null,
    "_natural_key_hash" varchar(64) not null,
    "_revision_no" integer not null,
    "_is_current" integer not null default 1,
    "_current_natural_key_hash" varchar(64) generated always as (case when "_is_current" = 1 then "_natural_key_hash" else null end) stored,
    "_published_at" text,
    "_source_updated_at" text,
    "_observed_at" text not null,
    "_valid_from" text,
    "_valid_to" text,
    "_payload_hash" varchar(64) not null,
    "l1_code" text,
    "l1_name" text,
    "l2_code" text,
    "l2_name" text,
    "l3_code" text,
    "l3_name" text,
    "ts_code" text,
    "name" text,
    "in_date" date,
    "out_date" date,
    "is_new" text,
    unique("_natural_key_hash","_revision_no"),
    unique("_current_natural_key_hash"),
    check ("_revision_no" > 0),
    check ("_is_current" in (0,1)),
    check ("_valid_to" is null or "_valid_from" is null or "_valid_to" >= "_valid_from")
);

create table if not exists "src_tushare_cyq_chips" (
    "_observation_id" varchar(64) primary key,
    "_batch_id" varchar(64) not null,
    "_natural_key_hash" varchar(64) not null,
    "_revision_no" integer not null,
    "_is_current" integer not null default 1,
    "_current_natural_key_hash" varchar(64) generated always as (case when "_is_current" = 1 then "_natural_key_hash" else null end) stored,
    "_published_at" text,
    "_source_updated_at" text,
    "_observed_at" text not null,
    "_valid_from" text,
    "_valid_to" text,
    "_payload_hash" varchar(64) not null,
    "ts_code" text,
    "trade_date" date,
    "price" decimal(38,8),
    "percent" decimal(38,8),
    unique("_natural_key_hash","_revision_no"),
    unique("_current_natural_key_hash"),
    check ("_revision_no" > 0),
    check ("_is_current" in (0,1)),
    check ("_valid_to" is null or "_valid_from" is null or "_valid_to" >= "_valid_from")
);

create table if not exists "src_tushare_cyq_perf" (
    "_observation_id" varchar(64) primary key,
    "_batch_id" varchar(64) not null,
    "_natural_key_hash" varchar(64) not null,
    "_revision_no" integer not null,
    "_is_current" integer not null default 1,
    "_current_natural_key_hash" varchar(64) generated always as (case when "_is_current" = 1 then "_natural_key_hash" else null end) stored,
    "_published_at" text,
    "_source_updated_at" text,
    "_observed_at" text not null,
    "_valid_from" text,
    "_valid_to" text,
    "_payload_hash" varchar(64) not null,
    "ts_code" text,
    "trade_date" date,
    "his_low" decimal(38,8),
    "his_high" decimal(38,8),
    "cost_5pct" decimal(38,8),
    "cost_15pct" decimal(38,8),
    "cost_50pct" decimal(38,8),
    "cost_85pct" decimal(38,8),
    "cost_95pct" decimal(38,8),
    "weight_avg" decimal(38,8),
    "winner_rate" decimal(38,8),
    unique("_natural_key_hash","_revision_no"),
    unique("_current_natural_key_hash"),
    check ("_revision_no" > 0),
    check ("_is_current" in (0,1)),
    check ("_valid_to" is null or "_valid_from" is null or "_valid_to" >= "_valid_from")
);

create table if not exists "src_tushare_dc_concept" (
    "_observation_id" varchar(64) primary key,
    "_batch_id" varchar(64) not null,
    "_natural_key_hash" varchar(64) not null,
    "_revision_no" integer not null,
    "_is_current" integer not null default 1,
    "_current_natural_key_hash" varchar(64) generated always as (case when "_is_current" = 1 then "_natural_key_hash" else null end) stored,
    "_published_at" text,
    "_source_updated_at" text,
    "_observed_at" text not null,
    "_valid_from" text,
    "_valid_to" text,
    "_payload_hash" varchar(64) not null,
    "theme_code" text,
    "trade_date" date,
    "name" text,
    "pct_change" text,
    "hot" text,
    "sort" text,
    "strength" text,
    "z_t_num" text,
    "main_change" text,
    "lead_stock" text,
    "lead_stock_code" text,
    "lead_stock_pct_change" text,
    unique("_natural_key_hash","_revision_no"),
    unique("_current_natural_key_hash"),
    check ("_revision_no" > 0),
    check ("_is_current" in (0,1)),
    check ("_valid_to" is null or "_valid_from" is null or "_valid_to" >= "_valid_from")
);

create table if not exists "src_tushare_dc_concept_cons" (
    "_observation_id" varchar(64) primary key,
    "_batch_id" varchar(64) not null,
    "_natural_key_hash" varchar(64) not null,
    "_revision_no" integer not null,
    "_is_current" integer not null default 1,
    "_current_natural_key_hash" varchar(64) generated always as (case when "_is_current" = 1 then "_natural_key_hash" else null end) stored,
    "_published_at" text,
    "_source_updated_at" text,
    "_observed_at" text not null,
    "_valid_from" text,
    "_valid_to" text,
    "_payload_hash" varchar(64) not null,
    "ts_code" text,
    "trade_date" date,
    "name" text,
    "theme_code" text,
    "industry_code" text,
    "industry" text,
    "reason" text,
    "hot_num" text,
    unique("_natural_key_hash","_revision_no"),
    unique("_current_natural_key_hash"),
    check ("_revision_no" > 0),
    check ("_is_current" in (0,1)),
    check ("_valid_to" is null or "_valid_from" is null or "_valid_to" >= "_valid_from")
);

create table if not exists "src_tushare_dc_hot" (
    "_observation_id" varchar(64) primary key,
    "_batch_id" varchar(64) not null,
    "_natural_key_hash" varchar(64) not null,
    "_revision_no" integer not null,
    "_is_current" integer not null default 1,
    "_current_natural_key_hash" varchar(64) generated always as (case when "_is_current" = 1 then "_natural_key_hash" else null end) stored,
    "_published_at" text,
    "_source_updated_at" text,
    "_observed_at" text not null,
    "_valid_from" text,
    "_valid_to" text,
    "_payload_hash" varchar(64) not null,
    "trade_date" date,
    "data_type" text,
    "ts_code" text,
    "ts_name" text,
    "rank" bigint,
    "pct_change" decimal(38,8),
    "current_price" decimal(38,8),
    "rank_time" text,
    unique("_natural_key_hash","_revision_no"),
    unique("_current_natural_key_hash"),
    check ("_revision_no" > 0),
    check ("_is_current" in (0,1)),
    check ("_valid_to" is null or "_valid_from" is null or "_valid_to" >= "_valid_from")
);

create table if not exists "src_tushare_dc_index" (
    "_observation_id" varchar(64) primary key,
    "_batch_id" varchar(64) not null,
    "_natural_key_hash" varchar(64) not null,
    "_revision_no" integer not null,
    "_is_current" integer not null default 1,
    "_current_natural_key_hash" varchar(64) generated always as (case when "_is_current" = 1 then "_natural_key_hash" else null end) stored,
    "_published_at" text,
    "_source_updated_at" text,
    "_observed_at" text not null,
    "_valid_from" text,
    "_valid_to" text,
    "_payload_hash" varchar(64) not null,
    "ts_code" text,
    "trade_date" date,
    "name" text,
    "leading" text,
    "leading_code" text,
    "pct_change" decimal(38,8),
    "leading_pct" decimal(38,8),
    "total_mv" decimal(38,8),
    "turnover_rate" decimal(38,8),
    "up_num" bigint,
    "down_num" bigint,
    "idx_type" text,
    "level" text,
    unique("_natural_key_hash","_revision_no"),
    unique("_current_natural_key_hash"),
    check ("_revision_no" > 0),
    check ("_is_current" in (0,1)),
    check ("_valid_to" is null or "_valid_from" is null or "_valid_to" >= "_valid_from")
);

create table if not exists "src_tushare_dc_member" (
    "_observation_id" varchar(64) primary key,
    "_batch_id" varchar(64) not null,
    "_natural_key_hash" varchar(64) not null,
    "_revision_no" integer not null,
    "_is_current" integer not null default 1,
    "_current_natural_key_hash" varchar(64) generated always as (case when "_is_current" = 1 then "_natural_key_hash" else null end) stored,
    "_published_at" text,
    "_source_updated_at" text,
    "_observed_at" text not null,
    "_valid_from" text,
    "_valid_to" text,
    "_payload_hash" varchar(64) not null,
    "trade_date" date,
    "ts_code" text,
    "con_code" text,
    "name" text,
    unique("_natural_key_hash","_revision_no"),
    unique("_current_natural_key_hash"),
    check ("_revision_no" > 0),
    check ("_is_current" in (0,1)),
    check ("_valid_to" is null or "_valid_from" is null or "_valid_to" >= "_valid_from")
);

create table if not exists "src_tushare_disclosure_date" (
    "_observation_id" varchar(64) primary key,
    "_batch_id" varchar(64) not null,
    "_natural_key_hash" varchar(64) not null,
    "_revision_no" integer not null,
    "_is_current" integer not null default 1,
    "_current_natural_key_hash" varchar(64) generated always as (case when "_is_current" = 1 then "_natural_key_hash" else null end) stored,
    "_published_at" text,
    "_source_updated_at" text,
    "_observed_at" text not null,
    "_valid_from" text,
    "_valid_to" text,
    "_payload_hash" varchar(64) not null,
    "ts_code" text,
    "ann_date" date,
    "end_date" date,
    "pre_date" date,
    "actual_date" date,
    "modify_date" date,
    unique("_natural_key_hash","_revision_no"),
    unique("_current_natural_key_hash"),
    check ("_revision_no" > 0),
    check ("_is_current" in (0,1)),
    check ("_valid_to" is null or "_valid_from" is null or "_valid_to" >= "_valid_from")
);

create table if not exists "src_tushare_dividend" (
    "_observation_id" varchar(64) primary key,
    "_batch_id" varchar(64) not null,
    "_natural_key_hash" varchar(64) not null,
    "_revision_no" integer not null,
    "_is_current" integer not null default 1,
    "_current_natural_key_hash" varchar(64) generated always as (case when "_is_current" = 1 then "_natural_key_hash" else null end) stored,
    "_published_at" text,
    "_source_updated_at" text,
    "_observed_at" text not null,
    "_valid_from" text,
    "_valid_to" text,
    "_payload_hash" varchar(64) not null,
    "ts_code" text,
    "end_date" date,
    "ann_date" date,
    "div_proc" text,
    "stk_div" decimal(38,8),
    "stk_bo_rate" decimal(38,8),
    "stk_co_rate" decimal(38,8),
    "cash_div" decimal(38,8),
    "cash_div_tax" decimal(38,8),
    "record_date" date,
    "ex_date" date,
    "pay_date" date,
    "div_listdate" date,
    "imp_ann_date" date,
    "base_date" date,
    "base_share" decimal(38,8),
    unique("_natural_key_hash","_revision_no"),
    unique("_current_natural_key_hash"),
    check ("_revision_no" > 0),
    check ("_is_current" in (0,1)),
    check ("_valid_to" is null or "_valid_from" is null or "_valid_to" >= "_valid_from")
);

create table if not exists "src_tushare_express" (
    "_observation_id" varchar(64) primary key,
    "_batch_id" varchar(64) not null,
    "_natural_key_hash" varchar(64) not null,
    "_revision_no" integer not null,
    "_is_current" integer not null default 1,
    "_current_natural_key_hash" varchar(64) generated always as (case when "_is_current" = 1 then "_natural_key_hash" else null end) stored,
    "_published_at" text,
    "_source_updated_at" text,
    "_observed_at" text not null,
    "_valid_from" text,
    "_valid_to" text,
    "_payload_hash" varchar(64) not null,
    "ts_code" text,
    "ann_date" date,
    "end_date" date,
    "revenue" decimal(38,8),
    "operate_profit" decimal(38,8),
    "total_profit" decimal(38,8),
    "n_income" decimal(38,8),
    "total_assets" decimal(38,8),
    "total_hldr_eqy_exc_min_int" decimal(38,8),
    "diluted_eps" decimal(38,8),
    "diluted_roe" decimal(38,8),
    "yoy_net_profit" decimal(38,8),
    "bps" decimal(38,8),
    "yoy_sales" decimal(38,8),
    "yoy_op" decimal(38,8),
    "yoy_tp" decimal(38,8),
    "yoy_dedu_np" decimal(38,8),
    "yoy_eps" decimal(38,8),
    "yoy_roe" decimal(38,8),
    "growth_assets" decimal(38,8),
    "yoy_equity" decimal(38,8),
    "growth_bps" decimal(38,8),
    "or_last_year" decimal(38,8),
    "op_last_year" decimal(38,8),
    "tp_last_year" decimal(38,8),
    "np_last_year" decimal(38,8),
    "eps_last_year" decimal(38,8),
    "open_net_assets" decimal(38,8),
    "open_bps" decimal(38,8),
    "perf_summary" text,
    "is_audit" bigint,
    "remark" text,
    unique("_natural_key_hash","_revision_no"),
    unique("_current_natural_key_hash"),
    check ("_revision_no" > 0),
    check ("_is_current" in (0,1)),
    check ("_valid_to" is null or "_valid_from" is null or "_valid_to" >= "_valid_from")
);

create table if not exists "src_tushare_fina_audit" (
    "_observation_id" varchar(64) primary key,
    "_batch_id" varchar(64) not null,
    "_natural_key_hash" varchar(64) not null,
    "_revision_no" integer not null,
    "_is_current" integer not null default 1,
    "_current_natural_key_hash" varchar(64) generated always as (case when "_is_current" = 1 then "_natural_key_hash" else null end) stored,
    "_published_at" text,
    "_source_updated_at" text,
    "_observed_at" text not null,
    "_valid_from" text,
    "_valid_to" text,
    "_payload_hash" varchar(64) not null,
    "ts_code" text,
    "ann_date" date,
    "end_date" date,
    "audit_result" text,
    "audit_fees" decimal(38,8),
    "audit_agency" text,
    "audit_sign" text,
    unique("_natural_key_hash","_revision_no"),
    unique("_current_natural_key_hash"),
    check ("_revision_no" > 0),
    check ("_is_current" in (0,1)),
    check ("_valid_to" is null or "_valid_from" is null or "_valid_to" >= "_valid_from")
);

create table if not exists "src_tushare_fina_indicator" (
    "_observation_id" varchar(64) primary key,
    "_batch_id" varchar(64) not null,
    "_natural_key_hash" varchar(64) not null,
    "_revision_no" integer not null,
    "_is_current" integer not null default 1,
    "_current_natural_key_hash" varchar(64) generated always as (case when "_is_current" = 1 then "_natural_key_hash" else null end) stored,
    "_published_at" text,
    "_source_updated_at" text,
    "_observed_at" text not null,
    "_valid_from" text,
    "_valid_to" text,
    "_payload_hash" varchar(64) not null,
    "ts_code" text,
    "ann_date" date,
    "end_date" date,
    "eps" decimal(38,8),
    "dt_eps" decimal(38,8),
    "total_revenue_ps" decimal(38,8),
    "revenue_ps" decimal(38,8),
    "capital_rese_ps" decimal(38,8),
    "surplus_rese_ps" decimal(38,8),
    "undist_profit_ps" decimal(38,8),
    "extra_item" decimal(38,8),
    "profit_dedt" decimal(38,8),
    "gross_margin" decimal(38,8),
    "current_ratio" decimal(38,8),
    "quick_ratio" decimal(38,8),
    "cash_ratio" decimal(38,8),
    "invturn_days" decimal(38,8),
    "arturn_days" decimal(38,8),
    "inv_turn" decimal(38,8),
    "ar_turn" decimal(38,8),
    "ca_turn" decimal(38,8),
    "fa_turn" decimal(38,8),
    "assets_turn" decimal(38,8),
    "op_income" decimal(38,8),
    "valuechange_income" decimal(38,8),
    "interst_income" decimal(38,8),
    "daa" decimal(38,8),
    "ebit" decimal(38,8),
    "ebitda" decimal(38,8),
    "fcff" decimal(38,8),
    "fcfe" decimal(38,8),
    "current_exint" decimal(38,8),
    "noncurrent_exint" decimal(38,8),
    "interestdebt" decimal(38,8),
    "netdebt" decimal(38,8),
    "tangible_asset" decimal(38,8),
    "working_capital" decimal(38,8),
    "networking_capital" decimal(38,8),
    "invest_capital" decimal(38,8),
    "retained_earnings" decimal(38,8),
    "diluted2_eps" decimal(38,8),
    "bps" decimal(38,8),
    "ocfps" decimal(38,8),
    "retainedps" decimal(38,8),
    "cfps" decimal(38,8),
    "ebit_ps" decimal(38,8),
    "fcff_ps" decimal(38,8),
    "fcfe_ps" decimal(38,8),
    "netprofit_margin" decimal(38,8),
    "grossprofit_margin" decimal(38,8),
    "cogs_of_sales" decimal(38,8),
    "expense_of_sales" decimal(38,8),
    "profit_to_gr" decimal(38,8),
    "saleexp_to_gr" decimal(38,8),
    "adminexp_of_gr" decimal(38,8),
    "finaexp_of_gr" decimal(38,8),
    "impai_ttm" decimal(38,8),
    "gc_of_gr" decimal(38,8),
    "op_of_gr" decimal(38,8),
    "ebit_of_gr" decimal(38,8),
    "roe" decimal(38,8),
    "roe_waa" decimal(38,8),
    "roe_dt" decimal(38,8),
    "roa" decimal(38,8),
    "npta" decimal(38,8),
    "roic" decimal(38,8),
    "roe_yearly" decimal(38,8),
    "roa2_yearly" decimal(38,8),
    "roe_avg" decimal(38,8),
    "opincome_of_ebt" decimal(38,8),
    "investincome_of_ebt" decimal(38,8),
    "n_op_profit_of_ebt" decimal(38,8),
    "tax_to_ebt" decimal(38,8),
    "dtprofit_to_profit" decimal(38,8),
    "salescash_to_or" decimal(38,8),
    "ocf_to_or" decimal(38,8),
    "ocf_to_opincome" decimal(38,8),
    "capitalized_to_da" decimal(38,8),
    "debt_to_assets" decimal(38,8),
    "assets_to_eqt" decimal(38,8),
    "dp_assets_to_eqt" decimal(38,8),
    "ca_to_assets" decimal(38,8),
    "nca_to_assets" decimal(38,8),
    "tbassets_to_totalassets" decimal(38,8),
    "int_to_talcap" decimal(38,8),
    "eqt_to_talcapital" decimal(38,8),
    "currentdebt_to_debt" decimal(38,8),
    "longdeb_to_debt" decimal(38,8),
    "ocf_to_shortdebt" decimal(38,8),
    "debt_to_eqt" decimal(38,8),
    "eqt_to_debt" decimal(38,8),
    "eqt_to_interestdebt" decimal(38,8),
    "tangibleasset_to_debt" decimal(38,8),
    "tangasset_to_intdebt" decimal(38,8),
    "tangibleasset_to_netdebt" decimal(38,8),
    "ocf_to_debt" decimal(38,8),
    "ocf_to_interestdebt" decimal(38,8),
    "ocf_to_netdebt" decimal(38,8),
    "ebit_to_interest" decimal(38,8),
    "longdebt_to_workingcapital" decimal(38,8),
    "ebitda_to_debt" decimal(38,8),
    "turn_days" decimal(38,8),
    "roa_yearly" decimal(38,8),
    "roa_dp" decimal(38,8),
    "fixed_assets" decimal(38,8),
    "profit_prefin_exp" decimal(38,8),
    "non_op_profit" decimal(38,8),
    "op_to_ebt" decimal(38,8),
    "nop_to_ebt" decimal(38,8),
    "ocf_to_profit" decimal(38,8),
    "cash_to_liqdebt" decimal(38,8),
    "cash_to_liqdebt_withinterest" decimal(38,8),
    "op_to_liqdebt" decimal(38,8),
    "op_to_debt" decimal(38,8),
    "roic_yearly" decimal(38,8),
    "total_fa_trun" decimal(38,8),
    "profit_to_op" decimal(38,8),
    "q_opincome" decimal(38,8),
    "q_investincome" decimal(38,8),
    "q_dtprofit" decimal(38,8),
    "q_eps" decimal(38,8),
    "q_netprofit_margin" decimal(38,8),
    "q_gsprofit_margin" decimal(38,8),
    "q_exp_to_sales" decimal(38,8),
    "q_profit_to_gr" decimal(38,8),
    "q_saleexp_to_gr" decimal(38,8),
    "q_adminexp_to_gr" decimal(38,8),
    "q_finaexp_to_gr" decimal(38,8),
    "q_impair_to_gr_ttm" decimal(38,8),
    "q_gc_to_gr" decimal(38,8),
    "q_op_to_gr" decimal(38,8),
    "q_roe" decimal(38,8),
    "q_dt_roe" decimal(38,8),
    "q_npta" decimal(38,8),
    "q_opincome_to_ebt" decimal(38,8),
    "q_investincome_to_ebt" decimal(38,8),
    "q_dtprofit_to_profit" decimal(38,8),
    "q_salescash_to_or" decimal(38,8),
    "q_ocf_to_sales" decimal(38,8),
    "q_ocf_to_or" decimal(38,8),
    "basic_eps_yoy" decimal(38,8),
    "dt_eps_yoy" decimal(38,8),
    "cfps_yoy" decimal(38,8),
    "op_yoy" decimal(38,8),
    "ebt_yoy" decimal(38,8),
    "netprofit_yoy" decimal(38,8),
    "dt_netprofit_yoy" decimal(38,8),
    "ocf_yoy" decimal(38,8),
    "roe_yoy" decimal(38,8),
    "bps_yoy" decimal(38,8),
    "assets_yoy" decimal(38,8),
    "eqt_yoy" decimal(38,8),
    "tr_yoy" decimal(38,8),
    "or_yoy" decimal(38,8),
    "q_gr_yoy" decimal(38,8),
    "q_gr_qoq" decimal(38,8),
    "q_sales_yoy" decimal(38,8),
    "q_sales_qoq" decimal(38,8),
    "q_op_yoy" decimal(38,8),
    "q_op_qoq" decimal(38,8),
    "q_profit_yoy" decimal(38,8),
    "q_profit_qoq" decimal(38,8),
    "q_netprofit_yoy" decimal(38,8),
    "q_netprofit_qoq" decimal(38,8),
    "equity_yoy" decimal(38,8),
    "rd_exp" decimal(38,8),
    "update_flag" text,
    unique("_natural_key_hash","_revision_no"),
    unique("_current_natural_key_hash"),
    check ("_revision_no" > 0),
    check ("_is_current" in (0,1)),
    check ("_valid_to" is null or "_valid_from" is null or "_valid_to" >= "_valid_from")
);

create table if not exists "src_tushare_fina_mainbz" (
    "_observation_id" varchar(64) primary key,
    "_batch_id" varchar(64) not null,
    "_natural_key_hash" varchar(64) not null,
    "_revision_no" integer not null,
    "_is_current" integer not null default 1,
    "_current_natural_key_hash" varchar(64) generated always as (case when "_is_current" = 1 then "_natural_key_hash" else null end) stored,
    "_published_at" text,
    "_source_updated_at" text,
    "_observed_at" text not null,
    "_valid_from" text,
    "_valid_to" text,
    "_payload_hash" varchar(64) not null,
    "ts_code" text,
    "end_date" date,
    "bz_item" text,
    "bz_code" text,
    "bz_sales" decimal(38,8),
    "bz_profit" decimal(38,8),
    "bz_cost" decimal(38,8),
    "curr_type" text,
    "update_flag" text,
    unique("_natural_key_hash","_revision_no"),
    unique("_current_natural_key_hash"),
    check ("_revision_no" > 0),
    check ("_is_current" in (0,1)),
    check ("_valid_to" is null or "_valid_from" is null or "_valid_to" >= "_valid_from")
);

create table if not exists "src_tushare_forecast" (
    "_observation_id" varchar(64) primary key,
    "_batch_id" varchar(64) not null,
    "_natural_key_hash" varchar(64) not null,
    "_revision_no" integer not null,
    "_is_current" integer not null default 1,
    "_current_natural_key_hash" varchar(64) generated always as (case when "_is_current" = 1 then "_natural_key_hash" else null end) stored,
    "_published_at" text,
    "_source_updated_at" text,
    "_observed_at" text not null,
    "_valid_from" text,
    "_valid_to" text,
    "_payload_hash" varchar(64) not null,
    "ts_code" text,
    "ann_date" date,
    "end_date" date,
    "type" text,
    "p_change_min" decimal(38,8),
    "p_change_max" decimal(38,8),
    "net_profit_min" decimal(38,8),
    "net_profit_max" decimal(38,8),
    "last_parent_net" decimal(38,8),
    "first_ann_date" date,
    "summary" text,
    "change_reason" text,
    unique("_natural_key_hash","_revision_no"),
    unique("_current_natural_key_hash"),
    check ("_revision_no" > 0),
    check ("_is_current" in (0,1)),
    check ("_valid_to" is null or "_valid_from" is null or "_valid_to" >= "_valid_from")
);

create table if not exists "src_tushare_ft_limit" (
    "_observation_id" varchar(64) primary key,
    "_batch_id" varchar(64) not null,
    "_natural_key_hash" varchar(64) not null,
    "_revision_no" integer not null,
    "_is_current" integer not null default 1,
    "_current_natural_key_hash" varchar(64) generated always as (case when "_is_current" = 1 then "_natural_key_hash" else null end) stored,
    "_published_at" text,
    "_source_updated_at" text,
    "_observed_at" text not null,
    "_valid_from" text,
    "_valid_to" text,
    "_payload_hash" varchar(64) not null,
    "trade_date" date,
    "ts_code" text,
    "name" text,
    "up_limit" decimal(38,8),
    "down_limit" decimal(38,8),
    "m_ratio" decimal(38,8),
    "cont" text,
    "exchange" text,
    unique("_natural_key_hash","_revision_no"),
    unique("_current_natural_key_hash"),
    check ("_revision_no" > 0),
    check ("_is_current" in (0,1)),
    check ("_valid_to" is null or "_valid_from" is null or "_valid_to" >= "_valid_from")
);

create table if not exists "src_tushare_fut_basic" (
    "_observation_id" varchar(64) primary key,
    "_batch_id" varchar(64) not null,
    "_natural_key_hash" varchar(64) not null,
    "_revision_no" integer not null,
    "_is_current" integer not null default 1,
    "_current_natural_key_hash" varchar(64) generated always as (case when "_is_current" = 1 then "_natural_key_hash" else null end) stored,
    "_published_at" text,
    "_source_updated_at" text,
    "_observed_at" text not null,
    "_valid_from" text,
    "_valid_to" text,
    "_payload_hash" varchar(64) not null,
    "ts_code" text,
    "symbol" text,
    "exchange" text,
    "name" text,
    "fut_code" text,
    "multiplier" decimal(38,8),
    "trade_unit" text,
    "per_unit" decimal(38,8),
    "quote_unit" text,
    "quote_unit_desc" text,
    "d_mode_desc" text,
    "list_date" date,
    "delist_date" date,
    "d_month" text,
    "last_ddate" date,
    "trade_time_desc" text,
    unique("_natural_key_hash","_revision_no"),
    unique("_current_natural_key_hash"),
    check ("_revision_no" > 0),
    check ("_is_current" in (0,1)),
    check ("_valid_to" is null or "_valid_from" is null or "_valid_to" >= "_valid_from")
);

create table if not exists "src_tushare_fut_holding" (
    "_observation_id" varchar(64) primary key,
    "_batch_id" varchar(64) not null,
    "_natural_key_hash" varchar(64) not null,
    "_revision_no" integer not null,
    "_is_current" integer not null default 1,
    "_current_natural_key_hash" varchar(64) generated always as (case when "_is_current" = 1 then "_natural_key_hash" else null end) stored,
    "_published_at" text,
    "_source_updated_at" text,
    "_observed_at" text not null,
    "_valid_from" text,
    "_valid_to" text,
    "_payload_hash" varchar(64) not null,
    "trade_date" date,
    "symbol" text,
    "broker" text,
    "vol" bigint,
    "vol_chg" bigint,
    "long_hld" bigint,
    "long_chg" bigint,
    "short_hld" bigint,
    "short_chg" bigint,
    "exchange" text,
    unique("_natural_key_hash","_revision_no"),
    unique("_current_natural_key_hash"),
    check ("_revision_no" > 0),
    check ("_is_current" in (0,1)),
    check ("_valid_to" is null or "_valid_from" is null or "_valid_to" >= "_valid_from")
);

create table if not exists "src_tushare_fut_mapping" (
    "_observation_id" varchar(64) primary key,
    "_batch_id" varchar(64) not null,
    "_natural_key_hash" varchar(64) not null,
    "_revision_no" integer not null,
    "_is_current" integer not null default 1,
    "_current_natural_key_hash" varchar(64) generated always as (case when "_is_current" = 1 then "_natural_key_hash" else null end) stored,
    "_published_at" text,
    "_source_updated_at" text,
    "_observed_at" text not null,
    "_valid_from" text,
    "_valid_to" text,
    "_payload_hash" varchar(64) not null,
    "ts_code" text,
    "trade_date" date,
    "mapping_ts_code" text,
    unique("_natural_key_hash","_revision_no"),
    unique("_current_natural_key_hash"),
    check ("_revision_no" > 0),
    check ("_is_current" in (0,1)),
    check ("_valid_to" is null or "_valid_from" is null or "_valid_to" >= "_valid_from")
);

create table if not exists "src_tushare_fut_settle" (
    "_observation_id" varchar(64) primary key,
    "_batch_id" varchar(64) not null,
    "_natural_key_hash" varchar(64) not null,
    "_revision_no" integer not null,
    "_is_current" integer not null default 1,
    "_current_natural_key_hash" varchar(64) generated always as (case when "_is_current" = 1 then "_natural_key_hash" else null end) stored,
    "_published_at" text,
    "_source_updated_at" text,
    "_observed_at" text not null,
    "_valid_from" text,
    "_valid_to" text,
    "_payload_hash" varchar(64) not null,
    "ts_code" text,
    "trade_date" date,
    "settle" decimal(38,8),
    "trading_fee_rate" decimal(38,8),
    "trading_fee" decimal(38,8),
    "delivery_fee" decimal(38,8),
    "b_hedging_margin_rate" decimal(38,8),
    "s_hedging_margin_rate" decimal(38,8),
    "long_margin_rate" decimal(38,8),
    "short_margin_rate" decimal(38,8),
    "offset_today_fee" decimal(38,8),
    "exchange" text,
    unique("_natural_key_hash","_revision_no"),
    unique("_current_natural_key_hash"),
    check ("_revision_no" > 0),
    check ("_is_current" in (0,1)),
    check ("_valid_to" is null or "_valid_from" is null or "_valid_to" >= "_valid_from")
);

create table if not exists "src_tushare_fut_trade_cal" (
    "_observation_id" varchar(64) primary key,
    "_batch_id" varchar(64) not null,
    "_natural_key_hash" varchar(64) not null,
    "_revision_no" integer not null,
    "_is_current" integer not null default 1,
    "_current_natural_key_hash" varchar(64) generated always as (case when "_is_current" = 1 then "_natural_key_hash" else null end) stored,
    "_published_at" text,
    "_source_updated_at" text,
    "_observed_at" text not null,
    "_valid_from" text,
    "_valid_to" text,
    "_payload_hash" varchar(64) not null,
    "exchange" text,
    "cal_date" date,
    "is_open" bigint,
    "pretrade_date" date,
    unique("_natural_key_hash","_revision_no"),
    unique("_current_natural_key_hash"),
    check ("_revision_no" > 0),
    check ("_is_current" in (0,1)),
    check ("_valid_to" is null or "_valid_from" is null or "_valid_to" >= "_valid_from")
);

create table if not exists "src_tushare_fut_wsr" (
    "_observation_id" varchar(64) primary key,
    "_batch_id" varchar(64) not null,
    "_natural_key_hash" varchar(64) not null,
    "_revision_no" integer not null,
    "_is_current" integer not null default 1,
    "_current_natural_key_hash" varchar(64) generated always as (case when "_is_current" = 1 then "_natural_key_hash" else null end) stored,
    "_published_at" text,
    "_source_updated_at" text,
    "_observed_at" text not null,
    "_valid_from" text,
    "_valid_to" text,
    "_payload_hash" varchar(64) not null,
    "trade_date" date,
    "symbol" text,
    "fut_name" text,
    "warehouse" text,
    "wh_id" text,
    "pre_vol" bigint,
    "vol" bigint,
    "vol_chg" bigint,
    "area" text,
    "year" text,
    "grade" text,
    "brand" text,
    "place" text,
    "pd" bigint,
    "is_ct" text,
    "unit" text,
    "exchange" text,
    unique("_natural_key_hash","_revision_no"),
    unique("_current_natural_key_hash"),
    check ("_revision_no" > 0),
    check ("_is_current" in (0,1)),
    check ("_valid_to" is null or "_valid_from" is null or "_valid_to" >= "_valid_from")
);

create table if not exists "src_tushare_hm_detail" (
    "_observation_id" varchar(64) primary key,
    "_batch_id" varchar(64) not null,
    "_natural_key_hash" varchar(64) not null,
    "_revision_no" integer not null,
    "_is_current" integer not null default 1,
    "_current_natural_key_hash" varchar(64) generated always as (case when "_is_current" = 1 then "_natural_key_hash" else null end) stored,
    "_published_at" text,
    "_source_updated_at" text,
    "_observed_at" text not null,
    "_valid_from" text,
    "_valid_to" text,
    "_payload_hash" varchar(64) not null,
    "trade_date" date,
    "ts_code" text,
    "ts_name" text,
    "buy_amount" decimal(38,8),
    "sell_amount" decimal(38,8),
    "net_amount" decimal(38,8),
    "hm_name" text,
    "hm_orgs" text,
    "tag" text,
    unique("_natural_key_hash","_revision_no"),
    unique("_current_natural_key_hash"),
    check ("_revision_no" > 0),
    check ("_is_current" in (0,1)),
    check ("_valid_to" is null or "_valid_from" is null or "_valid_to" >= "_valid_from")
);

create table if not exists "src_tushare_hm_list" (
    "_observation_id" varchar(64) primary key,
    "_batch_id" varchar(64) not null,
    "_natural_key_hash" varchar(64) not null,
    "_revision_no" integer not null,
    "_is_current" integer not null default 1,
    "_current_natural_key_hash" varchar(64) generated always as (case when "_is_current" = 1 then "_natural_key_hash" else null end) stored,
    "_published_at" text,
    "_source_updated_at" text,
    "_observed_at" text not null,
    "_valid_from" text,
    "_valid_to" text,
    "_payload_hash" varchar(64) not null,
    "name" text,
    "desc" text,
    "orgs" text,
    unique("_natural_key_hash","_revision_no"),
    unique("_current_natural_key_hash"),
    check ("_revision_no" > 0),
    check ("_is_current" in (0,1)),
    check ("_valid_to" is null or "_valid_from" is null or "_valid_to" >= "_valid_from")
);

create table if not exists "src_tushare_hsgt_top10" (
    "_observation_id" varchar(64) primary key,
    "_batch_id" varchar(64) not null,
    "_natural_key_hash" varchar(64) not null,
    "_revision_no" integer not null,
    "_is_current" integer not null default 1,
    "_current_natural_key_hash" varchar(64) generated always as (case when "_is_current" = 1 then "_natural_key_hash" else null end) stored,
    "_published_at" text,
    "_source_updated_at" text,
    "_observed_at" text not null,
    "_valid_from" text,
    "_valid_to" text,
    "_payload_hash" varchar(64) not null,
    "trade_date" date,
    "ts_code" text,
    "name" text,
    "close" decimal(38,8),
    "change" decimal(38,8),
    "rank" bigint,
    "market_type" text,
    "amount" decimal(38,8),
    "net_amount" decimal(38,8),
    "buy" decimal(38,8),
    "sell" decimal(38,8),
    unique("_natural_key_hash","_revision_no"),
    unique("_current_natural_key_hash"),
    check ("_revision_no" > 0),
    check ("_is_current" in (0,1)),
    check ("_valid_to" is null or "_valid_from" is null or "_valid_to" >= "_valid_from")
);

create table if not exists "src_tushare_idx_factor_pro" (
    "_observation_id" varchar(64) primary key,
    "_batch_id" varchar(64) not null,
    "_natural_key_hash" varchar(64) not null,
    "_revision_no" integer not null,
    "_is_current" integer not null default 1,
    "_current_natural_key_hash" varchar(64) generated always as (case when "_is_current" = 1 then "_natural_key_hash" else null end) stored,
    "_published_at" text,
    "_source_updated_at" text,
    "_observed_at" text not null,
    "_valid_from" text,
    "_valid_to" text,
    "_payload_hash" varchar(64) not null,
    "ts_code" text,
    "trade_date" date,
    "open" decimal(38,8),
    "high" decimal(38,8),
    "low" decimal(38,8),
    "close" decimal(38,8),
    "pre_close" decimal(38,8),
    "change" decimal(38,8),
    "pct_change" decimal(38,8),
    "vol" decimal(38,8),
    "amount" decimal(38,8),
    "asi_bfq" decimal(38,8),
    "asit_bfq" decimal(38,8),
    "atr_bfq" decimal(38,8),
    "bbi_bfq" decimal(38,8),
    "bias1_bfq" decimal(38,8),
    "bias2_bfq" decimal(38,8),
    "bias3_bfq" decimal(38,8),
    "boll_lower_bfq" decimal(38,8),
    "boll_mid_bfq" decimal(38,8),
    "boll_upper_bfq" decimal(38,8),
    "brar_ar_bfq" decimal(38,8),
    "brar_br_bfq" decimal(38,8),
    "cci_bfq" decimal(38,8),
    "cr_bfq" decimal(38,8),
    "dfma_dif_bfq" decimal(38,8),
    "dfma_difma_bfq" decimal(38,8),
    "dmi_adx_bfq" decimal(38,8),
    "dmi_adxr_bfq" decimal(38,8),
    "dmi_mdi_bfq" decimal(38,8),
    "dmi_pdi_bfq" decimal(38,8),
    "downdays" decimal(38,8),
    "updays" decimal(38,8),
    "dpo_bfq" decimal(38,8),
    "madpo_bfq" decimal(38,8),
    "ema_bfq_10" decimal(38,8),
    "ema_bfq_20" decimal(38,8),
    "ema_bfq_250" decimal(38,8),
    "ema_bfq_30" decimal(38,8),
    "ema_bfq_5" decimal(38,8),
    "ema_bfq_60" decimal(38,8),
    "ema_bfq_90" decimal(38,8),
    "emv_bfq" decimal(38,8),
    "maemv_bfq" decimal(38,8),
    "expma_12_bfq" decimal(38,8),
    "expma_50_bfq" decimal(38,8),
    "kdj_bfq" decimal(38,8),
    "kdj_d_bfq" decimal(38,8),
    "kdj_k_bfq" decimal(38,8),
    "ktn_down_bfq" decimal(38,8),
    "ktn_mid_bfq" decimal(38,8),
    "ktn_upper_bfq" decimal(38,8),
    "lowdays" decimal(38,8),
    "topdays" decimal(38,8),
    "ma_bfq_10" decimal(38,8),
    "ma_bfq_20" decimal(38,8),
    "ma_bfq_250" decimal(38,8),
    "ma_bfq_30" decimal(38,8),
    "ma_bfq_5" decimal(38,8),
    "ma_bfq_60" decimal(38,8),
    "ma_bfq_90" decimal(38,8),
    "macd_bfq" decimal(38,8),
    "macd_dea_bfq" decimal(38,8),
    "macd_dif_bfq" decimal(38,8),
    "mass_bfq" decimal(38,8),
    "ma_mass_bfq" decimal(38,8),
    "mfi_bfq" decimal(38,8),
    "mtm_bfq" decimal(38,8),
    "mtmma_bfq" decimal(38,8),
    "obv_bfq" decimal(38,8),
    "psy_bfq" decimal(38,8),
    "psyma_bfq" decimal(38,8),
    "roc_bfq" decimal(38,8),
    "maroc_bfq" decimal(38,8),
    "rsi_bfq_12" decimal(38,8),
    "rsi_bfq_24" decimal(38,8),
    "rsi_bfq_6" decimal(38,8),
    "taq_down_bfq" decimal(38,8),
    "taq_mid_bfq" decimal(38,8),
    "taq_up_bfq" decimal(38,8),
    "trix_bfq" decimal(38,8),
    "trma_bfq" decimal(38,8),
    "vr_bfq" decimal(38,8),
    "wr_bfq" decimal(38,8),
    "wr1_bfq" decimal(38,8),
    "xsii_td1_bfq" decimal(38,8),
    "xsii_td2_bfq" decimal(38,8),
    "xsii_td3_bfq" decimal(38,8),
    "xsii_td4_bfq" decimal(38,8),
    unique("_natural_key_hash","_revision_no"),
    unique("_current_natural_key_hash"),
    check ("_revision_no" > 0),
    check ("_is_current" in (0,1)),
    check ("_valid_to" is null or "_valid_from" is null or "_valid_to" >= "_valid_from")
);

create table if not exists "src_tushare_income" (
    "_observation_id" varchar(64) primary key,
    "_batch_id" varchar(64) not null,
    "_natural_key_hash" varchar(64) not null,
    "_revision_no" integer not null,
    "_is_current" integer not null default 1,
    "_current_natural_key_hash" varchar(64) generated always as (case when "_is_current" = 1 then "_natural_key_hash" else null end) stored,
    "_published_at" text,
    "_source_updated_at" text,
    "_observed_at" text not null,
    "_valid_from" text,
    "_valid_to" text,
    "_payload_hash" varchar(64) not null,
    "ts_code" text,
    "ann_date" date,
    "f_ann_date" date,
    "end_date" date,
    "report_type" text,
    "comp_type" text,
    "end_type" text,
    "basic_eps" decimal(38,8),
    "diluted_eps" decimal(38,8),
    "total_revenue" decimal(38,8),
    "revenue" decimal(38,8),
    "int_income" decimal(38,8),
    "prem_earned" decimal(38,8),
    "comm_income" decimal(38,8),
    "n_commis_income" decimal(38,8),
    "n_oth_income" decimal(38,8),
    "n_oth_b_income" decimal(38,8),
    "prem_income" decimal(38,8),
    "out_prem" decimal(38,8),
    "une_prem_reser" decimal(38,8),
    "reins_income" decimal(38,8),
    "n_sec_tb_income" decimal(38,8),
    "n_sec_uw_income" decimal(38,8),
    "n_asset_mg_income" decimal(38,8),
    "oth_b_income" decimal(38,8),
    "fv_value_chg_gain" decimal(38,8),
    "invest_income" decimal(38,8),
    "ass_invest_income" decimal(38,8),
    "forex_gain" decimal(38,8),
    "total_cogs" decimal(38,8),
    "oper_cost" decimal(38,8),
    "int_exp" decimal(38,8),
    "comm_exp" decimal(38,8),
    "biz_tax_surchg" decimal(38,8),
    "sell_exp" decimal(38,8),
    "admin_exp" decimal(38,8),
    "fin_exp" decimal(38,8),
    "assets_impair_loss" decimal(38,8),
    "prem_refund" decimal(38,8),
    "compens_payout" decimal(38,8),
    "reser_insur_liab" decimal(38,8),
    "div_payt" decimal(38,8),
    "reins_exp" decimal(38,8),
    "oper_exp" decimal(38,8),
    "compens_payout_refu" decimal(38,8),
    "insur_reser_refu" decimal(38,8),
    "reins_cost_refund" decimal(38,8),
    "other_bus_cost" decimal(38,8),
    "operate_profit" decimal(38,8),
    "non_oper_income" decimal(38,8),
    "non_oper_exp" decimal(38,8),
    "nca_disploss" decimal(38,8),
    "total_profit" decimal(38,8),
    "income_tax" decimal(38,8),
    "n_income" decimal(38,8),
    "n_income_attr_p" decimal(38,8),
    "minority_gain" decimal(38,8),
    "oth_compr_income" decimal(38,8),
    "t_compr_income" decimal(38,8),
    "compr_inc_attr_p" decimal(38,8),
    "compr_inc_attr_m_s" decimal(38,8),
    "ebit" decimal(38,8),
    "ebitda" decimal(38,8),
    "insurance_exp" decimal(38,8),
    "undist_profit" decimal(38,8),
    "distable_profit" decimal(38,8),
    "rd_exp" decimal(38,8),
    "fin_exp_int_exp" decimal(38,8),
    "fin_exp_int_inc" decimal(38,8),
    "transfer_surplus_rese" decimal(38,8),
    "transfer_housing_imprest" decimal(38,8),
    "transfer_oth" decimal(38,8),
    "adj_lossgain" decimal(38,8),
    "withdra_legal_surplus" decimal(38,8),
    "withdra_legal_pubfund" decimal(38,8),
    "withdra_biz_devfund" decimal(38,8),
    "withdra_rese_fund" decimal(38,8),
    "withdra_oth_ersu" decimal(38,8),
    "workers_welfare" decimal(38,8),
    "distr_profit_shrhder" decimal(38,8),
    "prfshare_payable_dvd" decimal(38,8),
    "comshare_payable_dvd" decimal(38,8),
    "capit_comstock_div" decimal(38,8),
    "net_after_nr_lp_correct" decimal(38,8),
    "credit_impa_loss" decimal(38,8),
    "net_expo_hedging_benefits" decimal(38,8),
    "oth_impair_loss_assets" decimal(38,8),
    "total_opcost" decimal(38,8),
    "amodcost_fin_assets" decimal(38,8),
    "oth_income" decimal(38,8),
    "asset_disp_income" decimal(38,8),
    "continued_net_profit" decimal(38,8),
    "end_net_profit" decimal(38,8),
    "update_flag" text,
    unique("_natural_key_hash","_revision_no"),
    unique("_current_natural_key_hash"),
    check ("_revision_no" > 0),
    check ("_is_current" in (0,1)),
    check ("_valid_to" is null or "_valid_from" is null or "_valid_to" >= "_valid_from")
);

create table if not exists "src_tushare_index_basic" (
    "_observation_id" varchar(64) primary key,
    "_batch_id" varchar(64) not null,
    "_natural_key_hash" varchar(64) not null,
    "_revision_no" integer not null,
    "_is_current" integer not null default 1,
    "_current_natural_key_hash" varchar(64) generated always as (case when "_is_current" = 1 then "_natural_key_hash" else null end) stored,
    "_published_at" text,
    "_source_updated_at" text,
    "_observed_at" text not null,
    "_valid_from" text,
    "_valid_to" text,
    "_payload_hash" varchar(64) not null,
    "ts_code" text,
    "name" text,
    "fullname" text,
    "market" text,
    "publisher" text,
    "index_type" text,
    "category" text,
    "base_date" date,
    "base_point" decimal(38,8),
    "list_date" date,
    "weight_rule" text,
    "desc" text,
    "exp_date" date,
    unique("_natural_key_hash","_revision_no"),
    unique("_current_natural_key_hash"),
    check ("_revision_no" > 0),
    check ("_is_current" in (0,1)),
    check ("_valid_to" is null or "_valid_from" is null or "_valid_to" >= "_valid_from")
);

create table if not exists "src_tushare_index_classify" (
    "_observation_id" varchar(64) primary key,
    "_batch_id" varchar(64) not null,
    "_natural_key_hash" varchar(64) not null,
    "_revision_no" integer not null,
    "_is_current" integer not null default 1,
    "_current_natural_key_hash" varchar(64) generated always as (case when "_is_current" = 1 then "_natural_key_hash" else null end) stored,
    "_published_at" text,
    "_source_updated_at" text,
    "_observed_at" text not null,
    "_valid_from" text,
    "_valid_to" text,
    "_payload_hash" varchar(64) not null,
    "index_code" text,
    "industry_name" text,
    "parent_code" text,
    "level" text,
    "industry_code" text,
    "is_pub" text,
    "src" text,
    unique("_natural_key_hash","_revision_no"),
    unique("_current_natural_key_hash"),
    check ("_revision_no" > 0),
    check ("_is_current" in (0,1)),
    check ("_valid_to" is null or "_valid_from" is null or "_valid_to" >= "_valid_from")
);

create table if not exists "src_tushare_index_global" (
    "_observation_id" varchar(64) primary key,
    "_batch_id" varchar(64) not null,
    "_natural_key_hash" varchar(64) not null,
    "_revision_no" integer not null,
    "_is_current" integer not null default 1,
    "_current_natural_key_hash" varchar(64) generated always as (case when "_is_current" = 1 then "_natural_key_hash" else null end) stored,
    "_published_at" text,
    "_source_updated_at" text,
    "_observed_at" text not null,
    "_valid_from" text,
    "_valid_to" text,
    "_payload_hash" varchar(64) not null,
    "ts_code" text,
    "trade_date" date,
    "open" decimal(38,8),
    "close" decimal(38,8),
    "high" decimal(38,8),
    "low" decimal(38,8),
    "pre_close" decimal(38,8),
    "change" decimal(38,8),
    "pct_chg" decimal(38,8),
    "swing" decimal(38,8),
    "vol" decimal(38,8),
    "amount" decimal(38,8),
    unique("_natural_key_hash","_revision_no"),
    unique("_current_natural_key_hash"),
    check ("_revision_no" > 0),
    check ("_is_current" in (0,1)),
    check ("_valid_to" is null or "_valid_from" is null or "_valid_to" >= "_valid_from")
);

create table if not exists "src_tushare_index_member_all" (
    "_observation_id" varchar(64) primary key,
    "_batch_id" varchar(64) not null,
    "_natural_key_hash" varchar(64) not null,
    "_revision_no" integer not null,
    "_is_current" integer not null default 1,
    "_current_natural_key_hash" varchar(64) generated always as (case when "_is_current" = 1 then "_natural_key_hash" else null end) stored,
    "_published_at" text,
    "_source_updated_at" text,
    "_observed_at" text not null,
    "_valid_from" text,
    "_valid_to" text,
    "_payload_hash" varchar(64) not null,
    "l1_code" text,
    "l1_name" text,
    "l2_code" text,
    "l2_name" text,
    "l3_code" text,
    "l3_name" text,
    "ts_code" text,
    "name" text,
    "in_date" date,
    "out_date" date,
    "is_new" text,
    unique("_natural_key_hash","_revision_no"),
    unique("_current_natural_key_hash"),
    check ("_revision_no" > 0),
    check ("_is_current" in (0,1)),
    check ("_valid_to" is null or "_valid_from" is null or "_valid_to" >= "_valid_from")
);

create table if not exists "src_tushare_index_weight" (
    "_observation_id" varchar(64) primary key,
    "_batch_id" varchar(64) not null,
    "_natural_key_hash" varchar(64) not null,
    "_revision_no" integer not null,
    "_is_current" integer not null default 1,
    "_current_natural_key_hash" varchar(64) generated always as (case when "_is_current" = 1 then "_natural_key_hash" else null end) stored,
    "_published_at" text,
    "_source_updated_at" text,
    "_observed_at" text not null,
    "_valid_from" text,
    "_valid_to" text,
    "_payload_hash" varchar(64) not null,
    "index_code" text,
    "con_code" text,
    "trade_date" date,
    "weight" decimal(38,8),
    unique("_natural_key_hash","_revision_no"),
    unique("_current_natural_key_hash"),
    check ("_revision_no" > 0),
    check ("_is_current" in (0,1)),
    check ("_valid_to" is null or "_valid_from" is null or "_valid_to" >= "_valid_from")
);

create table if not exists "src_tushare_kpl_concept_cons" (
    "_observation_id" varchar(64) primary key,
    "_batch_id" varchar(64) not null,
    "_natural_key_hash" varchar(64) not null,
    "_revision_no" integer not null,
    "_is_current" integer not null default 1,
    "_current_natural_key_hash" varchar(64) generated always as (case when "_is_current" = 1 then "_natural_key_hash" else null end) stored,
    "_published_at" text,
    "_source_updated_at" text,
    "_observed_at" text not null,
    "_valid_from" text,
    "_valid_to" text,
    "_payload_hash" varchar(64) not null,
    "ts_code" text,
    "name" text,
    "con_name" text,
    "con_code" text,
    "trade_date" date,
    "desc" text,
    "hot_num" bigint,
    unique("_natural_key_hash","_revision_no"),
    unique("_current_natural_key_hash"),
    check ("_revision_no" > 0),
    check ("_is_current" in (0,1)),
    check ("_valid_to" is null or "_valid_from" is null or "_valid_to" >= "_valid_from")
);

create table if not exists "src_tushare_kpl_list" (
    "_observation_id" varchar(64) primary key,
    "_batch_id" varchar(64) not null,
    "_natural_key_hash" varchar(64) not null,
    "_revision_no" integer not null,
    "_is_current" integer not null default 1,
    "_current_natural_key_hash" varchar(64) generated always as (case when "_is_current" = 1 then "_natural_key_hash" else null end) stored,
    "_published_at" text,
    "_source_updated_at" text,
    "_observed_at" text not null,
    "_valid_from" text,
    "_valid_to" text,
    "_payload_hash" varchar(64) not null,
    "ts_code" text,
    "name" text,
    "trade_date" date,
    "lu_time" text,
    "ld_time" text,
    "open_time" text,
    "last_time" text,
    "lu_desc" text,
    "tag" text,
    "theme" text,
    "net_change" decimal(38,8),
    "bid_amount" decimal(38,8),
    "status" text,
    "bid_change" decimal(38,8),
    "bid_turnover" decimal(38,8),
    "lu_bid_vol" decimal(38,8),
    "pct_chg" decimal(38,8),
    "bid_pct_chg" decimal(38,8),
    "rt_pct_chg" decimal(38,8),
    "limit_order" decimal(38,8),
    "amount" decimal(38,8),
    "turnover_rate" decimal(38,8),
    "free_float" decimal(38,8),
    "lu_limit_order" decimal(38,8),
    unique("_natural_key_hash","_revision_no"),
    unique("_current_natural_key_hash"),
    check ("_revision_no" > 0),
    check ("_is_current" in (0,1)),
    check ("_valid_to" is null or "_valid_from" is null or "_valid_to" >= "_valid_from")
);

create table if not exists "src_tushare_limit_cpt_list" (
    "_observation_id" varchar(64) primary key,
    "_batch_id" varchar(64) not null,
    "_natural_key_hash" varchar(64) not null,
    "_revision_no" integer not null,
    "_is_current" integer not null default 1,
    "_current_natural_key_hash" varchar(64) generated always as (case when "_is_current" = 1 then "_natural_key_hash" else null end) stored,
    "_published_at" text,
    "_source_updated_at" text,
    "_observed_at" text not null,
    "_valid_from" text,
    "_valid_to" text,
    "_payload_hash" varchar(64) not null,
    "ts_code" text,
    "name" text,
    "trade_date" date,
    "days" bigint,
    "up_stat" text,
    "cons_nums" bigint,
    "up_nums" bigint,
    "pct_chg" decimal(38,8),
    "rank" text,
    unique("_natural_key_hash","_revision_no"),
    unique("_current_natural_key_hash"),
    check ("_revision_no" > 0),
    check ("_is_current" in (0,1)),
    check ("_valid_to" is null or "_valid_from" is null or "_valid_to" >= "_valid_from")
);

create table if not exists "src_tushare_limit_list_d" (
    "_observation_id" varchar(64) primary key,
    "_batch_id" varchar(64) not null,
    "_natural_key_hash" varchar(64) not null,
    "_revision_no" integer not null,
    "_is_current" integer not null default 1,
    "_current_natural_key_hash" varchar(64) generated always as (case when "_is_current" = 1 then "_natural_key_hash" else null end) stored,
    "_published_at" text,
    "_source_updated_at" text,
    "_observed_at" text not null,
    "_valid_from" text,
    "_valid_to" text,
    "_payload_hash" varchar(64) not null,
    "trade_date" date,
    "ts_code" text,
    "industry" text,
    "name" text,
    "close" decimal(38,8),
    "pct_chg" decimal(38,8),
    "amount" decimal(38,8),
    "limit_amount" decimal(38,8),
    "float_mv" decimal(38,8),
    "total_mv" decimal(38,8),
    "turnover_ratio" decimal(38,8),
    "fd_amount" decimal(38,8),
    "first_time" text,
    "last_time" text,
    "open_times" text,
    "up_stat" text,
    "limit_times" text,
    "limit" text,
    unique("_natural_key_hash","_revision_no"),
    unique("_current_natural_key_hash"),
    check ("_revision_no" > 0),
    check ("_is_current" in (0,1)),
    check ("_valid_to" is null or "_valid_from" is null or "_valid_to" >= "_valid_from")
);

create table if not exists "src_tushare_limit_list_ths" (
    "_observation_id" varchar(64) primary key,
    "_batch_id" varchar(64) not null,
    "_natural_key_hash" varchar(64) not null,
    "_revision_no" integer not null,
    "_is_current" integer not null default 1,
    "_current_natural_key_hash" varchar(64) generated always as (case when "_is_current" = 1 then "_natural_key_hash" else null end) stored,
    "_published_at" text,
    "_source_updated_at" text,
    "_observed_at" text not null,
    "_valid_from" text,
    "_valid_to" text,
    "_payload_hash" varchar(64) not null,
    "trade_date" date,
    "ts_code" text,
    "name" text,
    "price" decimal(38,8),
    "pct_chg" decimal(38,8),
    "open_num" bigint,
    "lu_desc" text,
    "limit_type" text,
    "tag" text,
    "status" text,
    "first_lu_time" text,
    "last_lu_time" text,
    "first_ld_time" text,
    "last_ld_time" text,
    "limit_order" decimal(38,8),
    "limit_amount" decimal(38,8),
    "turnover_rate" decimal(38,8),
    "free_float" decimal(38,8),
    "lu_limit_order" decimal(38,8),
    "limit_up_suc_rate" decimal(38,8),
    "turnover" decimal(38,8),
    "rise_rate" decimal(38,8),
    "sum_float" decimal(38,8),
    "market_type" text,
    unique("_natural_key_hash","_revision_no"),
    unique("_current_natural_key_hash"),
    check ("_revision_no" > 0),
    check ("_is_current" in (0,1)),
    check ("_valid_to" is null or "_valid_from" is null or "_valid_to" >= "_valid_from")
);

create table if not exists "src_tushare_limit_step" (
    "_observation_id" varchar(64) primary key,
    "_batch_id" varchar(64) not null,
    "_natural_key_hash" varchar(64) not null,
    "_revision_no" integer not null,
    "_is_current" integer not null default 1,
    "_current_natural_key_hash" varchar(64) generated always as (case when "_is_current" = 1 then "_natural_key_hash" else null end) stored,
    "_published_at" text,
    "_source_updated_at" text,
    "_observed_at" text not null,
    "_valid_from" text,
    "_valid_to" text,
    "_payload_hash" varchar(64) not null,
    "ts_code" text,
    "name" text,
    "trade_date" date,
    "nums" text,
    unique("_natural_key_hash","_revision_no"),
    unique("_current_natural_key_hash"),
    check ("_revision_no" > 0),
    check ("_is_current" in (0,1)),
    check ("_valid_to" is null or "_valid_from" is null or "_valid_to" >= "_valid_from")
);

create table if not exists "src_tushare_margin" (
    "_observation_id" varchar(64) primary key,
    "_batch_id" varchar(64) not null,
    "_natural_key_hash" varchar(64) not null,
    "_revision_no" integer not null,
    "_is_current" integer not null default 1,
    "_current_natural_key_hash" varchar(64) generated always as (case when "_is_current" = 1 then "_natural_key_hash" else null end) stored,
    "_published_at" text,
    "_source_updated_at" text,
    "_observed_at" text not null,
    "_valid_from" text,
    "_valid_to" text,
    "_payload_hash" varchar(64) not null,
    "trade_date" date,
    "exchange_id" text,
    "rzye" decimal(38,8),
    "rzmre" decimal(38,8),
    "rzche" decimal(38,8),
    "rqye" decimal(38,8),
    "rqmcl" decimal(38,8),
    "rzrqye" decimal(38,8),
    "rqyl" decimal(38,8),
    unique("_natural_key_hash","_revision_no"),
    unique("_current_natural_key_hash"),
    check ("_revision_no" > 0),
    check ("_is_current" in (0,1)),
    check ("_valid_to" is null or "_valid_from" is null or "_valid_to" >= "_valid_from")
);

create table if not exists "src_tushare_margin_detail" (
    "_observation_id" varchar(64) primary key,
    "_batch_id" varchar(64) not null,
    "_natural_key_hash" varchar(64) not null,
    "_revision_no" integer not null,
    "_is_current" integer not null default 1,
    "_current_natural_key_hash" varchar(64) generated always as (case when "_is_current" = 1 then "_natural_key_hash" else null end) stored,
    "_published_at" text,
    "_source_updated_at" text,
    "_observed_at" text not null,
    "_valid_from" text,
    "_valid_to" text,
    "_payload_hash" varchar(64) not null,
    "trade_date" date,
    "ts_code" text,
    "name" text,
    "rzye" decimal(38,8),
    "rqye" decimal(38,8),
    "rzmre" decimal(38,8),
    "rqyl" decimal(38,8),
    "rzche" decimal(38,8),
    "rqchl" decimal(38,8),
    "rqmcl" decimal(38,8),
    "rzrqye" decimal(38,8),
    unique("_natural_key_hash","_revision_no"),
    unique("_current_natural_key_hash"),
    check ("_revision_no" > 0),
    check ("_is_current" in (0,1)),
    check ("_valid_to" is null or "_valid_from" is null or "_valid_to" >= "_valid_from")
);

create table if not exists "src_tushare_margin_secs" (
    "_observation_id" varchar(64) primary key,
    "_batch_id" varchar(64) not null,
    "_natural_key_hash" varchar(64) not null,
    "_revision_no" integer not null,
    "_is_current" integer not null default 1,
    "_current_natural_key_hash" varchar(64) generated always as (case when "_is_current" = 1 then "_natural_key_hash" else null end) stored,
    "_published_at" text,
    "_source_updated_at" text,
    "_observed_at" text not null,
    "_valid_from" text,
    "_valid_to" text,
    "_payload_hash" varchar(64) not null,
    "trade_date" date,
    "ts_code" text,
    "name" text,
    "exchange" text,
    unique("_natural_key_hash","_revision_no"),
    unique("_current_natural_key_hash"),
    check ("_revision_no" > 0),
    check ("_is_current" in (0,1)),
    check ("_valid_to" is null or "_valid_from" is null or "_valid_to" >= "_valid_from")
);

create table if not exists "src_tushare_namechange" (
    "_observation_id" varchar(64) primary key,
    "_batch_id" varchar(64) not null,
    "_natural_key_hash" varchar(64) not null,
    "_revision_no" integer not null,
    "_is_current" integer not null default 1,
    "_current_natural_key_hash" varchar(64) generated always as (case when "_is_current" = 1 then "_natural_key_hash" else null end) stored,
    "_published_at" text,
    "_source_updated_at" text,
    "_observed_at" text not null,
    "_valid_from" text,
    "_valid_to" text,
    "_payload_hash" varchar(64) not null,
    "ts_code" text,
    "name" text,
    "start_date" date,
    "end_date" date,
    "ann_date" date,
    "change_reason" text,
    unique("_natural_key_hash","_revision_no"),
    unique("_current_natural_key_hash"),
    check ("_revision_no" > 0),
    check ("_is_current" in (0,1)),
    check ("_valid_to" is null or "_valid_from" is null or "_valid_to" >= "_valid_from")
);

create table if not exists "src_tushare_new_share" (
    "_observation_id" varchar(64) primary key,
    "_batch_id" varchar(64) not null,
    "_natural_key_hash" varchar(64) not null,
    "_revision_no" integer not null,
    "_is_current" integer not null default 1,
    "_current_natural_key_hash" varchar(64) generated always as (case when "_is_current" = 1 then "_natural_key_hash" else null end) stored,
    "_published_at" text,
    "_source_updated_at" text,
    "_observed_at" text not null,
    "_valid_from" text,
    "_valid_to" text,
    "_payload_hash" varchar(64) not null,
    "ts_code" text,
    "sub_code" text,
    "name" text,
    "ipo_date" date,
    "issue_date" date,
    "amount" decimal(38,8),
    "market_amount" decimal(38,8),
    "price" decimal(38,8),
    "pe" decimal(38,8),
    "limit_amount" decimal(38,8),
    "funds" decimal(38,8),
    "ballot" decimal(38,8),
    unique("_natural_key_hash","_revision_no"),
    unique("_current_natural_key_hash"),
    check ("_revision_no" > 0),
    check ("_is_current" in (0,1)),
    check ("_valid_to" is null or "_valid_from" is null or "_valid_to" >= "_valid_from")
);

create table if not exists "src_tushare_opt_basic" (
    "_observation_id" varchar(64) primary key,
    "_batch_id" varchar(64) not null,
    "_natural_key_hash" varchar(64) not null,
    "_revision_no" integer not null,
    "_is_current" integer not null default 1,
    "_current_natural_key_hash" varchar(64) generated always as (case when "_is_current" = 1 then "_natural_key_hash" else null end) stored,
    "_published_at" text,
    "_source_updated_at" text,
    "_observed_at" text not null,
    "_valid_from" text,
    "_valid_to" text,
    "_payload_hash" varchar(64) not null,
    "ts_code" text,
    "symbol" text,
    "exchange" text,
    "name" text,
    "per_unit" text,
    "opt_code" text,
    "opt_type" text,
    "call_put" text,
    "exercise_type" text,
    "exercise_price" decimal(38,8),
    "opt_multiplier" decimal(38,8),
    "s_month" text,
    "maturity_date" date,
    "list_price" decimal(38,8),
    "list_date" date,
    "delist_date" date,
    "last_edate" date,
    "last_ddate" date,
    "quote_unit" text,
    "min_price_chg" text,
    unique("_natural_key_hash","_revision_no"),
    unique("_current_natural_key_hash"),
    check ("_revision_no" > 0),
    check ("_is_current" in (0,1)),
    check ("_valid_to" is null or "_valid_from" is null or "_valid_to" >= "_valid_from")
);

create table if not exists "src_tushare_pledge_detail" (
    "_observation_id" varchar(64) primary key,
    "_batch_id" varchar(64) not null,
    "_natural_key_hash" varchar(64) not null,
    "_revision_no" integer not null,
    "_is_current" integer not null default 1,
    "_current_natural_key_hash" varchar(64) generated always as (case when "_is_current" = 1 then "_natural_key_hash" else null end) stored,
    "_published_at" text,
    "_source_updated_at" text,
    "_observed_at" text not null,
    "_valid_from" text,
    "_valid_to" text,
    "_payload_hash" varchar(64) not null,
    "ts_code" text,
    "ann_date" date,
    "holder_name" text,
    "pledge_amount" decimal(38,8),
    "start_date" date,
    "end_date" date,
    "is_release" text,
    "release_date" date,
    "pledgor" text,
    "holding_amount" decimal(38,8),
    "pledged_amount" decimal(38,8),
    "p_total_ratio" decimal(38,8),
    "h_total_ratio" decimal(38,8),
    "is_buyback" text,
    unique("_natural_key_hash","_revision_no"),
    unique("_current_natural_key_hash"),
    check ("_revision_no" > 0),
    check ("_is_current" in (0,1)),
    check ("_valid_to" is null or "_valid_from" is null or "_valid_to" >= "_valid_from")
);

create table if not exists "src_tushare_pledge_stat" (
    "_observation_id" varchar(64) primary key,
    "_batch_id" varchar(64) not null,
    "_natural_key_hash" varchar(64) not null,
    "_revision_no" integer not null,
    "_is_current" integer not null default 1,
    "_current_natural_key_hash" varchar(64) generated always as (case when "_is_current" = 1 then "_natural_key_hash" else null end) stored,
    "_published_at" text,
    "_source_updated_at" text,
    "_observed_at" text not null,
    "_valid_from" text,
    "_valid_to" text,
    "_payload_hash" varchar(64) not null,
    "ts_code" text,
    "end_date" date,
    "pledge_count" bigint,
    "unrest_pledge" decimal(38,8),
    "rest_pledge" decimal(38,8),
    "total_share" decimal(38,8),
    "pledge_ratio" decimal(38,8),
    unique("_natural_key_hash","_revision_no"),
    unique("_current_natural_key_hash"),
    check ("_revision_no" > 0),
    check ("_is_current" in (0,1)),
    check ("_valid_to" is null or "_valid_from" is null or "_valid_to" >= "_valid_from")
);

create table if not exists "src_tushare_pro_bar_equity" (
    "_observation_id" varchar(64) primary key,
    "_batch_id" varchar(64) not null,
    "_natural_key_hash" varchar(64) not null,
    "_revision_no" integer not null,
    "_is_current" integer not null default 1,
    "_current_natural_key_hash" varchar(64) generated always as (case when "_is_current" = 1 then "_natural_key_hash" else null end) stored,
    "_published_at" text,
    "_source_updated_at" text,
    "_observed_at" text not null,
    "_valid_from" text,
    "_valid_to" text,
    "_payload_hash" varchar(64) not null,
    "ts_code" text,
    "start_date" date,
    "end_date" date,
    "asset" text,
    "adj" text,
    "freq" text,
    "ma" text,
    unique("_natural_key_hash","_revision_no"),
    unique("_current_natural_key_hash"),
    check ("_revision_no" > 0),
    check ("_is_current" in (0,1)),
    check ("_valid_to" is null or "_valid_from" is null or "_valid_to" >= "_valid_from")
);

create table if not exists "src_tushare_pro_bar_general" (
    "_observation_id" varchar(64) primary key,
    "_batch_id" varchar(64) not null,
    "_natural_key_hash" varchar(64) not null,
    "_revision_no" integer not null,
    "_is_current" integer not null default 1,
    "_current_natural_key_hash" varchar(64) generated always as (case when "_is_current" = 1 then "_natural_key_hash" else null end) stored,
    "_published_at" text,
    "_source_updated_at" text,
    "_observed_at" text not null,
    "_valid_from" text,
    "_valid_to" text,
    "_payload_hash" varchar(64) not null,
    "ts_code" text,
    "start_date" date,
    "end_date" date,
    "asset" text,
    "adj" text,
    "freq" text,
    "ma" text,
    "factors" text,
    "adjfactor" text,
    unique("_natural_key_hash","_revision_no"),
    unique("_current_natural_key_hash"),
    check ("_revision_no" > 0),
    check ("_is_current" in (0,1)),
    check ("_valid_to" is null or "_valid_from" is null or "_valid_to" >= "_valid_from")
);

create table if not exists "src_tushare_repurchase" (
    "_observation_id" varchar(64) primary key,
    "_batch_id" varchar(64) not null,
    "_natural_key_hash" varchar(64) not null,
    "_revision_no" integer not null,
    "_is_current" integer not null default 1,
    "_current_natural_key_hash" varchar(64) generated always as (case when "_is_current" = 1 then "_natural_key_hash" else null end) stored,
    "_published_at" text,
    "_source_updated_at" text,
    "_observed_at" text not null,
    "_valid_from" text,
    "_valid_to" text,
    "_payload_hash" varchar(64) not null,
    "ts_code" text,
    "ann_date" date,
    "end_date" date,
    "proc" text,
    "exp_date" date,
    "vol" decimal(38,8),
    "amount" decimal(38,8),
    "high_limit" decimal(38,8),
    "low_limit" decimal(38,8),
    unique("_natural_key_hash","_revision_no"),
    unique("_current_natural_key_hash"),
    check ("_revision_no" > 0),
    check ("_is_current" in (0,1)),
    check ("_valid_to" is null or "_valid_from" is null or "_valid_to" >= "_valid_from")
);

create table if not exists "src_tushare_share_float" (
    "_observation_id" varchar(64) primary key,
    "_batch_id" varchar(64) not null,
    "_natural_key_hash" varchar(64) not null,
    "_revision_no" integer not null,
    "_is_current" integer not null default 1,
    "_current_natural_key_hash" varchar(64) generated always as (case when "_is_current" = 1 then "_natural_key_hash" else null end) stored,
    "_published_at" text,
    "_source_updated_at" text,
    "_observed_at" text not null,
    "_valid_from" text,
    "_valid_to" text,
    "_payload_hash" varchar(64) not null,
    "ts_code" text,
    "ann_date" date,
    "float_date" date,
    "float_share" decimal(38,8),
    "float_ratio" decimal(38,8),
    "holder_name" text,
    "share_type" text,
    unique("_natural_key_hash","_revision_no"),
    unique("_current_natural_key_hash"),
    check ("_revision_no" > 0),
    check ("_is_current" in (0,1)),
    check ("_valid_to" is null or "_valid_from" is null or "_valid_to" >= "_valid_from")
);

create table if not exists "src_tushare_slb_len" (
    "_observation_id" varchar(64) primary key,
    "_batch_id" varchar(64) not null,
    "_natural_key_hash" varchar(64) not null,
    "_revision_no" integer not null,
    "_is_current" integer not null default 1,
    "_current_natural_key_hash" varchar(64) generated always as (case when "_is_current" = 1 then "_natural_key_hash" else null end) stored,
    "_published_at" text,
    "_source_updated_at" text,
    "_observed_at" text not null,
    "_valid_from" text,
    "_valid_to" text,
    "_payload_hash" varchar(64) not null,
    "trade_date" date,
    "ob" decimal(38,8),
    "auc_amount" decimal(38,8),
    "repo_amount" decimal(38,8),
    "repay_amount" decimal(38,8),
    "cb" decimal(38,8),
    unique("_natural_key_hash","_revision_no"),
    unique("_current_natural_key_hash"),
    check ("_revision_no" > 0),
    check ("_is_current" in (0,1)),
    check ("_valid_to" is null or "_valid_from" is null or "_valid_to" >= "_valid_from")
);

create table if not exists "src_tushare_slb_len_mm" (
    "_observation_id" varchar(64) primary key,
    "_batch_id" varchar(64) not null,
    "_natural_key_hash" varchar(64) not null,
    "_revision_no" integer not null,
    "_is_current" integer not null default 1,
    "_current_natural_key_hash" varchar(64) generated always as (case when "_is_current" = 1 then "_natural_key_hash" else null end) stored,
    "_published_at" text,
    "_source_updated_at" text,
    "_observed_at" text not null,
    "_valid_from" text,
    "_valid_to" text,
    "_payload_hash" varchar(64) not null,
    "trade_date" date,
    "ts_code" text,
    "name" text,
    "ope_inv" decimal(38,8),
    "lent_qnt" decimal(38,8),
    "cls_inv" decimal(38,8),
    "end_bal" decimal(38,8),
    unique("_natural_key_hash","_revision_no"),
    unique("_current_natural_key_hash"),
    check ("_revision_no" > 0),
    check ("_is_current" in (0,1)),
    check ("_valid_to" is null or "_valid_from" is null or "_valid_to" >= "_valid_from")
);

create table if not exists "src_tushare_slb_sec" (
    "_observation_id" varchar(64) primary key,
    "_batch_id" varchar(64) not null,
    "_natural_key_hash" varchar(64) not null,
    "_revision_no" integer not null,
    "_is_current" integer not null default 1,
    "_current_natural_key_hash" varchar(64) generated always as (case when "_is_current" = 1 then "_natural_key_hash" else null end) stored,
    "_published_at" text,
    "_source_updated_at" text,
    "_observed_at" text not null,
    "_valid_from" text,
    "_valid_to" text,
    "_payload_hash" varchar(64) not null,
    "trade_date" date,
    "ts_code" text,
    "name" text,
    "ope_inv" decimal(38,8),
    "lent_qnt" decimal(38,8),
    "cls_inv" decimal(38,8),
    "end_bal" decimal(38,8),
    unique("_natural_key_hash","_revision_no"),
    unique("_current_natural_key_hash"),
    check ("_revision_no" > 0),
    check ("_is_current" in (0,1)),
    check ("_valid_to" is null or "_valid_from" is null or "_valid_to" >= "_valid_from")
);

create table if not exists "src_tushare_slb_sec_detail" (
    "_observation_id" varchar(64) primary key,
    "_batch_id" varchar(64) not null,
    "_natural_key_hash" varchar(64) not null,
    "_revision_no" integer not null,
    "_is_current" integer not null default 1,
    "_current_natural_key_hash" varchar(64) generated always as (case when "_is_current" = 1 then "_natural_key_hash" else null end) stored,
    "_published_at" text,
    "_source_updated_at" text,
    "_observed_at" text not null,
    "_valid_from" text,
    "_valid_to" text,
    "_payload_hash" varchar(64) not null,
    "trade_date" date,
    "ts_code" text,
    "name" text,
    "tenor" text,
    "fee_rate" decimal(38,8),
    "lent_qnt" decimal(38,8),
    unique("_natural_key_hash","_revision_no"),
    unique("_current_natural_key_hash"),
    check ("_revision_no" > 0),
    check ("_is_current" in (0,1)),
    check ("_valid_to" is null or "_valid_from" is null or "_valid_to" >= "_valid_from")
);

create table if not exists "src_tushare_st" (
    "_observation_id" varchar(64) primary key,
    "_batch_id" varchar(64) not null,
    "_natural_key_hash" varchar(64) not null,
    "_revision_no" integer not null,
    "_is_current" integer not null default 1,
    "_current_natural_key_hash" varchar(64) generated always as (case when "_is_current" = 1 then "_natural_key_hash" else null end) stored,
    "_published_at" text,
    "_source_updated_at" text,
    "_observed_at" text not null,
    "_valid_from" text,
    "_valid_to" text,
    "_payload_hash" varchar(64) not null,
    "ts_code" text,
    "name" text,
    "pub_date" date,
    "imp_date" date,
    "st_type" text,
    "st_reason" text,
    "st_explain" text,
    unique("_natural_key_hash","_revision_no"),
    unique("_current_natural_key_hash"),
    check ("_revision_no" > 0),
    check ("_is_current" in (0,1)),
    check ("_valid_to" is null or "_valid_from" is null or "_valid_to" >= "_valid_from")
);

create table if not exists "src_tushare_stk_account" (
    "_observation_id" varchar(64) primary key,
    "_batch_id" varchar(64) not null,
    "_natural_key_hash" varchar(64) not null,
    "_revision_no" integer not null,
    "_is_current" integer not null default 1,
    "_current_natural_key_hash" varchar(64) generated always as (case when "_is_current" = 1 then "_natural_key_hash" else null end) stored,
    "_published_at" text,
    "_source_updated_at" text,
    "_observed_at" text not null,
    "_valid_from" text,
    "_valid_to" text,
    "_payload_hash" varchar(64) not null,
    "date" date,
    "weekly_new" decimal(38,8),
    "total" decimal(38,8),
    "weekly_hold" decimal(38,8),
    "weekly_trade" decimal(38,8),
    unique("_natural_key_hash","_revision_no"),
    unique("_current_natural_key_hash"),
    check ("_revision_no" > 0),
    check ("_is_current" in (0,1)),
    check ("_valid_to" is null or "_valid_from" is null or "_valid_to" >= "_valid_from")
);

create table if not exists "src_tushare_stk_account_old" (
    "_observation_id" varchar(64) primary key,
    "_batch_id" varchar(64) not null,
    "_natural_key_hash" varchar(64) not null,
    "_revision_no" integer not null,
    "_is_current" integer not null default 1,
    "_current_natural_key_hash" varchar(64) generated always as (case when "_is_current" = 1 then "_natural_key_hash" else null end) stored,
    "_published_at" text,
    "_source_updated_at" text,
    "_observed_at" text not null,
    "_valid_from" text,
    "_valid_to" text,
    "_payload_hash" varchar(64) not null,
    "date" date,
    "new_sh" bigint,
    "new_sz" bigint,
    "active_sh" decimal(38,8),
    "active_sz" decimal(38,8),
    "total_sh" decimal(38,8),
    "total_sz" decimal(38,8),
    "trade_sh" decimal(38,8),
    "trade_sz" decimal(38,8),
    unique("_natural_key_hash","_revision_no"),
    unique("_current_natural_key_hash"),
    check ("_revision_no" > 0),
    check ("_is_current" in (0,1)),
    check ("_valid_to" is null or "_valid_from" is null or "_valid_to" >= "_valid_from")
);

create table if not exists "src_tushare_stk_ah_comparison" (
    "_observation_id" varchar(64) primary key,
    "_batch_id" varchar(64) not null,
    "_natural_key_hash" varchar(64) not null,
    "_revision_no" integer not null,
    "_is_current" integer not null default 1,
    "_current_natural_key_hash" varchar(64) generated always as (case when "_is_current" = 1 then "_natural_key_hash" else null end) stored,
    "_published_at" text,
    "_source_updated_at" text,
    "_observed_at" text not null,
    "_valid_from" text,
    "_valid_to" text,
    "_payload_hash" varchar(64) not null,
    "hk_code" text,
    "ts_code" text,
    "trade_date" date,
    "hk_name" text,
    "hk_pct_chg" decimal(38,8),
    "hk_close" decimal(38,8),
    "name" text,
    "close" decimal(38,8),
    "pct_chg" decimal(38,8),
    "ah_comparison" decimal(38,8),
    "ah_premium" decimal(38,8),
    unique("_natural_key_hash","_revision_no"),
    unique("_current_natural_key_hash"),
    check ("_revision_no" > 0),
    check ("_is_current" in (0,1)),
    check ("_valid_to" is null or "_valid_from" is null or "_valid_to" >= "_valid_from")
);

create table if not exists "src_tushare_stk_alert" (
    "_observation_id" varchar(64) primary key,
    "_batch_id" varchar(64) not null,
    "_natural_key_hash" varchar(64) not null,
    "_revision_no" integer not null,
    "_is_current" integer not null default 1,
    "_current_natural_key_hash" varchar(64) generated always as (case when "_is_current" = 1 then "_natural_key_hash" else null end) stored,
    "_published_at" text,
    "_source_updated_at" text,
    "_observed_at" text not null,
    "_valid_from" text,
    "_valid_to" text,
    "_payload_hash" varchar(64) not null,
    "ts_code" text,
    "name" text,
    "start_date" date,
    "end_date" date,
    "type" text,
    unique("_natural_key_hash","_revision_no"),
    unique("_current_natural_key_hash"),
    check ("_revision_no" > 0),
    check ("_is_current" in (0,1)),
    check ("_valid_to" is null or "_valid_from" is null or "_valid_to" >= "_valid_from")
);

create table if not exists "src_tushare_stk_auction" (
    "_observation_id" varchar(64) primary key,
    "_batch_id" varchar(64) not null,
    "_natural_key_hash" varchar(64) not null,
    "_revision_no" integer not null,
    "_is_current" integer not null default 1,
    "_current_natural_key_hash" varchar(64) generated always as (case when "_is_current" = 1 then "_natural_key_hash" else null end) stored,
    "_published_at" text,
    "_source_updated_at" text,
    "_observed_at" text not null,
    "_valid_from" text,
    "_valid_to" text,
    "_payload_hash" varchar(64) not null,
    "ts_code" text,
    "trade_date" date,
    "vol" bigint,
    "price" bigint,
    "amount" decimal(38,8),
    "pre_close" decimal(38,8),
    "turnover_rate" decimal(38,8),
    "volume_ratio" decimal(38,8),
    "float_share" decimal(38,8),
    unique("_natural_key_hash","_revision_no"),
    unique("_current_natural_key_hash"),
    check ("_revision_no" > 0),
    check ("_is_current" in (0,1)),
    check ("_valid_to" is null or "_valid_from" is null or "_valid_to" >= "_valid_from")
);

create table if not exists "src_tushare_stk_auction_c" (
    "_observation_id" varchar(64) primary key,
    "_batch_id" varchar(64) not null,
    "_natural_key_hash" varchar(64) not null,
    "_revision_no" integer not null,
    "_is_current" integer not null default 1,
    "_current_natural_key_hash" varchar(64) generated always as (case when "_is_current" = 1 then "_natural_key_hash" else null end) stored,
    "_published_at" text,
    "_source_updated_at" text,
    "_observed_at" text not null,
    "_valid_from" text,
    "_valid_to" text,
    "_payload_hash" varchar(64) not null,
    "ts_code" text,
    "trade_date" date,
    "close" decimal(38,8),
    "open" decimal(38,8),
    "high" decimal(38,8),
    "low" decimal(38,8),
    "vol" decimal(38,8),
    "amount" decimal(38,8),
    "vwap" decimal(38,8),
    unique("_natural_key_hash","_revision_no"),
    unique("_current_natural_key_hash"),
    check ("_revision_no" > 0),
    check ("_is_current" in (0,1)),
    check ("_valid_to" is null or "_valid_from" is null or "_valid_to" >= "_valid_from")
);

create table if not exists "src_tushare_stk_auction_o" (
    "_observation_id" varchar(64) primary key,
    "_batch_id" varchar(64) not null,
    "_natural_key_hash" varchar(64) not null,
    "_revision_no" integer not null,
    "_is_current" integer not null default 1,
    "_current_natural_key_hash" varchar(64) generated always as (case when "_is_current" = 1 then "_natural_key_hash" else null end) stored,
    "_published_at" text,
    "_source_updated_at" text,
    "_observed_at" text not null,
    "_valid_from" text,
    "_valid_to" text,
    "_payload_hash" varchar(64) not null,
    "ts_code" text,
    "trade_date" date,
    "close" decimal(38,8),
    "open" decimal(38,8),
    "high" decimal(38,8),
    "low" decimal(38,8),
    "vol" decimal(38,8),
    "amount" decimal(38,8),
    "vwap" decimal(38,8),
    unique("_natural_key_hash","_revision_no"),
    unique("_current_natural_key_hash"),
    check ("_revision_no" > 0),
    check ("_is_current" in (0,1)),
    check ("_valid_to" is null or "_valid_from" is null or "_valid_to" >= "_valid_from")
);

create table if not exists "src_tushare_stk_factor" (
    "_observation_id" varchar(64) primary key,
    "_batch_id" varchar(64) not null,
    "_natural_key_hash" varchar(64) not null,
    "_revision_no" integer not null,
    "_is_current" integer not null default 1,
    "_current_natural_key_hash" varchar(64) generated always as (case when "_is_current" = 1 then "_natural_key_hash" else null end) stored,
    "_published_at" text,
    "_source_updated_at" text,
    "_observed_at" text not null,
    "_valid_from" text,
    "_valid_to" text,
    "_payload_hash" varchar(64) not null,
    "ts_code" text,
    "trade_date" date,
    "close" decimal(38,8),
    "open" decimal(38,8),
    "high" decimal(38,8),
    "low" decimal(38,8),
    "pre_close" decimal(38,8),
    "change" decimal(38,8),
    "pct_change" decimal(38,8),
    "vol" decimal(38,8),
    "amount" decimal(38,8),
    "adj_factor" decimal(38,8),
    "open_hfq" decimal(38,8),
    "open_qfq" decimal(38,8),
    "close_hfq" decimal(38,8),
    "close_qfq" decimal(38,8),
    "high_hfq" decimal(38,8),
    "high_qfq" decimal(38,8),
    "low_hfq" decimal(38,8),
    "low_qfq" decimal(38,8),
    "pre_close_hfq" decimal(38,8),
    "pre_close_qfq" decimal(38,8),
    "macd_dif" decimal(38,8),
    "macd_dea" decimal(38,8),
    "macd" decimal(38,8),
    "kdj_k" decimal(38,8),
    "kdj_d" decimal(38,8),
    "kdj_j" decimal(38,8),
    "rsi_6" decimal(38,8),
    "rsi_12" decimal(38,8),
    "rsi_24" decimal(38,8),
    "boll_upper" decimal(38,8),
    "boll_mid" decimal(38,8),
    "boll_lower" decimal(38,8),
    "cci" decimal(38,8),
    unique("_natural_key_hash","_revision_no"),
    unique("_current_natural_key_hash"),
    check ("_revision_no" > 0),
    check ("_is_current" in (0,1)),
    check ("_valid_to" is null or "_valid_from" is null or "_valid_to" >= "_valid_from")
);

create table if not exists "src_tushare_stk_factor_pro" (
    "_observation_id" varchar(64) primary key,
    "_batch_id" varchar(64) not null,
    "_natural_key_hash" varchar(64) not null,
    "_revision_no" integer not null,
    "_is_current" integer not null default 1,
    "_current_natural_key_hash" varchar(64) generated always as (case when "_is_current" = 1 then "_natural_key_hash" else null end) stored,
    "_published_at" text,
    "_source_updated_at" text,
    "_observed_at" text not null,
    "_valid_from" text,
    "_valid_to" text,
    "_payload_hash" varchar(64) not null,
    "ts_code" text,
    "trade_date" date,
    "open" decimal(38,8),
    "open_hfq" decimal(38,8),
    "open_qfq" decimal(38,8),
    "high" decimal(38,8),
    "high_hfq" decimal(38,8),
    "high_qfq" decimal(38,8),
    "low" decimal(38,8),
    "low_hfq" decimal(38,8),
    "low_qfq" decimal(38,8),
    "close" decimal(38,8),
    "close_hfq" decimal(38,8),
    "close_qfq" decimal(38,8),
    "pre_close" decimal(38,8),
    "change" decimal(38,8),
    "pct_chg" decimal(38,8),
    "vol" decimal(38,8),
    "amount" decimal(38,8),
    "turnover_rate" decimal(38,8),
    "turnover_rate_f" decimal(38,8),
    "volume_ratio" decimal(38,8),
    "pe" decimal(38,8),
    "pe_ttm" decimal(38,8),
    "pb" decimal(38,8),
    "ps" decimal(38,8),
    "ps_ttm" decimal(38,8),
    "dv_ratio" decimal(38,8),
    "dv_ttm" decimal(38,8),
    "total_share" decimal(38,8),
    "float_share" decimal(38,8),
    "free_share" decimal(38,8),
    "total_mv" decimal(38,8),
    "circ_mv" decimal(38,8),
    "adj_factor" decimal(38,8),
    "asi_bfq" decimal(38,8),
    "asi_hfq" decimal(38,8),
    "asi_qfq" decimal(38,8),
    "asit_bfq" decimal(38,8),
    "asit_hfq" decimal(38,8),
    "asit_qfq" decimal(38,8),
    "atr_bfq" decimal(38,8),
    "atr_hfq" decimal(38,8),
    "atr_qfq" decimal(38,8),
    "bbi_bfq" decimal(38,8),
    "bbi_hfq" decimal(38,8),
    "bbi_qfq" decimal(38,8),
    "bias1_bfq" decimal(38,8),
    "bias1_hfq" decimal(38,8),
    "bias1_qfq" decimal(38,8),
    "bias2_bfq" decimal(38,8),
    "bias2_hfq" decimal(38,8),
    "bias2_qfq" decimal(38,8),
    "bias3_bfq" decimal(38,8),
    "bias3_hfq" decimal(38,8),
    "bias3_qfq" decimal(38,8),
    "boll_lower_bfq" decimal(38,8),
    "boll_lower_hfq" decimal(38,8),
    "boll_lower_qfq" decimal(38,8),
    "boll_mid_bfq" decimal(38,8),
    "boll_mid_hfq" decimal(38,8),
    "boll_mid_qfq" decimal(38,8),
    "boll_upper_bfq" decimal(38,8),
    "boll_upper_hfq" decimal(38,8),
    "boll_upper_qfq" decimal(38,8),
    "brar_ar_bfq" decimal(38,8),
    "brar_ar_hfq" decimal(38,8),
    "brar_ar_qfq" decimal(38,8),
    "brar_br_bfq" decimal(38,8),
    "brar_br_hfq" decimal(38,8),
    "brar_br_qfq" decimal(38,8),
    "cci_bfq" decimal(38,8),
    "cci_hfq" decimal(38,8),
    "cci_qfq" decimal(38,8),
    "cr_bfq" decimal(38,8),
    "cr_hfq" decimal(38,8),
    "cr_qfq" decimal(38,8),
    "dfma_dif_bfq" decimal(38,8),
    "dfma_dif_hfq" decimal(38,8),
    "dfma_dif_qfq" decimal(38,8),
    "dfma_difma_bfq" decimal(38,8),
    "dfma_difma_hfq" decimal(38,8),
    "dfma_difma_qfq" decimal(38,8),
    "dmi_adx_bfq" decimal(38,8),
    "dmi_adx_hfq" decimal(38,8),
    "dmi_adx_qfq" decimal(38,8),
    "dmi_adxr_bfq" decimal(38,8),
    "dmi_adxr_hfq" decimal(38,8),
    "dmi_adxr_qfq" decimal(38,8),
    "dmi_mdi_bfq" decimal(38,8),
    "dmi_mdi_hfq" decimal(38,8),
    "dmi_mdi_qfq" decimal(38,8),
    "dmi_pdi_bfq" decimal(38,8),
    "dmi_pdi_hfq" decimal(38,8),
    "dmi_pdi_qfq" decimal(38,8),
    "downdays" decimal(38,8),
    "updays" decimal(38,8),
    "dpo_bfq" decimal(38,8),
    "dpo_hfq" decimal(38,8),
    "dpo_qfq" decimal(38,8),
    "madpo_bfq" decimal(38,8),
    "madpo_hfq" decimal(38,8),
    "madpo_qfq" decimal(38,8),
    "ema_bfq_10" decimal(38,8),
    "ema_bfq_20" decimal(38,8),
    "ema_bfq_250" decimal(38,8),
    "ema_bfq_30" decimal(38,8),
    "ema_bfq_5" decimal(38,8),
    "ema_bfq_60" decimal(38,8),
    "ema_bfq_90" decimal(38,8),
    "ema_hfq_10" decimal(38,8),
    "ema_hfq_20" decimal(38,8),
    "ema_hfq_250" decimal(38,8),
    "ema_hfq_30" decimal(38,8),
    "ema_hfq_5" decimal(38,8),
    "ema_hfq_60" decimal(38,8),
    "ema_hfq_90" decimal(38,8),
    "ema_qfq_10" decimal(38,8),
    "ema_qfq_20" decimal(38,8),
    "ema_qfq_250" decimal(38,8),
    "ema_qfq_30" decimal(38,8),
    "ema_qfq_5" decimal(38,8),
    "ema_qfq_60" decimal(38,8),
    "ema_qfq_90" decimal(38,8),
    "emv_bfq" decimal(38,8),
    "emv_hfq" decimal(38,8),
    "emv_qfq" decimal(38,8),
    "maemv_bfq" decimal(38,8),
    "maemv_hfq" decimal(38,8),
    "maemv_qfq" decimal(38,8),
    "expma_12_bfq" decimal(38,8),
    "expma_12_hfq" decimal(38,8),
    "expma_12_qfq" decimal(38,8),
    "expma_50_bfq" decimal(38,8),
    "expma_50_hfq" decimal(38,8),
    "expma_50_qfq" decimal(38,8),
    "kdj_bfq" decimal(38,8),
    "kdj_hfq" decimal(38,8),
    "kdj_qfq" decimal(38,8),
    "kdj_d_bfq" decimal(38,8),
    "kdj_d_hfq" decimal(38,8),
    "kdj_d_qfq" decimal(38,8),
    "kdj_k_bfq" decimal(38,8),
    "kdj_k_hfq" decimal(38,8),
    "kdj_k_qfq" decimal(38,8),
    "ktn_down_bfq" decimal(38,8),
    "ktn_down_hfq" decimal(38,8),
    "ktn_down_qfq" decimal(38,8),
    "ktn_mid_bfq" decimal(38,8),
    "ktn_mid_hfq" decimal(38,8),
    "ktn_mid_qfq" decimal(38,8),
    "ktn_upper_bfq" decimal(38,8),
    "ktn_upper_hfq" decimal(38,8),
    "ktn_upper_qfq" decimal(38,8),
    "lowdays" decimal(38,8),
    "topdays" decimal(38,8),
    "ma_bfq_10" decimal(38,8),
    "ma_bfq_20" decimal(38,8),
    "ma_bfq_250" decimal(38,8),
    "ma_bfq_30" decimal(38,8),
    "ma_bfq_5" decimal(38,8),
    "ma_bfq_60" decimal(38,8),
    "ma_bfq_90" decimal(38,8),
    "ma_hfq_10" decimal(38,8),
    "ma_hfq_20" decimal(38,8),
    "ma_hfq_250" decimal(38,8),
    "ma_hfq_30" decimal(38,8),
    "ma_hfq_5" decimal(38,8),
    "ma_hfq_60" decimal(38,8),
    "ma_hfq_90" decimal(38,8),
    "ma_qfq_10" decimal(38,8),
    "ma_qfq_20" decimal(38,8),
    "ma_qfq_250" decimal(38,8),
    "ma_qfq_30" decimal(38,8),
    "ma_qfq_5" decimal(38,8),
    "ma_qfq_60" decimal(38,8),
    "ma_qfq_90" decimal(38,8),
    "macd_bfq" decimal(38,8),
    "macd_hfq" decimal(38,8),
    "macd_qfq" decimal(38,8),
    "macd_dea_bfq" decimal(38,8),
    "macd_dea_hfq" decimal(38,8),
    "macd_dea_qfq" decimal(38,8),
    "macd_dif_bfq" decimal(38,8),
    "macd_dif_hfq" decimal(38,8),
    "macd_dif_qfq" decimal(38,8),
    "mass_bfq" decimal(38,8),
    "mass_hfq" decimal(38,8),
    "mass_qfq" decimal(38,8),
    "ma_mass_bfq" decimal(38,8),
    "ma_mass_hfq" decimal(38,8),
    "ma_mass_qfq" decimal(38,8),
    "mfi_bfq" decimal(38,8),
    "mfi_hfq" decimal(38,8),
    "mfi_qfq" decimal(38,8),
    "mtm_bfq" decimal(38,8),
    "mtm_hfq" decimal(38,8),
    "mtm_qfq" decimal(38,8),
    "mtmma_bfq" decimal(38,8),
    "mtmma_hfq" decimal(38,8),
    "mtmma_qfq" decimal(38,8),
    "obv_bfq" decimal(38,8),
    "obv_hfq" decimal(38,8),
    "obv_qfq" decimal(38,8),
    "psy_bfq" decimal(38,8),
    "psy_hfq" decimal(38,8),
    "psy_qfq" decimal(38,8),
    "psyma_bfq" decimal(38,8),
    "psyma_hfq" decimal(38,8),
    "psyma_qfq" decimal(38,8),
    "roc_bfq" decimal(38,8),
    "roc_hfq" decimal(38,8),
    "roc_qfq" decimal(38,8),
    "maroc_bfq" decimal(38,8),
    "maroc_hfq" decimal(38,8),
    "maroc_qfq" decimal(38,8),
    "rsi_bfq_12" decimal(38,8),
    "rsi_bfq_24" decimal(38,8),
    "rsi_bfq_6" decimal(38,8),
    "rsi_hfq_12" decimal(38,8),
    "rsi_hfq_24" decimal(38,8),
    "rsi_hfq_6" decimal(38,8),
    "rsi_qfq_12" decimal(38,8),
    "rsi_qfq_24" decimal(38,8),
    "rsi_qfq_6" decimal(38,8),
    "taq_down_bfq" decimal(38,8),
    "taq_down_hfq" decimal(38,8),
    "taq_down_qfq" decimal(38,8),
    "taq_mid_bfq" decimal(38,8),
    "taq_mid_hfq" decimal(38,8),
    "taq_mid_qfq" decimal(38,8),
    "taq_up_bfq" decimal(38,8),
    "taq_up_hfq" decimal(38,8),
    "taq_up_qfq" decimal(38,8),
    "trix_bfq" decimal(38,8),
    "trix_hfq" decimal(38,8),
    "trix_qfq" decimal(38,8),
    "trma_bfq" decimal(38,8),
    "trma_hfq" decimal(38,8),
    "trma_qfq" decimal(38,8),
    "vr_bfq" decimal(38,8),
    "vr_hfq" decimal(38,8),
    "vr_qfq" decimal(38,8),
    "wr_bfq" decimal(38,8),
    "wr_hfq" decimal(38,8),
    "wr_qfq" decimal(38,8),
    "wr1_bfq" decimal(38,8),
    "wr1_hfq" decimal(38,8),
    "wr1_qfq" decimal(38,8),
    "xsii_td1_bfq" decimal(38,8),
    "xsii_td1_hfq" decimal(38,8),
    "xsii_td1_qfq" decimal(38,8),
    "xsii_td2_bfq" decimal(38,8),
    "xsii_td2_hfq" decimal(38,8),
    "xsii_td2_qfq" decimal(38,8),
    "xsii_td3_bfq" decimal(38,8),
    "xsii_td3_hfq" decimal(38,8),
    "xsii_td3_qfq" decimal(38,8),
    "xsii_td4_bfq" decimal(38,8),
    "xsii_td4_hfq" decimal(38,8),
    "xsii_td4_qfq" decimal(38,8),
    unique("_natural_key_hash","_revision_no"),
    unique("_current_natural_key_hash"),
    check ("_revision_no" > 0),
    check ("_is_current" in (0,1)),
    check ("_valid_to" is null or "_valid_from" is null or "_valid_to" >= "_valid_from")
);

create table if not exists "src_tushare_stk_high_shock" (
    "_observation_id" varchar(64) primary key,
    "_batch_id" varchar(64) not null,
    "_natural_key_hash" varchar(64) not null,
    "_revision_no" integer not null,
    "_is_current" integer not null default 1,
    "_current_natural_key_hash" varchar(64) generated always as (case when "_is_current" = 1 then "_natural_key_hash" else null end) stored,
    "_published_at" text,
    "_source_updated_at" text,
    "_observed_at" text not null,
    "_valid_from" text,
    "_valid_to" text,
    "_payload_hash" varchar(64) not null,
    "ts_code" text,
    "trade_date" date,
    "name" text,
    "trade_market" text,
    "reason" text,
    "period" text,
    unique("_natural_key_hash","_revision_no"),
    unique("_current_natural_key_hash"),
    check ("_revision_no" > 0),
    check ("_is_current" in (0,1)),
    check ("_valid_to" is null or "_valid_from" is null or "_valid_to" >= "_valid_from")
);

create table if not exists "src_tushare_stk_holdernumber" (
    "_observation_id" varchar(64) primary key,
    "_batch_id" varchar(64) not null,
    "_natural_key_hash" varchar(64) not null,
    "_revision_no" integer not null,
    "_is_current" integer not null default 1,
    "_current_natural_key_hash" varchar(64) generated always as (case when "_is_current" = 1 then "_natural_key_hash" else null end) stored,
    "_published_at" text,
    "_source_updated_at" text,
    "_observed_at" text not null,
    "_valid_from" text,
    "_valid_to" text,
    "_payload_hash" varchar(64) not null,
    "ts_code" text,
    "ann_date" date,
    "end_date" date,
    "holder_num" bigint,
    unique("_natural_key_hash","_revision_no"),
    unique("_current_natural_key_hash"),
    check ("_revision_no" > 0),
    check ("_is_current" in (0,1)),
    check ("_valid_to" is null or "_valid_from" is null or "_valid_to" >= "_valid_from")
);

create table if not exists "src_tushare_stk_holdertrade" (
    "_observation_id" varchar(64) primary key,
    "_batch_id" varchar(64) not null,
    "_natural_key_hash" varchar(64) not null,
    "_revision_no" integer not null,
    "_is_current" integer not null default 1,
    "_current_natural_key_hash" varchar(64) generated always as (case when "_is_current" = 1 then "_natural_key_hash" else null end) stored,
    "_published_at" text,
    "_source_updated_at" text,
    "_observed_at" text not null,
    "_valid_from" text,
    "_valid_to" text,
    "_payload_hash" varchar(64) not null,
    "ts_code" text,
    "ann_date" date,
    "holder_name" text,
    "holder_type" text,
    "in_de" text,
    "change_vol" decimal(38,8),
    "change_ratio" decimal(38,8),
    "after_share" decimal(38,8),
    "after_ratio" decimal(38,8),
    "avg_price" decimal(38,8),
    "total_share" decimal(38,8),
    "begin_date" date,
    "close_date" date,
    unique("_natural_key_hash","_revision_no"),
    unique("_current_natural_key_hash"),
    check ("_revision_no" > 0),
    check ("_is_current" in (0,1)),
    check ("_valid_to" is null or "_valid_from" is null or "_valid_to" >= "_valid_from")
);

create table if not exists "src_tushare_stk_limit" (
    "_observation_id" varchar(64) primary key,
    "_batch_id" varchar(64) not null,
    "_natural_key_hash" varchar(64) not null,
    "_revision_no" integer not null,
    "_is_current" integer not null default 1,
    "_current_natural_key_hash" varchar(64) generated always as (case when "_is_current" = 1 then "_natural_key_hash" else null end) stored,
    "_published_at" text,
    "_source_updated_at" text,
    "_observed_at" text not null,
    "_valid_from" text,
    "_valid_to" text,
    "_payload_hash" varchar(64) not null,
    "trade_date" date,
    "ts_code" text,
    "pre_close" decimal(38,8),
    "up_limit" decimal(38,8),
    "down_limit" decimal(38,8),
    unique("_natural_key_hash","_revision_no"),
    unique("_current_natural_key_hash"),
    check ("_revision_no" > 0),
    check ("_is_current" in (0,1)),
    check ("_valid_to" is null or "_valid_from" is null or "_valid_to" >= "_valid_from")
);

create table if not exists "src_tushare_stk_managers" (
    "_observation_id" varchar(64) primary key,
    "_batch_id" varchar(64) not null,
    "_natural_key_hash" varchar(64) not null,
    "_revision_no" integer not null,
    "_is_current" integer not null default 1,
    "_current_natural_key_hash" varchar(64) generated always as (case when "_is_current" = 1 then "_natural_key_hash" else null end) stored,
    "_published_at" text,
    "_source_updated_at" text,
    "_observed_at" text not null,
    "_valid_from" text,
    "_valid_to" text,
    "_payload_hash" varchar(64) not null,
    "ts_code" text,
    "ann_date" date,
    "name" text,
    "gender" text,
    "lev" text,
    "title" text,
    "edu" text,
    "national" text,
    "birthday" text,
    "begin_date" date,
    "end_date" date,
    "resume" text,
    unique("_natural_key_hash","_revision_no"),
    unique("_current_natural_key_hash"),
    check ("_revision_no" > 0),
    check ("_is_current" in (0,1)),
    check ("_valid_to" is null or "_valid_from" is null or "_valid_to" >= "_valid_from")
);

create table if not exists "src_tushare_stk_nineturn" (
    "_observation_id" varchar(64) primary key,
    "_batch_id" varchar(64) not null,
    "_natural_key_hash" varchar(64) not null,
    "_revision_no" integer not null,
    "_is_current" integer not null default 1,
    "_current_natural_key_hash" varchar(64) generated always as (case when "_is_current" = 1 then "_natural_key_hash" else null end) stored,
    "_published_at" text,
    "_source_updated_at" text,
    "_observed_at" text not null,
    "_valid_from" text,
    "_valid_to" text,
    "_payload_hash" varchar(64) not null,
    "ts_code" text,
    "trade_date" date,
    "freq" text,
    "open" decimal(38,8),
    "high" decimal(38,8),
    "low" decimal(38,8),
    "close" decimal(38,8),
    "vol" decimal(38,8),
    "amount" decimal(38,8),
    "up_count" decimal(38,8),
    "down_count" decimal(38,8),
    "nine_up_turn" text,
    "nine_down_turn" text,
    unique("_natural_key_hash","_revision_no"),
    unique("_current_natural_key_hash"),
    check ("_revision_no" > 0),
    check ("_is_current" in (0,1)),
    check ("_valid_to" is null or "_valid_from" is null or "_valid_to" >= "_valid_from")
);

create table if not exists "src_tushare_stk_premarket" (
    "_observation_id" varchar(64) primary key,
    "_batch_id" varchar(64) not null,
    "_natural_key_hash" varchar(64) not null,
    "_revision_no" integer not null,
    "_is_current" integer not null default 1,
    "_current_natural_key_hash" varchar(64) generated always as (case when "_is_current" = 1 then "_natural_key_hash" else null end) stored,
    "_published_at" text,
    "_source_updated_at" text,
    "_observed_at" text not null,
    "_valid_from" text,
    "_valid_to" text,
    "_payload_hash" varchar(64) not null,
    "trade_date" date,
    "ts_code" text,
    "total_share" decimal(38,8),
    "float_share" decimal(38,8),
    "pre_close" decimal(38,8),
    "up_limit" decimal(38,8),
    "down_limit" decimal(38,8),
    unique("_natural_key_hash","_revision_no"),
    unique("_current_natural_key_hash"),
    check ("_revision_no" > 0),
    check ("_is_current" in (0,1)),
    check ("_valid_to" is null or "_valid_from" is null or "_valid_to" >= "_valid_from")
);

create table if not exists "src_tushare_stk_rewards" (
    "_observation_id" varchar(64) primary key,
    "_batch_id" varchar(64) not null,
    "_natural_key_hash" varchar(64) not null,
    "_revision_no" integer not null,
    "_is_current" integer not null default 1,
    "_current_natural_key_hash" varchar(64) generated always as (case when "_is_current" = 1 then "_natural_key_hash" else null end) stored,
    "_published_at" text,
    "_source_updated_at" text,
    "_observed_at" text not null,
    "_valid_from" text,
    "_valid_to" text,
    "_payload_hash" varchar(64) not null,
    "ts_code" text,
    "ann_date" date,
    "end_date" date,
    "name" text,
    "title" text,
    "reward" decimal(38,8),
    "hold_vol" decimal(38,8),
    unique("_natural_key_hash","_revision_no"),
    unique("_current_natural_key_hash"),
    check ("_revision_no" > 0),
    check ("_is_current" in (0,1)),
    check ("_valid_to" is null or "_valid_from" is null or "_valid_to" >= "_valid_from")
);

create table if not exists "src_tushare_stk_shock" (
    "_observation_id" varchar(64) primary key,
    "_batch_id" varchar(64) not null,
    "_natural_key_hash" varchar(64) not null,
    "_revision_no" integer not null,
    "_is_current" integer not null default 1,
    "_current_natural_key_hash" varchar(64) generated always as (case when "_is_current" = 1 then "_natural_key_hash" else null end) stored,
    "_published_at" text,
    "_source_updated_at" text,
    "_observed_at" text not null,
    "_valid_from" text,
    "_valid_to" text,
    "_payload_hash" varchar(64) not null,
    "ts_code" text,
    "trade_date" date,
    "name" text,
    "trade_market" text,
    "reason" text,
    "period" text,
    unique("_natural_key_hash","_revision_no"),
    unique("_current_natural_key_hash"),
    check ("_revision_no" > 0),
    check ("_is_current" in (0,1)),
    check ("_valid_to" is null or "_valid_from" is null or "_valid_to" >= "_valid_from")
);

create table if not exists "src_tushare_stk_surv" (
    "_observation_id" varchar(64) primary key,
    "_batch_id" varchar(64) not null,
    "_natural_key_hash" varchar(64) not null,
    "_revision_no" integer not null,
    "_is_current" integer not null default 1,
    "_current_natural_key_hash" varchar(64) generated always as (case when "_is_current" = 1 then "_natural_key_hash" else null end) stored,
    "_published_at" text,
    "_source_updated_at" text,
    "_observed_at" text not null,
    "_valid_from" text,
    "_valid_to" text,
    "_payload_hash" varchar(64) not null,
    "ts_code" text,
    "name" text,
    "surv_date" date,
    "fund_visitors" text,
    "rece_place" text,
    "rece_mode" text,
    "rece_org" text,
    "org_type" text,
    "comp_rece" text,
    "content" text,
    unique("_natural_key_hash","_revision_no"),
    unique("_current_natural_key_hash"),
    check ("_revision_no" > 0),
    check ("_is_current" in (0,1)),
    check ("_valid_to" is null or "_valid_from" is null or "_valid_to" >= "_valid_from")
);

create table if not exists "src_tushare_stk_week_month_adj" (
    "_observation_id" varchar(64) primary key,
    "_batch_id" varchar(64) not null,
    "_natural_key_hash" varchar(64) not null,
    "_revision_no" integer not null,
    "_is_current" integer not null default 1,
    "_current_natural_key_hash" varchar(64) generated always as (case when "_is_current" = 1 then "_natural_key_hash" else null end) stored,
    "_published_at" text,
    "_source_updated_at" text,
    "_observed_at" text not null,
    "_valid_from" text,
    "_valid_to" text,
    "_payload_hash" varchar(64) not null,
    "ts_code" text,
    "trade_date" date,
    "end_date" date,
    "freq" text,
    "open" decimal(38,8),
    "high" decimal(38,8),
    "low" decimal(38,8),
    "close" decimal(38,8),
    "pre_close" decimal(38,8),
    "open_qfq" decimal(38,8),
    "high_qfq" decimal(38,8),
    "low_qfq" decimal(38,8),
    "close_qfq" decimal(38,8),
    "open_hfq" decimal(38,8),
    "high_hfq" decimal(38,8),
    "low_hfq" decimal(38,8),
    "close_hfq" decimal(38,8),
    "vol" decimal(38,8),
    "amount" decimal(38,8),
    "change" decimal(38,8),
    "pct_chg" decimal(38,8),
    unique("_natural_key_hash","_revision_no"),
    unique("_current_natural_key_hash"),
    check ("_revision_no" > 0),
    check ("_is_current" in (0,1)),
    check ("_valid_to" is null or "_valid_from" is null or "_valid_to" >= "_valid_from")
);

create table if not exists "src_tushare_stock_basic" (
    "_observation_id" varchar(64) primary key,
    "_batch_id" varchar(64) not null,
    "_natural_key_hash" varchar(64) not null,
    "_revision_no" integer not null,
    "_is_current" integer not null default 1,
    "_current_natural_key_hash" varchar(64) generated always as (case when "_is_current" = 1 then "_natural_key_hash" else null end) stored,
    "_published_at" text,
    "_source_updated_at" text,
    "_observed_at" text not null,
    "_valid_from" text,
    "_valid_to" text,
    "_payload_hash" varchar(64) not null,
    "ts_code" text,
    "symbol" text,
    "name" text,
    "area" text,
    "industry" text,
    "fullname" text,
    "enname" text,
    "cnspell" text,
    "market" text,
    "exchange" text,
    "curr_type" text,
    "list_status" text,
    "list_date" date,
    "delist_date" date,
    "is_hs" text,
    "act_name" text,
    "act_ent_type" text,
    unique("_natural_key_hash","_revision_no"),
    unique("_current_natural_key_hash"),
    check ("_revision_no" > 0),
    check ("_is_current" in (0,1)),
    check ("_valid_to" is null or "_valid_from" is null or "_valid_to" >= "_valid_from")
);

create table if not exists "src_tushare_stock_company" (
    "_observation_id" varchar(64) primary key,
    "_batch_id" varchar(64) not null,
    "_natural_key_hash" varchar(64) not null,
    "_revision_no" integer not null,
    "_is_current" integer not null default 1,
    "_current_natural_key_hash" varchar(64) generated always as (case when "_is_current" = 1 then "_natural_key_hash" else null end) stored,
    "_published_at" text,
    "_source_updated_at" text,
    "_observed_at" text not null,
    "_valid_from" text,
    "_valid_to" text,
    "_payload_hash" varchar(64) not null,
    "ts_code" text,
    "com_name" text,
    "com_id" text,
    "exchange" text,
    "chairman" text,
    "manager" text,
    "secretary" text,
    "reg_capital" decimal(38,8),
    "setup_date" date,
    "province" text,
    "city" text,
    "introduction" text,
    "website" text,
    "email" text,
    "office" text,
    "employees" bigint,
    "main_business" text,
    "business_scope" text,
    unique("_natural_key_hash","_revision_no"),
    unique("_current_natural_key_hash"),
    check ("_revision_no" > 0),
    check ("_is_current" in (0,1)),
    check ("_valid_to" is null or "_valid_from" is null or "_valid_to" >= "_valid_from")
);

create table if not exists "src_tushare_stock_hsgt" (
    "_observation_id" varchar(64) primary key,
    "_batch_id" varchar(64) not null,
    "_natural_key_hash" varchar(64) not null,
    "_revision_no" integer not null,
    "_is_current" integer not null default 1,
    "_current_natural_key_hash" varchar(64) generated always as (case when "_is_current" = 1 then "_natural_key_hash" else null end) stored,
    "_published_at" text,
    "_source_updated_at" text,
    "_observed_at" text not null,
    "_valid_from" text,
    "_valid_to" text,
    "_payload_hash" varchar(64) not null,
    "ts_code" text,
    "trade_date" date,
    "type" text,
    "name" text,
    "type_name" text,
    unique("_natural_key_hash","_revision_no"),
    unique("_current_natural_key_hash"),
    check ("_revision_no" > 0),
    check ("_is_current" in (0,1)),
    check ("_valid_to" is null or "_valid_from" is null or "_valid_to" >= "_valid_from")
);

create table if not exists "src_tushare_stock_st" (
    "_observation_id" varchar(64) primary key,
    "_batch_id" varchar(64) not null,
    "_natural_key_hash" varchar(64) not null,
    "_revision_no" integer not null,
    "_is_current" integer not null default 1,
    "_current_natural_key_hash" varchar(64) generated always as (case when "_is_current" = 1 then "_natural_key_hash" else null end) stored,
    "_published_at" text,
    "_source_updated_at" text,
    "_observed_at" text not null,
    "_valid_from" text,
    "_valid_to" text,
    "_payload_hash" varchar(64) not null,
    "ts_code" text,
    "name" text,
    "trade_date" date,
    "type" text,
    "type_name" text,
    unique("_natural_key_hash","_revision_no"),
    unique("_current_natural_key_hash"),
    check ("_revision_no" > 0),
    check ("_is_current" in (0,1)),
    check ("_valid_to" is null or "_valid_from" is null or "_valid_to" >= "_valid_from")
);

create table if not exists "src_tushare_tdx_index" (
    "_observation_id" varchar(64) primary key,
    "_batch_id" varchar(64) not null,
    "_natural_key_hash" varchar(64) not null,
    "_revision_no" integer not null,
    "_is_current" integer not null default 1,
    "_current_natural_key_hash" varchar(64) generated always as (case when "_is_current" = 1 then "_natural_key_hash" else null end) stored,
    "_published_at" text,
    "_source_updated_at" text,
    "_observed_at" text not null,
    "_valid_from" text,
    "_valid_to" text,
    "_payload_hash" varchar(64) not null,
    "ts_code" text,
    "trade_date" date,
    "name" text,
    "idx_type" text,
    "idx_count" bigint,
    "total_share" decimal(38,8),
    "float_share" decimal(38,8),
    "total_mv" decimal(38,8),
    "float_mv" decimal(38,8),
    unique("_natural_key_hash","_revision_no"),
    unique("_current_natural_key_hash"),
    check ("_revision_no" > 0),
    check ("_is_current" in (0,1)),
    check ("_valid_to" is null or "_valid_from" is null or "_valid_to" >= "_valid_from")
);

create table if not exists "src_tushare_tdx_member" (
    "_observation_id" varchar(64) primary key,
    "_batch_id" varchar(64) not null,
    "_natural_key_hash" varchar(64) not null,
    "_revision_no" integer not null,
    "_is_current" integer not null default 1,
    "_current_natural_key_hash" varchar(64) generated always as (case when "_is_current" = 1 then "_natural_key_hash" else null end) stored,
    "_published_at" text,
    "_source_updated_at" text,
    "_observed_at" text not null,
    "_valid_from" text,
    "_valid_to" text,
    "_payload_hash" varchar(64) not null,
    "ts_code" text,
    "trade_date" date,
    "con_code" text,
    "con_name" text,
    unique("_natural_key_hash","_revision_no"),
    unique("_current_natural_key_hash"),
    check ("_revision_no" > 0),
    check ("_is_current" in (0,1)),
    check ("_valid_to" is null or "_valid_from" is null or "_valid_to" >= "_valid_from")
);

create table if not exists "src_tushare_ths_hot" (
    "_observation_id" varchar(64) primary key,
    "_batch_id" varchar(64) not null,
    "_natural_key_hash" varchar(64) not null,
    "_revision_no" integer not null,
    "_is_current" integer not null default 1,
    "_current_natural_key_hash" varchar(64) generated always as (case when "_is_current" = 1 then "_natural_key_hash" else null end) stored,
    "_published_at" text,
    "_source_updated_at" text,
    "_observed_at" text not null,
    "_valid_from" text,
    "_valid_to" text,
    "_payload_hash" varchar(64) not null,
    "trade_date" date,
    "data_type" text,
    "ts_code" text,
    "ts_name" text,
    "rank" bigint,
    "pct_change" decimal(38,8),
    "current_price" decimal(38,8),
    "concept" text,
    "rank_reason" text,
    "hot" decimal(38,8),
    "rank_time" text,
    unique("_natural_key_hash","_revision_no"),
    unique("_current_natural_key_hash"),
    check ("_revision_no" > 0),
    check ("_is_current" in (0,1)),
    check ("_valid_to" is null or "_valid_from" is null or "_valid_to" >= "_valid_from")
);

create table if not exists "src_tushare_ths_index" (
    "_observation_id" varchar(64) primary key,
    "_batch_id" varchar(64) not null,
    "_natural_key_hash" varchar(64) not null,
    "_revision_no" integer not null,
    "_is_current" integer not null default 1,
    "_current_natural_key_hash" varchar(64) generated always as (case when "_is_current" = 1 then "_natural_key_hash" else null end) stored,
    "_published_at" text,
    "_source_updated_at" text,
    "_observed_at" text not null,
    "_valid_from" text,
    "_valid_to" text,
    "_payload_hash" varchar(64) not null,
    "ts_code" text,
    "name" text,
    "count" bigint,
    "exchange" text,
    "list_date" date,
    "type" text,
    unique("_natural_key_hash","_revision_no"),
    unique("_current_natural_key_hash"),
    check ("_revision_no" > 0),
    check ("_is_current" in (0,1)),
    check ("_valid_to" is null or "_valid_from" is null or "_valid_to" >= "_valid_from")
);

create table if not exists "src_tushare_ths_member" (
    "_observation_id" varchar(64) primary key,
    "_batch_id" varchar(64) not null,
    "_natural_key_hash" varchar(64) not null,
    "_revision_no" integer not null,
    "_is_current" integer not null default 1,
    "_current_natural_key_hash" varchar(64) generated always as (case when "_is_current" = 1 then "_natural_key_hash" else null end) stored,
    "_published_at" text,
    "_source_updated_at" text,
    "_observed_at" text not null,
    "_valid_from" text,
    "_valid_to" text,
    "_payload_hash" varchar(64) not null,
    "ts_code" text,
    "con_code" text,
    "con_name" text,
    "weight" decimal(38,8),
    "in_date" date,
    "out_date" date,
    "is_new" text,
    unique("_natural_key_hash","_revision_no"),
    unique("_current_natural_key_hash"),
    check ("_revision_no" > 0),
    check ("_is_current" in (0,1)),
    check ("_valid_to" is null or "_valid_from" is null or "_valid_to" >= "_valid_from")
);

create table if not exists "src_tushare_top10_floatholders" (
    "_observation_id" varchar(64) primary key,
    "_batch_id" varchar(64) not null,
    "_natural_key_hash" varchar(64) not null,
    "_revision_no" integer not null,
    "_is_current" integer not null default 1,
    "_current_natural_key_hash" varchar(64) generated always as (case when "_is_current" = 1 then "_natural_key_hash" else null end) stored,
    "_published_at" text,
    "_source_updated_at" text,
    "_observed_at" text not null,
    "_valid_from" text,
    "_valid_to" text,
    "_payload_hash" varchar(64) not null,
    "ts_code" text,
    "ann_date" date,
    "end_date" date,
    "holder_name" text,
    "hold_amount" decimal(38,8),
    "hold_ratio" decimal(38,8),
    "hold_float_ratio" decimal(38,8),
    "hold_change" decimal(38,8),
    "holder_type" text,
    unique("_natural_key_hash","_revision_no"),
    unique("_current_natural_key_hash"),
    check ("_revision_no" > 0),
    check ("_is_current" in (0,1)),
    check ("_valid_to" is null or "_valid_from" is null or "_valid_to" >= "_valid_from")
);

create table if not exists "src_tushare_top10_holders" (
    "_observation_id" varchar(64) primary key,
    "_batch_id" varchar(64) not null,
    "_natural_key_hash" varchar(64) not null,
    "_revision_no" integer not null,
    "_is_current" integer not null default 1,
    "_current_natural_key_hash" varchar(64) generated always as (case when "_is_current" = 1 then "_natural_key_hash" else null end) stored,
    "_published_at" text,
    "_source_updated_at" text,
    "_observed_at" text not null,
    "_valid_from" text,
    "_valid_to" text,
    "_payload_hash" varchar(64) not null,
    "ts_code" text,
    "ann_date" date,
    "end_date" date,
    "holder_name" text,
    "hold_amount" decimal(38,8),
    "hold_ratio" decimal(38,8),
    "hold_float_ratio" decimal(38,8),
    "hold_change" decimal(38,8),
    "holder_type" text,
    unique("_natural_key_hash","_revision_no"),
    unique("_current_natural_key_hash"),
    check ("_revision_no" > 0),
    check ("_is_current" in (0,1)),
    check ("_valid_to" is null or "_valid_from" is null or "_valid_to" >= "_valid_from")
);

create table if not exists "src_tushare_top_inst" (
    "_observation_id" varchar(64) primary key,
    "_batch_id" varchar(64) not null,
    "_natural_key_hash" varchar(64) not null,
    "_revision_no" integer not null,
    "_is_current" integer not null default 1,
    "_current_natural_key_hash" varchar(64) generated always as (case when "_is_current" = 1 then "_natural_key_hash" else null end) stored,
    "_published_at" text,
    "_source_updated_at" text,
    "_observed_at" text not null,
    "_valid_from" text,
    "_valid_to" text,
    "_payload_hash" varchar(64) not null,
    "trade_date" date,
    "ts_code" text,
    "exalter" text,
    "side" text,
    "buy" decimal(38,8),
    "buy_rate" decimal(38,8),
    "sell" decimal(38,8),
    "sell_rate" decimal(38,8),
    "net_buy" decimal(38,8),
    "reason" text,
    unique("_natural_key_hash","_revision_no"),
    unique("_current_natural_key_hash"),
    check ("_revision_no" > 0),
    check ("_is_current" in (0,1)),
    check ("_valid_to" is null or "_valid_from" is null or "_valid_to" >= "_valid_from")
);

create table if not exists "src_tushare_top_list" (
    "_observation_id" varchar(64) primary key,
    "_batch_id" varchar(64) not null,
    "_natural_key_hash" varchar(64) not null,
    "_revision_no" integer not null,
    "_is_current" integer not null default 1,
    "_current_natural_key_hash" varchar(64) generated always as (case when "_is_current" = 1 then "_natural_key_hash" else null end) stored,
    "_published_at" text,
    "_source_updated_at" text,
    "_observed_at" text not null,
    "_valid_from" text,
    "_valid_to" text,
    "_payload_hash" varchar(64) not null,
    "trade_date" date,
    "ts_code" text,
    "name" text,
    "close" decimal(38,8),
    "pct_change" decimal(38,8),
    "turnover_rate" decimal(38,8),
    "amount" decimal(38,8),
    "l_sell" decimal(38,8),
    "l_buy" decimal(38,8),
    "l_amount" decimal(38,8),
    "net_amount" decimal(38,8),
    "net_rate" decimal(38,8),
    "amount_rate" decimal(38,8),
    "float_values" decimal(38,8),
    "reason" text,
    unique("_natural_key_hash","_revision_no"),
    unique("_current_natural_key_hash"),
    check ("_revision_no" > 0),
    check ("_is_current" in (0,1)),
    check ("_valid_to" is null or "_valid_from" is null or "_valid_to" >= "_valid_from")
);

create table if not exists "src_tushare_trade_cal" (
    "_observation_id" varchar(64) primary key,
    "_batch_id" varchar(64) not null,
    "_natural_key_hash" varchar(64) not null,
    "_revision_no" integer not null,
    "_is_current" integer not null default 1,
    "_current_natural_key_hash" varchar(64) generated always as (case when "_is_current" = 1 then "_natural_key_hash" else null end) stored,
    "_published_at" text,
    "_source_updated_at" text,
    "_observed_at" text not null,
    "_valid_from" text,
    "_valid_to" text,
    "_payload_hash" varchar(64) not null,
    "exchange" text,
    "cal_date" date,
    "is_open" text,
    "pretrade_date" date,
    unique("_natural_key_hash","_revision_no"),
    unique("_current_natural_key_hash"),
    check ("_revision_no" > 0),
    check ("_is_current" in (0,1)),
    check ("_valid_to" is null or "_valid_from" is null or "_valid_to" >= "_valid_from")
);

create table if not exists stored_object_chunks (
                object_id text not null,
                chunk_index integer not null,
                data bytea not null,
                size integer not null,
                sha256 text not null,
                primary key (object_id, chunk_index)
            );

create table if not exists stored_objects (
                id text primary key,
                namespace text not null,
                object_key text not null,
                content_type text,
                encoding text not null default 'binary',
                size integer not null,
                sha256 text not null,
                storage_mode text not null default 'database',
                source_path text,
                metadata_json text not null,
                created_at text not null,
                updated_at text not null,
                unique(namespace, object_key, sha256)
            );

create table if not exists strategy_admission_events (
                id text primary key,
                admission_id text not null,
                stage text not null,
                source_id text,
                payload_json text not null,
                created_at text not null
            );

create table if not exists strategy_admissions (
                id text primary key,
                strategy_id text not null,
                strategy_version_id text,
                parameters_sha256 text not null,
                profile_name text not null,
                profile_version text not null,
                sample_set text not null,
                current_stage text not null,
                baseline_snapshot_json text not null,
                evaluation_json text not null,
                created_at text not null,
                updated_at text not null,
                unique(strategy_id, parameters_sha256, profile_name, profile_version)
            );

create table if not exists strategy_versions (
                id text primary key,
                project_id text,
                strategy_path text,
                source_sha256 text,
                git_commit text,
                git_branch text,
                git_dirty integer not null default 0,
                git_status_hash text,
                metadata_json text not null,
                created_at text not null
            );

create table if not exists tasks (
                id text primary key,
                celery_task_id text,
                kind text not null,
                status text not null,
                title text not null,
                project_id text,
                related_id text,
                parameters_json text not null,
                log_path text not null,
                artifacts_json text,
                error text,
                created_at text not null,
                started_at text,
                finished_at text
            );

create table if not exists trade_calendar (
                market text not null,
                trade_date text not null,
                is_open integer not null,
                prev_trade_date text,
                next_trade_date text,
                source text,
                batch_id text,
                primary key (market, trade_date)
            );

create table if not exists universe_coverage_watermarks (
    universe_code text primary key,
    launch_date text not null,
    coverage_start text,
    coverage_end text,
    coverage_status text not null default 'missing',
    source text,
    expected_members integer,
    observed_snapshots integer not null default 0,
    membership_rows integer not null default 0,
    bundle_sha256 text,
    last_batch_id text,
    validation_json text not null,
    validated_at text not null,
    updated_at text not null
);

create table if not exists universe_membership (
                universe_code text not null,
                symbol text not null,
                start_date text not null,
                end_date text,
                announce_date text,
                effective_date text,
                weight double precision,
                source text not null,
                batch_id text,
                primary key (universe_code, symbol, start_date)
            );

create table if not exists verification_cases (
    id text primary key,
    verification_run_id text not null,
    case_key text not null,
    market text,
    symbol text,
    stage text not null,
    status text not null,
    trace_id text,
    resource_type text,
    resource_id text,
    error_code text,
    details_json text,
    artifact_path text,
    started_at text,
    finished_at text,
    unique(verification_run_id, case_key)
);

create table if not exists verification_runs (
    id text primary key,
    name text not null,
    status text not null,
    git_commit text,
    environment_json text,
    manifest_json text,
    summary_json text,
    artifact_path text,
    created_at text not null,
    started_at text,
    finished_at text
);

create table if not exists walk_forward_runs (
    id varchar(64) primary key,
    batch_id varchar(64) not null,
    status varchar(32) not null,
    dataset_version varchar(255) not null,
    universe_version varchar(255) not null,
    adjustment_contract varchar(255) not null,
    feature_pipeline_version varchar(255) not null,
    selection_metric varchar(64) not null,
    selection_rule varchar(255) not null,
    created_at varchar(64) not null,
    completed_at varchar(64), lineage_status varchar(32) not null default 'complete', lineage_reason varchar(255), batch_snapshot_json text, certificate_json text, certificate_digest varchar(64), certified_at varchar(64),
    unique(batch_id)
);

create table if not exists walk_forward_windows (
    id varchar(64) primary key,
    walk_forward_run_id varchar(64) not null,
    batch_id varchar(64) not null,
    project_id varchar(255) not null,
    symbol varchar(64) not null,
    fold integer not null,
    train_start varchar(10) not null,
    train_end varchar(10) not null,
    validation_start varchar(10) not null,
    validation_end varchar(10) not null,
    oos_start varchar(10) not null,
    oos_end varchar(10) not null,
    universe_version varchar(255) not null,
    dataset_version varchar(255) not null,
    adjustment_contract varchar(255) not null,
    feature_pipeline_version varchar(255) not null,
    fold_fingerprint varchar(64) not null,
    oos_input_fingerprint varchar(64) not null,
    status varchar(32) not null,
    created_at varchar(64) not null,
    completed_at varchar(64), project_snapshot_json text, selection_inputs_json text, selection_outputs_json text,
    unique(batch_id, project_id, symbol, fold)
);

create table if not exists workflow_events (
    id text primary key,
    workflow_id text not null,
    trace_id text not null,
    stage text not null,
    action text not null,
    resource_type text,
    resource_id text,
    status text not null,
    error_code text,
    message text,
    details_json text,
    created_at text not null
);

create table if not exists workflow_lineage_edges (
    id varchar(191) primary key,
    parent_type varchar(64) not null,
    parent_id varchar(191) not null,
    child_type varchar(64) not null,
    child_id varchar(191) not null,
    relation varchar(64) not null,
    contract_digest varchar(128),
    details_json text,
    created_at varchar(64) not null,
    unique(parent_type, parent_id, child_type, child_id, relation)
);

create table if not exists artifact_lineage_edges (
    parent_artifact_id varchar(128) not null,
    child_artifact_id varchar(128) not null,
    created_at varchar(64) not null,
    primary key (parent_artifact_id, child_artifact_id),
    foreign key (parent_artifact_id) references artifact_registry(artifact_id),
    foreign key (child_artifact_id) references artifact_registry(artifact_id)
);

create table if not exists artifact_promotion_events (
    id varchar(64) primary key,
    artifact_id varchar(128) not null,
    from_status varchar(32),
    to_status varchar(32) not null,
    owner varchar(32) not null,
    reason varchar(255),
    evidence_json text not null,
    created_at varchar(64) not null,
    foreign key (artifact_id) references artifact_registry(artifact_id)
);

create table if not exists data_release_components (
    data_release_id varchar(96) not null,
    role varchar(64) not null,
    component_release_id varchar(128) not null,
    dataset_key varchar(191) not null,
    schema_version varchar(32) not null,
    coverage_start varchar(32) not null,
    coverage_end varchar(32) not null,
    file_count integer not null,
    row_count bigint not null default 0,
    component_sha256 varchar(64) not null,
    component_json text not null,
    primary key (data_release_id, role),
    foreign key (data_release_id) references data_releases(id)
);

create table if not exists dataset_releases (
    id varchar(96) primary key,
    dataset_key varchar(191) not null,
    dataset_version varchar(191) not null,
    source varchar(64) not null,
    asset_class varchar(64) not null,
    market varchar(64) not null,
    venue varchar(64),
    resolution varchar(32) not null,
    data_type varchar(32) not null,
    adjust_mode varchar(32) not null,
    parquet_dataset_id varchar(64) not null,
    file_manifest_sha256 varchar(64) not null,
    qa_report_id varchar(64) not null,
    status varchar(32) not null,
    is_production integer not null default 1,
    is_certified integer not null default 1,
    coverage_start varchar(32),
    coverage_end varchar(32),
    row_count bigint not null default 0,
    file_count integer not null default 0,
    certified_by varchar(96) not null,
    certified_at varchar(64) not null,
    revoked_at varchar(64),
    revoke_reason varchar(255),
    metadata_json text not null,
    created_at varchar(64) not null,
    unique(dataset_key, dataset_version),
    unique(parquet_dataset_id, dataset_version),
    foreign key (parquet_dataset_id) references parquet_datasets(id)
);

create table if not exists market_instruments_v2 (
    id text primary key,
    asset_class text not null,
    instrument_type text not null,
    venue_id text,
    primary_symbol text not null,
    name text,
    currency text,
    issuer_id text,
    listed_date date,
    delisted_date date,
    expiry_date date,
    status text not null,
    lot_size decimal(28,8),
    tick_size decimal(20,8),
    contract_multiplier decimal(28,8),
    metadata_json json not null,
    created_at text not null,
    updated_at text not null,
    unique(asset_class,venue_id,primary_symbol),
    foreign key (venue_id) references market_venues_v2(id),
    check (asset_class in ('equity','index','future','option')),
    check (status in ('pending','active','suspended','expired','delisted','retired')),
    check (delisted_date is null or listed_date is null or delisted_date >= listed_date),
    check (lot_size is null or lot_size > 0),
    check (tick_size is null or tick_size > 0),
    check (contract_multiplier is null or contract_multiplier > 0)
);

create table if not exists paper_account_checkpoints (
    id varchar(64) primary key,
    paper_account_id varchar(64) not null,
    generation integer not null,
    cycle_id varchar(64),
    source_ledger_sequence integer not null,
    digest varchar(128) not null,
    checkpoint_json text not null,
    created_at varchar(64) not null,
    unique(paper_account_id, generation, source_ledger_sequence),
    unique(digest),
    foreign key (paper_account_id) references paper_accounts(id)
);

create table if not exists paper_account_daily_snapshots (
    id varchar(64) primary key,
    paper_account_id varchar(64) not null,
    generation integer not null,
    trading_date varchar(32) not null,
    projection_json text not null,
    benchmark_symbol varchar(64) not null,
    benchmark_return decimal(20,12) not null,
    source_ledger_sequence integer not null,
    source_checkpoint_digest varchar(128) not null,
    created_at varchar(64) not null,
    unique(paper_account_id, generation, trading_date),
    foreign key (paper_account_id) references paper_accounts(id)
);

create table if not exists paper_account_generations (
    id varchar(64) primary key,
    paper_account_id varchar(64) not null,
    generation integer not null,
    opening_cash decimal(28,8) not null,
    opening_ledger_entry_id varchar(64) not null,
    opening_checkpoint_digest varchar(128) not null,
    reason varchar(255) not null,
    created_at varchar(64) not null,
    unique(paper_account_id, generation),
    unique(opening_ledger_entry_id),
    foreign key (paper_account_id) references paper_accounts(id)
);

create table if not exists paper_account_position_projections (
    paper_account_id varchar(64) not null,
    generation integer not null,
    symbol varchar(64) not null,
    security_name varchar(191),
    market varchar(32) not null,
    quantity decimal(28,8) not null,
    sellable_quantity decimal(28,8) not null,
    frozen_quantity decimal(28,8) not null,
    average_cost decimal(28,8) not null,
    certified_price decimal(28,8),
    market_value decimal(28,8) not null,
    account_weight decimal(20,12) not null,
    daily_pnl decimal(28,8) not null,
    unrealized_pnl decimal(28,8) not null,
    realized_pnl decimal(28,8) not null,
    last_buy_date varchar(32),
    quote_data_timestamp varchar(64),
    data_status varchar(32) not null,
    updated_at varchar(64) not null,
    primary key (paper_account_id, generation, symbol),
    foreign key (paper_account_id) references paper_accounts(id)
);

create table if not exists paper_account_projections (
    paper_account_id varchar(64) primary key,
    generation integer not null,
    cash decimal(28,8) not null,
    available_cash decimal(28,8) not null,
    frozen_cash decimal(28,8) not null,
    market_value decimal(28,8) not null,
    total_equity decimal(28,8) not null,
    realized_pnl decimal(28,8) not null,
    unrealized_pnl decimal(28,8) not null,
    daily_pnl decimal(28,8) not null,
    cumulative_return decimal(20,12) not null,
    benchmark_return decimal(20,12) not null,
    excess_return decimal(20,12) not null,
    position_count integer not null,
    gross_exposure decimal(20,12) not null,
    net_exposure decimal(20,12) not null,
    turnover decimal(20,12) not null,
    last_valuation_at varchar(64),
    quote_data_timestamp varchar(64),
    source_ledger_sequence integer not null,
    source_checkpoint_digest varchar(128) not null,
    health_status varchar(32) not null,
    updated_at varchar(64) not null,
    foreign key (paper_account_id) references paper_accounts(id)
);

create table if not exists paper_notification_outbox (
    id varchar(64) primary key,
    paper_account_id varchar(64) not null,
    deployment_id varchar(64),
    cycle_id varchar(64),
    event_type varchar(64) not null,
    dedupe_key varchar(255) not null,
    payload_json text not null,
    status varchar(32) not null,
    attempt integer not null default 0,
    next_attempt_at varchar(64),
    delivered_at varchar(64),
    last_error text,
    created_at varchar(64) not null,
    updated_at varchar(64) not null, terminal_at varchar(64),
    unique(dedupe_key),
    foreign key (paper_account_id) references paper_accounts(id)
);

create table if not exists paper_risk_profiles (
    id varchar(64) primary key,
    paper_account_id varchar(64) not null,
    version integer not null,
    status varchar(32) not null,
    max_positions integer,
    max_position_weight decimal(20,12),
    cash_floor decimal(28,8),
    max_order_amount decimal(28,8),
    max_daily_turnover decimal(20,12),
    config_json text not null,
    config_fingerprint varchar(128) not null,
    created_at varchar(64) not null,
    superseded_at varchar(64),
    unique(paper_account_id, version),
    unique(config_fingerprint),
    foreign key (paper_account_id) references paper_accounts(id)
);

create table if not exists paper_strategy_deployments (
    id varchar(64) primary key,
    paper_account_id varchar(64) not null,
    generation integer not null,
    supersedes_deployment_id varchar(64),
    version integer not null,
    name varchar(191) not null,
    status varchar(32) not null,
    is_primary integer not null default 0,
    project_id varchar(64) not null,
    source_backtest_id varchar(64) not null,
    strategy_version_id varchar(128),
    project_snapshot_id varchar(128) not null,
    dataset_version_id varchar(255) not null,
    experiment_version_id varchar(128),
    schedule_type varchar(32) not null,
    schedule_expression varchar(128) not null,
    market_timezone varchar(64) not null,
    run_after_market_close integer not null default 1,
    execution_timing varchar(32) not null,
    signal_mode varchar(32) not null,
    parameters_json text not null,
    universe_config_json text not null,
    risk_config_version integer not null,
    strategy_fingerprint varchar(128) not null,
    dataset_fingerprint varchar(128) not null,
    deployment_fingerprint varchar(128) not null,
    last_successful_trading_date varchar(32),
    next_scheduled_at varchar(64),
    consecutive_failures integer not null default 0,
    created_at varchar(64) not null,
    updated_at varchar(64) not null,
    paused_at varchar(64),
    disabled_at varchar(64),
    unique(paper_account_id, version),
    unique(deployment_fingerprint),
    foreign key (paper_account_id) references paper_accounts(id)
);

create table if not exists provider_datasets_v2 (
    id text primary key,
    provider_id text not null,
    dataset_key text not null,
    api_name text not null,
    asset_class text not null,
    contract_version text not null,
    storage_tier text not null,
    status text not null,
    permission_status text not null default 'unknown',
    documentation_url text,
    created_at text not null,
    updated_at text not null,
    unique(provider_id,dataset_key,contract_version),
    foreign key (provider_id) references data_providers_v2(id),
    check (storage_tier in ('canonical','typed_source','columnar')),
    check (status in ('active','retired')),
    check (permission_status in ('unknown','available','empty','denied','retryable'))
);

create table if not exists qlib_lean_validations (
    id varchar(64) primary key,
    research_run_id varchar(64) not null,
    signal_snapshot_id varchar(64) not null,
    target_artifact_id varchar(128) not null,
    validation_artifact_id varchar(128) not null unique,
    data_release_id varchar(96) not null,
    model_release_id varchar(128) not null,
    lean_backtest_run_id varchar(64) not null,
    targets_sha256 varchar(64) not null,
    status varchar(32) not null,
    evidence_json text not null,
    created_at varchar(64) not null,
    unique(target_artifact_id, lean_backtest_run_id),
    foreign key (target_artifact_id) references artifact_registry(artifact_id),
    foreign key (validation_artifact_id) references artifact_registry(artifact_id)
);

create table if not exists source_priority_rules_v2 (
    id text primary key,
    fact_type text not null,
    asset_class text,
    market text,
    provider_id text not null,
    priority integer not null,
    valid_from text not null,
    valid_to text,
    reason text not null,
    created_at text not null,
    unique(fact_type,asset_class,market,provider_id,valid_from),
    foreign key (provider_id) references data_providers_v2(id),
    check (priority >= 0),
    check (valid_to is null or valid_to >= valid_from)
);

create table if not exists columnar_datasets_v2 (
    id text primary key,
    provider_dataset_id text not null,
    asset_class text not null,
    resolution text not null,
    storage_engine text not null,
    table_or_root text not null,
    schema_version text not null,
    status text not null,
    created_at text not null,
    updated_at text not null,
    unique(provider_dataset_id,resolution,storage_engine,schema_version),
    foreign key (provider_dataset_id) references provider_datasets_v2(id),
    check (storage_engine in ('clickhouse','parquet')),
    check (status in ('building','ready','failed','retired'))
);

create table if not exists dataset_contract_versions_v2 (
    id text primary key,
    provider_dataset_id text not null,
    contract_version text not null,
    effective_from date not null,
    effective_to date,
    natural_key_json json not null,
    fields_json json not null,
    contract_sha256 text not null,
    created_at text not null,
    unique(provider_dataset_id,contract_version),
    foreign key (provider_dataset_id) references provider_datasets_v2(id),
    check (effective_to is null or effective_to >= effective_from)
);

create table if not exists ingestion_runs_v2 (
    id text primary key,
    provider_dataset_id text not null,
    request_json json not null,
    status text not null,
    started_at text not null,
    finished_at text,
    observed_rows bigint not null default 0,
    accepted_rows bigint not null default 0,
    rejected_rows bigint not null default 0,
    raw_object_id text,
    payload_sha256 text,
    error text,
    foreign key (provider_dataset_id) references provider_datasets_v2(id),
    check (status in ('queued','running','success','partial','failed','cancelled')),
    check (observed_rows >= 0 and accepted_rows >= 0 and rejected_rows >= 0)
);

create table if not exists market_instrument_identifiers_v2 (
    id text primary key,
    instrument_id text not null,
    provider_id text,
    identifier_type text not null,
    identifier_value text not null,
    valid_from date not null,
    valid_to date,
    is_primary integer not null default 0,
    created_at text not null,
    unique(provider_id,identifier_type,identifier_value,valid_from),
    foreign key (instrument_id) references market_instruments_v2(id),
    foreign key (provider_id) references data_providers_v2(id),
    check (is_primary in (0,1)),
    check (valid_to is null or valid_to >= valid_from)
);

create table if not exists paper_account_trust_certifications (
    id varchar(96) primary key,
    paper_account_id varchar(64) not null,
    account_generation integer not null,
    dataset_release_id varchar(96) not null,
    status varchar(32) not null,
    checkpoint_count integer not null default 0,
    result_count integer not null default 0,
    evidence_json text not null,
    certified_at varchar(64) not null,
    expires_at varchar(64) not null,
    revoked_at varchar(64),
    revoke_reason varchar(255),
    unique(paper_account_id, account_generation, dataset_release_id),
    foreign key (paper_account_id) references paper_accounts(id),
    foreign key (dataset_release_id) references dataset_releases(id)
);

create table if not exists paper_execution_cycles (
    id varchar(64) primary key,
    paper_account_id varchar(64) not null,
    account_generation integer not null,
    deployment_id varchar(64) not null,
    trading_date varchar(32) not null,
    scheduled_at varchar(64) not null,
    started_at varchar(64),
    finished_at varchar(64),
    status varchar(48) not null,
    attempt integer not null default 0,
    idempotency_key varchar(255) not null,
    input_fingerprint varchar(128) not null,
    account_checkpoint_digest varchar(128) not null,
    strategy_fingerprint varchar(128) not null,
    dataset_fingerprint varchar(128) not null,
    result_digest varchar(128),
    signal_count integer not null default 0,
    intent_count integer not null default 0,
    order_count integer not null default 0,
    fill_count integer not null default 0,
    rejected_count integer not null default 0,
    skip_reason varchar(128),
    failure_code varchar(128),
    failure_detail text,
    lean_run_id varchar(128),
    paper_run_id varchar(64),
    daily_report_id varchar(64),
    lease_holder varchar(128),
    lease_expires_at varchar(64),
    version integer not null default 1,
    created_at varchar(64) not null,
    updated_at varchar(64) not null,
    unique(deployment_id, trading_date),
    unique(idempotency_key),
    foreign key (paper_account_id) references paper_accounts(id),
    foreign key (deployment_id) references paper_strategy_deployments(id)
);

create table if not exists reproducibility_certificates (
    id varchar(96) primary key,
    run_id varchar(191) not null,
    dataset_release_id varchar(96) not null,
    input_fingerprint varchar(64) not null,
    equivalence_digest varchar(64) not null,
    certificate_sha256 varchar(64) not null,
    canonical_result_sha256 varchar(64) not null,
    orders_sha256 varchar(64) not null,
    fills_sha256 varchar(64) not null,
    equity_sha256 varchar(64) not null,
    artifact_manifest_sha256 varchar(64) not null,
    stored_object_id varchar(64),
    status varchar(32) not null,
    certificate_json text not null,
    created_at varchar(64) not null, data_release_id varchar(96), logical_input_fingerprint varchar(64), execution_fingerprint varchar(64), runtime_identity_json text,
    unique(run_id),
    unique(certificate_sha256),
    foreign key (run_id) references backtest_runs(id),
    foreign key (dataset_release_id) references dataset_releases(id),
    foreign key (stored_object_id) references stored_objects(id)
);

create table if not exists columnar_partitions_v2 (
    id text primary key,
    dataset_id text not null,
    partition_key text not null,
    first_timestamp text,
    last_timestamp text,
    row_count bigint not null,
    byte_size bigint not null,
    content_sha256 text not null,
    storage_location text not null,
    status text not null,
    created_at text not null,
    unique(dataset_id,partition_key,content_sha256),
    foreign key (dataset_id) references columnar_datasets_v2(id),
    check (row_count >= 0 and byte_size >= 0),
    check (last_timestamp is null or first_timestamp is null or last_timestamp >= first_timestamp),
    check (status in ('pending','ready','quarantined','retired'))
);

create table if not exists paper_account_daily_reports (
    id varchar(64) primary key,
    paper_account_id varchar(64) not null,
    deployment_id varchar(64) not null,
    cycle_id varchar(64) not null,
    trading_date varchar(32) not null,
    report_json text not null,
    result_digest varchar(128) not null,
    created_at varchar(64) not null,
    unique(cycle_id),
    unique(result_digest),
    foreign key (paper_account_id) references paper_accounts(id),
    foreign key (deployment_id) references paper_strategy_deployments(id),
    foreign key (cycle_id) references paper_execution_cycles(id)
);

create table if not exists paper_execution_cycle_events (
    id varchar(64) primary key,
    cycle_id varchar(64) not null,
    sequence integer not null,
    from_status varchar(48),
    to_status varchar(48) not null,
    event_type varchar(64) not null,
    payload_json text not null,
    created_at varchar(64) not null,
    unique(cycle_id, sequence),
    foreign key (cycle_id) references paper_execution_cycles(id)
);

create table if not exists paper_strategy_signals (
    id varchar(64) primary key,
    paper_account_id varchar(64) not null,
    deployment_id varchar(64) not null,
    cycle_id varchar(64) not null,
    signal_key varchar(255) not null,
    signal_type varchar(32) not null,
    symbol varchar(64),
    signal_timestamp varchar(64) not null,
    intended_execution_date varchar(32),
    target_quantity decimal(28,8),
    target_weight decimal(20,12),
    previous_quantity decimal(28,8),
    previous_weight decimal(20,12),
    confidence decimal(20,12),
    evidence_json text not null,
    disposition varchar(64) not null,
    no_trade_reason varchar(128),
    intent_id varchar(64),
    constraint_decision_id varchar(64),
    lean_run_id varchar(128),
    data_timestamp varchar(64),
    created_at varchar(64) not null,
    unique(deployment_id, signal_key),
    foreign key (paper_account_id) references paper_accounts(id),
    foreign key (deployment_id) references paper_strategy_deployments(id),
    foreign key (cycle_id) references paper_execution_cycles(id)
);

create table if not exists source_observations_v2 (
    id text primary key,
    provider_dataset_id text not null,
    ingestion_run_id text not null,
    natural_key_hash text not null,
    revision_no integer not null,
    is_current integer not null default 1,
    current_natural_key_hash varchar(64) generated always as (case when is_current = 1 then natural_key_hash else null end) stored,
    published_at text,
    source_updated_at text,
    observed_at text not null,
    valid_from text,
    valid_to text,
    payload_hash text not null,
    source_table text not null,
    source_row_id text not null,
    unique(provider_dataset_id,natural_key_hash,revision_no),
    unique(provider_dataset_id,current_natural_key_hash),
    foreign key (provider_dataset_id) references provider_datasets_v2(id),
    foreign key (ingestion_run_id) references ingestion_runs_v2(id),
    check (revision_no > 0),
    check (is_current in (0,1)),
    check (valid_to is null or valid_from is null or valid_to >= valid_from)
);

create table if not exists equity_listings_v2 (
    instrument_id text primary key,
    issuer_id text not null,
    board text,
    list_status text not null,
    list_date date not null,
    delist_date date,
    issue_price decimal(20,8),
    source_observation_id text,
    foreign key (instrument_id) references market_instruments_v2(id),
    foreign key (issuer_id) references equity_issuers_v2(id),
    foreign key (source_observation_id) references source_observations_v2(id),
    check (delist_date is null or delist_date >= list_date)
);

create table if not exists equity_share_capital_v2 (
    id text primary key,
    instrument_id text not null,
    effective_date date not null,
    total_shares decimal(28,4),
    float_shares decimal(28,4),
    free_float_shares decimal(28,4),
    source_observation_id text not null,
    revision_no integer not null,
    is_current integer not null default 1,
    unique(instrument_id,effective_date,revision_no),
    foreign key (instrument_id) references market_instruments_v2(id),
    foreign key (source_observation_id) references source_observations_v2(id),
    check (revision_no > 0),
    check (is_current in (0,1))
);

create table if not exists fact_resolution_log_v2 (
    id text primary key,
    fact_type text not null,
    business_key_hash text not null,
    selected_observation_id text not null,
    candidate_observation_ids_json json not null,
    rule_id text,
    decision_reason text not null,
    selected_at text not null,
    unique(fact_type,business_key_hash,selected_at),
    foreign key (selected_observation_id) references source_observations_v2(id),
    foreign key (rule_id) references source_priority_rules_v2(id)
);

create table if not exists financial_reports_v2 (
    id text primary key,
    instrument_id text not null,
    report_type text not null,
    fiscal_period_end date not null,
    announcement_date date not null,
    effective_at text not null,
    currency text,
    provider_id text not null,
    source_observation_id text not null,
    revision_no integer not null,
    is_current integer not null default 1,
    unique(instrument_id,report_type,fiscal_period_end,announcement_date,provider_id,revision_no),
    foreign key (instrument_id) references market_instruments_v2(id),
    foreign key (provider_id) references data_providers_v2(id),
    foreign key (source_observation_id) references source_observations_v2(id),
    check (revision_no > 0),
    check (is_current in (0,1))
);

create table if not exists futures_continuous_mappings_v2 (
    id text primary key,
    continuous_instrument_id text not null,
    mapped_instrument_id text not null,
    trade_date date not null,
    provider_id text not null,
    source_observation_id text not null,
    revision_no integer not null,
    is_current integer not null default 1,
    unique(continuous_instrument_id,trade_date,provider_id,revision_no),
    foreign key (continuous_instrument_id) references market_instruments_v2(id),
    foreign key (mapped_instrument_id) references market_instruments_v2(id),
    foreign key (provider_id) references data_providers_v2(id),
    foreign key (source_observation_id) references source_observations_v2(id),
    check (continuous_instrument_id <> mapped_instrument_id),
    check (revision_no > 0),
    check (is_current in (0,1))
);

create table if not exists futures_contract_terms_v2 (
    instrument_id text primary key,
    product_code text not null,
    delivery_month text,
    trade_unit text,
    per_unit decimal(28,8),
    quote_unit text,
    delivery_method text,
    last_trade_date date,
    last_delivery_date date,
    trading_hours text,
    source_observation_id text,
    foreign key (instrument_id) references market_instruments_v2(id),
    foreign key (source_observation_id) references source_observations_v2(id),
    check (per_unit is null or per_unit > 0)
);

create table if not exists futures_settlement_params_v2 (
    id text primary key,
    instrument_id text not null,
    trade_date date not null,
    settlement decimal(20,8),
    trading_fee_rate decimal(20,10),
    trading_fee_per_contract decimal(20,8),
    delivery_fee decimal(20,8),
    minimum_margin_rate decimal(20,10),
    source_observation_id text not null,
    revision_no integer not null,
    is_current integer not null default 1,
    unique(instrument_id,trade_date,revision_no),
    foreign key (instrument_id) references market_instruments_v2(id),
    foreign key (source_observation_id) references source_observations_v2(id),
    check (revision_no > 0),
    check (is_current in (0,1))
);

create table if not exists index_definitions_v2 (
    instrument_id text primary key,
    publisher text,
    category text,
    index_style text,
    base_date date,
    base_point decimal(20,8),
    weighting_rule text,
    description text,
    source_observation_id text,
    foreign key (instrument_id) references market_instruments_v2(id),
    foreign key (source_observation_id) references source_observations_v2(id)
);

create table if not exists index_memberships_v2 (
    id text primary key,
    index_instrument_id text not null,
    member_instrument_id text not null,
    announced_at text,
    effective_from date not null,
    effective_to date,
    provider_id text not null,
    source_observation_id text not null,
    revision_no integer not null,
    is_current integer not null default 1,
    unique(index_instrument_id,member_instrument_id,effective_from,provider_id,revision_no),
    foreign key (index_instrument_id) references market_instruments_v2(id),
    foreign key (member_instrument_id) references market_instruments_v2(id),
    foreign key (provider_id) references data_providers_v2(id),
    foreign key (source_observation_id) references source_observations_v2(id),
    check (effective_to is null or effective_to >= effective_from),
    check (revision_no > 0),
    check (is_current in (0,1))
);

create table if not exists index_weights_v2 (
    id text primary key,
    index_instrument_id text not null,
    member_instrument_id text not null,
    weight_date date not null,
    weight decimal(20,10) not null,
    provider_id text not null,
    source_observation_id text not null,
    revision_no integer not null,
    is_current integer not null default 1,
    unique(index_instrument_id,member_instrument_id,weight_date,provider_id,revision_no),
    foreign key (index_instrument_id) references market_instruments_v2(id),
    foreign key (member_instrument_id) references market_instruments_v2(id),
    foreign key (provider_id) references data_providers_v2(id),
    foreign key (source_observation_id) references source_observations_v2(id),
    check (weight >= 0),
    check (revision_no > 0),
    check (is_current in (0,1))
);

create table if not exists market_instrument_relations_v2 (
    id text primary key,
    parent_instrument_id text not null,
    child_instrument_id text not null,
    relation_type text not null,
    valid_from date not null,
    valid_to date,
    source_observation_id text,
    unique(parent_instrument_id,child_instrument_id,relation_type,valid_from),
    foreign key (parent_instrument_id) references market_instruments_v2(id),
    foreign key (child_instrument_id) references market_instruments_v2(id),
    foreign key (source_observation_id) references source_observations_v2(id),
    check (parent_instrument_id <> child_instrument_id),
    check (valid_to is null or valid_to >= valid_from)
);

create table if not exists market_trading_sessions_v2 (
    venue_id text not null,
    trade_date date not null,
    session_type text not null default 'regular',
    is_open integer not null,
    open_at text,
    close_at text,
    previous_trade_date date,
    next_trade_date date,
    source_observation_id text,
    primary key (venue_id,trade_date,session_type),
    foreign key (venue_id) references market_venues_v2(id),
    foreign key (source_observation_id) references source_observations_v2(id),
    check (is_open in (0,1)),
    check (close_at is null or open_at is null or close_at >= open_at)
);

create table if not exists option_contract_terms_v2 (
    instrument_id text primary key,
    underlying_instrument_id text not null,
    option_type text not null,
    call_put text not null,
    exercise_style text,
    exercise_price decimal(20,8) not null,
    settlement_month text,
    maturity_date date not null,
    last_exercise_date date,
    last_delivery_date date,
    list_price decimal(20,8),
    quote_unit text,
    contract_unit decimal(28,8),
    minimum_price_change decimal(20,8),
    source_observation_id text,
    foreign key (instrument_id) references market_instruments_v2(id),
    foreign key (underlying_instrument_id) references market_instruments_v2(id),
    foreign key (source_observation_id) references source_observations_v2(id),
    check (call_put in ('call','put','C','P')),
    check (exercise_price >= 0),
    check (contract_unit is null or contract_unit > 0),
    check (minimum_price_change is null or minimum_price_change > 0)
);

create table if not exists financial_facts_v2 (
    report_id text not null,
    field_name text not null,
    value_decimal decimal(38,8),
    value_text text,
    unit text,
    scale integer not null default 0,
    primary key (report_id,field_name),
    foreign key (report_id) references financial_reports_v2(id),
    check (value_decimal is not null or value_text is not null)
);

create index if not exists idx_alert_deliveries_alert
                on alert_deliveries(alert_id, channel);

create index if not exists idx_alert_deliveries_retry
    on alert_deliveries(status, next_retry_at, attempt_count);

create index if not exists idx_alert_deliveries_status
                on alert_deliveries(status, updated_at);

create index if not exists idx_alert_events_status
                on alert_events(status, event_type, last_seen_at);

create index if not exists idx_api_idempotency_status_updated
    on api_idempotency_keys(status, updated_at);

create index if not exists idx_artifact_registry_model
    on artifact_registry(model_release_id, artifact_type, created_at);

create index if not exists idx_artifact_registry_release
    on artifact_registry(data_release_id, artifact_type, created_at);

create index if not exists idx_ashare_tech_agent_runs_report
    on ashare_tech_agent_runs(report_id, created_at desc);

create index if not exists idx_ashare_tech_agent_runs_status
    on ashare_tech_agent_runs(status, updated_at desc);

create index if not exists idx_ashare_tech_agent_stages_run
    on ashare_tech_agent_stages(run_id, sequence_no);

create index if not exists idx_ashare_tech_candidate_signals_report
    on ashare_tech_candidate_signals(report_id, symbol);

create index if not exists idx_ashare_tech_prediction_eval_summary
    on ashare_tech_prediction_evaluations(status, horizon_days, evaluated_date);

create index if not exists idx_ashare_tech_predictions_pending
    on ashare_tech_predictions(target_date, horizon_days);

create index if not exists idx_ashare_tech_predictions_report
    on ashare_tech_predictions(report_id, symbol);

create index if not exists idx_ashare_tech_prompt_templates_key
    on ashare_tech_prompt_templates(template_key, version_no desc);

create index if not exists idx_ashare_tech_reports_analysis_date
    on ashare_tech_reports(analysis_date desc);

create index if not exists idx_ashare_tech_reports_created
    on ashare_tech_reports(created_at desc);

create index if not exists idx_ashare_tech_reports_status
    on ashare_tech_reports(status, updated_at desc);

create index if not exists idx_ashare_tech_watchlist_group
    on ashare_tech_watchlist_items(group_key, enabled, code);

create index if not exists idx_asset_capabilities_state
    on asset_capabilities(state, asset_class, market, venue, resolution);

create index if not exists idx_backtest_results_job
                on backtest_results(job_id);

create index if not exists idx_backtest_runs_asset on backtest_runs(asset_class, venue, symbol);

create index if not exists idx_backtest_runs_created_at
                on backtest_runs(created_at desc);

create index if not exists idx_backtest_runs_data_release on backtest_runs(data_release_id);

create index if not exists idx_backtest_runs_execution_backend
    on backtest_runs(execution_backend, status, created_at);

create index if not exists idx_backtest_runs_project_status_created
    on backtest_runs(project_id, status, created_at desc);

create index if not exists idx_backtest_runs_release on backtest_runs(dataset_release_id);

create index if not exists idx_backtest_runs_status
                on backtest_runs(status);

create index if not exists idx_backtest_runs_symbol
                on backtest_runs(symbol);

create index if not exists idx_backtest_runs_task_created
    on backtest_runs(task_id, created_at desc);

create index if not exists idx_backtest_runs_terminal_trust
    on backtest_runs(status, trust_status, finished_at);

create index if not exists idx_cbond_call_events_date
                on cbond_call_events(announce_date, last_trade_date, status);

create index if not exists idx_cbond_stock_symbol
                on cbond_securities(stock_symbol);

create index if not exists idx_columnar_partitions_v2_range
    on columnar_partitions_v2(dataset_id,first_timestamp,last_timestamp,status);

create index if not exists idx_corporate_actions_symbol_date
                on corporate_actions(symbol, ex_date);

create index if not exists idx_data_assets_asset on data_assets(asset_class, venue, symbol);

create index if not exists idx_data_assets_status_created on data_assets(status, created_at desc);

create index if not exists idx_data_assets_symbol
                on data_assets(symbol);

create index if not exists idx_data_gap_resolution_lookup
    on data_gap_resolutions(market, symbol, status, trade_date);

create index if not exists idx_data_gaps_lookup
                on data_gaps(dataset, asset_class, market, symbol);

create index if not exists idx_data_quality_reports_lookup
                on data_quality_reports(report_type, asset_class, market, symbol, created_at desc);

create index if not exists idx_data_record_issues_status
    on data_record_issues(status, dataset_key);

create index if not exists idx_data_releases_status
    on data_releases(status, market, universe, coverage_end);

create index if not exists idx_data_sync_items_run
    on data_sync_items(run_id, status);

create index if not exists idx_data_sync_lineage_jobs_run
    on data_sync_lineage_jobs(run_id,dataset_key,status);

create index if not exists idx_data_sync_lineage_jobs_status
    on data_sync_lineage_jobs(status,created_at);

create index if not exists idx_data_sync_runs_heartbeat
    on data_sync_runs(status, heartbeat_at);

create index if not exists idx_data_sync_runs_status
    on data_sync_runs(status, created_at);

create index if not exists idx_data_sync_work_pending
    on data_sync_work_items(run_id, dataset_key, status, sequence_no);

create index if not exists idx_dataset_releases_active_scope
    on dataset_releases(status, source, asset_class, market, venue, resolution, data_type);

create index if not exists idx_dataset_versions_certified_source
    on dataset_versions(is_production, is_certified, asset_class, market, venue);

create index if not exists idx_dataset_versions_lookup
                on dataset_versions(asset_class, market, symbol, start_date, end_date);

create index if not exists idx_dataset_versions_release on dataset_versions(dataset_release_id);

create index if not exists idx_derived_layer_watermarks_status
    on derived_layer_watermarks(layer_key, status, materialized_end);

create index if not exists idx_derived_maintenance_retry
    on derived_maintenance_runs(status, next_retry_at, attempt_count);

create index if not exists idx_derived_maintenance_runs_status
    on derived_maintenance_runs(status, created_at);

create index if not exists idx_experiment_batch_attempts_item on experiment_batch_attempts(item_id, attempt);

create index if not exists idx_experiment_batch_items_batch_status on experiment_batch_items(batch_id, status, item_index);

create index if not exists idx_experiment_batch_items_related on experiment_batch_items(related_id);

create index if not exists idx_experiment_batches_created on experiment_batches(created_at);

create index if not exists idx_experiment_batches_status on experiment_batches(status, created_at);

create index if not exists idx_experiments_run
                on experiments(run_id);

create index if not exists idx_factor_evaluations_created_at
                on factor_evaluations(created_at desc);

create index if not exists idx_factor_values_name_date
                on factor_values(factor_name, trade_date, symbol);

create index if not exists idx_feature_pipeline_fits_window on feature_pipeline_fits(window_id, fit_phase);

create index if not exists idx_financial_facts_pit
                on financial_facts(symbol, field_name, effective_date, announce_date, report_date);

create index if not exists idx_financial_reports_v2_pit
    on financial_reports_v2(instrument_id,effective_at,report_type,fiscal_period_end);

create index if not exists idx_financial_statements_pit
                on financial_statements(symbol, statement_type, effective_date, announce_date, report_date);

create index if not exists idx_futures_continuous_builds_lookup
    on futures_continuous_builds(product, exchange, created_at);

create index if not exists idx_futures_contracts_product
                on futures_contracts(product, exchange, last_trade_date);

create index if not exists idx_futures_main_mapping_date
                on futures_main_mapping(product, exchange, trade_date);

create index if not exists idx_futures_roll_events_build
    on futures_roll_events(build_id, trade_date);

create index if not exists idx_import_batches_started_at
                on data_import_batches(started_at desc);

create index if not exists idx_index_artifacts_code
                on index_source_artifacts(index_code, fetched_at);

create index if not exists idx_index_events_asof
                on index_membership_events(index_code, effective_date, announce_date, symbol);

create index if not exists idx_index_memberships_v2_pit
    on index_memberships_v2(index_instrument_id,effective_from,effective_to,member_instrument_id);

create index if not exists idx_index_weights_date
                on index_weights(universe_code, trade_date, symbol);

create index if not exists idx_index_weights_v2_date
    on index_weights_v2(index_instrument_id,weight_date,is_current,member_instrument_id);

create index if not exists idx_industry_membership_pit
    on industry_membership(symbol, taxonomy, level_no, in_date, out_date);

create index if not exists idx_instrument_identifiers_instrument
    on instrument_identifiers(instrument_id, provider, identifier_type);

create UNIQUE index if not exists idx_instrument_identifiers_provider_value
    on instrument_identifiers(provider, identifier_type, identifier_value, valid_from);

create index if not exists idx_instruments_status
                on instruments(asset_class, market, status, listed_date, delisted_date);

create index if not exists idx_instruments_symbol
                on instruments(asset_class, market, venue, symbol);

create index if not exists idx_leakage_checks_window on leakage_check_results(window_id, decision);

create index if not exists idx_market_identifiers_v2_instrument
    on market_instrument_identifiers_v2(instrument_id,identifier_type,valid_from,valid_to);

create index if not exists idx_market_instruments_v2_status
    on market_instruments_v2(asset_class,venue_id,status,listed_date,delisted_date);

create index if not exists idx_ml_feature_files_set on ml_feature_files(feature_set_id);

create index if not exists idx_ml_feature_sets_created on ml_feature_sets(created_at);

create index if not exists idx_ml_prediction_files_run on ml_prediction_files(training_run_id);

create index if not exists idx_ml_training_runs_status on ml_training_runs(status, updated_at);

create index if not exists idx_ml_training_trials_run
    on ml_training_trials(training_run_id, fold_index, candidate_index);

create index if not exists idx_oos_evaluations_window on oos_evaluations(window_id, status);

create index if not exists idx_option_contract_terms_v2_chain
    on option_contract_terms_v2(underlying_instrument_id,maturity_date,call_put,exercise_price);

create index if not exists idx_paper_account_fills
    on paper_order_fills(paper_account_id, execution_cycle_id);

create index if not exists idx_paper_account_ledger_sequence
    on paper_ledger_entries(paper_account_id, account_generation, ledger_sequence);

create index if not exists idx_paper_account_trust_active
    on paper_account_trust_certifications(paper_account_id, account_generation, status, expires_at);

create index if not exists idx_paper_accounts_status_market
    on paper_accounts(status, market_scope, updated_at);

create index if not exists idx_paper_certification_cohorts_status
    on paper_certification_cohorts(status, created_at);

create index if not exists idx_paper_certification_members_account
    on paper_certification_members(paper_account_id, cohort_id);

create index if not exists idx_paper_checkpoints_run
    on paper_run_checkpoints(paper_run_id, phase);

create index if not exists idx_paper_constraint_intent
    on paper_constraint_decisions(intent_id, decision);

create index if not exists idx_paper_cycles_account_date
    on paper_execution_cycles(paper_account_id, trading_date, status);

create index if not exists idx_paper_cycles_due
    on paper_execution_cycles(status, scheduled_at, trading_date);

create index if not exists idx_paper_daily_job_events_job
    on paper_daily_job_events(job_id, sequence);

create index if not exists idx_paper_daily_jobs_session_date
    on paper_daily_jobs(session_id, trade_date);

create index if not exists idx_paper_daily_jobs_state_date
    on paper_daily_jobs(state, trade_date, scheduled_at);

create index if not exists idx_paper_deployments_account_status
    on paper_strategy_deployments(paper_account_id, status, is_primary);

create UNIQUE index if not exists idx_paper_fills_fingerprint
    on paper_order_fills(fill_fingerprint);

create index if not exists idx_paper_fills_intent
    on paper_order_fills(intent_id);

create index if not exists idx_paper_intents_session_date
    on paper_order_intents(session_id, trade_date);

create index if not exists idx_paper_lean_events_session_date
    on paper_lean_order_events(session_id, trade_date);

create index if not exists idx_paper_ledger_session_created
    on paper_ledger_entries(session_id, created_at);

create index if not exists idx_paper_ledger_trade_date
    on paper_ledger_entries(session_id, trade_date, entry_type);

create index if not exists idx_paper_orders_session_date
                on paper_orders(session_id, trade_date);

create index if not exists idx_paper_outbox_delivery
    on paper_notification_outbox(status, next_attempt_at, created_at);

create index if not exists idx_paper_outbox_terminal
    on paper_notification_outbox(status, next_attempt_at, attempt);

create index if not exists idx_paper_reconciliation_session_date
    on paper_reconciliation_records(session_id, trade_date, status);

create index if not exists idx_paper_reports_session_date
                on paper_daily_reports(session_id, trade_date);

create index if not exists idx_paper_sessions_created_at
                on paper_sessions(created_at desc);

create index if not exists idx_paper_signals_account_time
    on paper_strategy_signals(paper_account_id, signal_timestamp, disposition);

create index if not exists idx_paper_signals_session_date
                on paper_signals(session_id, trade_date);

create index if not exists idx_paper_snapshots_session_date
                on paper_portfolio_snapshots(session_id, trade_date);

create index if not exists idx_paper_transitions_intent_sequence
    on paper_order_transitions(intent_id, sequence);

create index if not exists idx_paper_universe_cert_status
                on paper_universe_certifications(universe_code, certification_status, certification_date);

create index if not exists idx_paper_universe_symbols_status
                on paper_universe_symbols(universe_code, certification_status, symbol);

create index if not exists idx_paper_walkforward_session_date
    on paper_walkforward_runs(session_id, trade_date);

create index if not exists idx_parameter_candidates_window on parameter_candidates(window_id, selected, candidate_key);

create index if not exists idx_parameter_selection_window on parameter_selection_events(window_id, selection_timestamp);

create index if not exists idx_parquet_datasets_certified_source
    on parquet_datasets(is_production, is_certified, source, asset_class, market, venue);

create index if not exists idx_parquet_datasets_lookup
                on parquet_datasets(asset_class, market, venue, resolution, data_type, adjust, source);

create index if not exists idx_parquet_datasets_release on parquet_datasets(dataset_release_id);

create index if not exists idx_parquet_files_dataset
                on parquet_files(dataset_id, first_timestamp, last_timestamp);

create index if not exists idx_pipeline_runs_created
                on pipeline_runs(started_at desc, status);

create index if not exists idx_pipeline_steps_run
                on pipeline_steps(run_id, step_name);

create index if not exists idx_portfolio_optimization_created
    on portfolio_optimization_runs(created_at);

create index if not exists idx_portfolio_optimization_status
    on portfolio_optimization_runs(status, created_at);

create index if not exists idx_projects_active_updated
    on projects(archived_at, updated_at);

create index if not exists idx_projects_name
                on projects(name);

create index if not exists idx_provider_availability_checked
                on provider_availability_log(provider, checked_at);

create index if not exists idx_provider_dataset_watermark_run
    on provider_dataset_watermarks(last_run_id, dataset_key);

create index if not exists idx_provider_ingestion_manifest_run
    on provider_ingestion_manifests(run_id, dataset_key, scope_key);

create index if not exists idx_provider_raw_archive_issues_run
    on provider_raw_archive_issues(run_id,dataset_key,detected_at);

create index if not exists idx_provider_raw_archive_issues_status
    on provider_raw_archive_issues(status,dataset_key,detected_at);

create index if not exists idx_provider_raw_archives_object
    on provider_raw_archives(object_id, created_at);

create index if not exists idx_provider_raw_archives_payload
    on provider_raw_archives(provider, dataset_key, payload_sha256);

create index if not exists idx_provider_raw_archives_run
    on provider_raw_archives(run_id, dataset_key, created_at);

create index if not exists idx_provider_raw_dataset_date
    on provider_raw_records(provider, dataset_key, business_date);

create index if not exists idx_provider_raw_dataset_instrument_date
    on provider_raw_records(dataset_key, instrument_code, business_date);

create index if not exists idx_qa_warning_allowlist_code
                on qa_warning_allowlist(warning_code, status, valid_until);

create index if not exists idx_qlib_import_data_release on qlib_research_imports(data_release_id, created_at);

create index if not exists idx_qlib_import_dataset
    on qlib_research_imports(dataset_fingerprint, created_at);

create index if not exists idx_qlib_lean_validation_target
    on qlib_lean_validations(target_artifact_id, status, created_at);

create index if not exists idx_qlib_signal_target_artifact
    on qlib_signal_snapshots(target_artifact_id, created_at);

create index if not exists idx_qlib_signal_trade_date
    on qlib_signal_snapshots(trade_date, created_at);

create index if not exists idx_reports_run_created
                on reports(run_id, created_at desc);

create index if not exists idx_reports_status_created
                on reports(status, created_at desc);

create index if not exists idx_reproducibility_golden_pair
    on reproducibility_certificates(input_fingerprint, equivalence_digest, status, created_at);

create index if not exists idx_research_run_items_run on research_run_items(run_id, item_index);

create index if not exists idx_research_runs_created on research_runs(created_at);

create index if not exists idx_research_runs_status on research_runs(status, created_at);

create index if not exists idx_research_workspaces_created on research_workspaces(created_at);

create index if not exists idx_restricted_runner_backend
    on restricted_runner_jobs(execution_backend, status, created_at);

create index if not exists idx_restricted_runner_jobs_status
    on restricted_runner_jobs(status, created_at);

create index if not exists idx_scheduler_leases_resource
                on scheduler_leases(resource, expires_at);

create index if not exists idx_securities_market_status
                on securities(market, status);

create index if not exists idx_security_name_history_pit
    on security_name_history(symbol, start_date, end_date);

create index if not exists idx_source_observations_v2_current
    on source_observations_v2(provider_dataset_id,natural_key_hash,is_current);

create index if not exists idx_source_observations_v2_observed
    on source_observations_v2(provider_dataset_id,observed_at);

create index if not exists "idx_src_tushare_bak_basic_current"
    on "src_tushare_bak_basic"("_natural_key_hash","_is_current");

create index if not exists "idx_src_tushare_bak_basic_observed"
    on "src_tushare_bak_basic"("_observed_at");

create index if not exists "idx_src_tushare_balancesheet_current"
    on "src_tushare_balancesheet"("_natural_key_hash","_is_current");

create index if not exists "idx_src_tushare_balancesheet_observed"
    on "src_tushare_balancesheet"("_observed_at");

create index if not exists "idx_src_tushare_block_trade_current"
    on "src_tushare_block_trade"("_natural_key_hash","_is_current");

create index if not exists "idx_src_tushare_block_trade_observed"
    on "src_tushare_block_trade"("_observed_at");

create index if not exists "idx_src_tushare_broker_recommend_current"
    on "src_tushare_broker_recommend"("_natural_key_hash","_is_current");

create index if not exists "idx_src_tushare_broker_recommend_observed"
    on "src_tushare_broker_recommend"("_observed_at");

create index if not exists "idx_src_tushare_bse_mapping_current"
    on "src_tushare_bse_mapping"("_natural_key_hash","_is_current");

create index if not exists "idx_src_tushare_bse_mapping_observed"
    on "src_tushare_bse_mapping"("_observed_at");

create index if not exists "idx_src_tushare_cashflow_current"
    on "src_tushare_cashflow"("_natural_key_hash","_is_current");

create index if not exists "idx_src_tushare_cashflow_observed"
    on "src_tushare_cashflow"("_observed_at");

create index if not exists "idx_src_tushare_ci_index_member_current"
    on "src_tushare_ci_index_member"("_natural_key_hash","_is_current");

create index if not exists "idx_src_tushare_ci_index_member_observed"
    on "src_tushare_ci_index_member"("_observed_at");

create index if not exists "idx_src_tushare_cyq_chips_current"
    on "src_tushare_cyq_chips"("_natural_key_hash","_is_current");

create index if not exists "idx_src_tushare_cyq_chips_observed"
    on "src_tushare_cyq_chips"("_observed_at");

create index if not exists "idx_src_tushare_cyq_perf_current"
    on "src_tushare_cyq_perf"("_natural_key_hash","_is_current");

create index if not exists "idx_src_tushare_cyq_perf_observed"
    on "src_tushare_cyq_perf"("_observed_at");

create index if not exists "idx_src_tushare_dc_concept_cons_current"
    on "src_tushare_dc_concept_cons"("_natural_key_hash","_is_current");

create index if not exists "idx_src_tushare_dc_concept_cons_observed"
    on "src_tushare_dc_concept_cons"("_observed_at");

create index if not exists "idx_src_tushare_dc_concept_current"
    on "src_tushare_dc_concept"("_natural_key_hash","_is_current");

create index if not exists "idx_src_tushare_dc_concept_observed"
    on "src_tushare_dc_concept"("_observed_at");

create index if not exists "idx_src_tushare_dc_hot_current"
    on "src_tushare_dc_hot"("_natural_key_hash","_is_current");

create index if not exists "idx_src_tushare_dc_hot_observed"
    on "src_tushare_dc_hot"("_observed_at");

create index if not exists "idx_src_tushare_dc_index_current"
    on "src_tushare_dc_index"("_natural_key_hash","_is_current");

create index if not exists "idx_src_tushare_dc_index_observed"
    on "src_tushare_dc_index"("_observed_at");

create index if not exists "idx_src_tushare_dc_member_current"
    on "src_tushare_dc_member"("_natural_key_hash","_is_current");

create index if not exists "idx_src_tushare_dc_member_observed"
    on "src_tushare_dc_member"("_observed_at");

create index if not exists "idx_src_tushare_disclosure_date_current"
    on "src_tushare_disclosure_date"("_natural_key_hash","_is_current");

create index if not exists "idx_src_tushare_disclosure_date_observed"
    on "src_tushare_disclosure_date"("_observed_at");

create index if not exists "idx_src_tushare_dividend_current"
    on "src_tushare_dividend"("_natural_key_hash","_is_current");

create index if not exists "idx_src_tushare_dividend_observed"
    on "src_tushare_dividend"("_observed_at");

create index if not exists "idx_src_tushare_express_current"
    on "src_tushare_express"("_natural_key_hash","_is_current");

create index if not exists "idx_src_tushare_express_observed"
    on "src_tushare_express"("_observed_at");

create index if not exists "idx_src_tushare_fina_audit_current"
    on "src_tushare_fina_audit"("_natural_key_hash","_is_current");

create index if not exists "idx_src_tushare_fina_audit_observed"
    on "src_tushare_fina_audit"("_observed_at");

create index if not exists "idx_src_tushare_fina_indicator_current"
    on "src_tushare_fina_indicator"("_natural_key_hash","_is_current");

create index if not exists "idx_src_tushare_fina_indicator_observed"
    on "src_tushare_fina_indicator"("_observed_at");

create index if not exists "idx_src_tushare_fina_mainbz_current"
    on "src_tushare_fina_mainbz"("_natural_key_hash","_is_current");

create index if not exists "idx_src_tushare_fina_mainbz_observed"
    on "src_tushare_fina_mainbz"("_observed_at");

create index if not exists "idx_src_tushare_forecast_current"
    on "src_tushare_forecast"("_natural_key_hash","_is_current");

create index if not exists "idx_src_tushare_forecast_observed"
    on "src_tushare_forecast"("_observed_at");

create index if not exists "idx_src_tushare_ft_limit_current"
    on "src_tushare_ft_limit"("_natural_key_hash","_is_current");

create index if not exists "idx_src_tushare_ft_limit_observed"
    on "src_tushare_ft_limit"("_observed_at");

create index if not exists "idx_src_tushare_fut_basic_current"
    on "src_tushare_fut_basic"("_natural_key_hash","_is_current");

create index if not exists "idx_src_tushare_fut_basic_observed"
    on "src_tushare_fut_basic"("_observed_at");

create index if not exists "idx_src_tushare_fut_holding_current"
    on "src_tushare_fut_holding"("_natural_key_hash","_is_current");

create index if not exists "idx_src_tushare_fut_holding_observed"
    on "src_tushare_fut_holding"("_observed_at");

create index if not exists "idx_src_tushare_fut_mapping_current"
    on "src_tushare_fut_mapping"("_natural_key_hash","_is_current");

create index if not exists "idx_src_tushare_fut_mapping_observed"
    on "src_tushare_fut_mapping"("_observed_at");

create index if not exists "idx_src_tushare_fut_settle_current"
    on "src_tushare_fut_settle"("_natural_key_hash","_is_current");

create index if not exists "idx_src_tushare_fut_settle_observed"
    on "src_tushare_fut_settle"("_observed_at");

create index if not exists "idx_src_tushare_fut_trade_cal_current"
    on "src_tushare_fut_trade_cal"("_natural_key_hash","_is_current");

create index if not exists "idx_src_tushare_fut_trade_cal_observed"
    on "src_tushare_fut_trade_cal"("_observed_at");

create index if not exists "idx_src_tushare_fut_wsr_current"
    on "src_tushare_fut_wsr"("_natural_key_hash","_is_current");

create index if not exists "idx_src_tushare_fut_wsr_observed"
    on "src_tushare_fut_wsr"("_observed_at");

create index if not exists "idx_src_tushare_hm_detail_current"
    on "src_tushare_hm_detail"("_natural_key_hash","_is_current");

create index if not exists "idx_src_tushare_hm_detail_observed"
    on "src_tushare_hm_detail"("_observed_at");

create index if not exists "idx_src_tushare_hm_list_current"
    on "src_tushare_hm_list"("_natural_key_hash","_is_current");

create index if not exists "idx_src_tushare_hm_list_observed"
    on "src_tushare_hm_list"("_observed_at");

create index if not exists "idx_src_tushare_hsgt_top10_current"
    on "src_tushare_hsgt_top10"("_natural_key_hash","_is_current");

create index if not exists "idx_src_tushare_hsgt_top10_observed"
    on "src_tushare_hsgt_top10"("_observed_at");

create index if not exists "idx_src_tushare_idx_factor_pro_current"
    on "src_tushare_idx_factor_pro"("_natural_key_hash","_is_current");

create index if not exists "idx_src_tushare_idx_factor_pro_observed"
    on "src_tushare_idx_factor_pro"("_observed_at");

create index if not exists "idx_src_tushare_income_current"
    on "src_tushare_income"("_natural_key_hash","_is_current");

create index if not exists "idx_src_tushare_income_observed"
    on "src_tushare_income"("_observed_at");

create index if not exists "idx_src_tushare_index_basic_current"
    on "src_tushare_index_basic"("_natural_key_hash","_is_current");

create index if not exists "idx_src_tushare_index_basic_observed"
    on "src_tushare_index_basic"("_observed_at");

create index if not exists "idx_src_tushare_index_classify_current"
    on "src_tushare_index_classify"("_natural_key_hash","_is_current");

create index if not exists "idx_src_tushare_index_classify_observed"
    on "src_tushare_index_classify"("_observed_at");

create index if not exists "idx_src_tushare_index_global_current"
    on "src_tushare_index_global"("_natural_key_hash","_is_current");

create index if not exists "idx_src_tushare_index_global_observed"
    on "src_tushare_index_global"("_observed_at");

create index if not exists "idx_src_tushare_index_member_all_current"
    on "src_tushare_index_member_all"("_natural_key_hash","_is_current");

create index if not exists "idx_src_tushare_index_member_all_observed"
    on "src_tushare_index_member_all"("_observed_at");

create index if not exists "idx_src_tushare_index_weight_current"
    on "src_tushare_index_weight"("_natural_key_hash","_is_current");

create index if not exists "idx_src_tushare_index_weight_observed"
    on "src_tushare_index_weight"("_observed_at");

create index if not exists "idx_src_tushare_kpl_concept_cons_current"
    on "src_tushare_kpl_concept_cons"("_natural_key_hash","_is_current");

create index if not exists "idx_src_tushare_kpl_concept_cons_observed"
    on "src_tushare_kpl_concept_cons"("_observed_at");

create index if not exists "idx_src_tushare_kpl_list_current"
    on "src_tushare_kpl_list"("_natural_key_hash","_is_current");

create index if not exists "idx_src_tushare_kpl_list_observed"
    on "src_tushare_kpl_list"("_observed_at");

create index if not exists "idx_src_tushare_limit_cpt_list_current"
    on "src_tushare_limit_cpt_list"("_natural_key_hash","_is_current");

create index if not exists "idx_src_tushare_limit_cpt_list_observed"
    on "src_tushare_limit_cpt_list"("_observed_at");

create index if not exists "idx_src_tushare_limit_list_d_current"
    on "src_tushare_limit_list_d"("_natural_key_hash","_is_current");

create index if not exists "idx_src_tushare_limit_list_d_observed"
    on "src_tushare_limit_list_d"("_observed_at");

create index if not exists "idx_src_tushare_limit_list_ths_current"
    on "src_tushare_limit_list_ths"("_natural_key_hash","_is_current");

create index if not exists "idx_src_tushare_limit_list_ths_observed"
    on "src_tushare_limit_list_ths"("_observed_at");

create index if not exists "idx_src_tushare_limit_step_current"
    on "src_tushare_limit_step"("_natural_key_hash","_is_current");

create index if not exists "idx_src_tushare_limit_step_observed"
    on "src_tushare_limit_step"("_observed_at");

create index if not exists "idx_src_tushare_margin_current"
    on "src_tushare_margin"("_natural_key_hash","_is_current");

create index if not exists "idx_src_tushare_margin_detail_current"
    on "src_tushare_margin_detail"("_natural_key_hash","_is_current");

create index if not exists "idx_src_tushare_margin_detail_observed"
    on "src_tushare_margin_detail"("_observed_at");

create index if not exists "idx_src_tushare_margin_observed"
    on "src_tushare_margin"("_observed_at");

create index if not exists "idx_src_tushare_margin_secs_current"
    on "src_tushare_margin_secs"("_natural_key_hash","_is_current");

create index if not exists "idx_src_tushare_margin_secs_observed"
    on "src_tushare_margin_secs"("_observed_at");

create index if not exists "idx_src_tushare_namechange_current"
    on "src_tushare_namechange"("_natural_key_hash","_is_current");

create index if not exists "idx_src_tushare_namechange_observed"
    on "src_tushare_namechange"("_observed_at");

create index if not exists "idx_src_tushare_new_share_current"
    on "src_tushare_new_share"("_natural_key_hash","_is_current");

create index if not exists "idx_src_tushare_new_share_observed"
    on "src_tushare_new_share"("_observed_at");

create index if not exists "idx_src_tushare_opt_basic_current"
    on "src_tushare_opt_basic"("_natural_key_hash","_is_current");

create index if not exists "idx_src_tushare_opt_basic_observed"
    on "src_tushare_opt_basic"("_observed_at");

create index if not exists "idx_src_tushare_pledge_detail_current"
    on "src_tushare_pledge_detail"("_natural_key_hash","_is_current");

create index if not exists "idx_src_tushare_pledge_detail_observed"
    on "src_tushare_pledge_detail"("_observed_at");

create index if not exists "idx_src_tushare_pledge_stat_current"
    on "src_tushare_pledge_stat"("_natural_key_hash","_is_current");

create index if not exists "idx_src_tushare_pledge_stat_observed"
    on "src_tushare_pledge_stat"("_observed_at");

create index if not exists "idx_src_tushare_pro_bar_equity_current"
    on "src_tushare_pro_bar_equity"("_natural_key_hash","_is_current");

create index if not exists "idx_src_tushare_pro_bar_equity_observed"
    on "src_tushare_pro_bar_equity"("_observed_at");

create index if not exists "idx_src_tushare_pro_bar_general_current"
    on "src_tushare_pro_bar_general"("_natural_key_hash","_is_current");

create index if not exists "idx_src_tushare_pro_bar_general_observed"
    on "src_tushare_pro_bar_general"("_observed_at");

create index if not exists "idx_src_tushare_repurchase_current"
    on "src_tushare_repurchase"("_natural_key_hash","_is_current");

create index if not exists "idx_src_tushare_repurchase_observed"
    on "src_tushare_repurchase"("_observed_at");

create index if not exists "idx_src_tushare_share_float_current"
    on "src_tushare_share_float"("_natural_key_hash","_is_current");

create index if not exists "idx_src_tushare_share_float_observed"
    on "src_tushare_share_float"("_observed_at");

create index if not exists "idx_src_tushare_slb_len_current"
    on "src_tushare_slb_len"("_natural_key_hash","_is_current");

create index if not exists "idx_src_tushare_slb_len_mm_current"
    on "src_tushare_slb_len_mm"("_natural_key_hash","_is_current");

create index if not exists "idx_src_tushare_slb_len_mm_observed"
    on "src_tushare_slb_len_mm"("_observed_at");

create index if not exists "idx_src_tushare_slb_len_observed"
    on "src_tushare_slb_len"("_observed_at");

create index if not exists "idx_src_tushare_slb_sec_current"
    on "src_tushare_slb_sec"("_natural_key_hash","_is_current");

create index if not exists "idx_src_tushare_slb_sec_detail_current"
    on "src_tushare_slb_sec_detail"("_natural_key_hash","_is_current");

create index if not exists "idx_src_tushare_slb_sec_detail_observed"
    on "src_tushare_slb_sec_detail"("_observed_at");

create index if not exists "idx_src_tushare_slb_sec_observed"
    on "src_tushare_slb_sec"("_observed_at");

create index if not exists "idx_src_tushare_st_current"
    on "src_tushare_st"("_natural_key_hash","_is_current");

create index if not exists "idx_src_tushare_st_observed"
    on "src_tushare_st"("_observed_at");

create index if not exists "idx_src_tushare_stk_account_current"
    on "src_tushare_stk_account"("_natural_key_hash","_is_current");

create index if not exists "idx_src_tushare_stk_account_observed"
    on "src_tushare_stk_account"("_observed_at");

create index if not exists "idx_src_tushare_stk_account_old_current"
    on "src_tushare_stk_account_old"("_natural_key_hash","_is_current");

create index if not exists "idx_src_tushare_stk_account_old_observed"
    on "src_tushare_stk_account_old"("_observed_at");

create index if not exists "idx_src_tushare_stk_ah_comparison_current"
    on "src_tushare_stk_ah_comparison"("_natural_key_hash","_is_current");

create index if not exists "idx_src_tushare_stk_ah_comparison_observed"
    on "src_tushare_stk_ah_comparison"("_observed_at");

create index if not exists "idx_src_tushare_stk_alert_current"
    on "src_tushare_stk_alert"("_natural_key_hash","_is_current");

create index if not exists "idx_src_tushare_stk_alert_observed"
    on "src_tushare_stk_alert"("_observed_at");

create index if not exists "idx_src_tushare_stk_auction_c_current"
    on "src_tushare_stk_auction_c"("_natural_key_hash","_is_current");

create index if not exists "idx_src_tushare_stk_auction_c_observed"
    on "src_tushare_stk_auction_c"("_observed_at");

create index if not exists "idx_src_tushare_stk_auction_current"
    on "src_tushare_stk_auction"("_natural_key_hash","_is_current");

create index if not exists "idx_src_tushare_stk_auction_o_current"
    on "src_tushare_stk_auction_o"("_natural_key_hash","_is_current");

create index if not exists "idx_src_tushare_stk_auction_o_observed"
    on "src_tushare_stk_auction_o"("_observed_at");

create index if not exists "idx_src_tushare_stk_auction_observed"
    on "src_tushare_stk_auction"("_observed_at");

create index if not exists "idx_src_tushare_stk_factor_current"
    on "src_tushare_stk_factor"("_natural_key_hash","_is_current");

create index if not exists "idx_src_tushare_stk_factor_observed"
    on "src_tushare_stk_factor"("_observed_at");

create index if not exists "idx_src_tushare_stk_factor_pro_current"
    on "src_tushare_stk_factor_pro"("_natural_key_hash","_is_current");

create index if not exists "idx_src_tushare_stk_factor_pro_observed"
    on "src_tushare_stk_factor_pro"("_observed_at");

create index if not exists "idx_src_tushare_stk_high_shock_current"
    on "src_tushare_stk_high_shock"("_natural_key_hash","_is_current");

create index if not exists "idx_src_tushare_stk_high_shock_observed"
    on "src_tushare_stk_high_shock"("_observed_at");

create index if not exists "idx_src_tushare_stk_holdernumber_current"
    on "src_tushare_stk_holdernumber"("_natural_key_hash","_is_current");

create index if not exists "idx_src_tushare_stk_holdernumber_observed"
    on "src_tushare_stk_holdernumber"("_observed_at");

create index if not exists "idx_src_tushare_stk_holdertrade_current"
    on "src_tushare_stk_holdertrade"("_natural_key_hash","_is_current");

create index if not exists "idx_src_tushare_stk_holdertrade_observed"
    on "src_tushare_stk_holdertrade"("_observed_at");

create index if not exists "idx_src_tushare_stk_limit_current"
    on "src_tushare_stk_limit"("_natural_key_hash","_is_current");

create index if not exists "idx_src_tushare_stk_limit_observed"
    on "src_tushare_stk_limit"("_observed_at");

create index if not exists "idx_src_tushare_stk_managers_current"
    on "src_tushare_stk_managers"("_natural_key_hash","_is_current");

create index if not exists "idx_src_tushare_stk_managers_observed"
    on "src_tushare_stk_managers"("_observed_at");

create index if not exists "idx_src_tushare_stk_nineturn_current"
    on "src_tushare_stk_nineturn"("_natural_key_hash","_is_current");

create index if not exists "idx_src_tushare_stk_nineturn_observed"
    on "src_tushare_stk_nineturn"("_observed_at");

create index if not exists "idx_src_tushare_stk_premarket_current"
    on "src_tushare_stk_premarket"("_natural_key_hash","_is_current");

create index if not exists "idx_src_tushare_stk_premarket_observed"
    on "src_tushare_stk_premarket"("_observed_at");

create index if not exists "idx_src_tushare_stk_rewards_current"
    on "src_tushare_stk_rewards"("_natural_key_hash","_is_current");

create index if not exists "idx_src_tushare_stk_rewards_observed"
    on "src_tushare_stk_rewards"("_observed_at");

create index if not exists "idx_src_tushare_stk_shock_current"
    on "src_tushare_stk_shock"("_natural_key_hash","_is_current");

create index if not exists "idx_src_tushare_stk_shock_observed"
    on "src_tushare_stk_shock"("_observed_at");

create index if not exists "idx_src_tushare_stk_surv_current"
    on "src_tushare_stk_surv"("_natural_key_hash","_is_current");

create index if not exists "idx_src_tushare_stk_surv_observed"
    on "src_tushare_stk_surv"("_observed_at");

create index if not exists "idx_src_tushare_stk_week_month_adj_current"
    on "src_tushare_stk_week_month_adj"("_natural_key_hash","_is_current");

create index if not exists "idx_src_tushare_stk_week_month_adj_observed"
    on "src_tushare_stk_week_month_adj"("_observed_at");

create index if not exists "idx_src_tushare_stock_basic_current"
    on "src_tushare_stock_basic"("_natural_key_hash","_is_current");

create index if not exists "idx_src_tushare_stock_basic_observed"
    on "src_tushare_stock_basic"("_observed_at");

create index if not exists "idx_src_tushare_stock_company_current"
    on "src_tushare_stock_company"("_natural_key_hash","_is_current");

create index if not exists "idx_src_tushare_stock_company_observed"
    on "src_tushare_stock_company"("_observed_at");

create index if not exists "idx_src_tushare_stock_hsgt_current"
    on "src_tushare_stock_hsgt"("_natural_key_hash","_is_current");

create index if not exists "idx_src_tushare_stock_hsgt_observed"
    on "src_tushare_stock_hsgt"("_observed_at");

create index if not exists "idx_src_tushare_stock_st_current"
    on "src_tushare_stock_st"("_natural_key_hash","_is_current");

create index if not exists "idx_src_tushare_stock_st_observed"
    on "src_tushare_stock_st"("_observed_at");

create index if not exists "idx_src_tushare_tdx_index_current"
    on "src_tushare_tdx_index"("_natural_key_hash","_is_current");

create index if not exists "idx_src_tushare_tdx_index_observed"
    on "src_tushare_tdx_index"("_observed_at");

create index if not exists "idx_src_tushare_tdx_member_current"
    on "src_tushare_tdx_member"("_natural_key_hash","_is_current");

create index if not exists "idx_src_tushare_tdx_member_observed"
    on "src_tushare_tdx_member"("_observed_at");

create index if not exists "idx_src_tushare_ths_hot_current"
    on "src_tushare_ths_hot"("_natural_key_hash","_is_current");

create index if not exists "idx_src_tushare_ths_hot_observed"
    on "src_tushare_ths_hot"("_observed_at");

create index if not exists "idx_src_tushare_ths_index_current"
    on "src_tushare_ths_index"("_natural_key_hash","_is_current");

create index if not exists "idx_src_tushare_ths_index_observed"
    on "src_tushare_ths_index"("_observed_at");

create index if not exists "idx_src_tushare_ths_member_current"
    on "src_tushare_ths_member"("_natural_key_hash","_is_current");

create index if not exists "idx_src_tushare_ths_member_observed"
    on "src_tushare_ths_member"("_observed_at");

create index if not exists "idx_src_tushare_top10_floatholders_current"
    on "src_tushare_top10_floatholders"("_natural_key_hash","_is_current");

create index if not exists "idx_src_tushare_top10_floatholders_observed"
    on "src_tushare_top10_floatholders"("_observed_at");

create index if not exists "idx_src_tushare_top10_holders_current"
    on "src_tushare_top10_holders"("_natural_key_hash","_is_current");

create index if not exists "idx_src_tushare_top10_holders_observed"
    on "src_tushare_top10_holders"("_observed_at");

create index if not exists "idx_src_tushare_top_inst_current"
    on "src_tushare_top_inst"("_natural_key_hash","_is_current");

create index if not exists "idx_src_tushare_top_inst_observed"
    on "src_tushare_top_inst"("_observed_at");

create index if not exists "idx_src_tushare_top_list_current"
    on "src_tushare_top_list"("_natural_key_hash","_is_current");

create index if not exists "idx_src_tushare_top_list_observed"
    on "src_tushare_top_list"("_observed_at");

create index if not exists "idx_src_tushare_trade_cal_current"
    on "src_tushare_trade_cal"("_natural_key_hash","_is_current");

create index if not exists "idx_src_tushare_trade_cal_observed"
    on "src_tushare_trade_cal"("_observed_at");

create index if not exists idx_stored_objects_hash
                on stored_objects(sha256);

create index if not exists idx_stored_objects_key_updated
                on stored_objects(object_key, updated_at desc);

create index if not exists idx_stored_objects_lookup
                on stored_objects(namespace, object_key, updated_at);

create index if not exists idx_stored_objects_namespace_updated
                on stored_objects(namespace, updated_at desc);

create index if not exists idx_strategy_admission_events
                on strategy_admission_events(admission_id, created_at);

create index if not exists idx_strategy_admissions_lookup
                on strategy_admissions(strategy_id, parameters_sha256, updated_at desc);

create index if not exists idx_strategy_versions_project
                on strategy_versions(project_id, created_at desc);

create index if not exists idx_tasks_created_at
                on tasks(created_at desc);

create index if not exists idx_universe_asof
                on universe_membership(universe_code, start_date, end_date);

create index if not exists idx_universe_coverage_status
    on universe_coverage_watermarks(coverage_status, coverage_end);

create index if not exists idx_verification_cases_run
    on verification_cases(verification_run_id, stage, status);

create index if not exists idx_verification_runs_created
    on verification_runs(created_at);

create UNIQUE index if not exists idx_walk_forward_certificate_digest
    on walk_forward_runs(certificate_digest);

create index if not exists idx_walk_forward_runs_status on walk_forward_runs(status, created_at);

create index if not exists idx_walk_forward_windows_batch on walk_forward_windows(batch_id, project_id, symbol, fold);

create index if not exists idx_walk_forward_windows_run on walk_forward_windows(walk_forward_run_id, fold);

create index if not exists idx_workflow_events_lookup
    on workflow_events(workflow_id, created_at);

create index if not exists idx_workflow_events_trace
    on workflow_events(trace_id, created_at);

create index if not exists idx_workflow_lineage_child
    on workflow_lineage_edges(child_type, child_id, created_at);

create index if not exists idx_workflow_lineage_parent
    on workflow_lineage_edges(parent_type, parent_id, created_at);

create UNIQUE index if not exists uq_paper_account_ledger_sequence
    on paper_ledger_entries(paper_account_id, account_generation, ledger_sequence);

create or replace view index_membership_pit as
            select
                universe_code as index_code,
                symbol,
                announce_date,
                effective_date,
                start_date,
                end_date,
                weight,
                source,
                batch_id
            from universe_membership;
