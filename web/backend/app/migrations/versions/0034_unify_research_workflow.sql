-- description: Unify standard research runs and notebook workspaces

create table if not exists research_workspaces (
    id varchar(64) primary key,
    task_id varchar(64),
    project_id varchar(191),
    status varchar(32) not null,
    port integer not null,
    container_id varchar(191),
    url varchar(255),
    log_path varchar(1024),
    error longtext,
    created_at varchar(64) not null,
    started_at varchar(64),
    finished_at varchar(64),
    readiness_status varchar(32),
    container_status varchar(32),
    workspace_path varchar(1024),
    last_checked_at varchar(64),
    project_name varchar(255),
    snapshot_id varchar(64)
);

create table if not exists research_runs (
    id varchar(64) primary key,
    task_id varchar(64),
    template_key varchar(64) not null,
    name varchar(255) not null,
    status varchar(32) not null,
    scope_json longtext not null,
    parameters_json longtext not null,
    result_json longtext,
    summary_json longtext,
    data_fingerprint varchar(128),
    source_research_run_id varchar(64),
    error longtext,
    cancel_requested integer not null default 0,
    created_at varchar(64) not null,
    started_at varchar(64),
    finished_at varchar(64)
);

create table if not exists research_run_items (
    id varchar(64) primary key,
    run_id varchar(64) not null,
    item_index integer not null,
    item_key varchar(255) not null,
    status varchar(32) not null,
    parameters_json longtext not null,
    result_json longtext,
    error longtext,
    created_at varchar(64) not null,
    started_at varchar(64),
    finished_at varchar(64),
    unique(run_id, item_key)
);

create index idx_research_runs_created on research_runs(created_at);
create index idx_research_runs_status on research_runs(status, created_at);
create index idx_research_run_items_run on research_run_items(run_id, item_index);
create index idx_research_workspaces_created on research_workspaces(created_at);

insert into research_workspaces
    (id, task_id, project_id, status, port, container_id, url, log_path, error,
     created_at, started_at, finished_at, readiness_status, container_status,
     workspace_path, last_checked_at, project_name)
select id, task_id, project_id, status, port, container_id, url, log_path, error,
       created_at, started_at, finished_at, readiness_status, container_status,
       workspace_path, last_checked_at, project_name
from research_sessions
where id not in (select id from research_workspaces);

insert into research_runs
    (id, template_key, name, status, scope_json, parameters_json, result_json,
     summary_json, error, cancel_requested, created_at, started_at, finished_at)
select id,
       case when mode = 'factor_batch' then 'factor-evaluation' else 'legacy-analysis' end,
       name, status, '{}', config_json, summary_json, summary_json,
       null, cancel_requested, created_at, started_at, finished_at
from experiment_batches
where kind = 'research' and id not in (select id from research_runs);

insert into research_run_items
    (id, run_id, item_index, item_key, status, parameters_json, result_json,
     error, created_at, started_at, finished_at)
select i.id, i.batch_id, i.item_index, i.item_key, i.status, i.parameters_json,
       i.result_json, i.error, i.created_at, i.started_at, i.finished_at
from experiment_batch_items i
join experiment_batches b on b.id = i.batch_id
where b.kind = 'research' and i.id not in (select id from research_run_items);

delete from experiment_batch_attempts
where item_id in (
    select i.id from experiment_batch_items i
    join experiment_batches b on b.id = i.batch_id
    where b.kind = 'research'
);

delete from experiment_batch_items
where batch_id in (select id from experiment_batches where kind = 'research');

delete from experiment_batches where kind = 'research';
delete from research_sessions;
