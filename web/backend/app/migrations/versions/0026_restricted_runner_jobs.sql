-- description: Persist restricted LEAN runner job specifications and outcomes
-- compatibility: additive, local runner mode remains available outside delegated Compose workers
-- rollback: stop delegated workers, archive runner evidence, then drop this table

create table if not exists restricted_runner_jobs (
    id varchar(64) primary key,
    run_id varchar(128) not null,
    spec_digest varchar(64) not null,
    image_digest varchar(255) not null,
    command_json longtext not null,
    mounts_json longtext not null,
    resource_limits_json longtext not null,
    network_policy varchar(32) not null,
    status varchar(32) not null,
    exit_code integer,
    timed_out integer not null default 0,
    error longtext,
    created_at varchar(64) not null,
    started_at varchar(64),
    finished_at varchar(64),
    unique(run_id),
    unique(spec_digest)
);

create index idx_restricted_runner_jobs_status
    on restricted_runner_jobs(status, created_at);
