-- description: Add LEAN paper walk-forward sessions and daily runs

alter table paper_sessions add column mode text not null default 'legacy_replay';
alter table paper_sessions add column legacy_read_only integer not null default 1;
alter table paper_sessions add column source_backtest_id text;
alter table paper_sessions add column strategy_version_id text;
alter table paper_sessions add column parameter_hash text;
alter table paper_sessions add column start_date text;
alter table paper_sessions add column last_processed_date text;
alter table paper_sessions add column auto_advance integer not null default 0;
alter table paper_sessions add column failure_json text;

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

create index if not exists idx_paper_walkforward_session_date
    on paper_walkforward_runs(session_id, trade_date);
create index if not exists idx_paper_lean_events_session_date
    on paper_lean_order_events(session_id, trade_date);
