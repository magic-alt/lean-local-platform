-- purpose: coordinate provider quotas across API and worker processes
-- compatibility: PostgreSQL 17 baseline P0001
-- rollback: stop provider ingestion, then drop provider_rate_limit_events
-- data: transient quota events only; no market facts
-- verification: concurrent acquisitions never exceed a bucket limit

create table if not exists provider_rate_limit_events (
    bucket_key text not null,
    event_id text primary key,
    occurred_at_ms bigint not null
);

create index if not exists idx_provider_rate_limit_bucket_time
    on provider_rate_limit_events(bucket_key, occurred_at_ms);
