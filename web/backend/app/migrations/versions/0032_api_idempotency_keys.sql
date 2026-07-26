-- description: Persist write-request idempotency keys and completed API responses
-- compatibility: additive table, clients without Idempotency-Key retain current behavior
-- rollback: stop accepting Idempotency-Key, wait for in-flight writes, then drop api_idempotency_keys

create table if not exists api_idempotency_keys (
    id varchar(64) primary key,
    idempotency_key varchar(255) not null,
    method varchar(16) not null,
    request_path varchar(1024) not null,
    request_path_sha256 varchar(64) not null,
    request_sha256 varchar(64) not null,
    status varchar(32) not null,
    response_status integer,
    response_body text,
    response_content_type varchar(255),
    trace_id varchar(128),
    created_at text not null,
    updated_at text not null,
    unique(idempotency_key, method, request_path_sha256)
);

create index if not exists idx_api_idempotency_status_updated
    on api_idempotency_keys(status, updated_at);
