-- description: Unify optimization orchestration, lineage and portfolio runs
-- rollback: stop optimization workloads and restore the verified pre-migration backup

create table if not exists workflow_lineage_edges (
    id varchar(191) primary key,
    parent_type varchar(64) not null,
    parent_id varchar(191) not null,
    child_type varchar(64) not null,
    child_id varchar(191) not null,
    relation varchar(64) not null,
    contract_digest varchar(128),
    details_json longtext,
    created_at varchar(64) not null,
    unique(parent_type, parent_id, child_type, child_id, relation)
);

create index idx_workflow_lineage_parent
    on workflow_lineage_edges(parent_type, parent_id, created_at);
create index idx_workflow_lineage_child
    on workflow_lineage_edges(child_type, child_id, created_at);

create table if not exists portfolio_optimization_runs (
    id varchar(64) primary key,
    name varchar(255) not null,
    status varchar(32) not null,
    objective varchar(32) not null,
    run_ids_json longtext not null,
    constraints_json longtext not null,
    input_fingerprints_json longtext not null,
    result_json longtext,
    base_currency varchar(16),
    resolution varchar(32),
    error longtext,
    archived_at varchar(64),
    created_at varchar(64) not null,
    started_at varchar(64),
    finished_at varchar(64)
);

create index idx_portfolio_optimization_created
    on portfolio_optimization_runs(created_at);
create index idx_portfolio_optimization_status
    on portfolio_optimization_runs(status, created_at);

alter table experiment_batches add column objective_metric varchar(32);
alter table experiment_batches add column source_backtest_run_id varchar(191);
alter table experiment_batches add column scope_hash varchar(128);
alter table experiment_batches add column data_fingerprint varchar(128);
alter table experiment_batches add column archived_at varchar(64);

update tasks
set status='cancelled',
    error=coalesce(error, 'Retired by optimization workflow migration.'),
    finished_at=coalesce(finished_at, created_at)
where kind='optimization' and status in ('created','queued','running');

insert into experiment_batches
    (id,kind,mode,name,status,config_json,summary_json,total,queued,running,
     succeeded,failed,skipped,cancelled,cancel_requested,created_at,started_at,
     finished_at,objective_metric)
select o.id,'optimization','single_symbol_grid',o.id,
       case when o.status in ('created','queued','running') then 'cancelled' else o.status end,
       o.parameters_json,o.result_json,
       (select count(*) from backtest_runs br where br.task_id=o.task_id),
       0,0,
       (select count(*) from backtest_runs br where br.task_id=o.task_id and br.status='success'),
       (select count(*) from backtest_runs br where br.task_id=o.task_id and br.status='failed'),
       0,
       (select count(*) from backtest_runs br where br.task_id=o.task_id and br.status='cancelled'),
       case when o.status in ('created','queued','running','cancelled') then 1 else 0 end,
       o.created_at,o.started_at,o.finished_at,'sharpe'
from optimization_runs o
where not exists (select 1 from experiment_batches b where b.id=o.id);

insert into experiment_batch_items
    (id,batch_id,item_index,item_key,project_id,symbol,status,parameters_json,
     related_id,task_id,attempt,result_json,error,created_at,started_at,finished_at)
select br.id,o.id,
       (select count(*) from backtest_runs prior
        where prior.task_id=o.task_id and prior.created_at<=br.created_at),
       br.id,br.project_id,br.symbol,br.status,br.parameters_json,
       br.id,br.task_id,1,null,br.error,br.created_at,br.started_at,br.finished_at
from optimization_runs o
join backtest_runs br on br.task_id=o.task_id
where br.batch_item_id is null
  and not exists (select 1 from experiment_batch_items i where i.id=br.id);

update backtest_runs
set batch_item_id=id
where batch_item_id is null
  and task_id in (select task_id from optimization_runs where task_id is not null);

insert into workflow_lineage_edges
    (id,parent_type,parent_id,child_type,child_id,relation,contract_digest,
     details_json,created_at)
select br.id,'optimization',o.id,'backtest_run',br.id,'candidate',null,'{}',br.created_at
from optimization_runs o
join backtest_runs br on br.task_id=o.task_id
where not exists (select 1 from workflow_lineage_edges e where e.id=br.id);

drop table optimization_runs;
