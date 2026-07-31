-- description: Add PIT cross-sectional machine-learning research metadata
-- compatibility: additive tables and financial statement audit columns
-- rollback: stop ML workers, archive registered models and feature manifests, then remove the added tables and columns with a reviewed forward migration

alter table financial_statements add column report_type varchar(32);
alter table financial_statements add column update_flag varchar(32);
alter table financial_statements add column payload_hash varchar(64);
alter table data_sync_runs add column request_scope_json longtext;

create table if not exists security_name_history (
    id varchar(64) primary key,
    symbol varchar(32) not null,
    name varchar(255) not null,
    start_date varchar(16) not null,
    end_date varchar(16),
    is_st integer not null default 0,
    source varchar(32) not null,
    payload_hash varchar(64) not null,
    created_at varchar(64) not null,
    unique(symbol, start_date, name)
);
create index if not exists idx_security_name_history_pit
    on security_name_history(symbol, start_date, end_date);

create table if not exists industry_membership (
    id varchar(64) primary key,
    symbol varchar(32) not null,
    industry_code varchar(32) not null,
    industry_name varchar(255),
    taxonomy varchar(32) not null,
    level_no integer not null,
    in_date varchar(16) not null,
    out_date varchar(16),
    source varchar(32) not null,
    payload_hash varchar(64) not null,
    created_at varchar(64) not null,
    unique(symbol, industry_code, taxonomy, in_date)
);
create index if not exists idx_industry_membership_pit
    on industry_membership(symbol, taxonomy, level_no, in_date, out_date);

create table if not exists ml_feature_sets (
    id varchar(64) primary key,
    fingerprint varchar(64) not null unique,
    universe_code varchar(32) not null,
    start_date varchar(16) not null,
    end_date varchar(16) not null,
    feature_version varchar(64) not null,
    status varchar(32) not null,
    row_count integer not null default 0,
    symbol_count integer not null default 0,
    feature_count integer not null default 0,
    manifest_json longtext not null,
    coverage_json longtext not null,
    created_at varchar(64) not null,
    completed_at varchar(64)
);
create index if not exists idx_ml_feature_sets_created on ml_feature_sets(created_at);

create table if not exists ml_feature_files (
    id varchar(64) primary key,
    feature_set_id varchar(64) not null,
    relative_path varchar(512) not null,
    sha256 varchar(64) not null,
    row_count integer not null,
    min_date varchar(16),
    max_date varchar(16),
    size_bytes integer not null,
    created_at varchar(64) not null,
    unique(feature_set_id, relative_path)
);
create index if not exists idx_ml_feature_files_set on ml_feature_files(feature_set_id);

create table if not exists ml_training_runs (
    id varchar(64) primary key,
    research_run_id varchar(64) not null unique,
    feature_set_id varchar(64),
    status varchar(32) not null,
    stage varchar(64) not null,
    progress real not null default 0,
    mlflow_run_id varchar(128),
    mlflow_experiment varchar(255),
    registered_model_name varchar(255),
    registered_model_version varchar(64),
    selected_trial_id varchar(64),
    metrics_json longtext not null,
    quality_json longtext not null,
    fold_plan_json longtext not null,
    artifacts_json longtext not null,
    error longtext,
    created_at varchar(64) not null,
    started_at varchar(64),
    finished_at varchar(64),
    updated_at varchar(64) not null
);
create index if not exists idx_ml_training_runs_status on ml_training_runs(status, updated_at);

create table if not exists ml_training_trials (
    id varchar(64) primary key,
    training_run_id varchar(64) not null,
    fold_index integer not null,
    candidate_index integer not null,
    status varchar(32) not null,
    parameters_json longtext not null,
    metrics_json longtext not null,
    best_iteration integer,
    mlflow_run_id varchar(128),
    selected integer not null default 0,
    created_at varchar(64) not null,
    finished_at varchar(64),
    unique(training_run_id, fold_index, candidate_index)
);
create index if not exists idx_ml_training_trials_run
    on ml_training_trials(training_run_id, fold_index, candidate_index);

create table if not exists ml_prediction_files (
    id varchar(64) primary key,
    training_run_id varchar(64) not null,
    split_key varchar(64) not null,
    relative_path varchar(1024) not null,
    sha256 varchar(64) not null,
    row_count integer not null,
    metrics_json longtext not null,
    created_at varchar(64) not null,
    unique(training_run_id, split_key)
);
create index if not exists idx_ml_prediction_files_run on ml_prediction_files(training_run_id);
