-- description: Add editable A-share technology watchlist and immutable report snapshots

create table if not exists ashare_tech_watchlist_items (
    code text primary key,
    name text not null,
    group_key text not null,
    enabled integer not null default 1,
    rule_tags_json text not null,
    source text not null default 'tushare:stock_basic',
    created_at text not null,
    updated_at text not null
);

create index if not exists idx_ashare_tech_watchlist_group
    on ashare_tech_watchlist_items(group_key, enabled, code);

alter table ashare_tech_reports add column pool_snapshot_json text;
alter table ashare_tech_reports add column pool_fingerprint text;
