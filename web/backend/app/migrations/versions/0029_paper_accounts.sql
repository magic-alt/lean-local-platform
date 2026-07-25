-- description: Add Paper multi-account, frozen deployments, execution cycles, projections, and notification outbox
-- compatibility: additive, legacy Paper sessions remain readable and are not backfilled
-- rollback: pause account scheduling, archive account evidence, then drop the 0029 tables and nullable bridge columns

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
    metadata_json longtext not null,
    created_at varchar(64) not null,
    updated_at varchar(64) not null,
    activated_at varchar(64),
    paused_at varchar(64),
    archived_at varchar(64),
    unique(shadow_session_id)
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
    config_json longtext not null,
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
    parameters_json longtext not null,
    universe_config_json longtext not null,
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
    failure_detail longtext,
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

create table if not exists paper_execution_cycle_events (
    id varchar(64) primary key,
    cycle_id varchar(64) not null,
    sequence integer not null,
    from_status varchar(48),
    to_status varchar(48) not null,
    event_type varchar(64) not null,
    payload_json longtext not null,
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
    evidence_json longtext not null,
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

create table if not exists paper_account_checkpoints (
    id varchar(64) primary key,
    paper_account_id varchar(64) not null,
    generation integer not null,
    cycle_id varchar(64),
    source_ledger_sequence integer not null,
    digest varchar(128) not null,
    checkpoint_json longtext not null,
    created_at varchar(64) not null,
    unique(paper_account_id, generation, source_ledger_sequence),
    unique(digest),
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

create table if not exists paper_account_daily_snapshots (
    id varchar(64) primary key,
    paper_account_id varchar(64) not null,
    generation integer not null,
    trading_date varchar(32) not null,
    projection_json longtext not null,
    benchmark_symbol varchar(64) not null,
    benchmark_return decimal(20,12) not null,
    source_ledger_sequence integer not null,
    source_checkpoint_digest varchar(128) not null,
    created_at varchar(64) not null,
    unique(paper_account_id, generation, trading_date),
    foreign key (paper_account_id) references paper_accounts(id)
);

create table if not exists paper_account_daily_reports (
    id varchar(64) primary key,
    paper_account_id varchar(64) not null,
    deployment_id varchar(64) not null,
    cycle_id varchar(64) not null,
    trading_date varchar(32) not null,
    report_json longtext not null,
    result_digest varchar(128) not null,
    created_at varchar(64) not null,
    unique(cycle_id),
    unique(result_digest),
    foreign key (paper_account_id) references paper_accounts(id),
    foreign key (deployment_id) references paper_strategy_deployments(id),
    foreign key (cycle_id) references paper_execution_cycles(id)
);

create table if not exists paper_notification_outbox (
    id varchar(64) primary key,
    paper_account_id varchar(64) not null,
    deployment_id varchar(64),
    cycle_id varchar(64),
    event_type varchar(64) not null,
    dedupe_key varchar(255) not null,
    payload_json longtext not null,
    status varchar(32) not null,
    attempt integer not null default 0,
    next_attempt_at varchar(64),
    delivered_at varchar(64),
    last_error longtext,
    created_at varchar(64) not null,
    updated_at varchar(64) not null,
    unique(dedupe_key),
    foreign key (paper_account_id) references paper_accounts(id)
);

alter table paper_order_intents add column paper_account_id varchar(64);
alter table paper_order_intents add column deployment_id varchar(64);
alter table paper_order_intents add column execution_cycle_id varchar(64);
alter table paper_order_intents add column account_generation integer;
alter table paper_order_intents add column precise_quantity decimal(28,8);
alter table paper_order_intents add column precise_requested_price decimal(28,8);

alter table paper_order_fills add column paper_account_id varchar(64);
alter table paper_order_fills add column execution_cycle_id varchar(64);
alter table paper_order_fills add column precise_quantity decimal(28,8);
alter table paper_order_fills add column precise_price decimal(28,8);
alter table paper_order_fills add column commission decimal(28,8);
alter table paper_order_fills add column stamp_duty decimal(28,8);
alter table paper_order_fills add column transfer_fee decimal(28,8);
alter table paper_order_fills add column precise_slippage decimal(28,8);

alter table paper_ledger_entries add column paper_account_id varchar(64);
alter table paper_ledger_entries add column account_generation integer;
alter table paper_ledger_entries add column execution_cycle_id varchar(64);
alter table paper_ledger_entries add column ledger_sequence integer;
alter table paper_ledger_entries add column precise_quantity decimal(28,8);
alter table paper_ledger_entries add column precise_amount decimal(28,8);

create index if not exists idx_paper_accounts_status_market
    on paper_accounts(status, market_scope, updated_at);
create index if not exists idx_paper_deployments_account_status
    on paper_strategy_deployments(paper_account_id, status, is_primary);
create index if not exists idx_paper_cycles_due
    on paper_execution_cycles(status, scheduled_at, trading_date);
create index if not exists idx_paper_cycles_account_date
    on paper_execution_cycles(paper_account_id, trading_date, status);
create index if not exists idx_paper_signals_account_time
    on paper_strategy_signals(paper_account_id, signal_timestamp, disposition);
create index if not exists idx_paper_account_ledger_sequence
    on paper_ledger_entries(paper_account_id, account_generation, ledger_sequence);
create index if not exists idx_paper_account_fills
    on paper_order_fills(paper_account_id, execution_cycle_id);
create index if not exists idx_paper_outbox_delivery
    on paper_notification_outbox(status, next_attempt_at, created_at);
