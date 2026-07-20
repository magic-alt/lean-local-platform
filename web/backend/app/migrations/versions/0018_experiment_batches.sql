-- description: Add reusable experiment batch orchestration

create table if not exists experiment_batches (
    id varchar(64) primary key,
    kind varchar(32) not null,
    mode varchar(64) not null,
    name varchar(255) not null,
    example_key varchar(128),
    status varchar(32) not null,
    config_json longtext not null,
    summary_json longtext,
    total integer not null default 0,
    queued integer not null default 0,
    running integer not null default 0,
    succeeded integer not null default 0,
    failed integer not null default 0,
    skipped integer not null default 0,
    cancelled integer not null default 0,
    cancel_requested integer not null default 0,
    created_at varchar(64) not null,
    started_at varchar(64),
    finished_at varchar(64)
);

create table if not exists experiment_batch_items (
    id varchar(64) primary key,
    batch_id varchar(64) not null,
    item_index integer not null,
    item_key varchar(255) not null,
    project_id varchar(255),
    symbol varchar(64),
    status varchar(32) not null,
    parameters_json longtext not null,
    related_id varchar(128),
    task_id varchar(64),
    attempt integer not null default 0,
    result_json longtext,
    error longtext,
    created_at varchar(64) not null,
    started_at varchar(64),
    finished_at varchar(64),
    unique(batch_id, item_key)
);

create table if not exists experiment_batch_attempts (
    id varchar(64) primary key,
    item_id varchar(64) not null,
    attempt integer not null,
    related_id varchar(128),
    task_id varchar(64),
    status varchar(32) not null,
    error longtext,
    created_at varchar(64) not null,
    finished_at varchar(64),
    unique(item_id, attempt)
);

create index idx_experiment_batches_created on experiment_batches(created_at);
create index idx_experiment_batches_status on experiment_batches(status, created_at);
create index idx_experiment_batch_items_batch_status on experiment_batch_items(batch_id, status, item_index);
create index idx_experiment_batch_items_related on experiment_batch_items(related_id);
create index idx_experiment_batch_attempts_item on experiment_batch_attempts(item_id, attempt);

alter table backtest_runs add column batch_item_id varchar(64);
alter table optimization_runs add column batch_id varchar(64);
