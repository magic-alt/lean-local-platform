-- description: Add bounded, resumable high-throughput TuShare synchronization metadata

alter table provider_dataset_catalog add column sync_policy text;
alter table provider_dataset_catalog add column skip_reason text;
alter table provider_dataset_catalog add column rate_limit_per_hour integer;
alter table provider_dataset_catalog add column next_allowed_at text;

alter table data_sync_items add column metrics_json text;

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

create index if not exists idx_data_sync_work_pending
    on data_sync_work_items(run_id, dataset_key, status, sequence_no);
