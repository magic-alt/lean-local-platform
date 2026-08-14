-- description: Add immutable composite data releases and the cross-engine artifact registry
-- compatibility: additive tables and nullable references; legacy dataset releases and Qlib v1 imports remain readable
-- rollback: stop v2 publishers/imports, archive manifests and artifact records, then remove additions through a reviewed forward migration

create table if not exists data_releases (
    id varchar(96) primary key,
    schema_version varchar(32) not null,
    profile varchar(96) not null,
    asset_class varchar(64) not null,
    market varchar(64) not null,
    universe varchar(96) not null,
    benchmark varchar(32) not null,
    coverage_start varchar(32) not null,
    coverage_end varchar(32) not null,
    as_of_time varchar(64) not null,
    identity_sha256 varchar(64) not null unique,
    manifest_sha256 varchar(64) not null unique,
    manifest_path varchar(1024) not null,
    status varchar(32) not null,
    created_at varchar(64) not null,
    revoked_at varchar(64),
    revoke_reason varchar(255)
);

create index if not exists idx_data_releases_status
    on data_releases(status, market, universe, coverage_end);

create table if not exists data_release_components (
    data_release_id varchar(96) not null,
    role varchar(64) not null,
    component_release_id varchar(128) not null,
    dataset_key varchar(191) not null,
    schema_version varchar(32) not null,
    coverage_start varchar(32) not null,
    coverage_end varchar(32) not null,
    file_count integer not null,
    row_count bigint not null default 0,
    component_sha256 varchar(64) not null,
    component_json longtext not null,
    primary key (data_release_id, role),
    foreign key (data_release_id) references data_releases(id)
);

create table if not exists artifact_registry (
    artifact_id varchar(128) primary key,
    schema_version varchar(32) not null,
    artifact_type varchar(64) not null,
    owner varchar(32) not null,
    promotion_status varchar(32) not null,
    data_release_id varchar(96) not null,
    universe_release_id varchar(128),
    model_release_id varchar(128),
    strategy_policy_id varchar(128),
    git_commit varchar(128) not null,
    container_digest varchar(255) not null,
    as_of_time varchar(64) not null,
    signal_date varchar(32),
    trade_date varchar(32),
    timezone varchar(64) not null,
    currency varchar(16) not null,
    payload_sha256 varchar(64) not null,
    object_key varchar(1024),
    media_type varchar(128),
    row_count bigint,
    metadata_json longtext not null,
    created_at varchar(64) not null
);

create index if not exists idx_artifact_registry_release
    on artifact_registry(data_release_id, artifact_type, created_at);
create index if not exists idx_artifact_registry_model
    on artifact_registry(model_release_id, artifact_type, created_at);

create table if not exists artifact_lineage_edges (
    parent_artifact_id varchar(128) not null,
    child_artifact_id varchar(128) not null,
    created_at varchar(64) not null,
    primary key (parent_artifact_id, child_artifact_id),
    foreign key (parent_artifact_id) references artifact_registry(artifact_id),
    foreign key (child_artifact_id) references artifact_registry(artifact_id)
);

create table if not exists artifact_promotion_events (
    id varchar(64) primary key,
    artifact_id varchar(128) not null,
    from_status varchar(32),
    to_status varchar(32) not null,
    owner varchar(32) not null,
    reason varchar(255),
    evidence_json longtext not null,
    created_at varchar(64) not null,
    foreign key (artifact_id) references artifact_registry(artifact_id)
);

alter table backtest_runs add column data_release_id varchar(96);
alter table reproducibility_certificates add column data_release_id varchar(96);
alter table qlib_research_imports add column data_release_id varchar(96);
alter table qlib_research_imports add column root_artifact_ids_json longtext;

create index if not exists idx_backtest_runs_data_release on backtest_runs(data_release_id);
create index if not exists idx_qlib_import_data_release on qlib_research_imports(data_release_id, created_at);
