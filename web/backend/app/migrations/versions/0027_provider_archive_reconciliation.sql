-- description: Record auditable resolution of quarantined provider archive references

alter table provider_raw_archive_issues add column status text not null default 'open';
alter table provider_raw_archive_issues add column resolution_code text;
alter table provider_raw_archive_issues add column resolution_run_id text;
alter table provider_raw_archive_issues add column resolution_evidence_json text;
alter table provider_raw_archive_issues add column resolved_at text;

create index if not exists idx_provider_raw_archive_issues_status
    on provider_raw_archive_issues(status,dataset_key,detected_at);
