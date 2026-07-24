-- description: Add immutable Paper v2 intents, transitions, fills, ledger, and recovery checkpoints

alter table paper_sessions add column pipeline_version integer not null default 1;

create table if not exists paper_order_intents (
    id varchar(64) primary key,
    session_id varchar(64) not null,
    paper_run_id varchar(64) not null,
    backtest_run_id varchar(128) not null,
    event_key varchar(128) not null,
    idempotency_key varchar(255) not null,
    correlation_id varchar(128) not null,
    version integer not null default 1,
    attempt integer not null default 1,
    trade_date varchar(32) not null,
    symbol varchar(64) not null,
    side varchar(16) not null,
    quantity real not null,
    requested_price real,
    raw_intent_json longtext not null,
    created_at varchar(64) not null,
    unique(session_id, idempotency_key),
    unique(session_id, event_key)
);

create table if not exists paper_order_transitions (
    id varchar(64) primary key,
    intent_id varchar(64) not null,
    sequence integer not null,
    from_state varchar(32),
    to_state varchar(32) not null,
    event_type varchar(64) not null,
    idempotency_key varchar(255) not null,
    correlation_id varchar(128) not null,
    version integer not null default 1,
    attempt integer not null default 1,
    payload_json longtext not null,
    created_at varchar(64) not null,
    unique(intent_id, sequence),
    unique(intent_id, idempotency_key)
);

create table if not exists paper_order_fills (
    id varchar(64) primary key,
    intent_id varchar(64) not null,
    external_fill_key varchar(255) not null,
    trade_date varchar(32) not null,
    quantity real not null,
    price real not null,
    fee real not null default 0,
    payload_json longtext not null,
    created_at varchar(64) not null,
    unique(intent_id, external_fill_key)
);

create table if not exists paper_ledger_entries (
    id varchar(64) primary key,
    session_id varchar(64) not null,
    intent_id varchar(64) not null,
    fill_id varchar(64),
    entry_type varchar(32) not null,
    asset varchar(32) not null,
    symbol varchar(64),
    quantity real not null default 0,
    amount real not null default 0,
    currency varchar(16) not null,
    idempotency_key varchar(255) not null,
    created_at varchar(64) not null,
    unique(session_id, idempotency_key)
);

create table if not exists paper_run_checkpoints (
    id varchar(64) primary key,
    paper_run_id varchar(64) not null,
    phase varchar(64) not null,
    status varchar(32) not null,
    digest varchar(128),
    payload_json longtext not null,
    created_at varchar(64) not null,
    completed_at varchar(64),
    unique(paper_run_id, phase)
);

create index idx_paper_intents_session_date
    on paper_order_intents(session_id, trade_date);
create index idx_paper_transitions_intent_sequence
    on paper_order_transitions(intent_id, sequence);
create index idx_paper_fills_intent
    on paper_order_fills(intent_id);
create index idx_paper_ledger_session_created
    on paper_ledger_entries(session_id, created_at);
create index idx_paper_checkpoints_run
    on paper_run_checkpoints(paper_run_id, phase);
