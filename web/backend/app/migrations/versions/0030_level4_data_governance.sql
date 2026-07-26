-- description: Add independent universe and derived-layer coverage watermarks

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

create index if not exists idx_universe_coverage_status
    on universe_coverage_watermarks(coverage_status, coverage_end);

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

create index if not exists idx_derived_layer_watermarks_status
    on derived_layer_watermarks(layer_key, status, materialized_end);

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
);

create index if not exists idx_derived_maintenance_runs_status
    on derived_maintenance_runs(status, created_at);
