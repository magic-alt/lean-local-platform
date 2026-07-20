-- description: Track live data-sync heartbeats for orphan recovery

alter table data_sync_runs add column heartbeat_at text;

create index if not exists idx_data_sync_runs_heartbeat
    on data_sync_runs(status, heartbeat_at);
