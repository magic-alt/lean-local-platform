-- description: Replace duplicated row JSON with compressed provider batch archives

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

create index if not exists idx_provider_raw_archives_run
    on provider_raw_archives(run_id, dataset_key, created_at);

create index if not exists idx_provider_raw_archives_payload
    on provider_raw_archives(provider, dataset_key, payload_sha256);
