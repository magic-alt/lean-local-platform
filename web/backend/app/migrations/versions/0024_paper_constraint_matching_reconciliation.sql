-- description: Add versioned Paper constraint, deterministic matching, and reconciliation evidence
-- compatibility: additive, legacy Paper sessions and v2 records remain readable
-- rollback: drop new evidence tables and indexes, then remove nullable columns only after archiving their records

alter table paper_order_intents add column lean_run_id varchar(128);
alter table paper_order_intents add column lean_order_id varchar(128);
alter table paper_order_intents add column project_snapshot_id varchar(128);
alter table paper_order_intents add column project_snapshot_hash varchar(128);
alter table paper_order_intents add column strategy_fingerprint varchar(128);
alter table paper_order_intents add column order_type varchar(32);
alter table paper_order_intents add column limit_price real;
alter table paper_order_intents add column stop_price real;
alter table paper_order_intents add column signal_time varchar(64);
alter table paper_order_intents add column requested_execution_time varchar(64);
alter table paper_order_intents add column dataset_version varchar(255);
alter table paper_order_intents add column universe_version varchar(255);
alter table paper_order_intents add column constraint_version varchar(64);

create table if not exists paper_constraint_decisions (
    id varchar(64) primary key,
    intent_id varchar(64) not null,
    decision varchar(16) not null,
    constraint_version varchar(64) not null,
    rule_code varchar(64),
    rule_inputs_json longtext not null,
    portfolio_snapshot_json longtext not null,
    reference_data_version varchar(255) not null,
    rules_json longtext not null,
    decision_digest varchar(64) not null,
    decision_timestamp varchar(64) not null,
    unique(intent_id),
    unique(decision_digest)
);

alter table paper_order_fills add column tax real not null default 0;
alter table paper_order_fills add column slippage real not null default 0;
alter table paper_order_fills add column fee_model_version varchar(64);
alter table paper_order_fills add column matching_contract varchar(64);
alter table paper_order_fills add column fill_fingerprint varchar(64);

create unique index idx_paper_fills_fingerprint
    on paper_order_fills(fill_fingerprint);

alter table paper_ledger_entries add column event_id varchar(64);
alter table paper_ledger_entries add column trade_date varchar(32);
alter table paper_ledger_entries add column debit_account varchar(128);
alter table paper_ledger_entries add column credit_account varchar(128);
alter table paper_ledger_entries add column correction_entry_id varchar(64);
alter table paper_ledger_entries add column reversal_entry_id varchar(64);

create table if not exists paper_reconciliation_records (
    id varchar(64) primary key,
    session_id varchar(64) not null,
    paper_run_id varchar(64) not null,
    trade_date varchar(32) not null,
    status varchar(32) not null,
    opening_cash real not null,
    ledger_cash_movement real not null,
    closing_cash real not null,
    cash_drift real not null,
    position_drift real not null,
    order_fill_ok integer not null,
    fill_ledger_ok integer not null,
    ledger_cash_ok integer not null,
    ledger_positions_ok integer not null,
    snapshot_ok integer not null,
    daily_report_ok integer not null,
    invariants_json longtext not null,
    result_digest varchar(64) not null,
    created_at varchar(64) not null,
    unique(session_id, trade_date),
    unique(paper_run_id),
    unique(result_digest)
);

create index idx_paper_constraint_intent
    on paper_constraint_decisions(intent_id, decision);
create index idx_paper_ledger_trade_date
    on paper_ledger_entries(session_id, trade_date, entry_type);
create index idx_paper_reconciliation_session_date
    on paper_reconciliation_records(session_id, trade_date, status);
