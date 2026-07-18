-- description: Add workflow verification and evidence-backed data gap resolution

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

create index if not exists idx_data_gap_resolution_lookup
    on data_gap_resolutions(market, symbol, status, trade_date);
create index if not exists idx_workflow_events_lookup
    on workflow_events(workflow_id, created_at);
create index if not exists idx_workflow_events_trace
    on workflow_events(trace_id, created_at);
create index if not exists idx_verification_runs_created
    on verification_runs(created_at);
create index if not exists idx_verification_cases_run
    on verification_cases(verification_run_id, stage, status);
