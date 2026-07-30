-- description: Merge structured Insights into A-share technology reports and retire the generic workflow
-- compatibility: destructive removal of generic Insight history; A-share reports remain readable
-- rollback: restore requires a verified pre-migration database backup

alter table ashare_tech_reports add column requested_provider text;
alter table ashare_tech_reports add column requested_model text;
alter table ashare_tech_reports add column prompt_version_id text;

alter table ashare_tech_agent_runs add column prompt_version_id text;
alter table ashare_tech_agent_runs add column prompt_snapshot_json text;
alter table ashare_tech_agent_runs add column prompt_fingerprint text;

alter table ashare_tech_agent_stages add column prompt_version_id text;
alter table ashare_tech_agent_stages add column system_prompt text;

alter table ashare_tech_predictions add column provider text;

create table if not exists ashare_tech_prompt_templates (
    id text primary key,
    template_key text not null,
    name text not null,
    description text,
    version_no integer not null,
    stage_prompts_json text not null,
    prompt_fingerprint text not null,
    created_at text not null,
    unique(template_key, version_no)
);

create index if not exists idx_ashare_tech_prompt_templates_key
    on ashare_tech_prompt_templates(template_key, version_no desc);

create table if not exists ashare_tech_agent_profiles (
    profile_key text primary key,
    provider text not null,
    model text not null,
    prompt_version_id text not null,
    updated_at text not null
);

create table if not exists ashare_tech_candidate_signals (
    id text primary key,
    run_id text not null,
    report_id text not null,
    symbol text not null,
    provider text,
    model text,
    prompt_version text not null,
    source_type text not null,
    raw_signal_json text not null,
    final_signal_json text not null,
    guardrail_json text not null,
    status text not null,
    created_at text not null,
    unique(run_id, symbol)
);

create index if not exists idx_ashare_tech_candidate_signals_report
    on ashare_tech_candidate_signals(report_id, symbol);

delete from tasks where kind='insight';
delete from decision_signals;
delete from insight_reports;
drop table if exists decision_signals;
drop table if exists insight_reports;
