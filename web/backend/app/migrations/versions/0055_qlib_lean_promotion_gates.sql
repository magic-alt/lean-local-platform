-- description: Bind Qlib target portfolios to immutable LEAN validation evidence
-- compatibility: additive; existing Qlib imports remain readable but cannot be promoted without an explicit target artifact binding
-- rollback: disable new promotion endpoints, retain immutable validation evidence, then remove additions only through a reviewed forward migration

alter table qlib_signal_snapshots add column target_artifact_id varchar(128);

create index if not exists idx_qlib_signal_target_artifact
    on qlib_signal_snapshots(target_artifact_id, created_at);

create table if not exists qlib_lean_validations (
    id varchar(64) primary key,
    research_run_id varchar(64) not null,
    signal_snapshot_id varchar(64) not null,
    target_artifact_id varchar(128) not null,
    validation_artifact_id varchar(128) not null unique,
    data_release_id varchar(96) not null,
    model_release_id varchar(128) not null,
    lean_backtest_run_id varchar(64) not null,
    targets_sha256 varchar(64) not null,
    status varchar(32) not null,
    evidence_json longtext not null,
    created_at varchar(64) not null,
    unique(target_artifact_id, lean_backtest_run_id),
    foreign key (target_artifact_id) references artifact_registry(artifact_id),
    foreign key (validation_artifact_id) references artifact_registry(artifact_id)
);

create index if not exists idx_qlib_lean_validation_target
    on qlib_lean_validations(target_artifact_id, status, created_at);
