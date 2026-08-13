-- description: Reconcile remaining metadata columns after legacy schema drift
-- rollback: retain additive control metadata and remove only through a reviewed forward migration

alter table instrument_identifiers add column provider varchar(96);
alter table instrument_identifiers add column identifier_type varchar(96);
alter table instrument_identifiers add column identifier_value varchar(96);
alter table instrument_identifiers add column exchange varchar(32);
alter table instrument_identifiers add column market varchar(32);
alter table instrument_identifiers add column valid_from varchar(32);
alter table instrument_identifiers add column valid_to varchar(32);
alter table instrument_identifiers add column is_primary integer not null default 0;
alter table instrument_identifiers add column batch_id varchar(64);
alter table instrument_identifiers add column updated_at varchar(32);

create unique index if not exists idx_instrument_identifiers_provider_value
    on instrument_identifiers(provider, identifier_type, identifier_value, valid_from);
create index if not exists idx_instrument_identifiers_instrument
    on instrument_identifiers(instrument_id, provider, identifier_type);

alter table financial_statements add column report_type varchar(32);
alter table financial_statements add column update_flag varchar(32);
alter table financial_statements add column payload_hash varchar(64);
