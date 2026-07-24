-- description: Add durable idempotent Paper daily scheduling and recovery state
-- compatibility: additive, existing sessions and Celery beat schedules continue to operate
-- rollback: stop the Paper scheduler, archive job events, then drop both tables

create table if not exists paper_daily_jobs (
    id varchar(64) primary key,
    session_id varchar(64) not null,
    trade_date varchar(32) not null,
    state varchar(48) not null,
    attempt integer not null default 0,
    max_attempts integer not null default 3,
    version integer not null default 1,
    paper_run_id varchar(64),
    task_id varchar(64),
    lease_holder varchar(128),
    lease_expires_at varchar(64),
    completion_marker varchar(128),
    correlation_id varchar(128) not null,
    last_error longtext,
    scheduled_at varchar(64) not null,
    started_at varchar(64),
    completed_at varchar(64),
    updated_at varchar(64) not null,
    unique(session_id, trade_date),
    unique(completion_marker)
);

create table if not exists paper_daily_job_events (
    id varchar(64) primary key,
    job_id varchar(64) not null,
    sequence integer not null,
    from_state varchar(48),
    to_state varchar(48) not null,
    event_type varchar(64) not null,
    payload_json longtext not null,
    correlation_id varchar(128) not null,
    created_at varchar(64) not null,
    unique(job_id, sequence)
);

create index idx_paper_daily_jobs_state_date
    on paper_daily_jobs(state, trade_date, scheduled_at);
create index idx_paper_daily_jobs_session_date
    on paper_daily_jobs(session_id, trade_date);
create index idx_paper_daily_job_events_job
    on paper_daily_job_events(job_id, sequence);
