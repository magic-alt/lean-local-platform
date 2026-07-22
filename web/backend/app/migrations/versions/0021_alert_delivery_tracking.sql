-- description: Persist operational alert delivery attempts and outcomes

create table if not exists alert_deliveries (
    id text primary key,
    alert_id text not null,
    channel text not null,
    status text not null,
    attempt_count integer not null default 0,
    last_attempt_at text,
    last_success_at text,
    next_retry_at text,
    last_error text,
    response_code integer,
    metadata_json text not null,
    created_at text not null,
    updated_at text not null,
    unique(alert_id, channel)
);

create index if not exists idx_alert_deliveries_status
    on alert_deliveries(status, updated_at);

create index if not exists idx_alert_deliveries_alert
    on alert_deliveries(alert_id, channel);
