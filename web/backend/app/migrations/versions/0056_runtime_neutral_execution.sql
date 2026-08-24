-- description: Add backend-neutral execution and runtime lineage without rewriting historical Docker evidence
-- compatibility: additive; historical rows remain Docker-compatible and new native rows use nullable legacy Docker fields
-- rollback: disable native dispatch and retain generic evidence; remove columns only through a reviewed forward migration
-- data migration: none; readers treat null execution_backend on historical rows as docker
-- affected tests: migration translation, runner v2, run fingerprint, reproducibility, research lifecycle

alter table backtest_runs add column execution_backend varchar(32);
alter table backtest_runs add column execution_id varchar(128);
alter table backtest_runs add column runtime_identity_json longtext;
alter table backtest_runs add column canonical_config_sha256 varchar(64);

alter table restricted_runner_jobs add column execution_backend varchar(32);
alter table restricted_runner_jobs add column execution_id varchar(128);
alter table restricted_runner_jobs add column runtime_ref varchar(512);
alter table restricted_runner_jobs add column runtime_digest varchar(64);
alter table restricted_runner_jobs add column runtime_identity_json longtext;
alter table restricted_runner_jobs add column sandbox_json longtext;

alter table experiments add column execution_backend varchar(32);
alter table experiments add column runtime_identity_json longtext;
alter table experiments add column canonical_config_sha256 varchar(64);

alter table reproducibility_certificates add column logical_input_fingerprint varchar(64);
alter table reproducibility_certificates add column execution_fingerprint varchar(64);
alter table reproducibility_certificates add column runtime_identity_json longtext;

alter table research_workspaces add column execution_backend varchar(32);
alter table research_workspaces add column execution_id varchar(128);
alter table research_workspaces add column runtime_identity_json longtext;

create index if not exists idx_backtest_runs_execution_backend
    on backtest_runs(execution_backend, status, created_at);

create index if not exists idx_restricted_runner_backend
    on restricted_runner_jobs(execution_backend, status, created_at);
