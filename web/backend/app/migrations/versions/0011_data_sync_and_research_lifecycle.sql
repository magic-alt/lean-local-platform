-- description: Add provider data synchronization and research lifecycle metadata

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
    metadata_json text,
    primary key (provider, dataset_key)
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
    finished_at text,
    unique(run_id, dataset_key)
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

create index if not exists idx_provider_raw_dataset_date
    on provider_raw_records(provider, dataset_key, business_date);
create index if not exists idx_data_sync_runs_status
    on data_sync_runs(status, created_at);
create index if not exists idx_data_sync_items_run
    on data_sync_items(run_id, status);
create index if not exists idx_data_record_issues_status
    on data_record_issues(status, dataset_key);

alter table research_sessions add column readiness_status text;
alter table research_sessions add column container_status text;
alter table research_sessions add column workspace_path text;
alter table research_sessions add column last_checked_at text;
alter table research_sessions add column project_name text;
