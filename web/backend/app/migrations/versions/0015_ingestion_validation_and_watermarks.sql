-- description: Add auditable ingestion manifests, coverage watermarks, and layered readiness

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

create index if not exists idx_provider_dataset_watermark_run
    on provider_dataset_watermarks(last_run_id, dataset_key);

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

create index if not exists idx_provider_ingestion_manifest_run
    on provider_ingestion_manifests(run_id, dataset_key, scope_key);

alter table data_sync_runs add column canonical_status text;
alter table data_sync_runs add column canonical_ready_at text;
alter table data_sync_runs add column derived_status_json text;

alter table data_sync_items add column canonical_status text;
alter table data_sync_items add column derived_status_json text;
