-- description: Durable asynchronous TuShare source-lineage jobs for high-throughput canonical ingestion
-- compatibility: additive job table; existing archives and source tables remain unchanged
-- rollback: stop lineage workers, drain or archive pending jobs, then drop this table through a reviewed forward migration

create table if not exists data_sync_lineage_jobs (
    id varchar(64) primary key,
    run_id varchar(64) not null,
    dataset_key varchar(255) not null,
    object_id varchar(64) not null,
    row_count integer not null default 0,
    status varchar(32) not null default 'pending',
    attempts integer not null default 0,
    error longtext,
    created_at varchar(32) not null,
    started_at varchar(32),
    finished_at varchar(32),
    unique(run_id,dataset_key,object_id)
);

create index if not exists idx_data_sync_lineage_jobs_status
    on data_sync_lineage_jobs(status,created_at);

create index if not exists idx_data_sync_lineage_jobs_run
    on data_sync_lineage_jobs(run_id,dataset_key,status);
