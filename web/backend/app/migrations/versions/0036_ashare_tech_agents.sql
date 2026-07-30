-- description: Add auditable multi-agent A-share technology forecasts and evaluations
-- compatibility: additive tables and columns; legacy deterministic reports remain readable

alter table ashare_tech_reports add column active_agent_run_id text;
alter table ashare_tech_reports add column analysis_mode text;
alter table ashare_tech_reports add column llm_status text;
alter table ashare_tech_reports add column agent_summary_json text;

create table if not exists ashare_tech_agent_runs (
    id text primary key,
    report_id text not null,
    task_id text,
    requested_date text not null,
    analysis_date text not null,
    analysis_mode text not null,
    status text not null,
    provider text,
    requested_model text,
    prompt_version text not null,
    input_fingerprint text not null,
    stage_summary_json text not null,
    usage_json text not null,
    fallback_reason text,
    created_at text not null,
    started_at text,
    finished_at text,
    updated_at text not null
);

create index if not exists idx_ashare_tech_agent_runs_report
    on ashare_tech_agent_runs(report_id, created_at desc);
create index if not exists idx_ashare_tech_agent_runs_status
    on ashare_tech_agent_runs(status, updated_at desc);

create table if not exists ashare_tech_agent_stages (
    id text primary key,
    run_id text not null,
    stage_key text not null,
    sequence_no integer not null,
    status text not null,
    provider text,
    model text,
    prompt_version text not null,
    input_fingerprint text not null,
    input_fact_ids_json text not null,
    output_json text,
    usage_json text not null,
    latency_ms integer,
    attempt_count integer not null default 0,
    error_category text,
    error text,
    started_at text,
    finished_at text,
    updated_at text not null,
    unique(run_id, stage_key)
);

create index if not exists idx_ashare_tech_agent_stages_run
    on ashare_tech_agent_stages(run_id, sequence_no);

create table if not exists ashare_tech_predictions (
    id text primary key,
    run_id text not null,
    report_id text not null,
    symbol text not null,
    horizon_days integer not null,
    predicted_direction text not null,
    probabilities_json text not null,
    confidence real not null,
    trend_score real not null,
    rule_conclusion text,
    selection_rank integer,
    selection_tier text not null,
    rationale text not null,
    evidence_ids_json text not null,
    neutral_band_pct real not null,
    entry_date text not null,
    entry_close real not null,
    target_date text,
    benchmark_code text not null,
    model text not null,
    prompt_version text not null,
    created_at text not null,
    unique(run_id, symbol, horizon_days)
);

create index if not exists idx_ashare_tech_predictions_pending
    on ashare_tech_predictions(target_date, horizon_days);
create index if not exists idx_ashare_tech_predictions_report
    on ashare_tech_predictions(report_id, symbol);

create table if not exists ashare_tech_prediction_evaluations (
    id text primary key,
    prediction_id text not null,
    run_id text not null,
    report_id text not null,
    symbol text not null,
    horizon_days integer not null,
    status text not null,
    evaluated_date text,
    entry_close real not null,
    exit_close real,
    benchmark_code text not null,
    benchmark_entry_close real,
    benchmark_exit_close real,
    return_pct real,
    benchmark_return_pct real,
    excess_return_pct real,
    realized_direction text,
    direction_hit integer,
    brier_score real,
    source_manifest_json text not null,
    missing_reason text,
    created_at text not null,
    updated_at text not null,
    unique(prediction_id)
);

create index if not exists idx_ashare_tech_prediction_eval_summary
    on ashare_tech_prediction_evaluations(status, horizon_days, evaluated_date);
