-- description: Add deterministic A-share technology daily reports

create table if not exists ashare_tech_reports (
    id text primary key,
    task_id text,
    requested_date text not null,
    analysis_date text,
    market_status text not null,
    status text not null,
    attempt_count integer not null default 0,
    data_cutoff_at text,
    primary_source text not null default 'tushare',
    sector_source text,
    data_completeness_json text not null,
    source_conflicts_json text not null,
    source_manifest_json text not null,
    context_json text,
    raw_response_json text,
    report_json text,
    model text,
    prompt_version text not null,
    previous_report_id text,
    input_fingerprint text,
    error text,
    created_at text not null,
    started_at text,
    finished_at text,
    updated_at text not null,
    unique(requested_date)
);

create index if not exists idx_ashare_tech_reports_created
    on ashare_tech_reports(created_at desc);
create index if not exists idx_ashare_tech_reports_analysis_date
    on ashare_tech_reports(analysis_date desc);
create index if not exists idx_ashare_tech_reports_status
    on ashare_tech_reports(status, updated_at desc);
