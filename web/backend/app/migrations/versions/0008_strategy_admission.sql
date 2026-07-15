-- description: Add trusted strategy admission baselines and immutable stage events

create table if not exists strategy_admissions (
    id text primary key,
    strategy_id text not null,
    strategy_version_id text,
    parameters_sha256 text not null,
    profile_name text not null,
    profile_version text not null,
    sample_set text not null,
    current_stage text not null,
    baseline_snapshot_json text not null,
    evaluation_json text not null,
    created_at text not null,
    updated_at text not null,
    unique(strategy_id, parameters_sha256, profile_name, profile_version)
);

create table if not exists strategy_admission_events (
    id text primary key,
    admission_id text not null,
    stage text not null,
    source_id text,
    payload_json text not null,
    created_at text not null
);

create index if not exists idx_strategy_admissions_lookup
    on strategy_admissions(strategy_id, parameters_sha256, updated_at);

create index if not exists idx_strategy_admission_events
    on strategy_admission_events(admission_id, created_at);
