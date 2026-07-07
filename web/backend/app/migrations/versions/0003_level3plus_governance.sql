-- description: Add Level 3+ universe, provider, pipeline, alert, and retention governance tables

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
    duration_seconds real,
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
    duration_seconds real,
    warnings_json text not null,
    errors_json text not null,
    details_json text not null
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

create index if not exists idx_paper_universe_cert_status
    on paper_universe_certifications(universe_code, certification_status, certification_date);

create index if not exists idx_paper_universe_symbols_status
    on paper_universe_symbols(universe_code, certification_status, symbol);

create index if not exists idx_qa_warning_allowlist_code
    on qa_warning_allowlist(warning_code, status, valid_until);

create index if not exists idx_provider_availability_checked
    on provider_availability_log(provider, checked_at);

create index if not exists idx_pipeline_runs_created
    on pipeline_runs(started_at desc, status);

create index if not exists idx_pipeline_steps_run
    on pipeline_steps(run_id, step_name);

create index if not exists idx_alert_events_status
    on alert_events(status, event_type, last_seen_at);
