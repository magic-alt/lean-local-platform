-- description: Persist frozen walk-forward selection, leakage, and OOS evidence
-- compatibility: additive, existing experiment batches remain readable and are not backfilled
-- rollback: drop the seven tables below in reverse dependency order after confirming no certified evidence references them

create table if not exists walk_forward_runs (
    id varchar(64) primary key,
    batch_id varchar(64) not null,
    status varchar(32) not null,
    dataset_version varchar(255) not null,
    universe_version varchar(255) not null,
    adjustment_contract varchar(255) not null,
    feature_pipeline_version varchar(255) not null,
    selection_metric varchar(64) not null,
    selection_rule varchar(255) not null,
    created_at varchar(64) not null,
    completed_at varchar(64),
    unique(batch_id)
);

create table if not exists walk_forward_windows (
    id varchar(64) primary key,
    walk_forward_run_id varchar(64) not null,
    batch_id varchar(64) not null,
    project_id varchar(255) not null,
    symbol varchar(64) not null,
    fold integer not null,
    train_start varchar(10) not null,
    train_end varchar(10) not null,
    validation_start varchar(10) not null,
    validation_end varchar(10) not null,
    oos_start varchar(10) not null,
    oos_end varchar(10) not null,
    universe_version varchar(255) not null,
    dataset_version varchar(255) not null,
    adjustment_contract varchar(255) not null,
    feature_pipeline_version varchar(255) not null,
    fold_fingerprint varchar(64) not null,
    oos_input_fingerprint varchar(64) not null,
    status varchar(32) not null,
    created_at varchar(64) not null,
    completed_at varchar(64),
    unique(batch_id, project_id, symbol, fold)
);

create table if not exists parameter_candidates (
    id varchar(64) primary key,
    window_id varchar(64) not null,
    candidate_key varchar(255) not null,
    parameters_json longtext not null,
    train_item_id varchar(64),
    validation_item_id varchar(64),
    validation_return double,
    validation_sharpe double,
    validation_max_drawdown double,
    validation_trade_count integer,
    validation_turnover double,
    constraint_violations integer not null default 0,
    selected integer not null default 0,
    not_selected_reason varchar(255),
    created_at varchar(64) not null,
    updated_at varchar(64) not null,
    unique(window_id, candidate_key)
);

create table if not exists parameter_selection_events (
    id varchar(64) primary key,
    window_id varchar(64) not null,
    selected_candidate_id varchar(64) not null,
    selection_metric varchar(64) not null,
    tie_break_rule varchar(255) not null,
    selected_parameters_json longtext not null,
    candidate_ranking_json longtext not null,
    selection_timestamp varchar(64) not null,
    selection_fingerprint varchar(64) not null,
    unique(window_id),
    unique(selection_fingerprint)
);

create table if not exists feature_pipeline_fits (
    id varchar(64) primary key,
    window_id varchar(64) not null,
    pipeline_version varchar(255) not null,
    fit_phase varchar(32) not null,
    fit_start varchar(10) not null,
    fit_end varchar(10) not null,
    fit_statistics_json longtext not null,
    fit_fingerprint varchar(64) not null,
    created_at varchar(64) not null,
    unique(window_id, pipeline_version, fit_phase),
    unique(fit_fingerprint)
);

create table if not exists leakage_check_results (
    id varchar(64) primary key,
    window_id varchar(64) not null,
    decision varchar(16) not null,
    check_version varchar(64) not null,
    result_json longtext not null,
    checked_at varchar(64) not null,
    unique(window_id, check_version)
);

create table if not exists oos_evaluations (
    id varchar(64) primary key,
    window_id varchar(64) not null,
    selected_candidate_id varchar(64) not null,
    oos_item_id varchar(64) not null,
    oos_run_id varchar(128),
    input_fingerprint varchar(64) not null,
    result_digest varchar(64),
    metrics_json longtext,
    status varchar(32) not null,
    created_at varchar(64) not null,
    completed_at varchar(64),
    unique(window_id),
    unique(oos_item_id)
);

create index idx_walk_forward_runs_status on walk_forward_runs(status, created_at);
create index idx_walk_forward_windows_run on walk_forward_windows(walk_forward_run_id, fold);
create index idx_walk_forward_windows_batch on walk_forward_windows(batch_id, project_id, symbol, fold);
create index idx_parameter_candidates_window on parameter_candidates(window_id, selected, candidate_key);
create index idx_parameter_selection_window on parameter_selection_events(window_id, selection_timestamp);
create index idx_feature_pipeline_fits_window on feature_pipeline_fits(window_id, fit_phase);
create index idx_leakage_checks_window on leakage_check_results(window_id, decision);
create index idx_oos_evaluations_window on oos_evaluations(window_id, status);
