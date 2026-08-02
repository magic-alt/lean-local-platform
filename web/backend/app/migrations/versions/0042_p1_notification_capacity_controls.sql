-- description: Bound notification retries and persist dead-letter terminal evidence
-- compatibility: additive terminal timestamps; existing delivery and outbox rows remain readable
-- rollback: stop notification workers, preserve delivery evidence, and remove additive columns only through a reviewed forward migration

alter table alert_deliveries add column terminal_at varchar(64);
alter table paper_notification_outbox add column terminal_at varchar(64);

create index idx_alert_deliveries_retry
    on alert_deliveries(status, next_retry_at, attempt_count);

create index idx_paper_outbox_terminal
    on paper_notification_outbox(status, next_attempt_at, attempt);
