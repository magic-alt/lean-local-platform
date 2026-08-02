-- description: Unify dataset releases, reproducibility certificates, Paper trust, capabilities, and maintenance recovery
-- compatibility: additive governance tables and nullable references; existing detail APIs and historical facts remain readable
-- rollback: stop certificate and maintenance writers, retain evidence rows, and remove additive references only through a reviewed forward migration

create table if not exists dataset_releases (
    id varchar(96) primary key,
    dataset_key varchar(191) not null,
    dataset_version varchar(191) not null,
    source varchar(64) not null,
    asset_class varchar(64) not null,
    market varchar(64) not null,
    venue varchar(64),
    resolution varchar(32) not null,
    data_type varchar(32) not null,
    adjust_mode varchar(32) not null,
    parquet_dataset_id varchar(64) not null,
    file_manifest_sha256 varchar(64) not null,
    qa_report_id varchar(64) not null,
    status varchar(32) not null,
    is_production integer not null default 1,
    is_certified integer not null default 1,
    coverage_start varchar(32),
    coverage_end varchar(32),
    row_count bigint not null default 0,
    file_count integer not null default 0,
    certified_by varchar(96) not null,
    certified_at varchar(64) not null,
    revoked_at varchar(64),
    revoke_reason varchar(255),
    metadata_json longtext not null,
    created_at varchar(64) not null,
    unique(dataset_key, dataset_version),
    unique(parquet_dataset_id, dataset_version),
    foreign key (parquet_dataset_id) references parquet_datasets(id)
);

create index idx_dataset_releases_active_scope
    on dataset_releases(status, source, asset_class, market, venue, resolution, data_type);

alter table parquet_datasets add column dataset_release_id varchar(96);
alter table dataset_versions add column dataset_release_id varchar(96);
alter table backtest_runs add column dataset_release_id varchar(96);
alter table backtest_runs add column reproducibility_certificate_id varchar(96);

create index idx_parquet_datasets_release on parquet_datasets(dataset_release_id);
create index idx_dataset_versions_release on dataset_versions(dataset_release_id);
create index idx_backtest_runs_release on backtest_runs(dataset_release_id);

create table if not exists reproducibility_certificates (
    id varchar(96) primary key,
    run_id varchar(191) not null,
    dataset_release_id varchar(96) not null,
    input_fingerprint varchar(64) not null,
    equivalence_digest varchar(64) not null,
    certificate_sha256 varchar(64) not null,
    canonical_result_sha256 varchar(64) not null,
    orders_sha256 varchar(64) not null,
    fills_sha256 varchar(64) not null,
    equity_sha256 varchar(64) not null,
    artifact_manifest_sha256 varchar(64) not null,
    stored_object_id varchar(64),
    status varchar(32) not null,
    certificate_json longtext not null,
    created_at varchar(64) not null,
    unique(run_id),
    unique(certificate_sha256),
    foreign key (run_id) references backtest_runs(id),
    foreign key (dataset_release_id) references dataset_releases(id),
    foreign key (stored_object_id) references stored_objects(id)
);

create index idx_reproducibility_golden_pair
    on reproducibility_certificates(input_fingerprint, equivalence_digest, status, created_at);

create table if not exists paper_account_trust_certifications (
    id varchar(96) primary key,
    paper_account_id varchar(64) not null,
    account_generation integer not null,
    dataset_release_id varchar(96) not null,
    status varchar(32) not null,
    checkpoint_count integer not null default 0,
    result_count integer not null default 0,
    evidence_json longtext not null,
    certified_at varchar(64) not null,
    expires_at varchar(64) not null,
    revoked_at varchar(64),
    revoke_reason varchar(255),
    unique(paper_account_id, account_generation, dataset_release_id),
    foreign key (paper_account_id) references paper_accounts(id),
    foreign key (dataset_release_id) references dataset_releases(id)
);

create index idx_paper_account_trust_active
    on paper_account_trust_certifications(paper_account_id, account_generation, status, expires_at);

create table if not exists asset_capabilities (
    id varchar(96) primary key,
    asset_class varchar(64) not null,
    market varchar(64) not null,
    venue varchar(64) not null,
    resolution varchar(32) not null,
    data_type varchar(32) not null,
    state varchar(32) not null,
    metadata_count bigint not null default 0,
    canonical_row_count bigint not null default 0,
    executable_reason varchar(255),
    evidence_json longtext not null,
    refreshed_at varchar(64) not null,
    unique(asset_class, market, venue, resolution, data_type)
);

create index idx_asset_capabilities_state
    on asset_capabilities(state, asset_class, market, venue, resolution);

alter table derived_maintenance_runs add column attempt_count integer not null default 0;
alter table derived_maintenance_runs add column max_attempts integer not null default 5;
alter table derived_maintenance_runs add column checkpoint_json longtext;
alter table derived_maintenance_runs add column checkpoint_at varchar(64);
alter table derived_maintenance_runs add column heartbeat_at varchar(64);
alter table derived_maintenance_runs add column next_retry_at varchar(64);
alter table derived_maintenance_runs add column alert_sent_at varchar(64);
alter table derived_maintenance_runs add column lease_owner varchar(96);

create index idx_derived_maintenance_retry
    on derived_maintenance_runs(status, next_retry_at, attempt_count);
