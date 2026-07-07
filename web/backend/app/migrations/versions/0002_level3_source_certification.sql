-- description: Add Level 3 source certification and instrument identifier metadata

alter table parquet_datasets add column dataset_version varchar(96);
alter table parquet_datasets add column environment varchar(32) not null default 'research';
alter table parquet_datasets add column is_production integer not null default 0;
alter table parquet_datasets add column is_certified integer not null default 0;
alter table parquet_datasets add column certified_at varchar(32);
alter table parquet_datasets add column certified_by varchar(96);
alter table parquet_datasets add column coverage_start varchar(32);
alter table parquet_datasets add column coverage_end varchar(32);
alter table parquet_datasets add column qa_status varchar(32);
alter table parquet_datasets add column qa_report_id varchar(64);

alter table dataset_versions add column dataset_version varchar(96);
alter table dataset_versions add column environment varchar(32) not null default 'research';
alter table dataset_versions add column is_production integer not null default 0;
alter table dataset_versions add column is_certified integer not null default 0;
alter table dataset_versions add column certified_at varchar(32);
alter table dataset_versions add column certified_by varchar(96);
alter table dataset_versions add column coverage_start varchar(32);
alter table dataset_versions add column coverage_end varchar(32);
alter table dataset_versions add column qa_status varchar(32);
alter table dataset_versions add column qa_report_id varchar(64);

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

update parquet_datasets
set dataset_version = coalesce(dataset_version, substr(dataset_key, 1, 96)),
    environment = case when source = 'akshare' then 'production' else 'research' end,
    is_production = case when source = 'akshare' then 1 else 0 end,
    is_certified = case when source = 'akshare' then 1 else 0 end,
    certified_at = case when source = 'akshare' then coalesce(certified_at, updated_at, created_at) else certified_at end,
    certified_by = case when source = 'akshare' then coalesce(certified_by, 'system') else certified_by end,
    coverage_start = coalesce(coverage_start, start_date),
    coverage_end = coalesce(coverage_end, end_date),
    qa_status = coalesce(qa_status, case when source = 'akshare' then 'ok' else 'research' end);

update dataset_versions
set dataset_version = coalesce(dataset_version, substr(dataset_key, 1, 96)),
    environment = case when coalesce(json_extract(metadata_json, '$.source'), '') = 'akshare' then 'production' else 'research' end,
    is_production = case when coalesce(json_extract(metadata_json, '$.source'), '') = 'akshare' then 1 else 0 end,
    is_certified = case when coalesce(json_extract(metadata_json, '$.source'), '') = 'akshare' then 1 else 0 end,
    certified_at = case when coalesce(json_extract(metadata_json, '$.source'), '') = 'akshare' then coalesce(certified_at, created_at) else certified_at end,
    certified_by = case when coalesce(json_extract(metadata_json, '$.source'), '') = 'akshare' then coalesce(certified_by, 'system') else certified_by end,
    coverage_start = coalesce(coverage_start, start_date),
    coverage_end = coalesce(coverage_end, end_date),
    qa_status = coalesce(qa_status, case when coalesce(json_extract(metadata_json, '$.source'), '') = 'akshare' then 'ok' else 'research' end);

create index if not exists idx_parquet_datasets_certified_source
    on parquet_datasets(is_production, is_certified, source, asset_class, market, venue);

create index if not exists idx_dataset_versions_certified_source
    on dataset_versions(is_production, is_certified, asset_class, market, venue);

create unique index if not exists idx_instrument_identifiers_provider_value
    on instrument_identifiers(provider, identifier_type, identifier_value, valid_from);

create index if not exists idx_instrument_identifiers_instrument
    on instrument_identifiers(instrument_id, provider, identifier_type);
