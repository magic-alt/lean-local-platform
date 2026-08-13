-- description: Reconcile market-lake control tables after the Parquet authority cutover
-- rollback: retain control metadata; remove only through a reviewed forward migration

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
    sync_policy text,
    skip_reason text,
    rate_limit_per_hour integer,
    next_allowed_at text,
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
    cancel_requested integer not null default 0,
    canonical_status text,
    canonical_ready_at text,
    derived_status_json text,
    heartbeat_at text,
    request_scope_json longtext
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
    metrics_json text,
    canonical_status text,
    derived_status_json text,
    unique(run_id, dataset_key)
);

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
    detected_at text not null,
    status text not null default 'open',
    resolution_code text,
    resolution_run_id text,
    resolution_evidence_json text,
    resolved_at text
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
    finished_at text,
    attempt_count integer not null default 0,
    max_attempts integer not null default 5,
    checkpoint_json longtext,
    checkpoint_at varchar(64),
    heartbeat_at varchar(64),
    next_retry_at varchar(64),
    alert_sent_at varchar(64),
    lease_owner varchar(96)
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
    evidence_json longtext not null,
    refreshed_at varchar(64) not null,
    unique(asset_class, market, venue, resolution, data_type)
);

create index if not exists idx_provider_raw_dataset_date on provider_raw_records(provider, dataset_key, business_date);
create index if not exists idx_provider_raw_dataset_instrument_date on provider_raw_records(dataset_key, instrument_code, business_date);
create index if not exists idx_data_sync_runs_status on data_sync_runs(status, created_at);
create index if not exists idx_data_sync_runs_heartbeat on data_sync_runs(status, heartbeat_at);
create index if not exists idx_data_sync_items_run on data_sync_items(run_id, status);
create index if not exists idx_data_sync_work_pending on data_sync_work_items(run_id, dataset_key, status, sequence_no);
create index if not exists idx_data_record_issues_status on data_record_issues(status, dataset_key);
create index if not exists idx_provider_dataset_watermark_run on provider_dataset_watermarks(last_run_id, dataset_key);
create index if not exists idx_provider_ingestion_manifest_run on provider_ingestion_manifests(run_id, dataset_key, scope_key);
create index if not exists idx_provider_raw_archives_run on provider_raw_archives(run_id, dataset_key, created_at);
create index if not exists idx_provider_raw_archives_payload on provider_raw_archives(provider, dataset_key, payload_sha256);
create index if not exists idx_provider_raw_archives_object on provider_raw_archives(object_id, created_at);
create index if not exists idx_provider_raw_archive_issues_run on provider_raw_archive_issues(run_id, dataset_key, detected_at);
create index if not exists idx_provider_raw_archive_issues_status on provider_raw_archive_issues(status, dataset_key, detected_at);
create index if not exists idx_universe_coverage_status on universe_coverage_watermarks(coverage_status, coverage_end);
create index if not exists idx_derived_layer_watermarks_status on derived_layer_watermarks(layer_key, status, materialized_end);
create index if not exists idx_derived_maintenance_runs_status on derived_maintenance_runs(status, created_at);
create index if not exists idx_derived_maintenance_retry on derived_maintenance_runs(status, next_retry_at, attempt_count);
create index if not exists idx_asset_capabilities_state on asset_capabilities(state, asset_class, market, venue, resolution);
