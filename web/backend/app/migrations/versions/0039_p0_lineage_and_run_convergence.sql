-- description: Preserve certified Paper and walk-forward evidence and quarantine orphaned domain work
-- compatibility: additive evidence, status and quarantine fields; raw historical facts are not deleted
-- rollback: stop reconcilers and scheduling, retain evidence tables, and remove only the additive guards with a reviewed forward migration

alter table walk_forward_runs add column lineage_status varchar(32) not null default 'complete';
alter table walk_forward_runs add column lineage_reason varchar(255);
alter table walk_forward_runs add column batch_snapshot_json longtext;
alter table walk_forward_windows add column project_snapshot_json longtext;
alter table walk_forward_windows add column selection_inputs_json longtext;
alter table walk_forward_windows add column selection_outputs_json longtext;

update walk_forward_runs
set lineage_status='lineage_broken',
    lineage_reason='parent_batch_missing'
where not exists (
    select 1 from experiment_batches batch where batch.id=walk_forward_runs.batch_id
);

update walk_forward_runs
set lineage_status='lineage_broken',
    lineage_reason=case
        when lineage_reason is null then 'project_missing'
        else lineage_reason
    end
where exists (
    select 1 from walk_forward_windows wf_window
    where wf_window.walk_forward_run_id=walk_forward_runs.id
      and not exists (select 1 from projects project where project.id=wf_window.project_id)
);

create table if not exists paper_certification_cohorts (
    id varchar(64) primary key,
    name varchar(191) not null,
    status varchar(32) not null,
    required_accounts integer not null default 2,
    required_sessions integer not null default 21,
    contract_json longtext not null,
    evidence_digest varchar(64),
    created_at varchar(64) not null,
    refreshed_at varchar(64),
    certified_at varchar(64)
);

create table if not exists paper_certification_members (
    id varchar(64) primary key,
    cohort_id varchar(64) not null,
    paper_account_id varchar(64) not null,
    account_generation integer not null,
    opening_cash decimal(28,8) not null,
    risk_profile_id varchar(64),
    deployment_id varchar(64),
    strategy_fingerprint varchar(128),
    dataset_fingerprint varchar(128),
    execution_mode varchar(32) not null,
    evidence_json longtext,
    evidence_digest varchar(64),
    certified_sessions integer not null default 0,
    status varchar(32) not null default 'collecting',
    added_at varchar(64) not null,
    refreshed_at varchar(64),
    unique(cohort_id, paper_account_id)
);

create index idx_paper_certification_cohorts_status
    on paper_certification_cohorts(status, created_at);
create index idx_paper_certification_members_account
    on paper_certification_members(paper_account_id, cohort_id);

alter table paper_daily_jobs add column quarantined_at varchar(64);
alter table paper_daily_jobs add column quarantine_reason varchar(255);
alter table paper_reconciliation_records add column quarantined_at varchar(64);
alter table paper_reconciliation_records add column quarantine_reason varchar(255);

update paper_daily_jobs
set quarantined_at=coalesce(quarantined_at, updated_at, scheduled_at),
    quarantine_reason=coalesce(quarantine_reason, 'parent_session_missing'),
    state=case when state='READY' then 'MANUAL_INTERVENTION_REQUIRED' else state end,
    last_error=coalesce(last_error, 'Quarantined because the parent Paper session is missing.')
where not exists (select 1 from paper_sessions session where session.id=paper_daily_jobs.session_id);

update paper_reconciliation_records
set quarantined_at=coalesce(quarantined_at, created_at),
    quarantine_reason=coalesce(quarantine_reason, 'parent_session_missing')
where not exists (
    select 1 from paper_sessions session where session.id=paper_reconciliation_records.session_id
);

alter table research_runs add column owner_heartbeat_at varchar(64);
alter table research_runs add column recovery_reason varchar(255);

update research_runs
set status='failed',
    recovery_reason='owner_task_missing',
    error=coalesce(error, 'Reconciled because the owning task is missing.'),
    finished_at=coalesce(finished_at, started_at, created_at)
where status='running'
  and (task_id is null or not exists (select 1 from tasks task where task.id=research_runs.task_id));
