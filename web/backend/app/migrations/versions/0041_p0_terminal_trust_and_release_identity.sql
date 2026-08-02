-- description: Fail closed on backtest trust and persist completed walk-forward certificates
-- compatibility: additive trust and certificate fields; historical run status and artifacts remain unchanged
-- rollback: stop trusted consumers, retain evidence, and remove additive fields only through a reviewed forward migration

alter table backtest_runs add column trust_status varchar(32) not null default 'unverified';
alter table backtest_runs add column trust_reason varchar(255);
alter table backtest_runs add column trust_evaluated_at varchar(64);

update backtest_runs
set trust_status='legacy_unverified',
    trust_reason='requires_final_gate_reconciliation'
where status='success';

create index idx_backtest_runs_terminal_trust
    on backtest_runs(status, trust_status, finished_at);

alter table walk_forward_runs add column certificate_json longtext;
alter table walk_forward_runs add column certificate_digest varchar(64);
alter table walk_forward_runs add column certified_at varchar(64);

create unique index idx_walk_forward_certificate_digest
    on walk_forward_runs(certificate_digest);
