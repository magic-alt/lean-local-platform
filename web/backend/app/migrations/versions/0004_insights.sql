-- description: Add structured insight reports and guarded decision signals

create table if not exists insight_reports (
    id text primary key,
    task_id text,
    symbol text not null,
    asset_class text not null,
    market text,
    venue text not null,
    resolution text not null default 'daily',
    data_type text not null default 'trade',
    as_of_date text,
    lookback_bars integer not null,
    backtest_run_id text,
    status text not null,
    model text,
    prompt_version text not null,
    input_fingerprint text,
    context_json text,
    raw_response_json text,
    report_json text,
    error text,
    created_at text not null,
    started_at text,
    finished_at text
);

create table if not exists decision_signals (
    id text primary key,
    insight_report_id text not null unique,
    symbol text not null,
    asset_class text not null,
    venue text not null,
    as_of_date text,
    raw_signal_json text not null,
    final_signal_json text not null,
    guardrail_json text not null,
    status text not null,
    paper_session_id text,
    paper_signal_id text,
    created_at text not null,
    updated_at text not null
);

create index if not exists idx_insight_reports_created
    on insight_reports(created_at desc);
create index if not exists idx_insight_reports_asset_symbol
    on insight_reports(asset_class, venue, symbol, created_at desc);
create index if not exists idx_decision_signals_status
    on decision_signals(status, created_at desc);
