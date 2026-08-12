-- description: Replace fragile project-history cascades with non-cascading project archival
-- compatibility: additive nullable marker; existing projects remain visible
-- rollback: restore archived source directories if needed, clear archived_at, then remove the column through a reviewed forward migration

alter table projects add column archived_at varchar(64);

create index idx_projects_active_updated
    on projects(archived_at, updated_at);
