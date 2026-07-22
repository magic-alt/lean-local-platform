-- description: Revoke legacy source certifications and index raw archive object references

update parquet_datasets
set environment = 'research',
    is_production = 0,
    is_certified = 0,
    certified_at = null,
    certified_by = null,
    qa_status = 'stale',
    qa_report_id = null;

create index if not exists idx_provider_raw_archives_object
    on provider_raw_archives(object_id, created_at);

update settings
set value_json = '"quantconnect/research@sha256:1548cafe8d696c1a30774413fc6f7c0d7f0205104f2f78110d9a84906ac65634"'
where key = 'researchImage'
  and value_json = '"quantconnect/research:latest"';
