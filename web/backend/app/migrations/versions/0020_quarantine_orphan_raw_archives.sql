-- description: Quarantine historical raw archive references whose stored objects are missing

create table if not exists provider_raw_archive_issues (
    archive_id text primary key,
    provider text not null,
    dataset_key text not null,
    run_id text not null,
    object_id text not null,
    row_count integer not null,
    payload_sha256 text not null,
    archive_sha256 text not null,
    uncompressed_size integer not null,
    compressed_size integer not null,
    compression text not null,
    archive_created_at text not null,
    issue_code text not null,
    detected_at text not null
);

insert into provider_raw_archive_issues
    (archive_id,provider,dataset_key,run_id,object_id,row_count,payload_sha256,
     archive_sha256,uncompressed_size,compressed_size,compression,archive_created_at,
     issue_code,detected_at)
select a.id,a.provider,a.dataset_key,a.run_id,a.object_id,a.row_count,a.payload_sha256,
       a.archive_sha256,a.uncompressed_size,a.compressed_size,a.compression,a.created_at,
       'stored_object_missing',current_timestamp
from provider_raw_archives a
left join stored_objects o on o.id=a.object_id
where o.id is null
  and not exists (
      select 1 from provider_raw_archive_issues i where i.archive_id=a.id
  );

delete from provider_raw_archives
where not exists (
    select 1 from stored_objects o where o.id=provider_raw_archives.object_id
);

create index if not exists idx_provider_raw_archive_issues_run
    on provider_raw_archive_issues(run_id,dataset_key,detected_at);
