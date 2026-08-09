-- description: Register external Qlib research runs and immutable latest target snapshots
-- compatibility: additive tables only
-- rollback: stop Qlib imports, archive manifests and target snapshots, then remove these tables with a reviewed forward migration

create table if not exists qlib_research_imports (
    id varchar(64) primary key,
    research_run_id varchar(64) not null unique,
    external_run_id varchar(128) not null unique,
    schema_version varchar(32) not null,
    run_kind varchar(64) not null,
    dataset_fingerprint varchar(128) not null,
    model_fingerprint varchar(128) not null,
    manifest_sha256 varchar(64) not null,
    manifest_json longtext not null,
    object_keys_json longtext not null,
    created_at varchar(64) not null
);
create index if not exists idx_qlib_import_dataset
    on qlib_research_imports(dataset_fingerprint, created_at);

create table if not exists qlib_signal_snapshots (
    id varchar(64) primary key,
    import_id varchar(64) not null,
    research_run_id varchar(64) not null,
    model_fingerprint varchar(128) not null,
    dataset_fingerprint varchar(128) not null,
    signal_date varchar(16) not null,
    trade_date varchar(16) not null,
    targets_sha256 varchar(64) not null,
    target_count integer not null,
    gross_exposure real not null,
    targets_json longtext not null,
    created_at varchar(64) not null,
    unique(model_fingerprint, dataset_fingerprint, signal_date)
);
create index if not exists idx_qlib_signal_trade_date
    on qlib_signal_snapshots(trade_date, created_at);
