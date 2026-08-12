-- description: Add contract-generated typed source tables for TuShare stock, index, futures and options data
-- rollback: stop TuShare ingestion, retain raw archives, and remove generated source tables through a reviewed forward migration
-- generated from contract version 2026-08-12.1; do not edit by hand

create table if not exists `src_tushare_stock_basic` (
    `_observation_id` varchar(64) primary key,
    `_batch_id` varchar(64) not null,
    `_natural_key_hash` varchar(64) not null,
    `_revision_no` integer not null,
    `_is_current` integer not null default 1,
    `_current_natural_key_hash` varchar(64) generated always as (case when `_is_current` = 1 then `_natural_key_hash` else null end) stored,
    `_published_at` datetime(6),
    `_source_updated_at` datetime(6),
    `_observed_at` datetime(6) not null,
    `_valid_from` datetime(6),
    `_valid_to` datetime(6),
    `_payload_hash` varchar(64) not null,
    `ts_code` longtext,
    `symbol` longtext,
    `name` longtext,
    `area` longtext,
    `industry` longtext,
    `fullname` longtext,
    `enname` longtext,
    `cnspell` longtext,
    `market` longtext,
    `exchange` longtext,
    `curr_type` longtext,
    `list_status` longtext,
    `list_date` date,
    `delist_date` date,
    `is_hs` longtext,
    `act_name` longtext,
    `act_ent_type` longtext,
    unique(`_natural_key_hash`,`_revision_no`),
    unique(`_current_natural_key_hash`),
    check (`_revision_no` > 0),
    check (`_is_current` in (0,1)),
    check (`_valid_to` is null or `_valid_from` is null or `_valid_to` >= `_valid_from`)
);

create index if not exists `idx_src_tushare_stock_basic_current`
    on `src_tushare_stock_basic`(`_natural_key_hash`,`_is_current`);
create index if not exists `idx_src_tushare_stock_basic_observed`
    on `src_tushare_stock_basic`(`_observed_at`);

create table if not exists `src_tushare_stk_premarket` (
    `_observation_id` varchar(64) primary key,
    `_batch_id` varchar(64) not null,
    `_natural_key_hash` varchar(64) not null,
    `_revision_no` integer not null,
    `_is_current` integer not null default 1,
    `_current_natural_key_hash` varchar(64) generated always as (case when `_is_current` = 1 then `_natural_key_hash` else null end) stored,
    `_published_at` datetime(6),
    `_source_updated_at` datetime(6),
    `_observed_at` datetime(6) not null,
    `_valid_from` datetime(6),
    `_valid_to` datetime(6),
    `_payload_hash` varchar(64) not null,
    `trade_date` date,
    `ts_code` longtext,
    `total_share` decimal(38,8),
    `float_share` decimal(38,8),
    `pre_close` decimal(38,8),
    `up_limit` decimal(38,8),
    `down_limit` decimal(38,8),
    unique(`_natural_key_hash`,`_revision_no`),
    unique(`_current_natural_key_hash`),
    check (`_revision_no` > 0),
    check (`_is_current` in (0,1)),
    check (`_valid_to` is null or `_valid_from` is null or `_valid_to` >= `_valid_from`)
);

create index if not exists `idx_src_tushare_stk_premarket_current`
    on `src_tushare_stk_premarket`(`_natural_key_hash`,`_is_current`);
create index if not exists `idx_src_tushare_stk_premarket_observed`
    on `src_tushare_stk_premarket`(`_observed_at`);

create table if not exists `src_tushare_trade_cal` (
    `_observation_id` varchar(64) primary key,
    `_batch_id` varchar(64) not null,
    `_natural_key_hash` varchar(64) not null,
    `_revision_no` integer not null,
    `_is_current` integer not null default 1,
    `_current_natural_key_hash` varchar(64) generated always as (case when `_is_current` = 1 then `_natural_key_hash` else null end) stored,
    `_published_at` datetime(6),
    `_source_updated_at` datetime(6),
    `_observed_at` datetime(6) not null,
    `_valid_from` datetime(6),
    `_valid_to` datetime(6),
    `_payload_hash` varchar(64) not null,
    `exchange` longtext,
    `cal_date` date,
    `is_open` longtext,
    `pretrade_date` date,
    unique(`_natural_key_hash`,`_revision_no`),
    unique(`_current_natural_key_hash`),
    check (`_revision_no` > 0),
    check (`_is_current` in (0,1)),
    check (`_valid_to` is null or `_valid_from` is null or `_valid_to` >= `_valid_from`)
);

create index if not exists `idx_src_tushare_trade_cal_current`
    on `src_tushare_trade_cal`(`_natural_key_hash`,`_is_current`);
create index if not exists `idx_src_tushare_trade_cal_observed`
    on `src_tushare_trade_cal`(`_observed_at`);

create table if not exists `src_tushare_stock_st` (
    `_observation_id` varchar(64) primary key,
    `_batch_id` varchar(64) not null,
    `_natural_key_hash` varchar(64) not null,
    `_revision_no` integer not null,
    `_is_current` integer not null default 1,
    `_current_natural_key_hash` varchar(64) generated always as (case when `_is_current` = 1 then `_natural_key_hash` else null end) stored,
    `_published_at` datetime(6),
    `_source_updated_at` datetime(6),
    `_observed_at` datetime(6) not null,
    `_valid_from` datetime(6),
    `_valid_to` datetime(6),
    `_payload_hash` varchar(64) not null,
    `ts_code` longtext,
    `name` longtext,
    `trade_date` date,
    `type` longtext,
    `type_name` longtext,
    unique(`_natural_key_hash`,`_revision_no`),
    unique(`_current_natural_key_hash`),
    check (`_revision_no` > 0),
    check (`_is_current` in (0,1)),
    check (`_valid_to` is null or `_valid_from` is null or `_valid_to` >= `_valid_from`)
);

create index if not exists `idx_src_tushare_stock_st_current`
    on `src_tushare_stock_st`(`_natural_key_hash`,`_is_current`);
create index if not exists `idx_src_tushare_stock_st_observed`
    on `src_tushare_stock_st`(`_observed_at`);

create table if not exists `src_tushare_st` (
    `_observation_id` varchar(64) primary key,
    `_batch_id` varchar(64) not null,
    `_natural_key_hash` varchar(64) not null,
    `_revision_no` integer not null,
    `_is_current` integer not null default 1,
    `_current_natural_key_hash` varchar(64) generated always as (case when `_is_current` = 1 then `_natural_key_hash` else null end) stored,
    `_published_at` datetime(6),
    `_source_updated_at` datetime(6),
    `_observed_at` datetime(6) not null,
    `_valid_from` datetime(6),
    `_valid_to` datetime(6),
    `_payload_hash` varchar(64) not null,
    `ts_code` longtext,
    `name` longtext,
    `pub_date` date,
    `imp_date` date,
    `st_type` longtext,
    `st_reason` longtext,
    `st_explain` longtext,
    unique(`_natural_key_hash`,`_revision_no`),
    unique(`_current_natural_key_hash`),
    check (`_revision_no` > 0),
    check (`_is_current` in (0,1)),
    check (`_valid_to` is null or `_valid_from` is null or `_valid_to` >= `_valid_from`)
);

create index if not exists `idx_src_tushare_st_current`
    on `src_tushare_st`(`_natural_key_hash`,`_is_current`);
create index if not exists `idx_src_tushare_st_observed`
    on `src_tushare_st`(`_observed_at`);

create table if not exists `src_tushare_stock_hsgt` (
    `_observation_id` varchar(64) primary key,
    `_batch_id` varchar(64) not null,
    `_natural_key_hash` varchar(64) not null,
    `_revision_no` integer not null,
    `_is_current` integer not null default 1,
    `_current_natural_key_hash` varchar(64) generated always as (case when `_is_current` = 1 then `_natural_key_hash` else null end) stored,
    `_published_at` datetime(6),
    `_source_updated_at` datetime(6),
    `_observed_at` datetime(6) not null,
    `_valid_from` datetime(6),
    `_valid_to` datetime(6),
    `_payload_hash` varchar(64) not null,
    `ts_code` longtext,
    `trade_date` date,
    `type` longtext,
    `name` longtext,
    `type_name` longtext,
    unique(`_natural_key_hash`,`_revision_no`),
    unique(`_current_natural_key_hash`),
    check (`_revision_no` > 0),
    check (`_is_current` in (0,1)),
    check (`_valid_to` is null or `_valid_from` is null or `_valid_to` >= `_valid_from`)
);

create index if not exists `idx_src_tushare_stock_hsgt_current`
    on `src_tushare_stock_hsgt`(`_natural_key_hash`,`_is_current`);
create index if not exists `idx_src_tushare_stock_hsgt_observed`
    on `src_tushare_stock_hsgt`(`_observed_at`);

create table if not exists `src_tushare_namechange` (
    `_observation_id` varchar(64) primary key,
    `_batch_id` varchar(64) not null,
    `_natural_key_hash` varchar(64) not null,
    `_revision_no` integer not null,
    `_is_current` integer not null default 1,
    `_current_natural_key_hash` varchar(64) generated always as (case when `_is_current` = 1 then `_natural_key_hash` else null end) stored,
    `_published_at` datetime(6),
    `_source_updated_at` datetime(6),
    `_observed_at` datetime(6) not null,
    `_valid_from` datetime(6),
    `_valid_to` datetime(6),
    `_payload_hash` varchar(64) not null,
    `ts_code` longtext,
    `name` longtext,
    `start_date` date,
    `end_date` date,
    `ann_date` date,
    `change_reason` longtext,
    unique(`_natural_key_hash`,`_revision_no`),
    unique(`_current_natural_key_hash`),
    check (`_revision_no` > 0),
    check (`_is_current` in (0,1)),
    check (`_valid_to` is null or `_valid_from` is null or `_valid_to` >= `_valid_from`)
);

create index if not exists `idx_src_tushare_namechange_current`
    on `src_tushare_namechange`(`_natural_key_hash`,`_is_current`);
create index if not exists `idx_src_tushare_namechange_observed`
    on `src_tushare_namechange`(`_observed_at`);

create table if not exists `src_tushare_stock_company` (
    `_observation_id` varchar(64) primary key,
    `_batch_id` varchar(64) not null,
    `_natural_key_hash` varchar(64) not null,
    `_revision_no` integer not null,
    `_is_current` integer not null default 1,
    `_current_natural_key_hash` varchar(64) generated always as (case when `_is_current` = 1 then `_natural_key_hash` else null end) stored,
    `_published_at` datetime(6),
    `_source_updated_at` datetime(6),
    `_observed_at` datetime(6) not null,
    `_valid_from` datetime(6),
    `_valid_to` datetime(6),
    `_payload_hash` varchar(64) not null,
    `ts_code` longtext,
    `com_name` longtext,
    `com_id` longtext,
    `exchange` longtext,
    `chairman` longtext,
    `manager` longtext,
    `secretary` longtext,
    `reg_capital` decimal(38,8),
    `setup_date` date,
    `province` longtext,
    `city` longtext,
    `introduction` longtext,
    `website` longtext,
    `email` longtext,
    `office` longtext,
    `employees` bigint,
    `main_business` longtext,
    `business_scope` longtext,
    unique(`_natural_key_hash`,`_revision_no`),
    unique(`_current_natural_key_hash`),
    check (`_revision_no` > 0),
    check (`_is_current` in (0,1)),
    check (`_valid_to` is null or `_valid_from` is null or `_valid_to` >= `_valid_from`)
);

create index if not exists `idx_src_tushare_stock_company_current`
    on `src_tushare_stock_company`(`_natural_key_hash`,`_is_current`);
create index if not exists `idx_src_tushare_stock_company_observed`
    on `src_tushare_stock_company`(`_observed_at`);

create table if not exists `src_tushare_stk_managers` (
    `_observation_id` varchar(64) primary key,
    `_batch_id` varchar(64) not null,
    `_natural_key_hash` varchar(64) not null,
    `_revision_no` integer not null,
    `_is_current` integer not null default 1,
    `_current_natural_key_hash` varchar(64) generated always as (case when `_is_current` = 1 then `_natural_key_hash` else null end) stored,
    `_published_at` datetime(6),
    `_source_updated_at` datetime(6),
    `_observed_at` datetime(6) not null,
    `_valid_from` datetime(6),
    `_valid_to` datetime(6),
    `_payload_hash` varchar(64) not null,
    `ts_code` longtext,
    `ann_date` date,
    `name` longtext,
    `gender` longtext,
    `lev` longtext,
    `title` longtext,
    `edu` longtext,
    `national` longtext,
    `birthday` longtext,
    `begin_date` date,
    `end_date` date,
    `resume` longtext,
    unique(`_natural_key_hash`,`_revision_no`),
    unique(`_current_natural_key_hash`),
    check (`_revision_no` > 0),
    check (`_is_current` in (0,1)),
    check (`_valid_to` is null or `_valid_from` is null or `_valid_to` >= `_valid_from`)
);

create index if not exists `idx_src_tushare_stk_managers_current`
    on `src_tushare_stk_managers`(`_natural_key_hash`,`_is_current`);
create index if not exists `idx_src_tushare_stk_managers_observed`
    on `src_tushare_stk_managers`(`_observed_at`);

create table if not exists `src_tushare_stk_rewards` (
    `_observation_id` varchar(64) primary key,
    `_batch_id` varchar(64) not null,
    `_natural_key_hash` varchar(64) not null,
    `_revision_no` integer not null,
    `_is_current` integer not null default 1,
    `_current_natural_key_hash` varchar(64) generated always as (case when `_is_current` = 1 then `_natural_key_hash` else null end) stored,
    `_published_at` datetime(6),
    `_source_updated_at` datetime(6),
    `_observed_at` datetime(6) not null,
    `_valid_from` datetime(6),
    `_valid_to` datetime(6),
    `_payload_hash` varchar(64) not null,
    `ts_code` longtext,
    `ann_date` date,
    `end_date` date,
    `name` longtext,
    `title` longtext,
    `reward` decimal(38,8),
    `hold_vol` decimal(38,8),
    unique(`_natural_key_hash`,`_revision_no`),
    unique(`_current_natural_key_hash`),
    check (`_revision_no` > 0),
    check (`_is_current` in (0,1)),
    check (`_valid_to` is null or `_valid_from` is null or `_valid_to` >= `_valid_from`)
);

create index if not exists `idx_src_tushare_stk_rewards_current`
    on `src_tushare_stk_rewards`(`_natural_key_hash`,`_is_current`);
create index if not exists `idx_src_tushare_stk_rewards_observed`
    on `src_tushare_stk_rewards`(`_observed_at`);

create table if not exists `src_tushare_bse_mapping` (
    `_observation_id` varchar(64) primary key,
    `_batch_id` varchar(64) not null,
    `_natural_key_hash` varchar(64) not null,
    `_revision_no` integer not null,
    `_is_current` integer not null default 1,
    `_current_natural_key_hash` varchar(64) generated always as (case when `_is_current` = 1 then `_natural_key_hash` else null end) stored,
    `_published_at` datetime(6),
    `_source_updated_at` datetime(6),
    `_observed_at` datetime(6) not null,
    `_valid_from` datetime(6),
    `_valid_to` datetime(6),
    `_payload_hash` varchar(64) not null,
    `name` longtext,
    `o_code` longtext,
    `n_code` longtext,
    `list_date` date,
    unique(`_natural_key_hash`,`_revision_no`),
    unique(`_current_natural_key_hash`),
    check (`_revision_no` > 0),
    check (`_is_current` in (0,1)),
    check (`_valid_to` is null or `_valid_from` is null or `_valid_to` >= `_valid_from`)
);

create index if not exists `idx_src_tushare_bse_mapping_current`
    on `src_tushare_bse_mapping`(`_natural_key_hash`,`_is_current`);
create index if not exists `idx_src_tushare_bse_mapping_observed`
    on `src_tushare_bse_mapping`(`_observed_at`);

create table if not exists `src_tushare_new_share` (
    `_observation_id` varchar(64) primary key,
    `_batch_id` varchar(64) not null,
    `_natural_key_hash` varchar(64) not null,
    `_revision_no` integer not null,
    `_is_current` integer not null default 1,
    `_current_natural_key_hash` varchar(64) generated always as (case when `_is_current` = 1 then `_natural_key_hash` else null end) stored,
    `_published_at` datetime(6),
    `_source_updated_at` datetime(6),
    `_observed_at` datetime(6) not null,
    `_valid_from` datetime(6),
    `_valid_to` datetime(6),
    `_payload_hash` varchar(64) not null,
    `ts_code` longtext,
    `sub_code` longtext,
    `name` longtext,
    `ipo_date` date,
    `issue_date` date,
    `amount` decimal(38,8),
    `market_amount` decimal(38,8),
    `price` decimal(38,8),
    `pe` decimal(38,8),
    `limit_amount` decimal(38,8),
    `funds` decimal(38,8),
    `ballot` decimal(38,8),
    unique(`_natural_key_hash`,`_revision_no`),
    unique(`_current_natural_key_hash`),
    check (`_revision_no` > 0),
    check (`_is_current` in (0,1)),
    check (`_valid_to` is null or `_valid_from` is null or `_valid_to` >= `_valid_from`)
);

create index if not exists `idx_src_tushare_new_share_current`
    on `src_tushare_new_share`(`_natural_key_hash`,`_is_current`);
create index if not exists `idx_src_tushare_new_share_observed`
    on `src_tushare_new_share`(`_observed_at`);

create table if not exists `src_tushare_bak_basic` (
    `_observation_id` varchar(64) primary key,
    `_batch_id` varchar(64) not null,
    `_natural_key_hash` varchar(64) not null,
    `_revision_no` integer not null,
    `_is_current` integer not null default 1,
    `_current_natural_key_hash` varchar(64) generated always as (case when `_is_current` = 1 then `_natural_key_hash` else null end) stored,
    `_published_at` datetime(6),
    `_source_updated_at` datetime(6),
    `_observed_at` datetime(6) not null,
    `_valid_from` datetime(6),
    `_valid_to` datetime(6),
    `_payload_hash` varchar(64) not null,
    `trade_date` date,
    `ts_code` longtext,
    `name` longtext,
    `industry` longtext,
    `area` longtext,
    `pe` decimal(38,8),
    `float_share` decimal(38,8),
    `total_share` decimal(38,8),
    `total_assets` decimal(38,8),
    `liquid_assets` decimal(38,8),
    `fixed_assets` decimal(38,8),
    `reserved` decimal(38,8),
    `reserved_pershare` decimal(38,8),
    `eps` decimal(38,8),
    `bvps` decimal(38,8),
    `pb` decimal(38,8),
    `list_date` date,
    `undp` decimal(38,8),
    `per_undp` decimal(38,8),
    `rev_yoy` decimal(38,8),
    `profit_yoy` decimal(38,8),
    `gpr` decimal(38,8),
    `npr` decimal(38,8),
    `holder_num` bigint,
    unique(`_natural_key_hash`,`_revision_no`),
    unique(`_current_natural_key_hash`),
    check (`_revision_no` > 0),
    check (`_is_current` in (0,1)),
    check (`_valid_to` is null or `_valid_from` is null or `_valid_to` >= `_valid_from`)
);

create index if not exists `idx_src_tushare_bak_basic_current`
    on `src_tushare_bak_basic`(`_natural_key_hash`,`_is_current`);
create index if not exists `idx_src_tushare_bak_basic_observed`
    on `src_tushare_bak_basic`(`_observed_at`);

create table if not exists `src_tushare_daily` (
    `_observation_id` varchar(64) primary key,
    `_batch_id` varchar(64) not null,
    `_natural_key_hash` varchar(64) not null,
    `_revision_no` integer not null,
    `_is_current` integer not null default 1,
    `_current_natural_key_hash` varchar(64) generated always as (case when `_is_current` = 1 then `_natural_key_hash` else null end) stored,
    `_published_at` datetime(6),
    `_source_updated_at` datetime(6),
    `_observed_at` datetime(6) not null,
    `_valid_from` datetime(6),
    `_valid_to` datetime(6),
    `_payload_hash` varchar(64) not null,
    `ts_code` longtext,
    `trade_date` date,
    `open` decimal(38,8),
    `high` decimal(38,8),
    `low` decimal(38,8),
    `close` decimal(38,8),
    `pre_close` decimal(38,8),
    `change` decimal(38,8),
    `pct_chg` decimal(38,8),
    `vol` decimal(38,8),
    `amount` decimal(38,8),
    `ah_vol` decimal(38,8),
    `ah_amount` decimal(38,8),
    unique(`_natural_key_hash`,`_revision_no`),
    unique(`_current_natural_key_hash`),
    check (`_revision_no` > 0),
    check (`_is_current` in (0,1)),
    check (`_valid_to` is null or `_valid_from` is null or `_valid_to` >= `_valid_from`)
);

create index if not exists `idx_src_tushare_daily_current`
    on `src_tushare_daily`(`_natural_key_hash`,`_is_current`);
create index if not exists `idx_src_tushare_daily_observed`
    on `src_tushare_daily`(`_observed_at`);

create table if not exists `src_tushare_stk_mins` (
    `_observation_id` varchar(64) primary key,
    `_batch_id` varchar(64) not null,
    `_natural_key_hash` varchar(64) not null,
    `_revision_no` integer not null,
    `_is_current` integer not null default 1,
    `_current_natural_key_hash` varchar(64) generated always as (case when `_is_current` = 1 then `_natural_key_hash` else null end) stored,
    `_published_at` datetime(6),
    `_source_updated_at` datetime(6),
    `_observed_at` datetime(6) not null,
    `_valid_from` datetime(6),
    `_valid_to` datetime(6),
    `_payload_hash` varchar(64) not null,
    `ts_code` longtext,
    `trade_time` datetime(6),
    `open` decimal(38,8),
    `close` decimal(38,8),
    `high` decimal(38,8),
    `low` decimal(38,8),
    `vol` bigint,
    `amount` decimal(38,8),
    unique(`_natural_key_hash`,`_revision_no`),
    unique(`_current_natural_key_hash`),
    check (`_revision_no` > 0),
    check (`_is_current` in (0,1)),
    check (`_valid_to` is null or `_valid_from` is null or `_valid_to` >= `_valid_from`)
);

create index if not exists `idx_src_tushare_stk_mins_current`
    on `src_tushare_stk_mins`(`_natural_key_hash`,`_is_current`);
create index if not exists `idx_src_tushare_stk_mins_observed`
    on `src_tushare_stk_mins`(`_observed_at`);

create table if not exists `src_tushare_weekly` (
    `_observation_id` varchar(64) primary key,
    `_batch_id` varchar(64) not null,
    `_natural_key_hash` varchar(64) not null,
    `_revision_no` integer not null,
    `_is_current` integer not null default 1,
    `_current_natural_key_hash` varchar(64) generated always as (case when `_is_current` = 1 then `_natural_key_hash` else null end) stored,
    `_published_at` datetime(6),
    `_source_updated_at` datetime(6),
    `_observed_at` datetime(6) not null,
    `_valid_from` datetime(6),
    `_valid_to` datetime(6),
    `_payload_hash` varchar(64) not null,
    `ts_code` longtext,
    `trade_date` date,
    `close` decimal(38,8),
    `open` decimal(38,8),
    `high` decimal(38,8),
    `low` decimal(38,8),
    `pre_close` decimal(38,8),
    `change` decimal(38,8),
    `pct_chg` decimal(38,8),
    `vol` decimal(38,8),
    `amount` decimal(38,8),
    unique(`_natural_key_hash`,`_revision_no`),
    unique(`_current_natural_key_hash`),
    check (`_revision_no` > 0),
    check (`_is_current` in (0,1)),
    check (`_valid_to` is null or `_valid_from` is null or `_valid_to` >= `_valid_from`)
);

create index if not exists `idx_src_tushare_weekly_current`
    on `src_tushare_weekly`(`_natural_key_hash`,`_is_current`);
create index if not exists `idx_src_tushare_weekly_observed`
    on `src_tushare_weekly`(`_observed_at`);

create table if not exists `src_tushare_monthly` (
    `_observation_id` varchar(64) primary key,
    `_batch_id` varchar(64) not null,
    `_natural_key_hash` varchar(64) not null,
    `_revision_no` integer not null,
    `_is_current` integer not null default 1,
    `_current_natural_key_hash` varchar(64) generated always as (case when `_is_current` = 1 then `_natural_key_hash` else null end) stored,
    `_published_at` datetime(6),
    `_source_updated_at` datetime(6),
    `_observed_at` datetime(6) not null,
    `_valid_from` datetime(6),
    `_valid_to` datetime(6),
    `_payload_hash` varchar(64) not null,
    `ts_code` longtext,
    `trade_date` date,
    `close` decimal(38,8),
    `open` decimal(38,8),
    `high` decimal(38,8),
    `low` decimal(38,8),
    `pre_close` decimal(38,8),
    `change` decimal(38,8),
    `pct_chg` decimal(38,8),
    `vol` decimal(38,8),
    `amount` decimal(38,8),
    unique(`_natural_key_hash`,`_revision_no`),
    unique(`_current_natural_key_hash`),
    check (`_revision_no` > 0),
    check (`_is_current` in (0,1)),
    check (`_valid_to` is null or `_valid_from` is null or `_valid_to` >= `_valid_from`)
);

create index if not exists `idx_src_tushare_monthly_current`
    on `src_tushare_monthly`(`_natural_key_hash`,`_is_current`);
create index if not exists `idx_src_tushare_monthly_observed`
    on `src_tushare_monthly`(`_observed_at`);

create table if not exists `src_tushare_pro_bar_equity` (
    `_observation_id` varchar(64) primary key,
    `_batch_id` varchar(64) not null,
    `_natural_key_hash` varchar(64) not null,
    `_revision_no` integer not null,
    `_is_current` integer not null default 1,
    `_current_natural_key_hash` varchar(64) generated always as (case when `_is_current` = 1 then `_natural_key_hash` else null end) stored,
    `_published_at` datetime(6),
    `_source_updated_at` datetime(6),
    `_observed_at` datetime(6) not null,
    `_valid_from` datetime(6),
    `_valid_to` datetime(6),
    `_payload_hash` varchar(64) not null,
    `ts_code` longtext,
    `start_date` date,
    `end_date` date,
    `asset` longtext,
    `adj` longtext,
    `freq` longtext,
    `ma` longtext,
    unique(`_natural_key_hash`,`_revision_no`),
    unique(`_current_natural_key_hash`),
    check (`_revision_no` > 0),
    check (`_is_current` in (0,1)),
    check (`_valid_to` is null or `_valid_from` is null or `_valid_to` >= `_valid_from`)
);

create index if not exists `idx_src_tushare_pro_bar_equity_current`
    on `src_tushare_pro_bar_equity`(`_natural_key_hash`,`_is_current`);
create index if not exists `idx_src_tushare_pro_bar_equity_observed`
    on `src_tushare_pro_bar_equity`(`_observed_at`);

create table if not exists `src_tushare_stk_weekly_monthly` (
    `_observation_id` varchar(64) primary key,
    `_batch_id` varchar(64) not null,
    `_natural_key_hash` varchar(64) not null,
    `_revision_no` integer not null,
    `_is_current` integer not null default 1,
    `_current_natural_key_hash` varchar(64) generated always as (case when `_is_current` = 1 then `_natural_key_hash` else null end) stored,
    `_published_at` datetime(6),
    `_source_updated_at` datetime(6),
    `_observed_at` datetime(6) not null,
    `_valid_from` datetime(6),
    `_valid_to` datetime(6),
    `_payload_hash` varchar(64) not null,
    `ts_code` longtext,
    `trade_date` date,
    `end_date` date,
    `freq` longtext,
    `open` decimal(38,8),
    `high` decimal(38,8),
    `low` decimal(38,8),
    `close` decimal(38,8),
    `pre_close` decimal(38,8),
    `vol` decimal(38,8),
    `amount` decimal(38,8),
    `change` decimal(38,8),
    `pct_chg` decimal(38,8),
    unique(`_natural_key_hash`,`_revision_no`),
    unique(`_current_natural_key_hash`),
    check (`_revision_no` > 0),
    check (`_is_current` in (0,1)),
    check (`_valid_to` is null or `_valid_from` is null or `_valid_to` >= `_valid_from`)
);

create index if not exists `idx_src_tushare_stk_weekly_monthly_current`
    on `src_tushare_stk_weekly_monthly`(`_natural_key_hash`,`_is_current`);
create index if not exists `idx_src_tushare_stk_weekly_monthly_observed`
    on `src_tushare_stk_weekly_monthly`(`_observed_at`);

create table if not exists `src_tushare_stk_week_month_adj` (
    `_observation_id` varchar(64) primary key,
    `_batch_id` varchar(64) not null,
    `_natural_key_hash` varchar(64) not null,
    `_revision_no` integer not null,
    `_is_current` integer not null default 1,
    `_current_natural_key_hash` varchar(64) generated always as (case when `_is_current` = 1 then `_natural_key_hash` else null end) stored,
    `_published_at` datetime(6),
    `_source_updated_at` datetime(6),
    `_observed_at` datetime(6) not null,
    `_valid_from` datetime(6),
    `_valid_to` datetime(6),
    `_payload_hash` varchar(64) not null,
    `ts_code` longtext,
    `trade_date` date,
    `end_date` date,
    `freq` longtext,
    `open` decimal(38,8),
    `high` decimal(38,8),
    `low` decimal(38,8),
    `close` decimal(38,8),
    `pre_close` decimal(38,8),
    `open_qfq` decimal(38,8),
    `high_qfq` decimal(38,8),
    `low_qfq` decimal(38,8),
    `close_qfq` decimal(38,8),
    `open_hfq` decimal(38,8),
    `high_hfq` decimal(38,8),
    `low_hfq` decimal(38,8),
    `close_hfq` decimal(38,8),
    `vol` decimal(38,8),
    `amount` decimal(38,8),
    `change` decimal(38,8),
    `pct_chg` decimal(38,8),
    unique(`_natural_key_hash`,`_revision_no`),
    unique(`_current_natural_key_hash`),
    check (`_revision_no` > 0),
    check (`_is_current` in (0,1)),
    check (`_valid_to` is null or `_valid_from` is null or `_valid_to` >= `_valid_from`)
);

create index if not exists `idx_src_tushare_stk_week_month_adj_current`
    on `src_tushare_stk_week_month_adj`(`_natural_key_hash`,`_is_current`);
create index if not exists `idx_src_tushare_stk_week_month_adj_observed`
    on `src_tushare_stk_week_month_adj`(`_observed_at`);

create table if not exists `src_tushare_adj_factor` (
    `_observation_id` varchar(64) primary key,
    `_batch_id` varchar(64) not null,
    `_natural_key_hash` varchar(64) not null,
    `_revision_no` integer not null,
    `_is_current` integer not null default 1,
    `_current_natural_key_hash` varchar(64) generated always as (case when `_is_current` = 1 then `_natural_key_hash` else null end) stored,
    `_published_at` datetime(6),
    `_source_updated_at` datetime(6),
    `_observed_at` datetime(6) not null,
    `_valid_from` datetime(6),
    `_valid_to` datetime(6),
    `_payload_hash` varchar(64) not null,
    `ts_code` longtext,
    `trade_date` date,
    `adj_factor` decimal(38,8),
    unique(`_natural_key_hash`,`_revision_no`),
    unique(`_current_natural_key_hash`),
    check (`_revision_no` > 0),
    check (`_is_current` in (0,1)),
    check (`_valid_to` is null or `_valid_from` is null or `_valid_to` >= `_valid_from`)
);

create index if not exists `idx_src_tushare_adj_factor_current`
    on `src_tushare_adj_factor`(`_natural_key_hash`,`_is_current`);
create index if not exists `idx_src_tushare_adj_factor_observed`
    on `src_tushare_adj_factor`(`_observed_at`);

create table if not exists `src_tushare_daily_basic` (
    `_observation_id` varchar(64) primary key,
    `_batch_id` varchar(64) not null,
    `_natural_key_hash` varchar(64) not null,
    `_revision_no` integer not null,
    `_is_current` integer not null default 1,
    `_current_natural_key_hash` varchar(64) generated always as (case when `_is_current` = 1 then `_natural_key_hash` else null end) stored,
    `_published_at` datetime(6),
    `_source_updated_at` datetime(6),
    `_observed_at` datetime(6) not null,
    `_valid_from` datetime(6),
    `_valid_to` datetime(6),
    `_payload_hash` varchar(64) not null,
    `ts_code` longtext,
    `trade_date` date,
    `close` decimal(38,8),
    `turnover_rate` decimal(38,8),
    `turnover_rate_f` decimal(38,8),
    `volume_ratio` decimal(38,8),
    `pe` decimal(38,8),
    `pe_ttm` decimal(38,8),
    `pb` decimal(38,8),
    `ps` decimal(38,8),
    `ps_ttm` decimal(38,8),
    `dv_ratio` decimal(38,8),
    `dv_ttm` decimal(38,8),
    `total_share` decimal(38,8),
    `float_share` decimal(38,8),
    `free_share` decimal(38,8),
    `total_mv` decimal(38,8),
    `circ_mv` decimal(38,8),
    `limit_status` bigint,
    unique(`_natural_key_hash`,`_revision_no`),
    unique(`_current_natural_key_hash`),
    check (`_revision_no` > 0),
    check (`_is_current` in (0,1)),
    check (`_valid_to` is null or `_valid_from` is null or `_valid_to` >= `_valid_from`)
);

create index if not exists `idx_src_tushare_daily_basic_current`
    on `src_tushare_daily_basic`(`_natural_key_hash`,`_is_current`);
create index if not exists `idx_src_tushare_daily_basic_observed`
    on `src_tushare_daily_basic`(`_observed_at`);

create table if not exists `src_tushare_pro_bar_general` (
    `_observation_id` varchar(64) primary key,
    `_batch_id` varchar(64) not null,
    `_natural_key_hash` varchar(64) not null,
    `_revision_no` integer not null,
    `_is_current` integer not null default 1,
    `_current_natural_key_hash` varchar(64) generated always as (case when `_is_current` = 1 then `_natural_key_hash` else null end) stored,
    `_published_at` datetime(6),
    `_source_updated_at` datetime(6),
    `_observed_at` datetime(6) not null,
    `_valid_from` datetime(6),
    `_valid_to` datetime(6),
    `_payload_hash` varchar(64) not null,
    `ts_code` longtext,
    `start_date` date,
    `end_date` date,
    `asset` longtext,
    `adj` longtext,
    `freq` longtext,
    `ma` longtext,
    `factors` longtext,
    `adjfactor` longtext,
    unique(`_natural_key_hash`,`_revision_no`),
    unique(`_current_natural_key_hash`),
    check (`_revision_no` > 0),
    check (`_is_current` in (0,1)),
    check (`_valid_to` is null or `_valid_from` is null or `_valid_to` >= `_valid_from`)
);

create index if not exists `idx_src_tushare_pro_bar_general_current`
    on `src_tushare_pro_bar_general`(`_natural_key_hash`,`_is_current`);
create index if not exists `idx_src_tushare_pro_bar_general_observed`
    on `src_tushare_pro_bar_general`(`_observed_at`);

create table if not exists `src_tushare_stk_limit` (
    `_observation_id` varchar(64) primary key,
    `_batch_id` varchar(64) not null,
    `_natural_key_hash` varchar(64) not null,
    `_revision_no` integer not null,
    `_is_current` integer not null default 1,
    `_current_natural_key_hash` varchar(64) generated always as (case when `_is_current` = 1 then `_natural_key_hash` else null end) stored,
    `_published_at` datetime(6),
    `_source_updated_at` datetime(6),
    `_observed_at` datetime(6) not null,
    `_valid_from` datetime(6),
    `_valid_to` datetime(6),
    `_payload_hash` varchar(64) not null,
    `trade_date` date,
    `ts_code` longtext,
    `pre_close` decimal(38,8),
    `up_limit` decimal(38,8),
    `down_limit` decimal(38,8),
    unique(`_natural_key_hash`,`_revision_no`),
    unique(`_current_natural_key_hash`),
    check (`_revision_no` > 0),
    check (`_is_current` in (0,1)),
    check (`_valid_to` is null or `_valid_from` is null or `_valid_to` >= `_valid_from`)
);

create index if not exists `idx_src_tushare_stk_limit_current`
    on `src_tushare_stk_limit`(`_natural_key_hash`,`_is_current`);
create index if not exists `idx_src_tushare_stk_limit_observed`
    on `src_tushare_stk_limit`(`_observed_at`);

create table if not exists `src_tushare_suspend_d` (
    `_observation_id` varchar(64) primary key,
    `_batch_id` varchar(64) not null,
    `_natural_key_hash` varchar(64) not null,
    `_revision_no` integer not null,
    `_is_current` integer not null default 1,
    `_current_natural_key_hash` varchar(64) generated always as (case when `_is_current` = 1 then `_natural_key_hash` else null end) stored,
    `_published_at` datetime(6),
    `_source_updated_at` datetime(6),
    `_observed_at` datetime(6) not null,
    `_valid_from` datetime(6),
    `_valid_to` datetime(6),
    `_payload_hash` varchar(64) not null,
    `ts_code` longtext,
    `trade_date` date,
    `suspend_timing` longtext,
    `suspend_type` longtext,
    unique(`_natural_key_hash`,`_revision_no`),
    unique(`_current_natural_key_hash`),
    check (`_revision_no` > 0),
    check (`_is_current` in (0,1)),
    check (`_valid_to` is null or `_valid_from` is null or `_valid_to` >= `_valid_from`)
);

create index if not exists `idx_src_tushare_suspend_d_current`
    on `src_tushare_suspend_d`(`_natural_key_hash`,`_is_current`);
create index if not exists `idx_src_tushare_suspend_d_observed`
    on `src_tushare_suspend_d`(`_observed_at`);

create table if not exists `src_tushare_hsgt_top10` (
    `_observation_id` varchar(64) primary key,
    `_batch_id` varchar(64) not null,
    `_natural_key_hash` varchar(64) not null,
    `_revision_no` integer not null,
    `_is_current` integer not null default 1,
    `_current_natural_key_hash` varchar(64) generated always as (case when `_is_current` = 1 then `_natural_key_hash` else null end) stored,
    `_published_at` datetime(6),
    `_source_updated_at` datetime(6),
    `_observed_at` datetime(6) not null,
    `_valid_from` datetime(6),
    `_valid_to` datetime(6),
    `_payload_hash` varchar(64) not null,
    `trade_date` date,
    `ts_code` longtext,
    `name` longtext,
    `close` decimal(38,8),
    `change` decimal(38,8),
    `rank` bigint,
    `market_type` longtext,
    `amount` decimal(38,8),
    `net_amount` decimal(38,8),
    `buy` decimal(38,8),
    `sell` decimal(38,8),
    unique(`_natural_key_hash`,`_revision_no`),
    unique(`_current_natural_key_hash`),
    check (`_revision_no` > 0),
    check (`_is_current` in (0,1)),
    check (`_valid_to` is null or `_valid_from` is null or `_valid_to` >= `_valid_from`)
);

create index if not exists `idx_src_tushare_hsgt_top10_current`
    on `src_tushare_hsgt_top10`(`_natural_key_hash`,`_is_current`);
create index if not exists `idx_src_tushare_hsgt_top10_observed`
    on `src_tushare_hsgt_top10`(`_observed_at`);

create table if not exists `src_tushare_bak_daily` (
    `_observation_id` varchar(64) primary key,
    `_batch_id` varchar(64) not null,
    `_natural_key_hash` varchar(64) not null,
    `_revision_no` integer not null,
    `_is_current` integer not null default 1,
    `_current_natural_key_hash` varchar(64) generated always as (case when `_is_current` = 1 then `_natural_key_hash` else null end) stored,
    `_published_at` datetime(6),
    `_source_updated_at` datetime(6),
    `_observed_at` datetime(6) not null,
    `_valid_from` datetime(6),
    `_valid_to` datetime(6),
    `_payload_hash` varchar(64) not null,
    `ts_code` longtext,
    `trade_date` date,
    `name` longtext,
    `pct_change` decimal(38,8),
    `close` decimal(38,8),
    `change` decimal(38,8),
    `open` decimal(38,8),
    `high` decimal(38,8),
    `low` decimal(38,8),
    `pre_close` decimal(38,8),
    `vol_ratio` decimal(38,8),
    `turn_over` decimal(38,8),
    `swing` decimal(38,8),
    `vol` decimal(38,8),
    `amount` decimal(38,8),
    `selling` decimal(38,8),
    `buying` decimal(38,8),
    `total_share` decimal(38,8),
    `float_share` decimal(38,8),
    `pe` decimal(38,8),
    `industry` longtext,
    `area` longtext,
    `float_mv` decimal(38,8),
    `total_mv` decimal(38,8),
    `avg_price` decimal(38,8),
    `strength` decimal(38,8),
    `activity` decimal(38,8),
    `avg_turnover` decimal(38,8),
    `attack` decimal(38,8),
    `interval_3` decimal(38,8),
    `interval_6` decimal(38,8),
    unique(`_natural_key_hash`,`_revision_no`),
    unique(`_current_natural_key_hash`),
    check (`_revision_no` > 0),
    check (`_is_current` in (0,1)),
    check (`_valid_to` is null or `_valid_from` is null or `_valid_to` >= `_valid_from`)
);

create index if not exists `idx_src_tushare_bak_daily_current`
    on `src_tushare_bak_daily`(`_natural_key_hash`,`_is_current`);
create index if not exists `idx_src_tushare_bak_daily_observed`
    on `src_tushare_bak_daily`(`_observed_at`);

create table if not exists `src_tushare_income` (
    `_observation_id` varchar(64) primary key,
    `_batch_id` varchar(64) not null,
    `_natural_key_hash` varchar(64) not null,
    `_revision_no` integer not null,
    `_is_current` integer not null default 1,
    `_current_natural_key_hash` varchar(64) generated always as (case when `_is_current` = 1 then `_natural_key_hash` else null end) stored,
    `_published_at` datetime(6),
    `_source_updated_at` datetime(6),
    `_observed_at` datetime(6) not null,
    `_valid_from` datetime(6),
    `_valid_to` datetime(6),
    `_payload_hash` varchar(64) not null,
    `ts_code` longtext,
    `ann_date` date,
    `f_ann_date` date,
    `end_date` date,
    `report_type` longtext,
    `comp_type` longtext,
    `end_type` longtext,
    `basic_eps` decimal(38,8),
    `diluted_eps` decimal(38,8),
    `total_revenue` decimal(38,8),
    `revenue` decimal(38,8),
    `int_income` decimal(38,8),
    `prem_earned` decimal(38,8),
    `comm_income` decimal(38,8),
    `n_commis_income` decimal(38,8),
    `n_oth_income` decimal(38,8),
    `n_oth_b_income` decimal(38,8),
    `prem_income` decimal(38,8),
    `out_prem` decimal(38,8),
    `une_prem_reser` decimal(38,8),
    `reins_income` decimal(38,8),
    `n_sec_tb_income` decimal(38,8),
    `n_sec_uw_income` decimal(38,8),
    `n_asset_mg_income` decimal(38,8),
    `oth_b_income` decimal(38,8),
    `fv_value_chg_gain` decimal(38,8),
    `invest_income` decimal(38,8),
    `ass_invest_income` decimal(38,8),
    `forex_gain` decimal(38,8),
    `total_cogs` decimal(38,8),
    `oper_cost` decimal(38,8),
    `int_exp` decimal(38,8),
    `comm_exp` decimal(38,8),
    `biz_tax_surchg` decimal(38,8),
    `sell_exp` decimal(38,8),
    `admin_exp` decimal(38,8),
    `fin_exp` decimal(38,8),
    `assets_impair_loss` decimal(38,8),
    `prem_refund` decimal(38,8),
    `compens_payout` decimal(38,8),
    `reser_insur_liab` decimal(38,8),
    `div_payt` decimal(38,8),
    `reins_exp` decimal(38,8),
    `oper_exp` decimal(38,8),
    `compens_payout_refu` decimal(38,8),
    `insur_reser_refu` decimal(38,8),
    `reins_cost_refund` decimal(38,8),
    `other_bus_cost` decimal(38,8),
    `operate_profit` decimal(38,8),
    `non_oper_income` decimal(38,8),
    `non_oper_exp` decimal(38,8),
    `nca_disploss` decimal(38,8),
    `total_profit` decimal(38,8),
    `income_tax` decimal(38,8),
    `n_income` decimal(38,8),
    `n_income_attr_p` decimal(38,8),
    `minority_gain` decimal(38,8),
    `oth_compr_income` decimal(38,8),
    `t_compr_income` decimal(38,8),
    `compr_inc_attr_p` decimal(38,8),
    `compr_inc_attr_m_s` decimal(38,8),
    `ebit` decimal(38,8),
    `ebitda` decimal(38,8),
    `insurance_exp` decimal(38,8),
    `undist_profit` decimal(38,8),
    `distable_profit` decimal(38,8),
    `rd_exp` decimal(38,8),
    `fin_exp_int_exp` decimal(38,8),
    `fin_exp_int_inc` decimal(38,8),
    `transfer_surplus_rese` decimal(38,8),
    `transfer_housing_imprest` decimal(38,8),
    `transfer_oth` decimal(38,8),
    `adj_lossgain` decimal(38,8),
    `withdra_legal_surplus` decimal(38,8),
    `withdra_legal_pubfund` decimal(38,8),
    `withdra_biz_devfund` decimal(38,8),
    `withdra_rese_fund` decimal(38,8),
    `withdra_oth_ersu` decimal(38,8),
    `workers_welfare` decimal(38,8),
    `distr_profit_shrhder` decimal(38,8),
    `prfshare_payable_dvd` decimal(38,8),
    `comshare_payable_dvd` decimal(38,8),
    `capit_comstock_div` decimal(38,8),
    `net_after_nr_lp_correct` decimal(38,8),
    `credit_impa_loss` decimal(38,8),
    `net_expo_hedging_benefits` decimal(38,8),
    `oth_impair_loss_assets` decimal(38,8),
    `total_opcost` decimal(38,8),
    `amodcost_fin_assets` decimal(38,8),
    `oth_income` decimal(38,8),
    `asset_disp_income` decimal(38,8),
    `continued_net_profit` decimal(38,8),
    `end_net_profit` decimal(38,8),
    `update_flag` longtext,
    unique(`_natural_key_hash`,`_revision_no`),
    unique(`_current_natural_key_hash`),
    check (`_revision_no` > 0),
    check (`_is_current` in (0,1)),
    check (`_valid_to` is null or `_valid_from` is null or `_valid_to` >= `_valid_from`)
);

create index if not exists `idx_src_tushare_income_current`
    on `src_tushare_income`(`_natural_key_hash`,`_is_current`);
create index if not exists `idx_src_tushare_income_observed`
    on `src_tushare_income`(`_observed_at`);

create table if not exists `src_tushare_balancesheet` (
    `_observation_id` varchar(64) primary key,
    `_batch_id` varchar(64) not null,
    `_natural_key_hash` varchar(64) not null,
    `_revision_no` integer not null,
    `_is_current` integer not null default 1,
    `_current_natural_key_hash` varchar(64) generated always as (case when `_is_current` = 1 then `_natural_key_hash` else null end) stored,
    `_published_at` datetime(6),
    `_source_updated_at` datetime(6),
    `_observed_at` datetime(6) not null,
    `_valid_from` datetime(6),
    `_valid_to` datetime(6),
    `_payload_hash` varchar(64) not null,
    `ts_code` longtext,
    `ann_date` date,
    `f_ann_date` date,
    `end_date` date,
    `report_type` longtext,
    `comp_type` longtext,
    `end_type` longtext,
    `total_share` decimal(38,8),
    `cap_rese` decimal(38,8),
    `undistr_porfit` decimal(38,8),
    `surplus_rese` decimal(38,8),
    `special_rese` decimal(38,8),
    `money_cap` decimal(38,8),
    `trad_asset` decimal(38,8),
    `notes_receiv` decimal(38,8),
    `accounts_receiv` decimal(38,8),
    `oth_receiv` decimal(38,8),
    `prepayment` decimal(38,8),
    `div_receiv` decimal(38,8),
    `int_receiv` decimal(38,8),
    `inventories` decimal(38,8),
    `amor_exp` decimal(38,8),
    `nca_within_1y` decimal(38,8),
    `sett_rsrv` decimal(38,8),
    `loanto_oth_bank_fi` decimal(38,8),
    `premium_receiv` decimal(38,8),
    `reinsur_receiv` decimal(38,8),
    `reinsur_res_receiv` decimal(38,8),
    `pur_resale_fa` decimal(38,8),
    `oth_cur_assets` decimal(38,8),
    `total_cur_assets` decimal(38,8),
    `fa_avail_for_sale` decimal(38,8),
    `htm_invest` decimal(38,8),
    `lt_eqt_invest` decimal(38,8),
    `invest_real_estate` decimal(38,8),
    `time_deposits` datetime(6),
    `oth_assets` decimal(38,8),
    `lt_rec` decimal(38,8),
    `fix_assets` decimal(38,8),
    `cip` decimal(38,8),
    `const_materials` decimal(38,8),
    `fixed_assets_disp` decimal(38,8),
    `produc_bio_assets` decimal(38,8),
    `oil_and_gas_assets` decimal(38,8),
    `intan_assets` decimal(38,8),
    `r_and_d` decimal(38,8),
    `goodwill` decimal(38,8),
    `lt_amor_exp` decimal(38,8),
    `defer_tax_assets` decimal(38,8),
    `decr_in_disbur` decimal(38,8),
    `oth_nca` decimal(38,8),
    `total_nca` decimal(38,8),
    `cash_reser_cb` decimal(38,8),
    `depos_in_oth_bfi` decimal(38,8),
    `prec_metals` decimal(38,8),
    `deriv_assets` decimal(38,8),
    `rr_reins_une_prem` decimal(38,8),
    `rr_reins_outstd_cla` decimal(38,8),
    `rr_reins_lins_liab` decimal(38,8),
    `rr_reins_lthins_liab` decimal(38,8),
    `refund_depos` decimal(38,8),
    `ph_pledge_loans` decimal(38,8),
    `refund_cap_depos` decimal(38,8),
    `indep_acct_assets` decimal(38,8),
    `client_depos` decimal(38,8),
    `client_prov` decimal(38,8),
    `transac_seat_fee` decimal(38,8),
    `invest_as_receiv` decimal(38,8),
    `total_assets` decimal(38,8),
    `lt_borr` decimal(38,8),
    `st_borr` decimal(38,8),
    `cb_borr` decimal(38,8),
    `depos_ib_deposits` decimal(38,8),
    `loan_oth_bank` decimal(38,8),
    `trading_fl` decimal(38,8),
    `notes_payable` decimal(38,8),
    `acct_payable` decimal(38,8),
    `adv_receipts` decimal(38,8),
    `sold_for_repur_fa` decimal(38,8),
    `comm_payable` decimal(38,8),
    `payroll_payable` decimal(38,8),
    `taxes_payable` decimal(38,8),
    `int_payable` decimal(38,8),
    `div_payable` decimal(38,8),
    `oth_payable` decimal(38,8),
    `acc_exp` decimal(38,8),
    `deferred_inc` decimal(38,8),
    `st_bonds_payable` decimal(38,8),
    `payable_to_reinsurer` decimal(38,8),
    `rsrv_insur_cont` decimal(38,8),
    `acting_trading_sec` decimal(38,8),
    `acting_uw_sec` decimal(38,8),
    `non_cur_liab_due_1y` decimal(38,8),
    `oth_cur_liab` decimal(38,8),
    `total_cur_liab` decimal(38,8),
    `bond_payable` decimal(38,8),
    `lt_payable` decimal(38,8),
    `specific_payables` decimal(38,8),
    `estimated_liab` decimal(38,8),
    `defer_tax_liab` decimal(38,8),
    `defer_inc_non_cur_liab` decimal(38,8),
    `oth_ncl` decimal(38,8),
    `total_ncl` decimal(38,8),
    `depos_oth_bfi` decimal(38,8),
    `deriv_liab` decimal(38,8),
    `depos` decimal(38,8),
    `agency_bus_liab` decimal(38,8),
    `oth_liab` decimal(38,8),
    `prem_receiv_adva` decimal(38,8),
    `depos_received` decimal(38,8),
    `ph_invest` decimal(38,8),
    `reser_une_prem` decimal(38,8),
    `reser_outstd_claims` decimal(38,8),
    `reser_lins_liab` decimal(38,8),
    `reser_lthins_liab` decimal(38,8),
    `indept_acc_liab` decimal(38,8),
    `pledge_borr` decimal(38,8),
    `indem_payable` decimal(38,8),
    `policy_div_payable` decimal(38,8),
    `total_liab` decimal(38,8),
    `treasury_share` decimal(38,8),
    `ordin_risk_reser` decimal(38,8),
    `forex_differ` decimal(38,8),
    `invest_loss_unconf` decimal(38,8),
    `minority_int` decimal(38,8),
    `total_hldr_eqy_exc_min_int` decimal(38,8),
    `total_hldr_eqy_inc_min_int` decimal(38,8),
    `total_liab_hldr_eqy` decimal(38,8),
    `lt_payroll_payable` decimal(38,8),
    `oth_comp_income` decimal(38,8),
    `oth_eqt_tools` decimal(38,8),
    `oth_eqt_tools_p_shr` decimal(38,8),
    `lending_funds` decimal(38,8),
    `acc_receivable` decimal(38,8),
    `st_fin_payable` decimal(38,8),
    `payables` decimal(38,8),
    `hfs_assets` decimal(38,8),
    `hfs_sales` decimal(38,8),
    `cost_fin_assets` decimal(38,8),
    `fair_value_fin_assets` decimal(38,8),
    `cip_total` decimal(38,8),
    `oth_pay_total` decimal(38,8),
    `long_pay_total` decimal(38,8),
    `debt_invest` decimal(38,8),
    `oth_debt_invest` decimal(38,8),
    `oth_eq_invest` decimal(38,8),
    `oth_illiq_fin_assets` decimal(38,8),
    `oth_eq_ppbond` decimal(38,8),
    `receiv_financing` decimal(38,8),
    `use_right_assets` decimal(38,8),
    `lease_liab` decimal(38,8),
    `contract_assets` decimal(38,8),
    `contract_liab` decimal(38,8),
    `accounts_receiv_bill` decimal(38,8),
    `accounts_pay` decimal(38,8),
    `oth_rcv_total` decimal(38,8),
    `fix_assets_total` decimal(38,8),
    `update_flag` longtext,
    unique(`_natural_key_hash`,`_revision_no`),
    unique(`_current_natural_key_hash`),
    check (`_revision_no` > 0),
    check (`_is_current` in (0,1)),
    check (`_valid_to` is null or `_valid_from` is null or `_valid_to` >= `_valid_from`)
);

create index if not exists `idx_src_tushare_balancesheet_current`
    on `src_tushare_balancesheet`(`_natural_key_hash`,`_is_current`);
create index if not exists `idx_src_tushare_balancesheet_observed`
    on `src_tushare_balancesheet`(`_observed_at`);

create table if not exists `src_tushare_cashflow` (
    `_observation_id` varchar(64) primary key,
    `_batch_id` varchar(64) not null,
    `_natural_key_hash` varchar(64) not null,
    `_revision_no` integer not null,
    `_is_current` integer not null default 1,
    `_current_natural_key_hash` varchar(64) generated always as (case when `_is_current` = 1 then `_natural_key_hash` else null end) stored,
    `_published_at` datetime(6),
    `_source_updated_at` datetime(6),
    `_observed_at` datetime(6) not null,
    `_valid_from` datetime(6),
    `_valid_to` datetime(6),
    `_payload_hash` varchar(64) not null,
    `ts_code` longtext,
    `ann_date` date,
    `f_ann_date` date,
    `end_date` date,
    `comp_type` longtext,
    `report_type` longtext,
    `end_type` longtext,
    `net_profit` decimal(38,8),
    `finan_exp` decimal(38,8),
    `c_fr_sale_sg` decimal(38,8),
    `recp_tax_rends` decimal(38,8),
    `n_depos_incr_fi` decimal(38,8),
    `n_incr_loans_cb` decimal(38,8),
    `n_inc_borr_oth_fi` decimal(38,8),
    `prem_fr_orig_contr` decimal(38,8),
    `n_incr_insured_dep` decimal(38,8),
    `n_reinsur_prem` decimal(38,8),
    `n_incr_disp_tfa` decimal(38,8),
    `ifc_cash_incr` decimal(38,8),
    `n_incr_disp_faas` decimal(38,8),
    `n_incr_loans_oth_bank` decimal(38,8),
    `n_cap_incr_repur` decimal(38,8),
    `c_fr_oth_operate_a` decimal(38,8),
    `c_inf_fr_operate_a` decimal(38,8),
    `c_paid_goods_s` decimal(38,8),
    `c_paid_to_for_empl` decimal(38,8),
    `c_paid_for_taxes` decimal(38,8),
    `n_incr_clt_loan_adv` decimal(38,8),
    `n_incr_dep_cbob` decimal(38,8),
    `c_pay_claims_orig_inco` decimal(38,8),
    `pay_handling_chrg` decimal(38,8),
    `pay_comm_insur_plcy` decimal(38,8),
    `oth_cash_pay_oper_act` decimal(38,8),
    `st_cash_out_act` decimal(38,8),
    `n_cashflow_act` decimal(38,8),
    `oth_recp_ral_inv_act` decimal(38,8),
    `c_disp_withdrwl_invest` decimal(38,8),
    `c_recp_return_invest` decimal(38,8),
    `n_recp_disp_fiolta` decimal(38,8),
    `n_recp_disp_sobu` decimal(38,8),
    `stot_inflows_inv_act` decimal(38,8),
    `c_pay_acq_const_fiolta` decimal(38,8),
    `c_paid_invest` decimal(38,8),
    `n_disp_subs_oth_biz` decimal(38,8),
    `oth_pay_ral_inv_act` decimal(38,8),
    `n_incr_pledge_loan` decimal(38,8),
    `stot_out_inv_act` decimal(38,8),
    `n_cashflow_inv_act` decimal(38,8),
    `c_recp_borrow` decimal(38,8),
    `proc_issue_bonds` decimal(38,8),
    `oth_cash_recp_ral_fnc_act` decimal(38,8),
    `stot_cash_in_fnc_act` decimal(38,8),
    `free_cashflow` decimal(38,8),
    `c_prepay_amt_borr` decimal(38,8),
    `c_pay_dist_dpcp_int_exp` decimal(38,8),
    `incl_dvd_profit_paid_sc_ms` decimal(38,8),
    `oth_cashpay_ral_fnc_act` decimal(38,8),
    `stot_cashout_fnc_act` decimal(38,8),
    `n_cash_flows_fnc_act` decimal(38,8),
    `eff_fx_flu_cash` decimal(38,8),
    `n_incr_cash_cash_equ` decimal(38,8),
    `c_cash_equ_beg_period` decimal(38,8),
    `c_cash_equ_end_period` decimal(38,8),
    `c_recp_cap_contrib` decimal(38,8),
    `incl_cash_rec_saims` decimal(38,8),
    `uncon_invest_loss` decimal(38,8),
    `prov_depr_assets` decimal(38,8),
    `depr_fa_coga_dpba` decimal(38,8),
    `amort_intang_assets` decimal(38,8),
    `lt_amort_deferred_exp` decimal(38,8),
    `decr_deferred_exp` decimal(38,8),
    `incr_acc_exp` decimal(38,8),
    `loss_disp_fiolta` decimal(38,8),
    `loss_scr_fa` decimal(38,8),
    `loss_fv_chg` decimal(38,8),
    `invest_loss` decimal(38,8),
    `decr_def_inc_tax_assets` decimal(38,8),
    `incr_def_inc_tax_liab` decimal(38,8),
    `decr_inventories` decimal(38,8),
    `decr_oper_payable` decimal(38,8),
    `incr_oper_payable` decimal(38,8),
    `others` decimal(38,8),
    `im_net_cashflow_oper_act` decimal(38,8),
    `conv_debt_into_cap` decimal(38,8),
    `conv_copbonds_due_within_1y` decimal(38,8),
    `fa_fnc_leases` decimal(38,8),
    `im_n_incr_cash_equ` decimal(38,8),
    `net_dism_capital_add` decimal(38,8),
    `net_cash_rece_sec` decimal(38,8),
    `credit_impa_loss` decimal(38,8),
    `use_right_asset_dep` decimal(38,8),
    `oth_loss_asset` decimal(38,8),
    `end_bal_cash` decimal(38,8),
    `beg_bal_cash` decimal(38,8),
    `end_bal_cash_equ` decimal(38,8),
    `beg_bal_cash_equ` decimal(38,8),
    `update_flag` longtext,
    unique(`_natural_key_hash`,`_revision_no`),
    unique(`_current_natural_key_hash`),
    check (`_revision_no` > 0),
    check (`_is_current` in (0,1)),
    check (`_valid_to` is null or `_valid_from` is null or `_valid_to` >= `_valid_from`)
);

create index if not exists `idx_src_tushare_cashflow_current`
    on `src_tushare_cashflow`(`_natural_key_hash`,`_is_current`);
create index if not exists `idx_src_tushare_cashflow_observed`
    on `src_tushare_cashflow`(`_observed_at`);

create table if not exists `src_tushare_forecast` (
    `_observation_id` varchar(64) primary key,
    `_batch_id` varchar(64) not null,
    `_natural_key_hash` varchar(64) not null,
    `_revision_no` integer not null,
    `_is_current` integer not null default 1,
    `_current_natural_key_hash` varchar(64) generated always as (case when `_is_current` = 1 then `_natural_key_hash` else null end) stored,
    `_published_at` datetime(6),
    `_source_updated_at` datetime(6),
    `_observed_at` datetime(6) not null,
    `_valid_from` datetime(6),
    `_valid_to` datetime(6),
    `_payload_hash` varchar(64) not null,
    `ts_code` longtext,
    `ann_date` date,
    `end_date` date,
    `type` longtext,
    `p_change_min` decimal(38,8),
    `p_change_max` decimal(38,8),
    `net_profit_min` decimal(38,8),
    `net_profit_max` decimal(38,8),
    `last_parent_net` decimal(38,8),
    `first_ann_date` date,
    `summary` longtext,
    `change_reason` longtext,
    unique(`_natural_key_hash`,`_revision_no`),
    unique(`_current_natural_key_hash`),
    check (`_revision_no` > 0),
    check (`_is_current` in (0,1)),
    check (`_valid_to` is null or `_valid_from` is null or `_valid_to` >= `_valid_from`)
);

create index if not exists `idx_src_tushare_forecast_current`
    on `src_tushare_forecast`(`_natural_key_hash`,`_is_current`);
create index if not exists `idx_src_tushare_forecast_observed`
    on `src_tushare_forecast`(`_observed_at`);

create table if not exists `src_tushare_express` (
    `_observation_id` varchar(64) primary key,
    `_batch_id` varchar(64) not null,
    `_natural_key_hash` varchar(64) not null,
    `_revision_no` integer not null,
    `_is_current` integer not null default 1,
    `_current_natural_key_hash` varchar(64) generated always as (case when `_is_current` = 1 then `_natural_key_hash` else null end) stored,
    `_published_at` datetime(6),
    `_source_updated_at` datetime(6),
    `_observed_at` datetime(6) not null,
    `_valid_from` datetime(6),
    `_valid_to` datetime(6),
    `_payload_hash` varchar(64) not null,
    `ts_code` longtext,
    `ann_date` date,
    `end_date` date,
    `revenue` decimal(38,8),
    `operate_profit` decimal(38,8),
    `total_profit` decimal(38,8),
    `n_income` decimal(38,8),
    `total_assets` decimal(38,8),
    `total_hldr_eqy_exc_min_int` decimal(38,8),
    `diluted_eps` decimal(38,8),
    `diluted_roe` decimal(38,8),
    `yoy_net_profit` decimal(38,8),
    `bps` decimal(38,8),
    `yoy_sales` decimal(38,8),
    `yoy_op` decimal(38,8),
    `yoy_tp` decimal(38,8),
    `yoy_dedu_np` decimal(38,8),
    `yoy_eps` decimal(38,8),
    `yoy_roe` decimal(38,8),
    `growth_assets` decimal(38,8),
    `yoy_equity` decimal(38,8),
    `growth_bps` decimal(38,8),
    `or_last_year` decimal(38,8),
    `op_last_year` decimal(38,8),
    `tp_last_year` decimal(38,8),
    `np_last_year` decimal(38,8),
    `eps_last_year` decimal(38,8),
    `open_net_assets` decimal(38,8),
    `open_bps` decimal(38,8),
    `perf_summary` longtext,
    `is_audit` bigint,
    `remark` longtext,
    unique(`_natural_key_hash`,`_revision_no`),
    unique(`_current_natural_key_hash`),
    check (`_revision_no` > 0),
    check (`_is_current` in (0,1)),
    check (`_valid_to` is null or `_valid_from` is null or `_valid_to` >= `_valid_from`)
);

create index if not exists `idx_src_tushare_express_current`
    on `src_tushare_express`(`_natural_key_hash`,`_is_current`);
create index if not exists `idx_src_tushare_express_observed`
    on `src_tushare_express`(`_observed_at`);

create table if not exists `src_tushare_dividend` (
    `_observation_id` varchar(64) primary key,
    `_batch_id` varchar(64) not null,
    `_natural_key_hash` varchar(64) not null,
    `_revision_no` integer not null,
    `_is_current` integer not null default 1,
    `_current_natural_key_hash` varchar(64) generated always as (case when `_is_current` = 1 then `_natural_key_hash` else null end) stored,
    `_published_at` datetime(6),
    `_source_updated_at` datetime(6),
    `_observed_at` datetime(6) not null,
    `_valid_from` datetime(6),
    `_valid_to` datetime(6),
    `_payload_hash` varchar(64) not null,
    `ts_code` longtext,
    `end_date` date,
    `ann_date` date,
    `div_proc` longtext,
    `stk_div` decimal(38,8),
    `stk_bo_rate` decimal(38,8),
    `stk_co_rate` decimal(38,8),
    `cash_div` decimal(38,8),
    `cash_div_tax` decimal(38,8),
    `record_date` date,
    `ex_date` date,
    `pay_date` date,
    `div_listdate` date,
    `imp_ann_date` date,
    `base_date` date,
    `base_share` decimal(38,8),
    unique(`_natural_key_hash`,`_revision_no`),
    unique(`_current_natural_key_hash`),
    check (`_revision_no` > 0),
    check (`_is_current` in (0,1)),
    check (`_valid_to` is null or `_valid_from` is null or `_valid_to` >= `_valid_from`)
);

create index if not exists `idx_src_tushare_dividend_current`
    on `src_tushare_dividend`(`_natural_key_hash`,`_is_current`);
create index if not exists `idx_src_tushare_dividend_observed`
    on `src_tushare_dividend`(`_observed_at`);

create table if not exists `src_tushare_fina_indicator` (
    `_observation_id` varchar(64) primary key,
    `_batch_id` varchar(64) not null,
    `_natural_key_hash` varchar(64) not null,
    `_revision_no` integer not null,
    `_is_current` integer not null default 1,
    `_current_natural_key_hash` varchar(64) generated always as (case when `_is_current` = 1 then `_natural_key_hash` else null end) stored,
    `_published_at` datetime(6),
    `_source_updated_at` datetime(6),
    `_observed_at` datetime(6) not null,
    `_valid_from` datetime(6),
    `_valid_to` datetime(6),
    `_payload_hash` varchar(64) not null,
    `ts_code` longtext,
    `ann_date` date,
    `end_date` date,
    `eps` decimal(38,8),
    `dt_eps` decimal(38,8),
    `total_revenue_ps` decimal(38,8),
    `revenue_ps` decimal(38,8),
    `capital_rese_ps` decimal(38,8),
    `surplus_rese_ps` decimal(38,8),
    `undist_profit_ps` decimal(38,8),
    `extra_item` decimal(38,8),
    `profit_dedt` decimal(38,8),
    `gross_margin` decimal(38,8),
    `current_ratio` decimal(38,8),
    `quick_ratio` decimal(38,8),
    `cash_ratio` decimal(38,8),
    `invturn_days` decimal(38,8),
    `arturn_days` decimal(38,8),
    `inv_turn` decimal(38,8),
    `ar_turn` decimal(38,8),
    `ca_turn` decimal(38,8),
    `fa_turn` decimal(38,8),
    `assets_turn` decimal(38,8),
    `op_income` decimal(38,8),
    `valuechange_income` decimal(38,8),
    `interst_income` decimal(38,8),
    `daa` decimal(38,8),
    `ebit` decimal(38,8),
    `ebitda` decimal(38,8),
    `fcff` decimal(38,8),
    `fcfe` decimal(38,8),
    `current_exint` decimal(38,8),
    `noncurrent_exint` decimal(38,8),
    `interestdebt` decimal(38,8),
    `netdebt` decimal(38,8),
    `tangible_asset` decimal(38,8),
    `working_capital` decimal(38,8),
    `networking_capital` decimal(38,8),
    `invest_capital` decimal(38,8),
    `retained_earnings` decimal(38,8),
    `diluted2_eps` decimal(38,8),
    `bps` decimal(38,8),
    `ocfps` decimal(38,8),
    `retainedps` decimal(38,8),
    `cfps` decimal(38,8),
    `ebit_ps` decimal(38,8),
    `fcff_ps` decimal(38,8),
    `fcfe_ps` decimal(38,8),
    `netprofit_margin` decimal(38,8),
    `grossprofit_margin` decimal(38,8),
    `cogs_of_sales` decimal(38,8),
    `expense_of_sales` decimal(38,8),
    `profit_to_gr` decimal(38,8),
    `saleexp_to_gr` decimal(38,8),
    `adminexp_of_gr` decimal(38,8),
    `finaexp_of_gr` decimal(38,8),
    `impai_ttm` decimal(38,8),
    `gc_of_gr` decimal(38,8),
    `op_of_gr` decimal(38,8),
    `ebit_of_gr` decimal(38,8),
    `roe` decimal(38,8),
    `roe_waa` decimal(38,8),
    `roe_dt` decimal(38,8),
    `roa` decimal(38,8),
    `npta` decimal(38,8),
    `roic` decimal(38,8),
    `roe_yearly` decimal(38,8),
    `roa2_yearly` decimal(38,8),
    `roe_avg` decimal(38,8),
    `opincome_of_ebt` decimal(38,8),
    `investincome_of_ebt` decimal(38,8),
    `n_op_profit_of_ebt` decimal(38,8),
    `tax_to_ebt` decimal(38,8),
    `dtprofit_to_profit` decimal(38,8),
    `salescash_to_or` decimal(38,8),
    `ocf_to_or` decimal(38,8),
    `ocf_to_opincome` decimal(38,8),
    `capitalized_to_da` decimal(38,8),
    `debt_to_assets` decimal(38,8),
    `assets_to_eqt` decimal(38,8),
    `dp_assets_to_eqt` decimal(38,8),
    `ca_to_assets` decimal(38,8),
    `nca_to_assets` decimal(38,8),
    `tbassets_to_totalassets` decimal(38,8),
    `int_to_talcap` decimal(38,8),
    `eqt_to_talcapital` decimal(38,8),
    `currentdebt_to_debt` decimal(38,8),
    `longdeb_to_debt` decimal(38,8),
    `ocf_to_shortdebt` decimal(38,8),
    `debt_to_eqt` decimal(38,8),
    `eqt_to_debt` decimal(38,8),
    `eqt_to_interestdebt` decimal(38,8),
    `tangibleasset_to_debt` decimal(38,8),
    `tangasset_to_intdebt` decimal(38,8),
    `tangibleasset_to_netdebt` decimal(38,8),
    `ocf_to_debt` decimal(38,8),
    `ocf_to_interestdebt` decimal(38,8),
    `ocf_to_netdebt` decimal(38,8),
    `ebit_to_interest` decimal(38,8),
    `longdebt_to_workingcapital` decimal(38,8),
    `ebitda_to_debt` decimal(38,8),
    `turn_days` decimal(38,8),
    `roa_yearly` decimal(38,8),
    `roa_dp` decimal(38,8),
    `fixed_assets` decimal(38,8),
    `profit_prefin_exp` decimal(38,8),
    `non_op_profit` decimal(38,8),
    `op_to_ebt` decimal(38,8),
    `nop_to_ebt` decimal(38,8),
    `ocf_to_profit` decimal(38,8),
    `cash_to_liqdebt` decimal(38,8),
    `cash_to_liqdebt_withinterest` decimal(38,8),
    `op_to_liqdebt` decimal(38,8),
    `op_to_debt` decimal(38,8),
    `roic_yearly` decimal(38,8),
    `total_fa_trun` decimal(38,8),
    `profit_to_op` decimal(38,8),
    `q_opincome` decimal(38,8),
    `q_investincome` decimal(38,8),
    `q_dtprofit` decimal(38,8),
    `q_eps` decimal(38,8),
    `q_netprofit_margin` decimal(38,8),
    `q_gsprofit_margin` decimal(38,8),
    `q_exp_to_sales` decimal(38,8),
    `q_profit_to_gr` decimal(38,8),
    `q_saleexp_to_gr` decimal(38,8),
    `q_adminexp_to_gr` decimal(38,8),
    `q_finaexp_to_gr` decimal(38,8),
    `q_impair_to_gr_ttm` decimal(38,8),
    `q_gc_to_gr` decimal(38,8),
    `q_op_to_gr` decimal(38,8),
    `q_roe` decimal(38,8),
    `q_dt_roe` decimal(38,8),
    `q_npta` decimal(38,8),
    `q_opincome_to_ebt` decimal(38,8),
    `q_investincome_to_ebt` decimal(38,8),
    `q_dtprofit_to_profit` decimal(38,8),
    `q_salescash_to_or` decimal(38,8),
    `q_ocf_to_sales` decimal(38,8),
    `q_ocf_to_or` decimal(38,8),
    `basic_eps_yoy` decimal(38,8),
    `dt_eps_yoy` decimal(38,8),
    `cfps_yoy` decimal(38,8),
    `op_yoy` decimal(38,8),
    `ebt_yoy` decimal(38,8),
    `netprofit_yoy` decimal(38,8),
    `dt_netprofit_yoy` decimal(38,8),
    `ocf_yoy` decimal(38,8),
    `roe_yoy` decimal(38,8),
    `bps_yoy` decimal(38,8),
    `assets_yoy` decimal(38,8),
    `eqt_yoy` decimal(38,8),
    `tr_yoy` decimal(38,8),
    `or_yoy` decimal(38,8),
    `q_gr_yoy` decimal(38,8),
    `q_gr_qoq` decimal(38,8),
    `q_sales_yoy` decimal(38,8),
    `q_sales_qoq` decimal(38,8),
    `q_op_yoy` decimal(38,8),
    `q_op_qoq` decimal(38,8),
    `q_profit_yoy` decimal(38,8),
    `q_profit_qoq` decimal(38,8),
    `q_netprofit_yoy` decimal(38,8),
    `q_netprofit_qoq` decimal(38,8),
    `equity_yoy` decimal(38,8),
    `rd_exp` decimal(38,8),
    `update_flag` longtext,
    unique(`_natural_key_hash`,`_revision_no`),
    unique(`_current_natural_key_hash`),
    check (`_revision_no` > 0),
    check (`_is_current` in (0,1)),
    check (`_valid_to` is null or `_valid_from` is null or `_valid_to` >= `_valid_from`)
);

create index if not exists `idx_src_tushare_fina_indicator_current`
    on `src_tushare_fina_indicator`(`_natural_key_hash`,`_is_current`);
create index if not exists `idx_src_tushare_fina_indicator_observed`
    on `src_tushare_fina_indicator`(`_observed_at`);

create table if not exists `src_tushare_fina_audit` (
    `_observation_id` varchar(64) primary key,
    `_batch_id` varchar(64) not null,
    `_natural_key_hash` varchar(64) not null,
    `_revision_no` integer not null,
    `_is_current` integer not null default 1,
    `_current_natural_key_hash` varchar(64) generated always as (case when `_is_current` = 1 then `_natural_key_hash` else null end) stored,
    `_published_at` datetime(6),
    `_source_updated_at` datetime(6),
    `_observed_at` datetime(6) not null,
    `_valid_from` datetime(6),
    `_valid_to` datetime(6),
    `_payload_hash` varchar(64) not null,
    `ts_code` longtext,
    `ann_date` date,
    `end_date` date,
    `audit_result` longtext,
    `audit_fees` decimal(38,8),
    `audit_agency` longtext,
    `audit_sign` longtext,
    unique(`_natural_key_hash`,`_revision_no`),
    unique(`_current_natural_key_hash`),
    check (`_revision_no` > 0),
    check (`_is_current` in (0,1)),
    check (`_valid_to` is null or `_valid_from` is null or `_valid_to` >= `_valid_from`)
);

create index if not exists `idx_src_tushare_fina_audit_current`
    on `src_tushare_fina_audit`(`_natural_key_hash`,`_is_current`);
create index if not exists `idx_src_tushare_fina_audit_observed`
    on `src_tushare_fina_audit`(`_observed_at`);

create table if not exists `src_tushare_fina_mainbz` (
    `_observation_id` varchar(64) primary key,
    `_batch_id` varchar(64) not null,
    `_natural_key_hash` varchar(64) not null,
    `_revision_no` integer not null,
    `_is_current` integer not null default 1,
    `_current_natural_key_hash` varchar(64) generated always as (case when `_is_current` = 1 then `_natural_key_hash` else null end) stored,
    `_published_at` datetime(6),
    `_source_updated_at` datetime(6),
    `_observed_at` datetime(6) not null,
    `_valid_from` datetime(6),
    `_valid_to` datetime(6),
    `_payload_hash` varchar(64) not null,
    `ts_code` longtext,
    `end_date` date,
    `bz_item` longtext,
    `bz_code` longtext,
    `bz_sales` decimal(38,8),
    `bz_profit` decimal(38,8),
    `bz_cost` decimal(38,8),
    `curr_type` longtext,
    `update_flag` longtext,
    unique(`_natural_key_hash`,`_revision_no`),
    unique(`_current_natural_key_hash`),
    check (`_revision_no` > 0),
    check (`_is_current` in (0,1)),
    check (`_valid_to` is null or `_valid_from` is null or `_valid_to` >= `_valid_from`)
);

create index if not exists `idx_src_tushare_fina_mainbz_current`
    on `src_tushare_fina_mainbz`(`_natural_key_hash`,`_is_current`);
create index if not exists `idx_src_tushare_fina_mainbz_observed`
    on `src_tushare_fina_mainbz`(`_observed_at`);

create table if not exists `src_tushare_disclosure_date` (
    `_observation_id` varchar(64) primary key,
    `_batch_id` varchar(64) not null,
    `_natural_key_hash` varchar(64) not null,
    `_revision_no` integer not null,
    `_is_current` integer not null default 1,
    `_current_natural_key_hash` varchar(64) generated always as (case when `_is_current` = 1 then `_natural_key_hash` else null end) stored,
    `_published_at` datetime(6),
    `_source_updated_at` datetime(6),
    `_observed_at` datetime(6) not null,
    `_valid_from` datetime(6),
    `_valid_to` datetime(6),
    `_payload_hash` varchar(64) not null,
    `ts_code` longtext,
    `ann_date` date,
    `end_date` date,
    `pre_date` date,
    `actual_date` date,
    `modify_date` date,
    unique(`_natural_key_hash`,`_revision_no`),
    unique(`_current_natural_key_hash`),
    check (`_revision_no` > 0),
    check (`_is_current` in (0,1)),
    check (`_valid_to` is null or `_valid_from` is null or `_valid_to` >= `_valid_from`)
);

create index if not exists `idx_src_tushare_disclosure_date_current`
    on `src_tushare_disclosure_date`(`_natural_key_hash`,`_is_current`);
create index if not exists `idx_src_tushare_disclosure_date_observed`
    on `src_tushare_disclosure_date`(`_observed_at`);

create table if not exists `src_tushare_stk_shock` (
    `_observation_id` varchar(64) primary key,
    `_batch_id` varchar(64) not null,
    `_natural_key_hash` varchar(64) not null,
    `_revision_no` integer not null,
    `_is_current` integer not null default 1,
    `_current_natural_key_hash` varchar(64) generated always as (case when `_is_current` = 1 then `_natural_key_hash` else null end) stored,
    `_published_at` datetime(6),
    `_source_updated_at` datetime(6),
    `_observed_at` datetime(6) not null,
    `_valid_from` datetime(6),
    `_valid_to` datetime(6),
    `_payload_hash` varchar(64) not null,
    `ts_code` longtext,
    `trade_date` date,
    `name` longtext,
    `trade_market` longtext,
    `reason` longtext,
    `period` longtext,
    unique(`_natural_key_hash`,`_revision_no`),
    unique(`_current_natural_key_hash`),
    check (`_revision_no` > 0),
    check (`_is_current` in (0,1)),
    check (`_valid_to` is null or `_valid_from` is null or `_valid_to` >= `_valid_from`)
);

create index if not exists `idx_src_tushare_stk_shock_current`
    on `src_tushare_stk_shock`(`_natural_key_hash`,`_is_current`);
create index if not exists `idx_src_tushare_stk_shock_observed`
    on `src_tushare_stk_shock`(`_observed_at`);

create table if not exists `src_tushare_stk_high_shock` (
    `_observation_id` varchar(64) primary key,
    `_batch_id` varchar(64) not null,
    `_natural_key_hash` varchar(64) not null,
    `_revision_no` integer not null,
    `_is_current` integer not null default 1,
    `_current_natural_key_hash` varchar(64) generated always as (case when `_is_current` = 1 then `_natural_key_hash` else null end) stored,
    `_published_at` datetime(6),
    `_source_updated_at` datetime(6),
    `_observed_at` datetime(6) not null,
    `_valid_from` datetime(6),
    `_valid_to` datetime(6),
    `_payload_hash` varchar(64) not null,
    `ts_code` longtext,
    `trade_date` date,
    `name` longtext,
    `trade_market` longtext,
    `reason` longtext,
    `period` longtext,
    unique(`_natural_key_hash`,`_revision_no`),
    unique(`_current_natural_key_hash`),
    check (`_revision_no` > 0),
    check (`_is_current` in (0,1)),
    check (`_valid_to` is null or `_valid_from` is null or `_valid_to` >= `_valid_from`)
);

create index if not exists `idx_src_tushare_stk_high_shock_current`
    on `src_tushare_stk_high_shock`(`_natural_key_hash`,`_is_current`);
create index if not exists `idx_src_tushare_stk_high_shock_observed`
    on `src_tushare_stk_high_shock`(`_observed_at`);

create table if not exists `src_tushare_stk_alert` (
    `_observation_id` varchar(64) primary key,
    `_batch_id` varchar(64) not null,
    `_natural_key_hash` varchar(64) not null,
    `_revision_no` integer not null,
    `_is_current` integer not null default 1,
    `_current_natural_key_hash` varchar(64) generated always as (case when `_is_current` = 1 then `_natural_key_hash` else null end) stored,
    `_published_at` datetime(6),
    `_source_updated_at` datetime(6),
    `_observed_at` datetime(6) not null,
    `_valid_from` datetime(6),
    `_valid_to` datetime(6),
    `_payload_hash` varchar(64) not null,
    `ts_code` longtext,
    `name` longtext,
    `start_date` date,
    `end_date` date,
    `type` longtext,
    unique(`_natural_key_hash`,`_revision_no`),
    unique(`_current_natural_key_hash`),
    check (`_revision_no` > 0),
    check (`_is_current` in (0,1)),
    check (`_valid_to` is null or `_valid_from` is null or `_valid_to` >= `_valid_from`)
);

create index if not exists `idx_src_tushare_stk_alert_current`
    on `src_tushare_stk_alert`(`_natural_key_hash`,`_is_current`);
create index if not exists `idx_src_tushare_stk_alert_observed`
    on `src_tushare_stk_alert`(`_observed_at`);

create table if not exists `src_tushare_top10_holders` (
    `_observation_id` varchar(64) primary key,
    `_batch_id` varchar(64) not null,
    `_natural_key_hash` varchar(64) not null,
    `_revision_no` integer not null,
    `_is_current` integer not null default 1,
    `_current_natural_key_hash` varchar(64) generated always as (case when `_is_current` = 1 then `_natural_key_hash` else null end) stored,
    `_published_at` datetime(6),
    `_source_updated_at` datetime(6),
    `_observed_at` datetime(6) not null,
    `_valid_from` datetime(6),
    `_valid_to` datetime(6),
    `_payload_hash` varchar(64) not null,
    `ts_code` longtext,
    `ann_date` date,
    `end_date` date,
    `holder_name` longtext,
    `hold_amount` decimal(38,8),
    `hold_ratio` decimal(38,8),
    `hold_float_ratio` decimal(38,8),
    `hold_change` decimal(38,8),
    `holder_type` longtext,
    unique(`_natural_key_hash`,`_revision_no`),
    unique(`_current_natural_key_hash`),
    check (`_revision_no` > 0),
    check (`_is_current` in (0,1)),
    check (`_valid_to` is null or `_valid_from` is null or `_valid_to` >= `_valid_from`)
);

create index if not exists `idx_src_tushare_top10_holders_current`
    on `src_tushare_top10_holders`(`_natural_key_hash`,`_is_current`);
create index if not exists `idx_src_tushare_top10_holders_observed`
    on `src_tushare_top10_holders`(`_observed_at`);

create table if not exists `src_tushare_top10_floatholders` (
    `_observation_id` varchar(64) primary key,
    `_batch_id` varchar(64) not null,
    `_natural_key_hash` varchar(64) not null,
    `_revision_no` integer not null,
    `_is_current` integer not null default 1,
    `_current_natural_key_hash` varchar(64) generated always as (case when `_is_current` = 1 then `_natural_key_hash` else null end) stored,
    `_published_at` datetime(6),
    `_source_updated_at` datetime(6),
    `_observed_at` datetime(6) not null,
    `_valid_from` datetime(6),
    `_valid_to` datetime(6),
    `_payload_hash` varchar(64) not null,
    `ts_code` longtext,
    `ann_date` date,
    `end_date` date,
    `holder_name` longtext,
    `hold_amount` decimal(38,8),
    `hold_ratio` decimal(38,8),
    `hold_float_ratio` decimal(38,8),
    `hold_change` decimal(38,8),
    `holder_type` longtext,
    unique(`_natural_key_hash`,`_revision_no`),
    unique(`_current_natural_key_hash`),
    check (`_revision_no` > 0),
    check (`_is_current` in (0,1)),
    check (`_valid_to` is null or `_valid_from` is null or `_valid_to` >= `_valid_from`)
);

create index if not exists `idx_src_tushare_top10_floatholders_current`
    on `src_tushare_top10_floatholders`(`_natural_key_hash`,`_is_current`);
create index if not exists `idx_src_tushare_top10_floatholders_observed`
    on `src_tushare_top10_floatholders`(`_observed_at`);

create table if not exists `src_tushare_pledge_stat` (
    `_observation_id` varchar(64) primary key,
    `_batch_id` varchar(64) not null,
    `_natural_key_hash` varchar(64) not null,
    `_revision_no` integer not null,
    `_is_current` integer not null default 1,
    `_current_natural_key_hash` varchar(64) generated always as (case when `_is_current` = 1 then `_natural_key_hash` else null end) stored,
    `_published_at` datetime(6),
    `_source_updated_at` datetime(6),
    `_observed_at` datetime(6) not null,
    `_valid_from` datetime(6),
    `_valid_to` datetime(6),
    `_payload_hash` varchar(64) not null,
    `ts_code` longtext,
    `end_date` date,
    `pledge_count` bigint,
    `unrest_pledge` decimal(38,8),
    `rest_pledge` decimal(38,8),
    `total_share` decimal(38,8),
    `pledge_ratio` decimal(38,8),
    unique(`_natural_key_hash`,`_revision_no`),
    unique(`_current_natural_key_hash`),
    check (`_revision_no` > 0),
    check (`_is_current` in (0,1)),
    check (`_valid_to` is null or `_valid_from` is null or `_valid_to` >= `_valid_from`)
);

create index if not exists `idx_src_tushare_pledge_stat_current`
    on `src_tushare_pledge_stat`(`_natural_key_hash`,`_is_current`);
create index if not exists `idx_src_tushare_pledge_stat_observed`
    on `src_tushare_pledge_stat`(`_observed_at`);

create table if not exists `src_tushare_pledge_detail` (
    `_observation_id` varchar(64) primary key,
    `_batch_id` varchar(64) not null,
    `_natural_key_hash` varchar(64) not null,
    `_revision_no` integer not null,
    `_is_current` integer not null default 1,
    `_current_natural_key_hash` varchar(64) generated always as (case when `_is_current` = 1 then `_natural_key_hash` else null end) stored,
    `_published_at` datetime(6),
    `_source_updated_at` datetime(6),
    `_observed_at` datetime(6) not null,
    `_valid_from` datetime(6),
    `_valid_to` datetime(6),
    `_payload_hash` varchar(64) not null,
    `ts_code` longtext,
    `ann_date` date,
    `holder_name` longtext,
    `pledge_amount` decimal(38,8),
    `start_date` date,
    `end_date` date,
    `is_release` longtext,
    `release_date` date,
    `pledgor` longtext,
    `holding_amount` decimal(38,8),
    `pledged_amount` decimal(38,8),
    `p_total_ratio` decimal(38,8),
    `h_total_ratio` decimal(38,8),
    `is_buyback` longtext,
    unique(`_natural_key_hash`,`_revision_no`),
    unique(`_current_natural_key_hash`),
    check (`_revision_no` > 0),
    check (`_is_current` in (0,1)),
    check (`_valid_to` is null or `_valid_from` is null or `_valid_to` >= `_valid_from`)
);

create index if not exists `idx_src_tushare_pledge_detail_current`
    on `src_tushare_pledge_detail`(`_natural_key_hash`,`_is_current`);
create index if not exists `idx_src_tushare_pledge_detail_observed`
    on `src_tushare_pledge_detail`(`_observed_at`);

create table if not exists `src_tushare_repurchase` (
    `_observation_id` varchar(64) primary key,
    `_batch_id` varchar(64) not null,
    `_natural_key_hash` varchar(64) not null,
    `_revision_no` integer not null,
    `_is_current` integer not null default 1,
    `_current_natural_key_hash` varchar(64) generated always as (case when `_is_current` = 1 then `_natural_key_hash` else null end) stored,
    `_published_at` datetime(6),
    `_source_updated_at` datetime(6),
    `_observed_at` datetime(6) not null,
    `_valid_from` datetime(6),
    `_valid_to` datetime(6),
    `_payload_hash` varchar(64) not null,
    `ts_code` longtext,
    `ann_date` date,
    `end_date` date,
    `proc` longtext,
    `exp_date` date,
    `vol` decimal(38,8),
    `amount` decimal(38,8),
    `high_limit` decimal(38,8),
    `low_limit` decimal(38,8),
    unique(`_natural_key_hash`,`_revision_no`),
    unique(`_current_natural_key_hash`),
    check (`_revision_no` > 0),
    check (`_is_current` in (0,1)),
    check (`_valid_to` is null or `_valid_from` is null or `_valid_to` >= `_valid_from`)
);

create index if not exists `idx_src_tushare_repurchase_current`
    on `src_tushare_repurchase`(`_natural_key_hash`,`_is_current`);
create index if not exists `idx_src_tushare_repurchase_observed`
    on `src_tushare_repurchase`(`_observed_at`);

create table if not exists `src_tushare_share_float` (
    `_observation_id` varchar(64) primary key,
    `_batch_id` varchar(64) not null,
    `_natural_key_hash` varchar(64) not null,
    `_revision_no` integer not null,
    `_is_current` integer not null default 1,
    `_current_natural_key_hash` varchar(64) generated always as (case when `_is_current` = 1 then `_natural_key_hash` else null end) stored,
    `_published_at` datetime(6),
    `_source_updated_at` datetime(6),
    `_observed_at` datetime(6) not null,
    `_valid_from` datetime(6),
    `_valid_to` datetime(6),
    `_payload_hash` varchar(64) not null,
    `ts_code` longtext,
    `ann_date` date,
    `float_date` date,
    `float_share` decimal(38,8),
    `float_ratio` decimal(38,8),
    `holder_name` longtext,
    `share_type` longtext,
    unique(`_natural_key_hash`,`_revision_no`),
    unique(`_current_natural_key_hash`),
    check (`_revision_no` > 0),
    check (`_is_current` in (0,1)),
    check (`_valid_to` is null or `_valid_from` is null or `_valid_to` >= `_valid_from`)
);

create index if not exists `idx_src_tushare_share_float_current`
    on `src_tushare_share_float`(`_natural_key_hash`,`_is_current`);
create index if not exists `idx_src_tushare_share_float_observed`
    on `src_tushare_share_float`(`_observed_at`);

create table if not exists `src_tushare_block_trade` (
    `_observation_id` varchar(64) primary key,
    `_batch_id` varchar(64) not null,
    `_natural_key_hash` varchar(64) not null,
    `_revision_no` integer not null,
    `_is_current` integer not null default 1,
    `_current_natural_key_hash` varchar(64) generated always as (case when `_is_current` = 1 then `_natural_key_hash` else null end) stored,
    `_published_at` datetime(6),
    `_source_updated_at` datetime(6),
    `_observed_at` datetime(6) not null,
    `_valid_from` datetime(6),
    `_valid_to` datetime(6),
    `_payload_hash` varchar(64) not null,
    `ts_code` longtext,
    `trade_date` date,
    `price` decimal(38,8),
    `vol` decimal(38,8),
    `amount` decimal(38,8),
    `buyer` longtext,
    `seller` longtext,
    unique(`_natural_key_hash`,`_revision_no`),
    unique(`_current_natural_key_hash`),
    check (`_revision_no` > 0),
    check (`_is_current` in (0,1)),
    check (`_valid_to` is null or `_valid_from` is null or `_valid_to` >= `_valid_from`)
);

create index if not exists `idx_src_tushare_block_trade_current`
    on `src_tushare_block_trade`(`_natural_key_hash`,`_is_current`);
create index if not exists `idx_src_tushare_block_trade_observed`
    on `src_tushare_block_trade`(`_observed_at`);

create table if not exists `src_tushare_stk_account` (
    `_observation_id` varchar(64) primary key,
    `_batch_id` varchar(64) not null,
    `_natural_key_hash` varchar(64) not null,
    `_revision_no` integer not null,
    `_is_current` integer not null default 1,
    `_current_natural_key_hash` varchar(64) generated always as (case when `_is_current` = 1 then `_natural_key_hash` else null end) stored,
    `_published_at` datetime(6),
    `_source_updated_at` datetime(6),
    `_observed_at` datetime(6) not null,
    `_valid_from` datetime(6),
    `_valid_to` datetime(6),
    `_payload_hash` varchar(64) not null,
    `date` date,
    `weekly_new` decimal(38,8),
    `total` decimal(38,8),
    `weekly_hold` decimal(38,8),
    `weekly_trade` decimal(38,8),
    unique(`_natural_key_hash`,`_revision_no`),
    unique(`_current_natural_key_hash`),
    check (`_revision_no` > 0),
    check (`_is_current` in (0,1)),
    check (`_valid_to` is null or `_valid_from` is null or `_valid_to` >= `_valid_from`)
);

create index if not exists `idx_src_tushare_stk_account_current`
    on `src_tushare_stk_account`(`_natural_key_hash`,`_is_current`);
create index if not exists `idx_src_tushare_stk_account_observed`
    on `src_tushare_stk_account`(`_observed_at`);

create table if not exists `src_tushare_stk_account_old` (
    `_observation_id` varchar(64) primary key,
    `_batch_id` varchar(64) not null,
    `_natural_key_hash` varchar(64) not null,
    `_revision_no` integer not null,
    `_is_current` integer not null default 1,
    `_current_natural_key_hash` varchar(64) generated always as (case when `_is_current` = 1 then `_natural_key_hash` else null end) stored,
    `_published_at` datetime(6),
    `_source_updated_at` datetime(6),
    `_observed_at` datetime(6) not null,
    `_valid_from` datetime(6),
    `_valid_to` datetime(6),
    `_payload_hash` varchar(64) not null,
    `date` date,
    `new_sh` bigint,
    `new_sz` bigint,
    `active_sh` decimal(38,8),
    `active_sz` decimal(38,8),
    `total_sh` decimal(38,8),
    `total_sz` decimal(38,8),
    `trade_sh` decimal(38,8),
    `trade_sz` decimal(38,8),
    unique(`_natural_key_hash`,`_revision_no`),
    unique(`_current_natural_key_hash`),
    check (`_revision_no` > 0),
    check (`_is_current` in (0,1)),
    check (`_valid_to` is null or `_valid_from` is null or `_valid_to` >= `_valid_from`)
);

create index if not exists `idx_src_tushare_stk_account_old_current`
    on `src_tushare_stk_account_old`(`_natural_key_hash`,`_is_current`);
create index if not exists `idx_src_tushare_stk_account_old_observed`
    on `src_tushare_stk_account_old`(`_observed_at`);

create table if not exists `src_tushare_stk_holdernumber` (
    `_observation_id` varchar(64) primary key,
    `_batch_id` varchar(64) not null,
    `_natural_key_hash` varchar(64) not null,
    `_revision_no` integer not null,
    `_is_current` integer not null default 1,
    `_current_natural_key_hash` varchar(64) generated always as (case when `_is_current` = 1 then `_natural_key_hash` else null end) stored,
    `_published_at` datetime(6),
    `_source_updated_at` datetime(6),
    `_observed_at` datetime(6) not null,
    `_valid_from` datetime(6),
    `_valid_to` datetime(6),
    `_payload_hash` varchar(64) not null,
    `ts_code` longtext,
    `ann_date` date,
    `end_date` date,
    `holder_num` bigint,
    unique(`_natural_key_hash`,`_revision_no`),
    unique(`_current_natural_key_hash`),
    check (`_revision_no` > 0),
    check (`_is_current` in (0,1)),
    check (`_valid_to` is null or `_valid_from` is null or `_valid_to` >= `_valid_from`)
);

create index if not exists `idx_src_tushare_stk_holdernumber_current`
    on `src_tushare_stk_holdernumber`(`_natural_key_hash`,`_is_current`);
create index if not exists `idx_src_tushare_stk_holdernumber_observed`
    on `src_tushare_stk_holdernumber`(`_observed_at`);

create table if not exists `src_tushare_stk_holdertrade` (
    `_observation_id` varchar(64) primary key,
    `_batch_id` varchar(64) not null,
    `_natural_key_hash` varchar(64) not null,
    `_revision_no` integer not null,
    `_is_current` integer not null default 1,
    `_current_natural_key_hash` varchar(64) generated always as (case when `_is_current` = 1 then `_natural_key_hash` else null end) stored,
    `_published_at` datetime(6),
    `_source_updated_at` datetime(6),
    `_observed_at` datetime(6) not null,
    `_valid_from` datetime(6),
    `_valid_to` datetime(6),
    `_payload_hash` varchar(64) not null,
    `ts_code` longtext,
    `ann_date` date,
    `holder_name` longtext,
    `holder_type` longtext,
    `in_de` longtext,
    `change_vol` decimal(38,8),
    `change_ratio` decimal(38,8),
    `after_share` decimal(38,8),
    `after_ratio` decimal(38,8),
    `avg_price` decimal(38,8),
    `total_share` decimal(38,8),
    `begin_date` date,
    `close_date` date,
    unique(`_natural_key_hash`,`_revision_no`),
    unique(`_current_natural_key_hash`),
    check (`_revision_no` > 0),
    check (`_is_current` in (0,1)),
    check (`_valid_to` is null or `_valid_from` is null or `_valid_to` >= `_valid_from`)
);

create index if not exists `idx_src_tushare_stk_holdertrade_current`
    on `src_tushare_stk_holdertrade`(`_natural_key_hash`,`_is_current`);
create index if not exists `idx_src_tushare_stk_holdertrade_observed`
    on `src_tushare_stk_holdertrade`(`_observed_at`);

create table if not exists `src_tushare_report_rc` (
    `_observation_id` varchar(64) primary key,
    `_batch_id` varchar(64) not null,
    `_natural_key_hash` varchar(64) not null,
    `_revision_no` integer not null,
    `_is_current` integer not null default 1,
    `_current_natural_key_hash` varchar(64) generated always as (case when `_is_current` = 1 then `_natural_key_hash` else null end) stored,
    `_published_at` datetime(6),
    `_source_updated_at` datetime(6),
    `_observed_at` datetime(6) not null,
    `_valid_from` datetime(6),
    `_valid_to` datetime(6),
    `_payload_hash` varchar(64) not null,
    `ts_code` longtext,
    `name` longtext,
    `report_date` date,
    `report_title` longtext,
    `report_type` longtext,
    `classify` longtext,
    `org_name` longtext,
    `author_name` longtext,
    `quarter` longtext,
    `op_rt` decimal(38,8),
    `op_pr` decimal(38,8),
    `tp` decimal(38,8),
    `np` decimal(38,8),
    `eps` decimal(38,8),
    `pe` decimal(38,8),
    `rd` decimal(38,8),
    `roe` decimal(38,8),
    `ev_ebitda` decimal(38,8),
    `rating` longtext,
    `max_price` decimal(38,8),
    `min_price` decimal(38,8),
    `imp_dg` longtext,
    `create_time` datetime(6),
    unique(`_natural_key_hash`,`_revision_no`),
    unique(`_current_natural_key_hash`),
    check (`_revision_no` > 0),
    check (`_is_current` in (0,1)),
    check (`_valid_to` is null or `_valid_from` is null or `_valid_to` >= `_valid_from`)
);

create index if not exists `idx_src_tushare_report_rc_current`
    on `src_tushare_report_rc`(`_natural_key_hash`,`_is_current`);
create index if not exists `idx_src_tushare_report_rc_observed`
    on `src_tushare_report_rc`(`_observed_at`);

create table if not exists `src_tushare_cyq_perf` (
    `_observation_id` varchar(64) primary key,
    `_batch_id` varchar(64) not null,
    `_natural_key_hash` varchar(64) not null,
    `_revision_no` integer not null,
    `_is_current` integer not null default 1,
    `_current_natural_key_hash` varchar(64) generated always as (case when `_is_current` = 1 then `_natural_key_hash` else null end) stored,
    `_published_at` datetime(6),
    `_source_updated_at` datetime(6),
    `_observed_at` datetime(6) not null,
    `_valid_from` datetime(6),
    `_valid_to` datetime(6),
    `_payload_hash` varchar(64) not null,
    `ts_code` longtext,
    `trade_date` date,
    `his_low` decimal(38,8),
    `his_high` decimal(38,8),
    `cost_5pct` decimal(38,8),
    `cost_15pct` decimal(38,8),
    `cost_50pct` decimal(38,8),
    `cost_85pct` decimal(38,8),
    `cost_95pct` decimal(38,8),
    `weight_avg` decimal(38,8),
    `winner_rate` decimal(38,8),
    unique(`_natural_key_hash`,`_revision_no`),
    unique(`_current_natural_key_hash`),
    check (`_revision_no` > 0),
    check (`_is_current` in (0,1)),
    check (`_valid_to` is null or `_valid_from` is null or `_valid_to` >= `_valid_from`)
);

create index if not exists `idx_src_tushare_cyq_perf_current`
    on `src_tushare_cyq_perf`(`_natural_key_hash`,`_is_current`);
create index if not exists `idx_src_tushare_cyq_perf_observed`
    on `src_tushare_cyq_perf`(`_observed_at`);

create table if not exists `src_tushare_cyq_chips` (
    `_observation_id` varchar(64) primary key,
    `_batch_id` varchar(64) not null,
    `_natural_key_hash` varchar(64) not null,
    `_revision_no` integer not null,
    `_is_current` integer not null default 1,
    `_current_natural_key_hash` varchar(64) generated always as (case when `_is_current` = 1 then `_natural_key_hash` else null end) stored,
    `_published_at` datetime(6),
    `_source_updated_at` datetime(6),
    `_observed_at` datetime(6) not null,
    `_valid_from` datetime(6),
    `_valid_to` datetime(6),
    `_payload_hash` varchar(64) not null,
    `ts_code` longtext,
    `trade_date` date,
    `price` decimal(38,8),
    `percent` decimal(38,8),
    unique(`_natural_key_hash`,`_revision_no`),
    unique(`_current_natural_key_hash`),
    check (`_revision_no` > 0),
    check (`_is_current` in (0,1)),
    check (`_valid_to` is null or `_valid_from` is null or `_valid_to` >= `_valid_from`)
);

create index if not exists `idx_src_tushare_cyq_chips_current`
    on `src_tushare_cyq_chips`(`_natural_key_hash`,`_is_current`);
create index if not exists `idx_src_tushare_cyq_chips_observed`
    on `src_tushare_cyq_chips`(`_observed_at`);

create table if not exists `src_tushare_stk_factor` (
    `_observation_id` varchar(64) primary key,
    `_batch_id` varchar(64) not null,
    `_natural_key_hash` varchar(64) not null,
    `_revision_no` integer not null,
    `_is_current` integer not null default 1,
    `_current_natural_key_hash` varchar(64) generated always as (case when `_is_current` = 1 then `_natural_key_hash` else null end) stored,
    `_published_at` datetime(6),
    `_source_updated_at` datetime(6),
    `_observed_at` datetime(6) not null,
    `_valid_from` datetime(6),
    `_valid_to` datetime(6),
    `_payload_hash` varchar(64) not null,
    `ts_code` longtext,
    `trade_date` date,
    `close` decimal(38,8),
    `open` decimal(38,8),
    `high` decimal(38,8),
    `low` decimal(38,8),
    `pre_close` decimal(38,8),
    `change` decimal(38,8),
    `pct_change` decimal(38,8),
    `vol` decimal(38,8),
    `amount` decimal(38,8),
    `adj_factor` decimal(38,8),
    `open_hfq` decimal(38,8),
    `open_qfq` decimal(38,8),
    `close_hfq` decimal(38,8),
    `close_qfq` decimal(38,8),
    `high_hfq` decimal(38,8),
    `high_qfq` decimal(38,8),
    `low_hfq` decimal(38,8),
    `low_qfq` decimal(38,8),
    `pre_close_hfq` decimal(38,8),
    `pre_close_qfq` decimal(38,8),
    `macd_dif` decimal(38,8),
    `macd_dea` decimal(38,8),
    `macd` decimal(38,8),
    `kdj_k` decimal(38,8),
    `kdj_d` decimal(38,8),
    `kdj_j` decimal(38,8),
    `rsi_6` decimal(38,8),
    `rsi_12` decimal(38,8),
    `rsi_24` decimal(38,8),
    `boll_upper` decimal(38,8),
    `boll_mid` decimal(38,8),
    `boll_lower` decimal(38,8),
    `cci` decimal(38,8),
    unique(`_natural_key_hash`,`_revision_no`),
    unique(`_current_natural_key_hash`),
    check (`_revision_no` > 0),
    check (`_is_current` in (0,1)),
    check (`_valid_to` is null or `_valid_from` is null or `_valid_to` >= `_valid_from`)
);

create index if not exists `idx_src_tushare_stk_factor_current`
    on `src_tushare_stk_factor`(`_natural_key_hash`,`_is_current`);
create index if not exists `idx_src_tushare_stk_factor_observed`
    on `src_tushare_stk_factor`(`_observed_at`);

create table if not exists `src_tushare_stk_factor_pro` (
    `_observation_id` varchar(64) primary key,
    `_batch_id` varchar(64) not null,
    `_natural_key_hash` varchar(64) not null,
    `_revision_no` integer not null,
    `_is_current` integer not null default 1,
    `_current_natural_key_hash` varchar(64) generated always as (case when `_is_current` = 1 then `_natural_key_hash` else null end) stored,
    `_published_at` datetime(6),
    `_source_updated_at` datetime(6),
    `_observed_at` datetime(6) not null,
    `_valid_from` datetime(6),
    `_valid_to` datetime(6),
    `_payload_hash` varchar(64) not null,
    `ts_code` longtext,
    `trade_date` date,
    `open` decimal(38,8),
    `open_hfq` decimal(38,8),
    `open_qfq` decimal(38,8),
    `high` decimal(38,8),
    `high_hfq` decimal(38,8),
    `high_qfq` decimal(38,8),
    `low` decimal(38,8),
    `low_hfq` decimal(38,8),
    `low_qfq` decimal(38,8),
    `close` decimal(38,8),
    `close_hfq` decimal(38,8),
    `close_qfq` decimal(38,8),
    `pre_close` decimal(38,8),
    `change` decimal(38,8),
    `pct_chg` decimal(38,8),
    `vol` decimal(38,8),
    `amount` decimal(38,8),
    `turnover_rate` decimal(38,8),
    `turnover_rate_f` decimal(38,8),
    `volume_ratio` decimal(38,8),
    `pe` decimal(38,8),
    `pe_ttm` decimal(38,8),
    `pb` decimal(38,8),
    `ps` decimal(38,8),
    `ps_ttm` decimal(38,8),
    `dv_ratio` decimal(38,8),
    `dv_ttm` decimal(38,8),
    `total_share` decimal(38,8),
    `float_share` decimal(38,8),
    `free_share` decimal(38,8),
    `total_mv` decimal(38,8),
    `circ_mv` decimal(38,8),
    `adj_factor` decimal(38,8),
    `asi_bfq` decimal(38,8),
    `asi_hfq` decimal(38,8),
    `asi_qfq` decimal(38,8),
    `asit_bfq` decimal(38,8),
    `asit_hfq` decimal(38,8),
    `asit_qfq` decimal(38,8),
    `atr_bfq` decimal(38,8),
    `atr_hfq` decimal(38,8),
    `atr_qfq` decimal(38,8),
    `bbi_bfq` decimal(38,8),
    `bbi_hfq` decimal(38,8),
    `bbi_qfq` decimal(38,8),
    `bias1_bfq` decimal(38,8),
    `bias1_hfq` decimal(38,8),
    `bias1_qfq` decimal(38,8),
    `bias2_bfq` decimal(38,8),
    `bias2_hfq` decimal(38,8),
    `bias2_qfq` decimal(38,8),
    `bias3_bfq` decimal(38,8),
    `bias3_hfq` decimal(38,8),
    `bias3_qfq` decimal(38,8),
    `boll_lower_bfq` decimal(38,8),
    `boll_lower_hfq` decimal(38,8),
    `boll_lower_qfq` decimal(38,8),
    `boll_mid_bfq` decimal(38,8),
    `boll_mid_hfq` decimal(38,8),
    `boll_mid_qfq` decimal(38,8),
    `boll_upper_bfq` decimal(38,8),
    `boll_upper_hfq` decimal(38,8),
    `boll_upper_qfq` decimal(38,8),
    `brar_ar_bfq` decimal(38,8),
    `brar_ar_hfq` decimal(38,8),
    `brar_ar_qfq` decimal(38,8),
    `brar_br_bfq` decimal(38,8),
    `brar_br_hfq` decimal(38,8),
    `brar_br_qfq` decimal(38,8),
    `cci_bfq` decimal(38,8),
    `cci_hfq` decimal(38,8),
    `cci_qfq` decimal(38,8),
    `cr_bfq` decimal(38,8),
    `cr_hfq` decimal(38,8),
    `cr_qfq` decimal(38,8),
    `dfma_dif_bfq` decimal(38,8),
    `dfma_dif_hfq` decimal(38,8),
    `dfma_dif_qfq` decimal(38,8),
    `dfma_difma_bfq` decimal(38,8),
    `dfma_difma_hfq` decimal(38,8),
    `dfma_difma_qfq` decimal(38,8),
    `dmi_adx_bfq` decimal(38,8),
    `dmi_adx_hfq` decimal(38,8),
    `dmi_adx_qfq` decimal(38,8),
    `dmi_adxr_bfq` decimal(38,8),
    `dmi_adxr_hfq` decimal(38,8),
    `dmi_adxr_qfq` decimal(38,8),
    `dmi_mdi_bfq` decimal(38,8),
    `dmi_mdi_hfq` decimal(38,8),
    `dmi_mdi_qfq` decimal(38,8),
    `dmi_pdi_bfq` decimal(38,8),
    `dmi_pdi_hfq` decimal(38,8),
    `dmi_pdi_qfq` decimal(38,8),
    `downdays` decimal(38,8),
    `updays` decimal(38,8),
    `dpo_bfq` decimal(38,8),
    `dpo_hfq` decimal(38,8),
    `dpo_qfq` decimal(38,8),
    `madpo_bfq` decimal(38,8),
    `madpo_hfq` decimal(38,8),
    `madpo_qfq` decimal(38,8),
    `ema_bfq_10` decimal(38,8),
    `ema_bfq_20` decimal(38,8),
    `ema_bfq_250` decimal(38,8),
    `ema_bfq_30` decimal(38,8),
    `ema_bfq_5` decimal(38,8),
    `ema_bfq_60` decimal(38,8),
    `ema_bfq_90` decimal(38,8),
    `ema_hfq_10` decimal(38,8),
    `ema_hfq_20` decimal(38,8),
    `ema_hfq_250` decimal(38,8),
    `ema_hfq_30` decimal(38,8),
    `ema_hfq_5` decimal(38,8),
    `ema_hfq_60` decimal(38,8),
    `ema_hfq_90` decimal(38,8),
    `ema_qfq_10` decimal(38,8),
    `ema_qfq_20` decimal(38,8),
    `ema_qfq_250` decimal(38,8),
    `ema_qfq_30` decimal(38,8),
    `ema_qfq_5` decimal(38,8),
    `ema_qfq_60` decimal(38,8),
    `ema_qfq_90` decimal(38,8),
    `emv_bfq` decimal(38,8),
    `emv_hfq` decimal(38,8),
    `emv_qfq` decimal(38,8),
    `maemv_bfq` decimal(38,8),
    `maemv_hfq` decimal(38,8),
    `maemv_qfq` decimal(38,8),
    `expma_12_bfq` decimal(38,8),
    `expma_12_hfq` decimal(38,8),
    `expma_12_qfq` decimal(38,8),
    `expma_50_bfq` decimal(38,8),
    `expma_50_hfq` decimal(38,8),
    `expma_50_qfq` decimal(38,8),
    `kdj_bfq` decimal(38,8),
    `kdj_hfq` decimal(38,8),
    `kdj_qfq` decimal(38,8),
    `kdj_d_bfq` decimal(38,8),
    `kdj_d_hfq` decimal(38,8),
    `kdj_d_qfq` decimal(38,8),
    `kdj_k_bfq` decimal(38,8),
    `kdj_k_hfq` decimal(38,8),
    `kdj_k_qfq` decimal(38,8),
    `ktn_down_bfq` decimal(38,8),
    `ktn_down_hfq` decimal(38,8),
    `ktn_down_qfq` decimal(38,8),
    `ktn_mid_bfq` decimal(38,8),
    `ktn_mid_hfq` decimal(38,8),
    `ktn_mid_qfq` decimal(38,8),
    `ktn_upper_bfq` decimal(38,8),
    `ktn_upper_hfq` decimal(38,8),
    `ktn_upper_qfq` decimal(38,8),
    `lowdays` decimal(38,8),
    `topdays` decimal(38,8),
    `ma_bfq_10` decimal(38,8),
    `ma_bfq_20` decimal(38,8),
    `ma_bfq_250` decimal(38,8),
    `ma_bfq_30` decimal(38,8),
    `ma_bfq_5` decimal(38,8),
    `ma_bfq_60` decimal(38,8),
    `ma_bfq_90` decimal(38,8),
    `ma_hfq_10` decimal(38,8),
    `ma_hfq_20` decimal(38,8),
    `ma_hfq_250` decimal(38,8),
    `ma_hfq_30` decimal(38,8),
    `ma_hfq_5` decimal(38,8),
    `ma_hfq_60` decimal(38,8),
    `ma_hfq_90` decimal(38,8),
    `ma_qfq_10` decimal(38,8),
    `ma_qfq_20` decimal(38,8),
    `ma_qfq_250` decimal(38,8),
    `ma_qfq_30` decimal(38,8),
    `ma_qfq_5` decimal(38,8),
    `ma_qfq_60` decimal(38,8),
    `ma_qfq_90` decimal(38,8),
    `macd_bfq` decimal(38,8),
    `macd_hfq` decimal(38,8),
    `macd_qfq` decimal(38,8),
    `macd_dea_bfq` decimal(38,8),
    `macd_dea_hfq` decimal(38,8),
    `macd_dea_qfq` decimal(38,8),
    `macd_dif_bfq` decimal(38,8),
    `macd_dif_hfq` decimal(38,8),
    `macd_dif_qfq` decimal(38,8),
    `mass_bfq` decimal(38,8),
    `mass_hfq` decimal(38,8),
    `mass_qfq` decimal(38,8),
    `ma_mass_bfq` decimal(38,8),
    `ma_mass_hfq` decimal(38,8),
    `ma_mass_qfq` decimal(38,8),
    `mfi_bfq` decimal(38,8),
    `mfi_hfq` decimal(38,8),
    `mfi_qfq` decimal(38,8),
    `mtm_bfq` decimal(38,8),
    `mtm_hfq` decimal(38,8),
    `mtm_qfq` decimal(38,8),
    `mtmma_bfq` decimal(38,8),
    `mtmma_hfq` decimal(38,8),
    `mtmma_qfq` decimal(38,8),
    `obv_bfq` decimal(38,8),
    `obv_hfq` decimal(38,8),
    `obv_qfq` decimal(38,8),
    `psy_bfq` decimal(38,8),
    `psy_hfq` decimal(38,8),
    `psy_qfq` decimal(38,8),
    `psyma_bfq` decimal(38,8),
    `psyma_hfq` decimal(38,8),
    `psyma_qfq` decimal(38,8),
    `roc_bfq` decimal(38,8),
    `roc_hfq` decimal(38,8),
    `roc_qfq` decimal(38,8),
    `maroc_bfq` decimal(38,8),
    `maroc_hfq` decimal(38,8),
    `maroc_qfq` decimal(38,8),
    `rsi_bfq_12` decimal(38,8),
    `rsi_bfq_24` decimal(38,8),
    `rsi_bfq_6` decimal(38,8),
    `rsi_hfq_12` decimal(38,8),
    `rsi_hfq_24` decimal(38,8),
    `rsi_hfq_6` decimal(38,8),
    `rsi_qfq_12` decimal(38,8),
    `rsi_qfq_24` decimal(38,8),
    `rsi_qfq_6` decimal(38,8),
    `taq_down_bfq` decimal(38,8),
    `taq_down_hfq` decimal(38,8),
    `taq_down_qfq` decimal(38,8),
    `taq_mid_bfq` decimal(38,8),
    `taq_mid_hfq` decimal(38,8),
    `taq_mid_qfq` decimal(38,8),
    `taq_up_bfq` decimal(38,8),
    `taq_up_hfq` decimal(38,8),
    `taq_up_qfq` decimal(38,8),
    `trix_bfq` decimal(38,8),
    `trix_hfq` decimal(38,8),
    `trix_qfq` decimal(38,8),
    `trma_bfq` decimal(38,8),
    `trma_hfq` decimal(38,8),
    `trma_qfq` decimal(38,8),
    `vr_bfq` decimal(38,8),
    `vr_hfq` decimal(38,8),
    `vr_qfq` decimal(38,8),
    `wr_bfq` decimal(38,8),
    `wr_hfq` decimal(38,8),
    `wr_qfq` decimal(38,8),
    `wr1_bfq` decimal(38,8),
    `wr1_hfq` decimal(38,8),
    `wr1_qfq` decimal(38,8),
    `xsii_td1_bfq` decimal(38,8),
    `xsii_td1_hfq` decimal(38,8),
    `xsii_td1_qfq` decimal(38,8),
    `xsii_td2_bfq` decimal(38,8),
    `xsii_td2_hfq` decimal(38,8),
    `xsii_td2_qfq` decimal(38,8),
    `xsii_td3_bfq` decimal(38,8),
    `xsii_td3_hfq` decimal(38,8),
    `xsii_td3_qfq` decimal(38,8),
    `xsii_td4_bfq` decimal(38,8),
    `xsii_td4_hfq` decimal(38,8),
    `xsii_td4_qfq` decimal(38,8),
    unique(`_natural_key_hash`,`_revision_no`),
    unique(`_current_natural_key_hash`),
    check (`_revision_no` > 0),
    check (`_is_current` in (0,1)),
    check (`_valid_to` is null or `_valid_from` is null or `_valid_to` >= `_valid_from`)
);

create index if not exists `idx_src_tushare_stk_factor_pro_current`
    on `src_tushare_stk_factor_pro`(`_natural_key_hash`,`_is_current`);
create index if not exists `idx_src_tushare_stk_factor_pro_observed`
    on `src_tushare_stk_factor_pro`(`_observed_at`);

create table if not exists `src_tushare_stk_auction_o` (
    `_observation_id` varchar(64) primary key,
    `_batch_id` varchar(64) not null,
    `_natural_key_hash` varchar(64) not null,
    `_revision_no` integer not null,
    `_is_current` integer not null default 1,
    `_current_natural_key_hash` varchar(64) generated always as (case when `_is_current` = 1 then `_natural_key_hash` else null end) stored,
    `_published_at` datetime(6),
    `_source_updated_at` datetime(6),
    `_observed_at` datetime(6) not null,
    `_valid_from` datetime(6),
    `_valid_to` datetime(6),
    `_payload_hash` varchar(64) not null,
    `ts_code` longtext,
    `trade_date` date,
    `close` decimal(38,8),
    `open` decimal(38,8),
    `high` decimal(38,8),
    `low` decimal(38,8),
    `vol` decimal(38,8),
    `amount` decimal(38,8),
    `vwap` decimal(38,8),
    unique(`_natural_key_hash`,`_revision_no`),
    unique(`_current_natural_key_hash`),
    check (`_revision_no` > 0),
    check (`_is_current` in (0,1)),
    check (`_valid_to` is null or `_valid_from` is null or `_valid_to` >= `_valid_from`)
);

create index if not exists `idx_src_tushare_stk_auction_o_current`
    on `src_tushare_stk_auction_o`(`_natural_key_hash`,`_is_current`);
create index if not exists `idx_src_tushare_stk_auction_o_observed`
    on `src_tushare_stk_auction_o`(`_observed_at`);

create table if not exists `src_tushare_stk_auction_c` (
    `_observation_id` varchar(64) primary key,
    `_batch_id` varchar(64) not null,
    `_natural_key_hash` varchar(64) not null,
    `_revision_no` integer not null,
    `_is_current` integer not null default 1,
    `_current_natural_key_hash` varchar(64) generated always as (case when `_is_current` = 1 then `_natural_key_hash` else null end) stored,
    `_published_at` datetime(6),
    `_source_updated_at` datetime(6),
    `_observed_at` datetime(6) not null,
    `_valid_from` datetime(6),
    `_valid_to` datetime(6),
    `_payload_hash` varchar(64) not null,
    `ts_code` longtext,
    `trade_date` date,
    `close` decimal(38,8),
    `open` decimal(38,8),
    `high` decimal(38,8),
    `low` decimal(38,8),
    `vol` decimal(38,8),
    `amount` decimal(38,8),
    `vwap` decimal(38,8),
    unique(`_natural_key_hash`,`_revision_no`),
    unique(`_current_natural_key_hash`),
    check (`_revision_no` > 0),
    check (`_is_current` in (0,1)),
    check (`_valid_to` is null or `_valid_from` is null or `_valid_to` >= `_valid_from`)
);

create index if not exists `idx_src_tushare_stk_auction_c_current`
    on `src_tushare_stk_auction_c`(`_natural_key_hash`,`_is_current`);
create index if not exists `idx_src_tushare_stk_auction_c_observed`
    on `src_tushare_stk_auction_c`(`_observed_at`);

create table if not exists `src_tushare_stk_nineturn` (
    `_observation_id` varchar(64) primary key,
    `_batch_id` varchar(64) not null,
    `_natural_key_hash` varchar(64) not null,
    `_revision_no` integer not null,
    `_is_current` integer not null default 1,
    `_current_natural_key_hash` varchar(64) generated always as (case when `_is_current` = 1 then `_natural_key_hash` else null end) stored,
    `_published_at` datetime(6),
    `_source_updated_at` datetime(6),
    `_observed_at` datetime(6) not null,
    `_valid_from` datetime(6),
    `_valid_to` datetime(6),
    `_payload_hash` varchar(64) not null,
    `ts_code` longtext,
    `trade_date` date,
    `freq` longtext,
    `open` decimal(38,8),
    `high` decimal(38,8),
    `low` decimal(38,8),
    `close` decimal(38,8),
    `vol` decimal(38,8),
    `amount` decimal(38,8),
    `up_count` decimal(38,8),
    `down_count` decimal(38,8),
    `nine_up_turn` longtext,
    `nine_down_turn` longtext,
    unique(`_natural_key_hash`,`_revision_no`),
    unique(`_current_natural_key_hash`),
    check (`_revision_no` > 0),
    check (`_is_current` in (0,1)),
    check (`_valid_to` is null or `_valid_from` is null or `_valid_to` >= `_valid_from`)
);

create index if not exists `idx_src_tushare_stk_nineturn_current`
    on `src_tushare_stk_nineturn`(`_natural_key_hash`,`_is_current`);
create index if not exists `idx_src_tushare_stk_nineturn_observed`
    on `src_tushare_stk_nineturn`(`_observed_at`);

create table if not exists `src_tushare_stk_ah_comparison` (
    `_observation_id` varchar(64) primary key,
    `_batch_id` varchar(64) not null,
    `_natural_key_hash` varchar(64) not null,
    `_revision_no` integer not null,
    `_is_current` integer not null default 1,
    `_current_natural_key_hash` varchar(64) generated always as (case when `_is_current` = 1 then `_natural_key_hash` else null end) stored,
    `_published_at` datetime(6),
    `_source_updated_at` datetime(6),
    `_observed_at` datetime(6) not null,
    `_valid_from` datetime(6),
    `_valid_to` datetime(6),
    `_payload_hash` varchar(64) not null,
    `hk_code` longtext,
    `ts_code` longtext,
    `trade_date` date,
    `hk_name` longtext,
    `hk_pct_chg` decimal(38,8),
    `hk_close` decimal(38,8),
    `name` longtext,
    `close` decimal(38,8),
    `pct_chg` decimal(38,8),
    `ah_comparison` decimal(38,8),
    `ah_premium` decimal(38,8),
    unique(`_natural_key_hash`,`_revision_no`),
    unique(`_current_natural_key_hash`),
    check (`_revision_no` > 0),
    check (`_is_current` in (0,1)),
    check (`_valid_to` is null or `_valid_from` is null or `_valid_to` >= `_valid_from`)
);

create index if not exists `idx_src_tushare_stk_ah_comparison_current`
    on `src_tushare_stk_ah_comparison`(`_natural_key_hash`,`_is_current`);
create index if not exists `idx_src_tushare_stk_ah_comparison_observed`
    on `src_tushare_stk_ah_comparison`(`_observed_at`);

create table if not exists `src_tushare_stk_surv` (
    `_observation_id` varchar(64) primary key,
    `_batch_id` varchar(64) not null,
    `_natural_key_hash` varchar(64) not null,
    `_revision_no` integer not null,
    `_is_current` integer not null default 1,
    `_current_natural_key_hash` varchar(64) generated always as (case when `_is_current` = 1 then `_natural_key_hash` else null end) stored,
    `_published_at` datetime(6),
    `_source_updated_at` datetime(6),
    `_observed_at` datetime(6) not null,
    `_valid_from` datetime(6),
    `_valid_to` datetime(6),
    `_payload_hash` varchar(64) not null,
    `ts_code` longtext,
    `name` longtext,
    `surv_date` date,
    `fund_visitors` longtext,
    `rece_place` longtext,
    `rece_mode` longtext,
    `rece_org` longtext,
    `org_type` longtext,
    `comp_rece` longtext,
    `content` longtext,
    unique(`_natural_key_hash`,`_revision_no`),
    unique(`_current_natural_key_hash`),
    check (`_revision_no` > 0),
    check (`_is_current` in (0,1)),
    check (`_valid_to` is null or `_valid_from` is null or `_valid_to` >= `_valid_from`)
);

create index if not exists `idx_src_tushare_stk_surv_current`
    on `src_tushare_stk_surv`(`_natural_key_hash`,`_is_current`);
create index if not exists `idx_src_tushare_stk_surv_observed`
    on `src_tushare_stk_surv`(`_observed_at`);

create table if not exists `src_tushare_broker_recommend` (
    `_observation_id` varchar(64) primary key,
    `_batch_id` varchar(64) not null,
    `_natural_key_hash` varchar(64) not null,
    `_revision_no` integer not null,
    `_is_current` integer not null default 1,
    `_current_natural_key_hash` varchar(64) generated always as (case when `_is_current` = 1 then `_natural_key_hash` else null end) stored,
    `_published_at` datetime(6),
    `_source_updated_at` datetime(6),
    `_observed_at` datetime(6) not null,
    `_valid_from` datetime(6),
    `_valid_to` datetime(6),
    `_payload_hash` varchar(64) not null,
    `month` longtext,
    `broker` longtext,
    `ts_code` longtext,
    `name` longtext,
    unique(`_natural_key_hash`,`_revision_no`),
    unique(`_current_natural_key_hash`),
    check (`_revision_no` > 0),
    check (`_is_current` in (0,1)),
    check (`_valid_to` is null or `_valid_from` is null or `_valid_to` >= `_valid_from`)
);

create index if not exists `idx_src_tushare_broker_recommend_current`
    on `src_tushare_broker_recommend`(`_natural_key_hash`,`_is_current`);
create index if not exists `idx_src_tushare_broker_recommend_observed`
    on `src_tushare_broker_recommend`(`_observed_at`);

create table if not exists `src_tushare_margin` (
    `_observation_id` varchar(64) primary key,
    `_batch_id` varchar(64) not null,
    `_natural_key_hash` varchar(64) not null,
    `_revision_no` integer not null,
    `_is_current` integer not null default 1,
    `_current_natural_key_hash` varchar(64) generated always as (case when `_is_current` = 1 then `_natural_key_hash` else null end) stored,
    `_published_at` datetime(6),
    `_source_updated_at` datetime(6),
    `_observed_at` datetime(6) not null,
    `_valid_from` datetime(6),
    `_valid_to` datetime(6),
    `_payload_hash` varchar(64) not null,
    `trade_date` date,
    `exchange_id` longtext,
    `rzye` decimal(38,8),
    `rzmre` decimal(38,8),
    `rzche` decimal(38,8),
    `rqye` decimal(38,8),
    `rqmcl` decimal(38,8),
    `rzrqye` decimal(38,8),
    `rqyl` decimal(38,8),
    unique(`_natural_key_hash`,`_revision_no`),
    unique(`_current_natural_key_hash`),
    check (`_revision_no` > 0),
    check (`_is_current` in (0,1)),
    check (`_valid_to` is null or `_valid_from` is null or `_valid_to` >= `_valid_from`)
);

create index if not exists `idx_src_tushare_margin_current`
    on `src_tushare_margin`(`_natural_key_hash`,`_is_current`);
create index if not exists `idx_src_tushare_margin_observed`
    on `src_tushare_margin`(`_observed_at`);

create table if not exists `src_tushare_margin_detail` (
    `_observation_id` varchar(64) primary key,
    `_batch_id` varchar(64) not null,
    `_natural_key_hash` varchar(64) not null,
    `_revision_no` integer not null,
    `_is_current` integer not null default 1,
    `_current_natural_key_hash` varchar(64) generated always as (case when `_is_current` = 1 then `_natural_key_hash` else null end) stored,
    `_published_at` datetime(6),
    `_source_updated_at` datetime(6),
    `_observed_at` datetime(6) not null,
    `_valid_from` datetime(6),
    `_valid_to` datetime(6),
    `_payload_hash` varchar(64) not null,
    `trade_date` date,
    `ts_code` longtext,
    `name` longtext,
    `rzye` decimal(38,8),
    `rqye` decimal(38,8),
    `rzmre` decimal(38,8),
    `rqyl` decimal(38,8),
    `rzche` decimal(38,8),
    `rqchl` decimal(38,8),
    `rqmcl` decimal(38,8),
    `rzrqye` decimal(38,8),
    unique(`_natural_key_hash`,`_revision_no`),
    unique(`_current_natural_key_hash`),
    check (`_revision_no` > 0),
    check (`_is_current` in (0,1)),
    check (`_valid_to` is null or `_valid_from` is null or `_valid_to` >= `_valid_from`)
);

create index if not exists `idx_src_tushare_margin_detail_current`
    on `src_tushare_margin_detail`(`_natural_key_hash`,`_is_current`);
create index if not exists `idx_src_tushare_margin_detail_observed`
    on `src_tushare_margin_detail`(`_observed_at`);

create table if not exists `src_tushare_margin_secs` (
    `_observation_id` varchar(64) primary key,
    `_batch_id` varchar(64) not null,
    `_natural_key_hash` varchar(64) not null,
    `_revision_no` integer not null,
    `_is_current` integer not null default 1,
    `_current_natural_key_hash` varchar(64) generated always as (case when `_is_current` = 1 then `_natural_key_hash` else null end) stored,
    `_published_at` datetime(6),
    `_source_updated_at` datetime(6),
    `_observed_at` datetime(6) not null,
    `_valid_from` datetime(6),
    `_valid_to` datetime(6),
    `_payload_hash` varchar(64) not null,
    `trade_date` date,
    `ts_code` longtext,
    `name` longtext,
    `exchange` longtext,
    unique(`_natural_key_hash`,`_revision_no`),
    unique(`_current_natural_key_hash`),
    check (`_revision_no` > 0),
    check (`_is_current` in (0,1)),
    check (`_valid_to` is null or `_valid_from` is null or `_valid_to` >= `_valid_from`)
);

create index if not exists `idx_src_tushare_margin_secs_current`
    on `src_tushare_margin_secs`(`_natural_key_hash`,`_is_current`);
create index if not exists `idx_src_tushare_margin_secs_observed`
    on `src_tushare_margin_secs`(`_observed_at`);

create table if not exists `src_tushare_slb_sec` (
    `_observation_id` varchar(64) primary key,
    `_batch_id` varchar(64) not null,
    `_natural_key_hash` varchar(64) not null,
    `_revision_no` integer not null,
    `_is_current` integer not null default 1,
    `_current_natural_key_hash` varchar(64) generated always as (case when `_is_current` = 1 then `_natural_key_hash` else null end) stored,
    `_published_at` datetime(6),
    `_source_updated_at` datetime(6),
    `_observed_at` datetime(6) not null,
    `_valid_from` datetime(6),
    `_valid_to` datetime(6),
    `_payload_hash` varchar(64) not null,
    `trade_date` date,
    `ts_code` longtext,
    `name` longtext,
    `ope_inv` decimal(38,8),
    `lent_qnt` decimal(38,8),
    `cls_inv` decimal(38,8),
    `end_bal` decimal(38,8),
    unique(`_natural_key_hash`,`_revision_no`),
    unique(`_current_natural_key_hash`),
    check (`_revision_no` > 0),
    check (`_is_current` in (0,1)),
    check (`_valid_to` is null or `_valid_from` is null or `_valid_to` >= `_valid_from`)
);

create index if not exists `idx_src_tushare_slb_sec_current`
    on `src_tushare_slb_sec`(`_natural_key_hash`,`_is_current`);
create index if not exists `idx_src_tushare_slb_sec_observed`
    on `src_tushare_slb_sec`(`_observed_at`);

create table if not exists `src_tushare_slb_len` (
    `_observation_id` varchar(64) primary key,
    `_batch_id` varchar(64) not null,
    `_natural_key_hash` varchar(64) not null,
    `_revision_no` integer not null,
    `_is_current` integer not null default 1,
    `_current_natural_key_hash` varchar(64) generated always as (case when `_is_current` = 1 then `_natural_key_hash` else null end) stored,
    `_published_at` datetime(6),
    `_source_updated_at` datetime(6),
    `_observed_at` datetime(6) not null,
    `_valid_from` datetime(6),
    `_valid_to` datetime(6),
    `_payload_hash` varchar(64) not null,
    `trade_date` date,
    `ob` decimal(38,8),
    `auc_amount` decimal(38,8),
    `repo_amount` decimal(38,8),
    `repay_amount` decimal(38,8),
    `cb` decimal(38,8),
    unique(`_natural_key_hash`,`_revision_no`),
    unique(`_current_natural_key_hash`),
    check (`_revision_no` > 0),
    check (`_is_current` in (0,1)),
    check (`_valid_to` is null or `_valid_from` is null or `_valid_to` >= `_valid_from`)
);

create index if not exists `idx_src_tushare_slb_len_current`
    on `src_tushare_slb_len`(`_natural_key_hash`,`_is_current`);
create index if not exists `idx_src_tushare_slb_len_observed`
    on `src_tushare_slb_len`(`_observed_at`);

create table if not exists `src_tushare_slb_sec_detail` (
    `_observation_id` varchar(64) primary key,
    `_batch_id` varchar(64) not null,
    `_natural_key_hash` varchar(64) not null,
    `_revision_no` integer not null,
    `_is_current` integer not null default 1,
    `_current_natural_key_hash` varchar(64) generated always as (case when `_is_current` = 1 then `_natural_key_hash` else null end) stored,
    `_published_at` datetime(6),
    `_source_updated_at` datetime(6),
    `_observed_at` datetime(6) not null,
    `_valid_from` datetime(6),
    `_valid_to` datetime(6),
    `_payload_hash` varchar(64) not null,
    `trade_date` date,
    `ts_code` longtext,
    `name` longtext,
    `tenor` longtext,
    `fee_rate` decimal(38,8),
    `lent_qnt` decimal(38,8),
    unique(`_natural_key_hash`,`_revision_no`),
    unique(`_current_natural_key_hash`),
    check (`_revision_no` > 0),
    check (`_is_current` in (0,1)),
    check (`_valid_to` is null or `_valid_from` is null or `_valid_to` >= `_valid_from`)
);

create index if not exists `idx_src_tushare_slb_sec_detail_current`
    on `src_tushare_slb_sec_detail`(`_natural_key_hash`,`_is_current`);
create index if not exists `idx_src_tushare_slb_sec_detail_observed`
    on `src_tushare_slb_sec_detail`(`_observed_at`);

create table if not exists `src_tushare_slb_len_mm` (
    `_observation_id` varchar(64) primary key,
    `_batch_id` varchar(64) not null,
    `_natural_key_hash` varchar(64) not null,
    `_revision_no` integer not null,
    `_is_current` integer not null default 1,
    `_current_natural_key_hash` varchar(64) generated always as (case when `_is_current` = 1 then `_natural_key_hash` else null end) stored,
    `_published_at` datetime(6),
    `_source_updated_at` datetime(6),
    `_observed_at` datetime(6) not null,
    `_valid_from` datetime(6),
    `_valid_to` datetime(6),
    `_payload_hash` varchar(64) not null,
    `trade_date` date,
    `ts_code` longtext,
    `name` longtext,
    `ope_inv` decimal(38,8),
    `lent_qnt` decimal(38,8),
    `cls_inv` decimal(38,8),
    `end_bal` decimal(38,8),
    unique(`_natural_key_hash`,`_revision_no`),
    unique(`_current_natural_key_hash`),
    check (`_revision_no` > 0),
    check (`_is_current` in (0,1)),
    check (`_valid_to` is null or `_valid_from` is null or `_valid_to` >= `_valid_from`)
);

create index if not exists `idx_src_tushare_slb_len_mm_current`
    on `src_tushare_slb_len_mm`(`_natural_key_hash`,`_is_current`);
create index if not exists `idx_src_tushare_slb_len_mm_observed`
    on `src_tushare_slb_len_mm`(`_observed_at`);

create table if not exists `src_tushare_moneyflow` (
    `_observation_id` varchar(64) primary key,
    `_batch_id` varchar(64) not null,
    `_natural_key_hash` varchar(64) not null,
    `_revision_no` integer not null,
    `_is_current` integer not null default 1,
    `_current_natural_key_hash` varchar(64) generated always as (case when `_is_current` = 1 then `_natural_key_hash` else null end) stored,
    `_published_at` datetime(6),
    `_source_updated_at` datetime(6),
    `_observed_at` datetime(6) not null,
    `_valid_from` datetime(6),
    `_valid_to` datetime(6),
    `_payload_hash` varchar(64) not null,
    `ts_code` longtext,
    `trade_date` date,
    `buy_sm_vol` bigint,
    `buy_sm_amount` decimal(38,8),
    `sell_sm_vol` bigint,
    `sell_sm_amount` decimal(38,8),
    `buy_md_vol` bigint,
    `buy_md_amount` decimal(38,8),
    `sell_md_vol` bigint,
    `sell_md_amount` decimal(38,8),
    `buy_lg_vol` bigint,
    `buy_lg_amount` decimal(38,8),
    `sell_lg_vol` bigint,
    `sell_lg_amount` decimal(38,8),
    `buy_elg_vol` bigint,
    `buy_elg_amount` decimal(38,8),
    `sell_elg_vol` bigint,
    `sell_elg_amount` decimal(38,8),
    `net_mf_vol` bigint,
    `net_mf_amount` decimal(38,8),
    unique(`_natural_key_hash`,`_revision_no`),
    unique(`_current_natural_key_hash`),
    check (`_revision_no` > 0),
    check (`_is_current` in (0,1)),
    check (`_valid_to` is null or `_valid_from` is null or `_valid_to` >= `_valid_from`)
);

create index if not exists `idx_src_tushare_moneyflow_current`
    on `src_tushare_moneyflow`(`_natural_key_hash`,`_is_current`);
create index if not exists `idx_src_tushare_moneyflow_observed`
    on `src_tushare_moneyflow`(`_observed_at`);

create table if not exists `src_tushare_moneyflow_ths` (
    `_observation_id` varchar(64) primary key,
    `_batch_id` varchar(64) not null,
    `_natural_key_hash` varchar(64) not null,
    `_revision_no` integer not null,
    `_is_current` integer not null default 1,
    `_current_natural_key_hash` varchar(64) generated always as (case when `_is_current` = 1 then `_natural_key_hash` else null end) stored,
    `_published_at` datetime(6),
    `_source_updated_at` datetime(6),
    `_observed_at` datetime(6) not null,
    `_valid_from` datetime(6),
    `_valid_to` datetime(6),
    `_payload_hash` varchar(64) not null,
    `trade_date` date,
    `ts_code` longtext,
    `name` longtext,
    `pct_change` decimal(38,8),
    `latest` decimal(38,8),
    `net_amount` decimal(38,8),
    `net_d5_amount` decimal(38,8),
    `buy_lg_amount` decimal(38,8),
    `buy_lg_amount_rate` decimal(38,8),
    `buy_md_amount` decimal(38,8),
    `buy_md_amount_rate` decimal(38,8),
    `buy_sm_amount` decimal(38,8),
    `buy_sm_amount_rate` decimal(38,8),
    unique(`_natural_key_hash`,`_revision_no`),
    unique(`_current_natural_key_hash`),
    check (`_revision_no` > 0),
    check (`_is_current` in (0,1)),
    check (`_valid_to` is null or `_valid_from` is null or `_valid_to` >= `_valid_from`)
);

create index if not exists `idx_src_tushare_moneyflow_ths_current`
    on `src_tushare_moneyflow_ths`(`_natural_key_hash`,`_is_current`);
create index if not exists `idx_src_tushare_moneyflow_ths_observed`
    on `src_tushare_moneyflow_ths`(`_observed_at`);

create table if not exists `src_tushare_moneyflow_dc` (
    `_observation_id` varchar(64) primary key,
    `_batch_id` varchar(64) not null,
    `_natural_key_hash` varchar(64) not null,
    `_revision_no` integer not null,
    `_is_current` integer not null default 1,
    `_current_natural_key_hash` varchar(64) generated always as (case when `_is_current` = 1 then `_natural_key_hash` else null end) stored,
    `_published_at` datetime(6),
    `_source_updated_at` datetime(6),
    `_observed_at` datetime(6) not null,
    `_valid_from` datetime(6),
    `_valid_to` datetime(6),
    `_payload_hash` varchar(64) not null,
    `trade_date` date,
    `ts_code` longtext,
    `name` longtext,
    `pct_change` decimal(38,8),
    `close` decimal(38,8),
    `net_amount` decimal(38,8),
    `net_amount_rate` decimal(38,8),
    `buy_elg_amount` decimal(38,8),
    `buy_elg_amount_rate` decimal(38,8),
    `buy_lg_amount` decimal(38,8),
    `buy_lg_amount_rate` decimal(38,8),
    `buy_md_amount` decimal(38,8),
    `buy_md_amount_rate` decimal(38,8),
    `buy_sm_amount` decimal(38,8),
    `buy_sm_amount_rate` decimal(38,8),
    unique(`_natural_key_hash`,`_revision_no`),
    unique(`_current_natural_key_hash`),
    check (`_revision_no` > 0),
    check (`_is_current` in (0,1)),
    check (`_valid_to` is null or `_valid_from` is null or `_valid_to` >= `_valid_from`)
);

create index if not exists `idx_src_tushare_moneyflow_dc_current`
    on `src_tushare_moneyflow_dc`(`_natural_key_hash`,`_is_current`);
create index if not exists `idx_src_tushare_moneyflow_dc_observed`
    on `src_tushare_moneyflow_dc`(`_observed_at`);

create table if not exists `src_tushare_moneyflow_cnt_ths` (
    `_observation_id` varchar(64) primary key,
    `_batch_id` varchar(64) not null,
    `_natural_key_hash` varchar(64) not null,
    `_revision_no` integer not null,
    `_is_current` integer not null default 1,
    `_current_natural_key_hash` varchar(64) generated always as (case when `_is_current` = 1 then `_natural_key_hash` else null end) stored,
    `_published_at` datetime(6),
    `_source_updated_at` datetime(6),
    `_observed_at` datetime(6) not null,
    `_valid_from` datetime(6),
    `_valid_to` datetime(6),
    `_payload_hash` varchar(64) not null,
    `trade_date` date,
    `ts_code` longtext,
    `name` longtext,
    `lead_stock` longtext,
    `close_price` decimal(38,8),
    `pct_change` decimal(38,8),
    `industry_index` decimal(38,8),
    `company_num` bigint,
    `pct_change_stock` decimal(38,8),
    `net_buy_amount` decimal(38,8),
    `net_sell_amount` decimal(38,8),
    `net_amount` decimal(38,8),
    unique(`_natural_key_hash`,`_revision_no`),
    unique(`_current_natural_key_hash`),
    check (`_revision_no` > 0),
    check (`_is_current` in (0,1)),
    check (`_valid_to` is null or `_valid_from` is null or `_valid_to` >= `_valid_from`)
);

create index if not exists `idx_src_tushare_moneyflow_cnt_ths_current`
    on `src_tushare_moneyflow_cnt_ths`(`_natural_key_hash`,`_is_current`);
create index if not exists `idx_src_tushare_moneyflow_cnt_ths_observed`
    on `src_tushare_moneyflow_cnt_ths`(`_observed_at`);

create table if not exists `src_tushare_moneyflow_ind_ths` (
    `_observation_id` varchar(64) primary key,
    `_batch_id` varchar(64) not null,
    `_natural_key_hash` varchar(64) not null,
    `_revision_no` integer not null,
    `_is_current` integer not null default 1,
    `_current_natural_key_hash` varchar(64) generated always as (case when `_is_current` = 1 then `_natural_key_hash` else null end) stored,
    `_published_at` datetime(6),
    `_source_updated_at` datetime(6),
    `_observed_at` datetime(6) not null,
    `_valid_from` datetime(6),
    `_valid_to` datetime(6),
    `_payload_hash` varchar(64) not null,
    `trade_date` date,
    `ts_code` longtext,
    `industry` longtext,
    `lead_stock` longtext,
    `close` decimal(38,8),
    `pct_change` decimal(38,8),
    `company_num` bigint,
    `pct_change_stock` decimal(38,8),
    `close_price` decimal(38,8),
    `net_buy_amount` decimal(38,8),
    `net_sell_amount` decimal(38,8),
    `net_amount` decimal(38,8),
    unique(`_natural_key_hash`,`_revision_no`),
    unique(`_current_natural_key_hash`),
    check (`_revision_no` > 0),
    check (`_is_current` in (0,1)),
    check (`_valid_to` is null or `_valid_from` is null or `_valid_to` >= `_valid_from`)
);

create index if not exists `idx_src_tushare_moneyflow_ind_ths_current`
    on `src_tushare_moneyflow_ind_ths`(`_natural_key_hash`,`_is_current`);
create index if not exists `idx_src_tushare_moneyflow_ind_ths_observed`
    on `src_tushare_moneyflow_ind_ths`(`_observed_at`);

create table if not exists `src_tushare_moneyflow_ind_dc` (
    `_observation_id` varchar(64) primary key,
    `_batch_id` varchar(64) not null,
    `_natural_key_hash` varchar(64) not null,
    `_revision_no` integer not null,
    `_is_current` integer not null default 1,
    `_current_natural_key_hash` varchar(64) generated always as (case when `_is_current` = 1 then `_natural_key_hash` else null end) stored,
    `_published_at` datetime(6),
    `_source_updated_at` datetime(6),
    `_observed_at` datetime(6) not null,
    `_valid_from` datetime(6),
    `_valid_to` datetime(6),
    `_payload_hash` varchar(64) not null,
    `trade_date` date,
    `content_type` longtext,
    `ts_code` longtext,
    `name` longtext,
    `pct_change` decimal(38,8),
    `close` decimal(38,8),
    `net_amount` decimal(38,8),
    `net_amount_rate` decimal(38,8),
    `buy_elg_amount` decimal(38,8),
    `buy_elg_amount_rate` decimal(38,8),
    `buy_lg_amount` decimal(38,8),
    `buy_lg_amount_rate` decimal(38,8),
    `buy_md_amount` decimal(38,8),
    `buy_md_amount_rate` decimal(38,8),
    `buy_sm_amount` decimal(38,8),
    `buy_sm_amount_rate` decimal(38,8),
    `buy_sm_amount_stock` longtext,
    `rank` bigint,
    unique(`_natural_key_hash`,`_revision_no`),
    unique(`_current_natural_key_hash`),
    check (`_revision_no` > 0),
    check (`_is_current` in (0,1)),
    check (`_valid_to` is null or `_valid_from` is null or `_valid_to` >= `_valid_from`)
);

create index if not exists `idx_src_tushare_moneyflow_ind_dc_current`
    on `src_tushare_moneyflow_ind_dc`(`_natural_key_hash`,`_is_current`);
create index if not exists `idx_src_tushare_moneyflow_ind_dc_observed`
    on `src_tushare_moneyflow_ind_dc`(`_observed_at`);

create table if not exists `src_tushare_moneyflow_mkt_dc` (
    `_observation_id` varchar(64) primary key,
    `_batch_id` varchar(64) not null,
    `_natural_key_hash` varchar(64) not null,
    `_revision_no` integer not null,
    `_is_current` integer not null default 1,
    `_current_natural_key_hash` varchar(64) generated always as (case when `_is_current` = 1 then `_natural_key_hash` else null end) stored,
    `_published_at` datetime(6),
    `_source_updated_at` datetime(6),
    `_observed_at` datetime(6) not null,
    `_valid_from` datetime(6),
    `_valid_to` datetime(6),
    `_payload_hash` varchar(64) not null,
    `trade_date` date,
    `close_sh` decimal(38,8),
    `pct_change_sh` decimal(38,8),
    `close_sz` decimal(38,8),
    `pct_change_sz` decimal(38,8),
    `net_amount` decimal(38,8),
    `net_amount_rate` decimal(38,8),
    `buy_elg_amount` decimal(38,8),
    `buy_elg_amount_rate` decimal(38,8),
    `buy_lg_amount` decimal(38,8),
    `buy_lg_amount_rate` decimal(38,8),
    `buy_md_amount` decimal(38,8),
    `buy_md_amount_rate` decimal(38,8),
    `buy_sm_amount` decimal(38,8),
    `buy_sm_amount_rate` decimal(38,8),
    unique(`_natural_key_hash`,`_revision_no`),
    unique(`_current_natural_key_hash`),
    check (`_revision_no` > 0),
    check (`_is_current` in (0,1)),
    check (`_valid_to` is null or `_valid_from` is null or `_valid_to` >= `_valid_from`)
);

create index if not exists `idx_src_tushare_moneyflow_mkt_dc_current`
    on `src_tushare_moneyflow_mkt_dc`(`_natural_key_hash`,`_is_current`);
create index if not exists `idx_src_tushare_moneyflow_mkt_dc_observed`
    on `src_tushare_moneyflow_mkt_dc`(`_observed_at`);

create table if not exists `src_tushare_top_list` (
    `_observation_id` varchar(64) primary key,
    `_batch_id` varchar(64) not null,
    `_natural_key_hash` varchar(64) not null,
    `_revision_no` integer not null,
    `_is_current` integer not null default 1,
    `_current_natural_key_hash` varchar(64) generated always as (case when `_is_current` = 1 then `_natural_key_hash` else null end) stored,
    `_published_at` datetime(6),
    `_source_updated_at` datetime(6),
    `_observed_at` datetime(6) not null,
    `_valid_from` datetime(6),
    `_valid_to` datetime(6),
    `_payload_hash` varchar(64) not null,
    `trade_date` date,
    `ts_code` longtext,
    `name` longtext,
    `close` decimal(38,8),
    `pct_change` decimal(38,8),
    `turnover_rate` decimal(38,8),
    `amount` decimal(38,8),
    `l_sell` decimal(38,8),
    `l_buy` decimal(38,8),
    `l_amount` decimal(38,8),
    `net_amount` decimal(38,8),
    `net_rate` decimal(38,8),
    `amount_rate` decimal(38,8),
    `float_values` decimal(38,8),
    `reason` longtext,
    unique(`_natural_key_hash`,`_revision_no`),
    unique(`_current_natural_key_hash`),
    check (`_revision_no` > 0),
    check (`_is_current` in (0,1)),
    check (`_valid_to` is null or `_valid_from` is null or `_valid_to` >= `_valid_from`)
);

create index if not exists `idx_src_tushare_top_list_current`
    on `src_tushare_top_list`(`_natural_key_hash`,`_is_current`);
create index if not exists `idx_src_tushare_top_list_observed`
    on `src_tushare_top_list`(`_observed_at`);

create table if not exists `src_tushare_top_inst` (
    `_observation_id` varchar(64) primary key,
    `_batch_id` varchar(64) not null,
    `_natural_key_hash` varchar(64) not null,
    `_revision_no` integer not null,
    `_is_current` integer not null default 1,
    `_current_natural_key_hash` varchar(64) generated always as (case when `_is_current` = 1 then `_natural_key_hash` else null end) stored,
    `_published_at` datetime(6),
    `_source_updated_at` datetime(6),
    `_observed_at` datetime(6) not null,
    `_valid_from` datetime(6),
    `_valid_to` datetime(6),
    `_payload_hash` varchar(64) not null,
    `trade_date` date,
    `ts_code` longtext,
    `exalter` longtext,
    `side` longtext,
    `buy` decimal(38,8),
    `buy_rate` decimal(38,8),
    `sell` decimal(38,8),
    `sell_rate` decimal(38,8),
    `net_buy` decimal(38,8),
    `reason` longtext,
    unique(`_natural_key_hash`,`_revision_no`),
    unique(`_current_natural_key_hash`),
    check (`_revision_no` > 0),
    check (`_is_current` in (0,1)),
    check (`_valid_to` is null or `_valid_from` is null or `_valid_to` >= `_valid_from`)
);

create index if not exists `idx_src_tushare_top_inst_current`
    on `src_tushare_top_inst`(`_natural_key_hash`,`_is_current`);
create index if not exists `idx_src_tushare_top_inst_observed`
    on `src_tushare_top_inst`(`_observed_at`);

create table if not exists `src_tushare_limit_list_ths` (
    `_observation_id` varchar(64) primary key,
    `_batch_id` varchar(64) not null,
    `_natural_key_hash` varchar(64) not null,
    `_revision_no` integer not null,
    `_is_current` integer not null default 1,
    `_current_natural_key_hash` varchar(64) generated always as (case when `_is_current` = 1 then `_natural_key_hash` else null end) stored,
    `_published_at` datetime(6),
    `_source_updated_at` datetime(6),
    `_observed_at` datetime(6) not null,
    `_valid_from` datetime(6),
    `_valid_to` datetime(6),
    `_payload_hash` varchar(64) not null,
    `trade_date` date,
    `ts_code` longtext,
    `name` longtext,
    `price` decimal(38,8),
    `pct_chg` decimal(38,8),
    `open_num` bigint,
    `lu_desc` longtext,
    `limit_type` longtext,
    `tag` longtext,
    `status` longtext,
    `first_lu_time` datetime(6),
    `last_lu_time` datetime(6),
    `first_ld_time` datetime(6),
    `last_ld_time` datetime(6),
    `limit_order` decimal(38,8),
    `limit_amount` decimal(38,8),
    `turnover_rate` decimal(38,8),
    `free_float` decimal(38,8),
    `lu_limit_order` decimal(38,8),
    `limit_up_suc_rate` decimal(38,8),
    `turnover` decimal(38,8),
    `rise_rate` decimal(38,8),
    `sum_float` decimal(38,8),
    `market_type` longtext,
    unique(`_natural_key_hash`,`_revision_no`),
    unique(`_current_natural_key_hash`),
    check (`_revision_no` > 0),
    check (`_is_current` in (0,1)),
    check (`_valid_to` is null or `_valid_from` is null or `_valid_to` >= `_valid_from`)
);

create index if not exists `idx_src_tushare_limit_list_ths_current`
    on `src_tushare_limit_list_ths`(`_natural_key_hash`,`_is_current`);
create index if not exists `idx_src_tushare_limit_list_ths_observed`
    on `src_tushare_limit_list_ths`(`_observed_at`);

create table if not exists `src_tushare_limit_list_d` (
    `_observation_id` varchar(64) primary key,
    `_batch_id` varchar(64) not null,
    `_natural_key_hash` varchar(64) not null,
    `_revision_no` integer not null,
    `_is_current` integer not null default 1,
    `_current_natural_key_hash` varchar(64) generated always as (case when `_is_current` = 1 then `_natural_key_hash` else null end) stored,
    `_published_at` datetime(6),
    `_source_updated_at` datetime(6),
    `_observed_at` datetime(6) not null,
    `_valid_from` datetime(6),
    `_valid_to` datetime(6),
    `_payload_hash` varchar(64) not null,
    `trade_date` date,
    `ts_code` longtext,
    `industry` longtext,
    `name` longtext,
    `close` decimal(38,8),
    `pct_chg` decimal(38,8),
    `amount` decimal(38,8),
    `limit_amount` decimal(38,8),
    `float_mv` decimal(38,8),
    `total_mv` decimal(38,8),
    `turnover_ratio` decimal(38,8),
    `fd_amount` decimal(38,8),
    `first_time` datetime(6),
    `last_time` datetime(6),
    `open_times` datetime(6),
    `up_stat` longtext,
    `limit_times` datetime(6),
    `limit` longtext,
    unique(`_natural_key_hash`,`_revision_no`),
    unique(`_current_natural_key_hash`),
    check (`_revision_no` > 0),
    check (`_is_current` in (0,1)),
    check (`_valid_to` is null or `_valid_from` is null or `_valid_to` >= `_valid_from`)
);

create index if not exists `idx_src_tushare_limit_list_d_current`
    on `src_tushare_limit_list_d`(`_natural_key_hash`,`_is_current`);
create index if not exists `idx_src_tushare_limit_list_d_observed`
    on `src_tushare_limit_list_d`(`_observed_at`);

create table if not exists `src_tushare_limit_step` (
    `_observation_id` varchar(64) primary key,
    `_batch_id` varchar(64) not null,
    `_natural_key_hash` varchar(64) not null,
    `_revision_no` integer not null,
    `_is_current` integer not null default 1,
    `_current_natural_key_hash` varchar(64) generated always as (case when `_is_current` = 1 then `_natural_key_hash` else null end) stored,
    `_published_at` datetime(6),
    `_source_updated_at` datetime(6),
    `_observed_at` datetime(6) not null,
    `_valid_from` datetime(6),
    `_valid_to` datetime(6),
    `_payload_hash` varchar(64) not null,
    `ts_code` longtext,
    `name` longtext,
    `trade_date` date,
    `nums` longtext,
    unique(`_natural_key_hash`,`_revision_no`),
    unique(`_current_natural_key_hash`),
    check (`_revision_no` > 0),
    check (`_is_current` in (0,1)),
    check (`_valid_to` is null or `_valid_from` is null or `_valid_to` >= `_valid_from`)
);

create index if not exists `idx_src_tushare_limit_step_current`
    on `src_tushare_limit_step`(`_natural_key_hash`,`_is_current`);
create index if not exists `idx_src_tushare_limit_step_observed`
    on `src_tushare_limit_step`(`_observed_at`);

create table if not exists `src_tushare_limit_cpt_list` (
    `_observation_id` varchar(64) primary key,
    `_batch_id` varchar(64) not null,
    `_natural_key_hash` varchar(64) not null,
    `_revision_no` integer not null,
    `_is_current` integer not null default 1,
    `_current_natural_key_hash` varchar(64) generated always as (case when `_is_current` = 1 then `_natural_key_hash` else null end) stored,
    `_published_at` datetime(6),
    `_source_updated_at` datetime(6),
    `_observed_at` datetime(6) not null,
    `_valid_from` datetime(6),
    `_valid_to` datetime(6),
    `_payload_hash` varchar(64) not null,
    `ts_code` longtext,
    `name` longtext,
    `trade_date` date,
    `days` bigint,
    `up_stat` longtext,
    `cons_nums` bigint,
    `up_nums` bigint,
    `pct_chg` decimal(38,8),
    `rank` longtext,
    unique(`_natural_key_hash`,`_revision_no`),
    unique(`_current_natural_key_hash`),
    check (`_revision_no` > 0),
    check (`_is_current` in (0,1)),
    check (`_valid_to` is null or `_valid_from` is null or `_valid_to` >= `_valid_from`)
);

create index if not exists `idx_src_tushare_limit_cpt_list_current`
    on `src_tushare_limit_cpt_list`(`_natural_key_hash`,`_is_current`);
create index if not exists `idx_src_tushare_limit_cpt_list_observed`
    on `src_tushare_limit_cpt_list`(`_observed_at`);

create table if not exists `src_tushare_ths_index` (
    `_observation_id` varchar(64) primary key,
    `_batch_id` varchar(64) not null,
    `_natural_key_hash` varchar(64) not null,
    `_revision_no` integer not null,
    `_is_current` integer not null default 1,
    `_current_natural_key_hash` varchar(64) generated always as (case when `_is_current` = 1 then `_natural_key_hash` else null end) stored,
    `_published_at` datetime(6),
    `_source_updated_at` datetime(6),
    `_observed_at` datetime(6) not null,
    `_valid_from` datetime(6),
    `_valid_to` datetime(6),
    `_payload_hash` varchar(64) not null,
    `ts_code` longtext,
    `name` longtext,
    `count` bigint,
    `exchange` longtext,
    `list_date` date,
    `type` longtext,
    unique(`_natural_key_hash`,`_revision_no`),
    unique(`_current_natural_key_hash`),
    check (`_revision_no` > 0),
    check (`_is_current` in (0,1)),
    check (`_valid_to` is null or `_valid_from` is null or `_valid_to` >= `_valid_from`)
);

create index if not exists `idx_src_tushare_ths_index_current`
    on `src_tushare_ths_index`(`_natural_key_hash`,`_is_current`);
create index if not exists `idx_src_tushare_ths_index_observed`
    on `src_tushare_ths_index`(`_observed_at`);

create table if not exists `src_tushare_ths_daily` (
    `_observation_id` varchar(64) primary key,
    `_batch_id` varchar(64) not null,
    `_natural_key_hash` varchar(64) not null,
    `_revision_no` integer not null,
    `_is_current` integer not null default 1,
    `_current_natural_key_hash` varchar(64) generated always as (case when `_is_current` = 1 then `_natural_key_hash` else null end) stored,
    `_published_at` datetime(6),
    `_source_updated_at` datetime(6),
    `_observed_at` datetime(6) not null,
    `_valid_from` datetime(6),
    `_valid_to` datetime(6),
    `_payload_hash` varchar(64) not null,
    `ts_code` longtext,
    `trade_date` date,
    `close` decimal(38,8),
    `open` decimal(38,8),
    `high` decimal(38,8),
    `low` decimal(38,8),
    `pre_close` decimal(38,8),
    `avg_price` decimal(38,8),
    `change` decimal(38,8),
    `pct_change` decimal(38,8),
    `vol` decimal(38,8),
    `turnover_rate` decimal(38,8),
    `total_mv` decimal(38,8),
    `float_mv` decimal(38,8),
    unique(`_natural_key_hash`,`_revision_no`),
    unique(`_current_natural_key_hash`),
    check (`_revision_no` > 0),
    check (`_is_current` in (0,1)),
    check (`_valid_to` is null or `_valid_from` is null or `_valid_to` >= `_valid_from`)
);

create index if not exists `idx_src_tushare_ths_daily_current`
    on `src_tushare_ths_daily`(`_natural_key_hash`,`_is_current`);
create index if not exists `idx_src_tushare_ths_daily_observed`
    on `src_tushare_ths_daily`(`_observed_at`);

create table if not exists `src_tushare_ths_member` (
    `_observation_id` varchar(64) primary key,
    `_batch_id` varchar(64) not null,
    `_natural_key_hash` varchar(64) not null,
    `_revision_no` integer not null,
    `_is_current` integer not null default 1,
    `_current_natural_key_hash` varchar(64) generated always as (case when `_is_current` = 1 then `_natural_key_hash` else null end) stored,
    `_published_at` datetime(6),
    `_source_updated_at` datetime(6),
    `_observed_at` datetime(6) not null,
    `_valid_from` datetime(6),
    `_valid_to` datetime(6),
    `_payload_hash` varchar(64) not null,
    `ts_code` longtext,
    `con_code` longtext,
    `con_name` longtext,
    `weight` decimal(38,8),
    `in_date` date,
    `out_date` date,
    `is_new` longtext,
    unique(`_natural_key_hash`,`_revision_no`),
    unique(`_current_natural_key_hash`),
    check (`_revision_no` > 0),
    check (`_is_current` in (0,1)),
    check (`_valid_to` is null or `_valid_from` is null or `_valid_to` >= `_valid_from`)
);

create index if not exists `idx_src_tushare_ths_member_current`
    on `src_tushare_ths_member`(`_natural_key_hash`,`_is_current`);
create index if not exists `idx_src_tushare_ths_member_observed`
    on `src_tushare_ths_member`(`_observed_at`);

create table if not exists `src_tushare_dc_index` (
    `_observation_id` varchar(64) primary key,
    `_batch_id` varchar(64) not null,
    `_natural_key_hash` varchar(64) not null,
    `_revision_no` integer not null,
    `_is_current` integer not null default 1,
    `_current_natural_key_hash` varchar(64) generated always as (case when `_is_current` = 1 then `_natural_key_hash` else null end) stored,
    `_published_at` datetime(6),
    `_source_updated_at` datetime(6),
    `_observed_at` datetime(6) not null,
    `_valid_from` datetime(6),
    `_valid_to` datetime(6),
    `_payload_hash` varchar(64) not null,
    `ts_code` longtext,
    `trade_date` date,
    `name` longtext,
    `leading` longtext,
    `leading_code` longtext,
    `pct_change` decimal(38,8),
    `leading_pct` decimal(38,8),
    `total_mv` decimal(38,8),
    `turnover_rate` decimal(38,8),
    `up_num` bigint,
    `down_num` bigint,
    `idx_type` longtext,
    `level` longtext,
    unique(`_natural_key_hash`,`_revision_no`),
    unique(`_current_natural_key_hash`),
    check (`_revision_no` > 0),
    check (`_is_current` in (0,1)),
    check (`_valid_to` is null or `_valid_from` is null or `_valid_to` >= `_valid_from`)
);

create index if not exists `idx_src_tushare_dc_index_current`
    on `src_tushare_dc_index`(`_natural_key_hash`,`_is_current`);
create index if not exists `idx_src_tushare_dc_index_observed`
    on `src_tushare_dc_index`(`_observed_at`);

create table if not exists `src_tushare_dc_member` (
    `_observation_id` varchar(64) primary key,
    `_batch_id` varchar(64) not null,
    `_natural_key_hash` varchar(64) not null,
    `_revision_no` integer not null,
    `_is_current` integer not null default 1,
    `_current_natural_key_hash` varchar(64) generated always as (case when `_is_current` = 1 then `_natural_key_hash` else null end) stored,
    `_published_at` datetime(6),
    `_source_updated_at` datetime(6),
    `_observed_at` datetime(6) not null,
    `_valid_from` datetime(6),
    `_valid_to` datetime(6),
    `_payload_hash` varchar(64) not null,
    `trade_date` date,
    `ts_code` longtext,
    `con_code` longtext,
    `name` longtext,
    unique(`_natural_key_hash`,`_revision_no`),
    unique(`_current_natural_key_hash`),
    check (`_revision_no` > 0),
    check (`_is_current` in (0,1)),
    check (`_valid_to` is null or `_valid_from` is null or `_valid_to` >= `_valid_from`)
);

create index if not exists `idx_src_tushare_dc_member_current`
    on `src_tushare_dc_member`(`_natural_key_hash`,`_is_current`);
create index if not exists `idx_src_tushare_dc_member_observed`
    on `src_tushare_dc_member`(`_observed_at`);

create table if not exists `src_tushare_dc_daily` (
    `_observation_id` varchar(64) primary key,
    `_batch_id` varchar(64) not null,
    `_natural_key_hash` varchar(64) not null,
    `_revision_no` integer not null,
    `_is_current` integer not null default 1,
    `_current_natural_key_hash` varchar(64) generated always as (case when `_is_current` = 1 then `_natural_key_hash` else null end) stored,
    `_published_at` datetime(6),
    `_source_updated_at` datetime(6),
    `_observed_at` datetime(6) not null,
    `_valid_from` datetime(6),
    `_valid_to` datetime(6),
    `_payload_hash` varchar(64) not null,
    `ts_code` longtext,
    `trade_date` date,
    `close` decimal(38,8),
    `open` decimal(38,8),
    `high` decimal(38,8),
    `low` decimal(38,8),
    `change` decimal(38,8),
    `pct_change` decimal(38,8),
    `vol` decimal(38,8),
    `amount` decimal(38,8),
    `swing` decimal(38,8),
    `turnover_rate` decimal(38,8),
    unique(`_natural_key_hash`,`_revision_no`),
    unique(`_current_natural_key_hash`),
    check (`_revision_no` > 0),
    check (`_is_current` in (0,1)),
    check (`_valid_to` is null or `_valid_from` is null or `_valid_to` >= `_valid_from`)
);

create index if not exists `idx_src_tushare_dc_daily_current`
    on `src_tushare_dc_daily`(`_natural_key_hash`,`_is_current`);
create index if not exists `idx_src_tushare_dc_daily_observed`
    on `src_tushare_dc_daily`(`_observed_at`);

create table if not exists `src_tushare_stk_auction` (
    `_observation_id` varchar(64) primary key,
    `_batch_id` varchar(64) not null,
    `_natural_key_hash` varchar(64) not null,
    `_revision_no` integer not null,
    `_is_current` integer not null default 1,
    `_current_natural_key_hash` varchar(64) generated always as (case when `_is_current` = 1 then `_natural_key_hash` else null end) stored,
    `_published_at` datetime(6),
    `_source_updated_at` datetime(6),
    `_observed_at` datetime(6) not null,
    `_valid_from` datetime(6),
    `_valid_to` datetime(6),
    `_payload_hash` varchar(64) not null,
    `ts_code` longtext,
    `trade_date` date,
    `vol` bigint,
    `price` bigint,
    `amount` decimal(38,8),
    `pre_close` decimal(38,8),
    `turnover_rate` decimal(38,8),
    `volume_ratio` decimal(38,8),
    `float_share` decimal(38,8),
    unique(`_natural_key_hash`,`_revision_no`),
    unique(`_current_natural_key_hash`),
    check (`_revision_no` > 0),
    check (`_is_current` in (0,1)),
    check (`_valid_to` is null or `_valid_from` is null or `_valid_to` >= `_valid_from`)
);

create index if not exists `idx_src_tushare_stk_auction_current`
    on `src_tushare_stk_auction`(`_natural_key_hash`,`_is_current`);
create index if not exists `idx_src_tushare_stk_auction_observed`
    on `src_tushare_stk_auction`(`_observed_at`);

create table if not exists `src_tushare_hm_list` (
    `_observation_id` varchar(64) primary key,
    `_batch_id` varchar(64) not null,
    `_natural_key_hash` varchar(64) not null,
    `_revision_no` integer not null,
    `_is_current` integer not null default 1,
    `_current_natural_key_hash` varchar(64) generated always as (case when `_is_current` = 1 then `_natural_key_hash` else null end) stored,
    `_published_at` datetime(6),
    `_source_updated_at` datetime(6),
    `_observed_at` datetime(6) not null,
    `_valid_from` datetime(6),
    `_valid_to` datetime(6),
    `_payload_hash` varchar(64) not null,
    `name` longtext,
    `desc` longtext,
    `orgs` longtext,
    unique(`_natural_key_hash`,`_revision_no`),
    unique(`_current_natural_key_hash`),
    check (`_revision_no` > 0),
    check (`_is_current` in (0,1)),
    check (`_valid_to` is null or `_valid_from` is null or `_valid_to` >= `_valid_from`)
);

create index if not exists `idx_src_tushare_hm_list_current`
    on `src_tushare_hm_list`(`_natural_key_hash`,`_is_current`);
create index if not exists `idx_src_tushare_hm_list_observed`
    on `src_tushare_hm_list`(`_observed_at`);

create table if not exists `src_tushare_hm_detail` (
    `_observation_id` varchar(64) primary key,
    `_batch_id` varchar(64) not null,
    `_natural_key_hash` varchar(64) not null,
    `_revision_no` integer not null,
    `_is_current` integer not null default 1,
    `_current_natural_key_hash` varchar(64) generated always as (case when `_is_current` = 1 then `_natural_key_hash` else null end) stored,
    `_published_at` datetime(6),
    `_source_updated_at` datetime(6),
    `_observed_at` datetime(6) not null,
    `_valid_from` datetime(6),
    `_valid_to` datetime(6),
    `_payload_hash` varchar(64) not null,
    `trade_date` date,
    `ts_code` longtext,
    `ts_name` longtext,
    `buy_amount` decimal(38,8),
    `sell_amount` decimal(38,8),
    `net_amount` decimal(38,8),
    `hm_name` longtext,
    `hm_orgs` longtext,
    `tag` longtext,
    unique(`_natural_key_hash`,`_revision_no`),
    unique(`_current_natural_key_hash`),
    check (`_revision_no` > 0),
    check (`_is_current` in (0,1)),
    check (`_valid_to` is null or `_valid_from` is null or `_valid_to` >= `_valid_from`)
);

create index if not exists `idx_src_tushare_hm_detail_current`
    on `src_tushare_hm_detail`(`_natural_key_hash`,`_is_current`);
create index if not exists `idx_src_tushare_hm_detail_observed`
    on `src_tushare_hm_detail`(`_observed_at`);

create table if not exists `src_tushare_ths_hot` (
    `_observation_id` varchar(64) primary key,
    `_batch_id` varchar(64) not null,
    `_natural_key_hash` varchar(64) not null,
    `_revision_no` integer not null,
    `_is_current` integer not null default 1,
    `_current_natural_key_hash` varchar(64) generated always as (case when `_is_current` = 1 then `_natural_key_hash` else null end) stored,
    `_published_at` datetime(6),
    `_source_updated_at` datetime(6),
    `_observed_at` datetime(6) not null,
    `_valid_from` datetime(6),
    `_valid_to` datetime(6),
    `_payload_hash` varchar(64) not null,
    `trade_date` date,
    `data_type` longtext,
    `ts_code` longtext,
    `ts_name` longtext,
    `rank` bigint,
    `pct_change` decimal(38,8),
    `current_price` decimal(38,8),
    `concept` longtext,
    `rank_reason` longtext,
    `hot` decimal(38,8),
    `rank_time` datetime(6),
    unique(`_natural_key_hash`,`_revision_no`),
    unique(`_current_natural_key_hash`),
    check (`_revision_no` > 0),
    check (`_is_current` in (0,1)),
    check (`_valid_to` is null or `_valid_from` is null or `_valid_to` >= `_valid_from`)
);

create index if not exists `idx_src_tushare_ths_hot_current`
    on `src_tushare_ths_hot`(`_natural_key_hash`,`_is_current`);
create index if not exists `idx_src_tushare_ths_hot_observed`
    on `src_tushare_ths_hot`(`_observed_at`);

create table if not exists `src_tushare_dc_hot` (
    `_observation_id` varchar(64) primary key,
    `_batch_id` varchar(64) not null,
    `_natural_key_hash` varchar(64) not null,
    `_revision_no` integer not null,
    `_is_current` integer not null default 1,
    `_current_natural_key_hash` varchar(64) generated always as (case when `_is_current` = 1 then `_natural_key_hash` else null end) stored,
    `_published_at` datetime(6),
    `_source_updated_at` datetime(6),
    `_observed_at` datetime(6) not null,
    `_valid_from` datetime(6),
    `_valid_to` datetime(6),
    `_payload_hash` varchar(64) not null,
    `trade_date` date,
    `data_type` longtext,
    `ts_code` longtext,
    `ts_name` longtext,
    `rank` bigint,
    `pct_change` decimal(38,8),
    `current_price` decimal(38,8),
    `rank_time` datetime(6),
    unique(`_natural_key_hash`,`_revision_no`),
    unique(`_current_natural_key_hash`),
    check (`_revision_no` > 0),
    check (`_is_current` in (0,1)),
    check (`_valid_to` is null or `_valid_from` is null or `_valid_to` >= `_valid_from`)
);

create index if not exists `idx_src_tushare_dc_hot_current`
    on `src_tushare_dc_hot`(`_natural_key_hash`,`_is_current`);
create index if not exists `idx_src_tushare_dc_hot_observed`
    on `src_tushare_dc_hot`(`_observed_at`);

create table if not exists `src_tushare_tdx_index` (
    `_observation_id` varchar(64) primary key,
    `_batch_id` varchar(64) not null,
    `_natural_key_hash` varchar(64) not null,
    `_revision_no` integer not null,
    `_is_current` integer not null default 1,
    `_current_natural_key_hash` varchar(64) generated always as (case when `_is_current` = 1 then `_natural_key_hash` else null end) stored,
    `_published_at` datetime(6),
    `_source_updated_at` datetime(6),
    `_observed_at` datetime(6) not null,
    `_valid_from` datetime(6),
    `_valid_to` datetime(6),
    `_payload_hash` varchar(64) not null,
    `ts_code` longtext,
    `trade_date` date,
    `name` longtext,
    `idx_type` longtext,
    `idx_count` bigint,
    `total_share` decimal(38,8),
    `float_share` decimal(38,8),
    `total_mv` decimal(38,8),
    `float_mv` decimal(38,8),
    unique(`_natural_key_hash`,`_revision_no`),
    unique(`_current_natural_key_hash`),
    check (`_revision_no` > 0),
    check (`_is_current` in (0,1)),
    check (`_valid_to` is null or `_valid_from` is null or `_valid_to` >= `_valid_from`)
);

create index if not exists `idx_src_tushare_tdx_index_current`
    on `src_tushare_tdx_index`(`_natural_key_hash`,`_is_current`);
create index if not exists `idx_src_tushare_tdx_index_observed`
    on `src_tushare_tdx_index`(`_observed_at`);

create table if not exists `src_tushare_tdx_member` (
    `_observation_id` varchar(64) primary key,
    `_batch_id` varchar(64) not null,
    `_natural_key_hash` varchar(64) not null,
    `_revision_no` integer not null,
    `_is_current` integer not null default 1,
    `_current_natural_key_hash` varchar(64) generated always as (case when `_is_current` = 1 then `_natural_key_hash` else null end) stored,
    `_published_at` datetime(6),
    `_source_updated_at` datetime(6),
    `_observed_at` datetime(6) not null,
    `_valid_from` datetime(6),
    `_valid_to` datetime(6),
    `_payload_hash` varchar(64) not null,
    `ts_code` longtext,
    `trade_date` date,
    `con_code` longtext,
    `con_name` longtext,
    unique(`_natural_key_hash`,`_revision_no`),
    unique(`_current_natural_key_hash`),
    check (`_revision_no` > 0),
    check (`_is_current` in (0,1)),
    check (`_valid_to` is null or `_valid_from` is null or `_valid_to` >= `_valid_from`)
);

create index if not exists `idx_src_tushare_tdx_member_current`
    on `src_tushare_tdx_member`(`_natural_key_hash`,`_is_current`);
create index if not exists `idx_src_tushare_tdx_member_observed`
    on `src_tushare_tdx_member`(`_observed_at`);

create table if not exists `src_tushare_tdx_daily` (
    `_observation_id` varchar(64) primary key,
    `_batch_id` varchar(64) not null,
    `_natural_key_hash` varchar(64) not null,
    `_revision_no` integer not null,
    `_is_current` integer not null default 1,
    `_current_natural_key_hash` varchar(64) generated always as (case when `_is_current` = 1 then `_natural_key_hash` else null end) stored,
    `_published_at` datetime(6),
    `_source_updated_at` datetime(6),
    `_observed_at` datetime(6) not null,
    `_valid_from` datetime(6),
    `_valid_to` datetime(6),
    `_payload_hash` varchar(64) not null,
    `ts_code` longtext,
    `trade_date` date,
    `close` decimal(38,8),
    `open` decimal(38,8),
    `high` decimal(38,8),
    `low` decimal(38,8),
    `pre_close` decimal(38,8),
    `change` decimal(38,8),
    `pct_change` decimal(38,8),
    `vol` decimal(38,8),
    `amount` decimal(38,8),
    `rise` longtext,
    `vol_ratio` decimal(38,8),
    `turnover_rate` decimal(38,8),
    `swing` decimal(38,8),
    `up_num` bigint,
    `down_num` bigint,
    `limit_up_num` bigint,
    `limit_down_num` bigint,
    `lu_days` bigint,
    `field_3day` decimal(38,8),
    `field_5day` decimal(38,8),
    `field_10day` decimal(38,8),
    `field_20day` decimal(38,8),
    `field_60day` decimal(38,8),
    `mtd` decimal(38,8),
    `ytd` decimal(38,8),
    `field_1year` decimal(38,8),
    `pe` longtext,
    `pb` longtext,
    `float_mv` decimal(38,8),
    `ab_total_mv` decimal(38,8),
    `float_share` decimal(38,8),
    `total_share` decimal(38,8),
    `bm_buy_net` decimal(38,8),
    `bm_buy_ratio` decimal(38,8),
    `bm_net` decimal(38,8),
    `bm_ratio` decimal(38,8),
    unique(`_natural_key_hash`,`_revision_no`),
    unique(`_current_natural_key_hash`),
    check (`_revision_no` > 0),
    check (`_is_current` in (0,1)),
    check (`_valid_to` is null or `_valid_from` is null or `_valid_to` >= `_valid_from`)
);

create index if not exists `idx_src_tushare_tdx_daily_current`
    on `src_tushare_tdx_daily`(`_natural_key_hash`,`_is_current`);
create index if not exists `idx_src_tushare_tdx_daily_observed`
    on `src_tushare_tdx_daily`(`_observed_at`);

create table if not exists `src_tushare_kpl_list` (
    `_observation_id` varchar(64) primary key,
    `_batch_id` varchar(64) not null,
    `_natural_key_hash` varchar(64) not null,
    `_revision_no` integer not null,
    `_is_current` integer not null default 1,
    `_current_natural_key_hash` varchar(64) generated always as (case when `_is_current` = 1 then `_natural_key_hash` else null end) stored,
    `_published_at` datetime(6),
    `_source_updated_at` datetime(6),
    `_observed_at` datetime(6) not null,
    `_valid_from` datetime(6),
    `_valid_to` datetime(6),
    `_payload_hash` varchar(64) not null,
    `ts_code` longtext,
    `name` longtext,
    `trade_date` date,
    `lu_time` datetime(6),
    `ld_time` datetime(6),
    `open_time` datetime(6),
    `last_time` datetime(6),
    `lu_desc` longtext,
    `tag` longtext,
    `theme` longtext,
    `net_change` decimal(38,8),
    `bid_amount` decimal(38,8),
    `status` longtext,
    `bid_change` decimal(38,8),
    `bid_turnover` decimal(38,8),
    `lu_bid_vol` decimal(38,8),
    `pct_chg` decimal(38,8),
    `bid_pct_chg` decimal(38,8),
    `rt_pct_chg` decimal(38,8),
    `limit_order` decimal(38,8),
    `amount` decimal(38,8),
    `turnover_rate` decimal(38,8),
    `free_float` decimal(38,8),
    `lu_limit_order` decimal(38,8),
    unique(`_natural_key_hash`,`_revision_no`),
    unique(`_current_natural_key_hash`),
    check (`_revision_no` > 0),
    check (`_is_current` in (0,1)),
    check (`_valid_to` is null or `_valid_from` is null or `_valid_to` >= `_valid_from`)
);

create index if not exists `idx_src_tushare_kpl_list_current`
    on `src_tushare_kpl_list`(`_natural_key_hash`,`_is_current`);
create index if not exists `idx_src_tushare_kpl_list_observed`
    on `src_tushare_kpl_list`(`_observed_at`);

create table if not exists `src_tushare_kpl_concept_cons` (
    `_observation_id` varchar(64) primary key,
    `_batch_id` varchar(64) not null,
    `_natural_key_hash` varchar(64) not null,
    `_revision_no` integer not null,
    `_is_current` integer not null default 1,
    `_current_natural_key_hash` varchar(64) generated always as (case when `_is_current` = 1 then `_natural_key_hash` else null end) stored,
    `_published_at` datetime(6),
    `_source_updated_at` datetime(6),
    `_observed_at` datetime(6) not null,
    `_valid_from` datetime(6),
    `_valid_to` datetime(6),
    `_payload_hash` varchar(64) not null,
    `ts_code` longtext,
    `name` longtext,
    `con_name` longtext,
    `con_code` longtext,
    `trade_date` date,
    `desc` longtext,
    `hot_num` bigint,
    unique(`_natural_key_hash`,`_revision_no`),
    unique(`_current_natural_key_hash`),
    check (`_revision_no` > 0),
    check (`_is_current` in (0,1)),
    check (`_valid_to` is null or `_valid_from` is null or `_valid_to` >= `_valid_from`)
);

create index if not exists `idx_src_tushare_kpl_concept_cons_current`
    on `src_tushare_kpl_concept_cons`(`_natural_key_hash`,`_is_current`);
create index if not exists `idx_src_tushare_kpl_concept_cons_observed`
    on `src_tushare_kpl_concept_cons`(`_observed_at`);

create table if not exists `src_tushare_dc_concept` (
    `_observation_id` varchar(64) primary key,
    `_batch_id` varchar(64) not null,
    `_natural_key_hash` varchar(64) not null,
    `_revision_no` integer not null,
    `_is_current` integer not null default 1,
    `_current_natural_key_hash` varchar(64) generated always as (case when `_is_current` = 1 then `_natural_key_hash` else null end) stored,
    `_published_at` datetime(6),
    `_source_updated_at` datetime(6),
    `_observed_at` datetime(6) not null,
    `_valid_from` datetime(6),
    `_valid_to` datetime(6),
    `_payload_hash` varchar(64) not null,
    `theme_code` longtext,
    `trade_date` date,
    `name` longtext,
    `pct_change` longtext,
    `hot` longtext,
    `sort` longtext,
    `strength` longtext,
    `z_t_num` longtext,
    `main_change` longtext,
    `lead_stock` longtext,
    `lead_stock_code` longtext,
    `lead_stock_pct_change` longtext,
    unique(`_natural_key_hash`,`_revision_no`),
    unique(`_current_natural_key_hash`),
    check (`_revision_no` > 0),
    check (`_is_current` in (0,1)),
    check (`_valid_to` is null or `_valid_from` is null or `_valid_to` >= `_valid_from`)
);

create index if not exists `idx_src_tushare_dc_concept_current`
    on `src_tushare_dc_concept`(`_natural_key_hash`,`_is_current`);
create index if not exists `idx_src_tushare_dc_concept_observed`
    on `src_tushare_dc_concept`(`_observed_at`);

create table if not exists `src_tushare_dc_concept_cons` (
    `_observation_id` varchar(64) primary key,
    `_batch_id` varchar(64) not null,
    `_natural_key_hash` varchar(64) not null,
    `_revision_no` integer not null,
    `_is_current` integer not null default 1,
    `_current_natural_key_hash` varchar(64) generated always as (case when `_is_current` = 1 then `_natural_key_hash` else null end) stored,
    `_published_at` datetime(6),
    `_source_updated_at` datetime(6),
    `_observed_at` datetime(6) not null,
    `_valid_from` datetime(6),
    `_valid_to` datetime(6),
    `_payload_hash` varchar(64) not null,
    `ts_code` longtext,
    `trade_date` date,
    `name` longtext,
    `theme_code` longtext,
    `industry_code` longtext,
    `industry` longtext,
    `reason` longtext,
    `hot_num` longtext,
    unique(`_natural_key_hash`,`_revision_no`),
    unique(`_current_natural_key_hash`),
    check (`_revision_no` > 0),
    check (`_is_current` in (0,1)),
    check (`_valid_to` is null or `_valid_from` is null or `_valid_to` >= `_valid_from`)
);

create index if not exists `idx_src_tushare_dc_concept_cons_current`
    on `src_tushare_dc_concept_cons`(`_natural_key_hash`,`_is_current`);
create index if not exists `idx_src_tushare_dc_concept_cons_observed`
    on `src_tushare_dc_concept_cons`(`_observed_at`);

create table if not exists `src_tushare_index_basic` (
    `_observation_id` varchar(64) primary key,
    `_batch_id` varchar(64) not null,
    `_natural_key_hash` varchar(64) not null,
    `_revision_no` integer not null,
    `_is_current` integer not null default 1,
    `_current_natural_key_hash` varchar(64) generated always as (case when `_is_current` = 1 then `_natural_key_hash` else null end) stored,
    `_published_at` datetime(6),
    `_source_updated_at` datetime(6),
    `_observed_at` datetime(6) not null,
    `_valid_from` datetime(6),
    `_valid_to` datetime(6),
    `_payload_hash` varchar(64) not null,
    `ts_code` longtext,
    `name` longtext,
    `fullname` longtext,
    `market` longtext,
    `publisher` longtext,
    `index_type` longtext,
    `category` longtext,
    `base_date` date,
    `base_point` decimal(38,8),
    `list_date` date,
    `weight_rule` longtext,
    `desc` longtext,
    `exp_date` date,
    unique(`_natural_key_hash`,`_revision_no`),
    unique(`_current_natural_key_hash`),
    check (`_revision_no` > 0),
    check (`_is_current` in (0,1)),
    check (`_valid_to` is null or `_valid_from` is null or `_valid_to` >= `_valid_from`)
);

create index if not exists `idx_src_tushare_index_basic_current`
    on `src_tushare_index_basic`(`_natural_key_hash`,`_is_current`);
create index if not exists `idx_src_tushare_index_basic_observed`
    on `src_tushare_index_basic`(`_observed_at`);

create table if not exists `src_tushare_index_daily` (
    `_observation_id` varchar(64) primary key,
    `_batch_id` varchar(64) not null,
    `_natural_key_hash` varchar(64) not null,
    `_revision_no` integer not null,
    `_is_current` integer not null default 1,
    `_current_natural_key_hash` varchar(64) generated always as (case when `_is_current` = 1 then `_natural_key_hash` else null end) stored,
    `_published_at` datetime(6),
    `_source_updated_at` datetime(6),
    `_observed_at` datetime(6) not null,
    `_valid_from` datetime(6),
    `_valid_to` datetime(6),
    `_payload_hash` varchar(64) not null,
    `ts_code` longtext,
    `trade_date` date,
    `close` decimal(38,8),
    `open` decimal(38,8),
    `high` decimal(38,8),
    `low` decimal(38,8),
    `pre_close` decimal(38,8),
    `change` longtext,
    `pct_chg` decimal(38,8),
    `vol` decimal(38,8),
    `amount` decimal(38,8),
    unique(`_natural_key_hash`,`_revision_no`),
    unique(`_current_natural_key_hash`),
    check (`_revision_no` > 0),
    check (`_is_current` in (0,1)),
    check (`_valid_to` is null or `_valid_from` is null or `_valid_to` >= `_valid_from`)
);

create index if not exists `idx_src_tushare_index_daily_current`
    on `src_tushare_index_daily`(`_natural_key_hash`,`_is_current`);
create index if not exists `idx_src_tushare_index_daily_observed`
    on `src_tushare_index_daily`(`_observed_at`);

create table if not exists `src_tushare_rt_idx_k` (
    `_observation_id` varchar(64) primary key,
    `_batch_id` varchar(64) not null,
    `_natural_key_hash` varchar(64) not null,
    `_revision_no` integer not null,
    `_is_current` integer not null default 1,
    `_current_natural_key_hash` varchar(64) generated always as (case when `_is_current` = 1 then `_natural_key_hash` else null end) stored,
    `_published_at` datetime(6),
    `_source_updated_at` datetime(6),
    `_observed_at` datetime(6) not null,
    `_valid_from` datetime(6),
    `_valid_to` datetime(6),
    `_payload_hash` varchar(64) not null,
    `ts_code` longtext,
    `name` longtext,
    `trade_time` datetime(6),
    `close` decimal(38,8),
    `pre_close` decimal(38,8),
    `high` decimal(38,8),
    `open` decimal(38,8),
    `low` decimal(38,8),
    `vol` decimal(38,8),
    `amount` decimal(38,8),
    unique(`_natural_key_hash`,`_revision_no`),
    unique(`_current_natural_key_hash`),
    check (`_revision_no` > 0),
    check (`_is_current` in (0,1)),
    check (`_valid_to` is null or `_valid_from` is null or `_valid_to` >= `_valid_from`)
);

create index if not exists `idx_src_tushare_rt_idx_k_current`
    on `src_tushare_rt_idx_k`(`_natural_key_hash`,`_is_current`);
create index if not exists `idx_src_tushare_rt_idx_k_observed`
    on `src_tushare_rt_idx_k`(`_observed_at`);

create table if not exists `src_tushare_rt_idx_min` (
    `_observation_id` varchar(64) primary key,
    `_batch_id` varchar(64) not null,
    `_natural_key_hash` varchar(64) not null,
    `_revision_no` integer not null,
    `_is_current` integer not null default 1,
    `_current_natural_key_hash` varchar(64) generated always as (case when `_is_current` = 1 then `_natural_key_hash` else null end) stored,
    `_published_at` datetime(6),
    `_source_updated_at` datetime(6),
    `_observed_at` datetime(6) not null,
    `_valid_from` datetime(6),
    `_valid_to` datetime(6),
    `_payload_hash` varchar(64) not null,
    `ts_code` longtext,
    `time` datetime(6),
    `open` decimal(38,8),
    `close` decimal(38,8),
    `high` decimal(38,8),
    `low` decimal(38,8),
    `vol` decimal(38,8),
    `amount` decimal(38,8),
    unique(`_natural_key_hash`,`_revision_no`),
    unique(`_current_natural_key_hash`),
    check (`_revision_no` > 0),
    check (`_is_current` in (0,1)),
    check (`_valid_to` is null or `_valid_from` is null or `_valid_to` >= `_valid_from`)
);

create index if not exists `idx_src_tushare_rt_idx_min_current`
    on `src_tushare_rt_idx_min`(`_natural_key_hash`,`_is_current`);
create index if not exists `idx_src_tushare_rt_idx_min_observed`
    on `src_tushare_rt_idx_min`(`_observed_at`);

create table if not exists `src_tushare_rt_idx_min_daily` (
    `_observation_id` varchar(64) primary key,
    `_batch_id` varchar(64) not null,
    `_natural_key_hash` varchar(64) not null,
    `_revision_no` integer not null,
    `_is_current` integer not null default 1,
    `_current_natural_key_hash` varchar(64) generated always as (case when `_is_current` = 1 then `_natural_key_hash` else null end) stored,
    `_published_at` datetime(6),
    `_source_updated_at` datetime(6),
    `_observed_at` datetime(6) not null,
    `_valid_from` datetime(6),
    `_valid_to` datetime(6),
    `_payload_hash` varchar(64) not null,
    `ts_code` longtext,
    `time` datetime(6),
    `open` decimal(38,8),
    `close` decimal(38,8),
    `high` decimal(38,8),
    `low` decimal(38,8),
    `vol` decimal(38,8),
    `amount` decimal(38,8),
    unique(`_natural_key_hash`,`_revision_no`),
    unique(`_current_natural_key_hash`),
    check (`_revision_no` > 0),
    check (`_is_current` in (0,1)),
    check (`_valid_to` is null or `_valid_from` is null or `_valid_to` >= `_valid_from`)
);

create index if not exists `idx_src_tushare_rt_idx_min_daily_current`
    on `src_tushare_rt_idx_min_daily`(`_natural_key_hash`,`_is_current`);
create index if not exists `idx_src_tushare_rt_idx_min_daily_observed`
    on `src_tushare_rt_idx_min_daily`(`_observed_at`);

create table if not exists `src_tushare_index_weekly` (
    `_observation_id` varchar(64) primary key,
    `_batch_id` varchar(64) not null,
    `_natural_key_hash` varchar(64) not null,
    `_revision_no` integer not null,
    `_is_current` integer not null default 1,
    `_current_natural_key_hash` varchar(64) generated always as (case when `_is_current` = 1 then `_natural_key_hash` else null end) stored,
    `_published_at` datetime(6),
    `_source_updated_at` datetime(6),
    `_observed_at` datetime(6) not null,
    `_valid_from` datetime(6),
    `_valid_to` datetime(6),
    `_payload_hash` varchar(64) not null,
    `ts_code` longtext,
    `trade_date` date,
    `close` decimal(38,8),
    `open` decimal(38,8),
    `high` decimal(38,8),
    `low` decimal(38,8),
    `pre_close` decimal(38,8),
    `change` decimal(38,8),
    `pct_chg` decimal(38,8),
    `vol` decimal(38,8),
    `amount` decimal(38,8),
    unique(`_natural_key_hash`,`_revision_no`),
    unique(`_current_natural_key_hash`),
    check (`_revision_no` > 0),
    check (`_is_current` in (0,1)),
    check (`_valid_to` is null or `_valid_from` is null or `_valid_to` >= `_valid_from`)
);

create index if not exists `idx_src_tushare_index_weekly_current`
    on `src_tushare_index_weekly`(`_natural_key_hash`,`_is_current`);
create index if not exists `idx_src_tushare_index_weekly_observed`
    on `src_tushare_index_weekly`(`_observed_at`);

create table if not exists `src_tushare_idx_mins` (
    `_observation_id` varchar(64) primary key,
    `_batch_id` varchar(64) not null,
    `_natural_key_hash` varchar(64) not null,
    `_revision_no` integer not null,
    `_is_current` integer not null default 1,
    `_current_natural_key_hash` varchar(64) generated always as (case when `_is_current` = 1 then `_natural_key_hash` else null end) stored,
    `_published_at` datetime(6),
    `_source_updated_at` datetime(6),
    `_observed_at` datetime(6) not null,
    `_valid_from` datetime(6),
    `_valid_to` datetime(6),
    `_payload_hash` varchar(64) not null,
    `ts_code` longtext,
    `trade_time` datetime(6),
    `open` decimal(38,8),
    `close` decimal(38,8),
    `high` decimal(38,8),
    `low` decimal(38,8),
    `vol` bigint,
    `amount` decimal(38,8),
    unique(`_natural_key_hash`,`_revision_no`),
    unique(`_current_natural_key_hash`),
    check (`_revision_no` > 0),
    check (`_is_current` in (0,1)),
    check (`_valid_to` is null or `_valid_from` is null or `_valid_to` >= `_valid_from`)
);

create index if not exists `idx_src_tushare_idx_mins_current`
    on `src_tushare_idx_mins`(`_natural_key_hash`,`_is_current`);
create index if not exists `idx_src_tushare_idx_mins_observed`
    on `src_tushare_idx_mins`(`_observed_at`);

create table if not exists `src_tushare_index_monthly` (
    `_observation_id` varchar(64) primary key,
    `_batch_id` varchar(64) not null,
    `_natural_key_hash` varchar(64) not null,
    `_revision_no` integer not null,
    `_is_current` integer not null default 1,
    `_current_natural_key_hash` varchar(64) generated always as (case when `_is_current` = 1 then `_natural_key_hash` else null end) stored,
    `_published_at` datetime(6),
    `_source_updated_at` datetime(6),
    `_observed_at` datetime(6) not null,
    `_valid_from` datetime(6),
    `_valid_to` datetime(6),
    `_payload_hash` varchar(64) not null,
    `ts_code` longtext,
    `trade_date` date,
    `close` decimal(38,8),
    `open` decimal(38,8),
    `high` decimal(38,8),
    `low` decimal(38,8),
    `pre_close` decimal(38,8),
    `change` decimal(38,8),
    `pct_chg` decimal(38,8),
    `vol` decimal(38,8),
    `amount` decimal(38,8),
    unique(`_natural_key_hash`,`_revision_no`),
    unique(`_current_natural_key_hash`),
    check (`_revision_no` > 0),
    check (`_is_current` in (0,1)),
    check (`_valid_to` is null or `_valid_from` is null or `_valid_to` >= `_valid_from`)
);

create index if not exists `idx_src_tushare_index_monthly_current`
    on `src_tushare_index_monthly`(`_natural_key_hash`,`_is_current`);
create index if not exists `idx_src_tushare_index_monthly_observed`
    on `src_tushare_index_monthly`(`_observed_at`);

create table if not exists `src_tushare_index_weight` (
    `_observation_id` varchar(64) primary key,
    `_batch_id` varchar(64) not null,
    `_natural_key_hash` varchar(64) not null,
    `_revision_no` integer not null,
    `_is_current` integer not null default 1,
    `_current_natural_key_hash` varchar(64) generated always as (case when `_is_current` = 1 then `_natural_key_hash` else null end) stored,
    `_published_at` datetime(6),
    `_source_updated_at` datetime(6),
    `_observed_at` datetime(6) not null,
    `_valid_from` datetime(6),
    `_valid_to` datetime(6),
    `_payload_hash` varchar(64) not null,
    `index_code` longtext,
    `con_code` longtext,
    `trade_date` date,
    `weight` decimal(38,8),
    unique(`_natural_key_hash`,`_revision_no`),
    unique(`_current_natural_key_hash`),
    check (`_revision_no` > 0),
    check (`_is_current` in (0,1)),
    check (`_valid_to` is null or `_valid_from` is null or `_valid_to` >= `_valid_from`)
);

create index if not exists `idx_src_tushare_index_weight_current`
    on `src_tushare_index_weight`(`_natural_key_hash`,`_is_current`);
create index if not exists `idx_src_tushare_index_weight_observed`
    on `src_tushare_index_weight`(`_observed_at`);

create table if not exists `src_tushare_index_dailybasic` (
    `_observation_id` varchar(64) primary key,
    `_batch_id` varchar(64) not null,
    `_natural_key_hash` varchar(64) not null,
    `_revision_no` integer not null,
    `_is_current` integer not null default 1,
    `_current_natural_key_hash` varchar(64) generated always as (case when `_is_current` = 1 then `_natural_key_hash` else null end) stored,
    `_published_at` datetime(6),
    `_source_updated_at` datetime(6),
    `_observed_at` datetime(6) not null,
    `_valid_from` datetime(6),
    `_valid_to` datetime(6),
    `_payload_hash` varchar(64) not null,
    `ts_code` longtext,
    `trade_date` date,
    `total_mv` decimal(38,8),
    `float_mv` decimal(38,8),
    `total_share` decimal(38,8),
    `float_share` decimal(38,8),
    `free_share` decimal(38,8),
    `turnover_rate` decimal(38,8),
    `turnover_rate_f` decimal(38,8),
    `pe` decimal(38,8),
    `pe_ttm` decimal(38,8),
    `pb` decimal(38,8),
    unique(`_natural_key_hash`,`_revision_no`),
    unique(`_current_natural_key_hash`),
    check (`_revision_no` > 0),
    check (`_is_current` in (0,1)),
    check (`_valid_to` is null or `_valid_from` is null or `_valid_to` >= `_valid_from`)
);

create index if not exists `idx_src_tushare_index_dailybasic_current`
    on `src_tushare_index_dailybasic`(`_natural_key_hash`,`_is_current`);
create index if not exists `idx_src_tushare_index_dailybasic_observed`
    on `src_tushare_index_dailybasic`(`_observed_at`);

create table if not exists `src_tushare_index_classify` (
    `_observation_id` varchar(64) primary key,
    `_batch_id` varchar(64) not null,
    `_natural_key_hash` varchar(64) not null,
    `_revision_no` integer not null,
    `_is_current` integer not null default 1,
    `_current_natural_key_hash` varchar(64) generated always as (case when `_is_current` = 1 then `_natural_key_hash` else null end) stored,
    `_published_at` datetime(6),
    `_source_updated_at` datetime(6),
    `_observed_at` datetime(6) not null,
    `_valid_from` datetime(6),
    `_valid_to` datetime(6),
    `_payload_hash` varchar(64) not null,
    `index_code` longtext,
    `industry_name` longtext,
    `parent_code` longtext,
    `level` longtext,
    `industry_code` longtext,
    `is_pub` longtext,
    `src` longtext,
    unique(`_natural_key_hash`,`_revision_no`),
    unique(`_current_natural_key_hash`),
    check (`_revision_no` > 0),
    check (`_is_current` in (0,1)),
    check (`_valid_to` is null or `_valid_from` is null or `_valid_to` >= `_valid_from`)
);

create index if not exists `idx_src_tushare_index_classify_current`
    on `src_tushare_index_classify`(`_natural_key_hash`,`_is_current`);
create index if not exists `idx_src_tushare_index_classify_observed`
    on `src_tushare_index_classify`(`_observed_at`);

create table if not exists `src_tushare_index_member_all` (
    `_observation_id` varchar(64) primary key,
    `_batch_id` varchar(64) not null,
    `_natural_key_hash` varchar(64) not null,
    `_revision_no` integer not null,
    `_is_current` integer not null default 1,
    `_current_natural_key_hash` varchar(64) generated always as (case when `_is_current` = 1 then `_natural_key_hash` else null end) stored,
    `_published_at` datetime(6),
    `_source_updated_at` datetime(6),
    `_observed_at` datetime(6) not null,
    `_valid_from` datetime(6),
    `_valid_to` datetime(6),
    `_payload_hash` varchar(64) not null,
    `l1_code` longtext,
    `l1_name` longtext,
    `l2_code` longtext,
    `l2_name` longtext,
    `l3_code` longtext,
    `l3_name` longtext,
    `ts_code` longtext,
    `name` longtext,
    `in_date` date,
    `out_date` date,
    `is_new` longtext,
    unique(`_natural_key_hash`,`_revision_no`),
    unique(`_current_natural_key_hash`),
    check (`_revision_no` > 0),
    check (`_is_current` in (0,1)),
    check (`_valid_to` is null or `_valid_from` is null or `_valid_to` >= `_valid_from`)
);

create index if not exists `idx_src_tushare_index_member_all_current`
    on `src_tushare_index_member_all`(`_natural_key_hash`,`_is_current`);
create index if not exists `idx_src_tushare_index_member_all_observed`
    on `src_tushare_index_member_all`(`_observed_at`);

create table if not exists `src_tushare_sw_daily` (
    `_observation_id` varchar(64) primary key,
    `_batch_id` varchar(64) not null,
    `_natural_key_hash` varchar(64) not null,
    `_revision_no` integer not null,
    `_is_current` integer not null default 1,
    `_current_natural_key_hash` varchar(64) generated always as (case when `_is_current` = 1 then `_natural_key_hash` else null end) stored,
    `_published_at` datetime(6),
    `_source_updated_at` datetime(6),
    `_observed_at` datetime(6) not null,
    `_valid_from` datetime(6),
    `_valid_to` datetime(6),
    `_payload_hash` varchar(64) not null,
    `ts_code` longtext,
    `trade_date` date,
    `name` longtext,
    `open` decimal(38,8),
    `low` decimal(38,8),
    `high` decimal(38,8),
    `close` decimal(38,8),
    `change` decimal(38,8),
    `pct_change` decimal(38,8),
    `vol` decimal(38,8),
    `amount` decimal(38,8),
    `pe` decimal(38,8),
    `pb` decimal(38,8),
    `float_mv` decimal(38,8),
    `total_mv` decimal(38,8),
    unique(`_natural_key_hash`,`_revision_no`),
    unique(`_current_natural_key_hash`),
    check (`_revision_no` > 0),
    check (`_is_current` in (0,1)),
    check (`_valid_to` is null or `_valid_from` is null or `_valid_to` >= `_valid_from`)
);

create index if not exists `idx_src_tushare_sw_daily_current`
    on `src_tushare_sw_daily`(`_natural_key_hash`,`_is_current`);
create index if not exists `idx_src_tushare_sw_daily_observed`
    on `src_tushare_sw_daily`(`_observed_at`);

create table if not exists `src_tushare_rt_sw_k` (
    `_observation_id` varchar(64) primary key,
    `_batch_id` varchar(64) not null,
    `_natural_key_hash` varchar(64) not null,
    `_revision_no` integer not null,
    `_is_current` integer not null default 1,
    `_current_natural_key_hash` varchar(64) generated always as (case when `_is_current` = 1 then `_natural_key_hash` else null end) stored,
    `_published_at` datetime(6),
    `_source_updated_at` datetime(6),
    `_observed_at` datetime(6) not null,
    `_valid_from` datetime(6),
    `_valid_to` datetime(6),
    `_payload_hash` varchar(64) not null,
    `ts_code` longtext,
    `name` longtext,
    `trade_time` datetime(6),
    `close` decimal(38,8),
    `pre_close` decimal(38,8),
    `high` decimal(38,8),
    `open` decimal(38,8),
    `low` decimal(38,8),
    `vol` decimal(38,8),
    `amount` decimal(38,8),
    `pct_change` decimal(38,8),
    unique(`_natural_key_hash`,`_revision_no`),
    unique(`_current_natural_key_hash`),
    check (`_revision_no` > 0),
    check (`_is_current` in (0,1)),
    check (`_valid_to` is null or `_valid_from` is null or `_valid_to` >= `_valid_from`)
);

create index if not exists `idx_src_tushare_rt_sw_k_current`
    on `src_tushare_rt_sw_k`(`_natural_key_hash`,`_is_current`);
create index if not exists `idx_src_tushare_rt_sw_k_observed`
    on `src_tushare_rt_sw_k`(`_observed_at`);

create table if not exists `src_tushare_sw_mins` (
    `_observation_id` varchar(64) primary key,
    `_batch_id` varchar(64) not null,
    `_natural_key_hash` varchar(64) not null,
    `_revision_no` integer not null,
    `_is_current` integer not null default 1,
    `_current_natural_key_hash` varchar(64) generated always as (case when `_is_current` = 1 then `_natural_key_hash` else null end) stored,
    `_published_at` datetime(6),
    `_source_updated_at` datetime(6),
    `_observed_at` datetime(6) not null,
    `_valid_from` datetime(6),
    `_valid_to` datetime(6),
    `_payload_hash` varchar(64) not null,
    `ts_code` longtext,
    `trade_time` datetime(6),
    `open` decimal(38,8),
    `close` decimal(38,8),
    `high` decimal(38,8),
    `low` decimal(38,8),
    `amount` decimal(38,8),
    `vol` decimal(38,8),
    unique(`_natural_key_hash`,`_revision_no`),
    unique(`_current_natural_key_hash`),
    check (`_revision_no` > 0),
    check (`_is_current` in (0,1)),
    check (`_valid_to` is null or `_valid_from` is null or `_valid_to` >= `_valid_from`)
);

create index if not exists `idx_src_tushare_sw_mins_current`
    on `src_tushare_sw_mins`(`_natural_key_hash`,`_is_current`);
create index if not exists `idx_src_tushare_sw_mins_observed`
    on `src_tushare_sw_mins`(`_observed_at`);

create table if not exists `src_tushare_ci_index_member` (
    `_observation_id` varchar(64) primary key,
    `_batch_id` varchar(64) not null,
    `_natural_key_hash` varchar(64) not null,
    `_revision_no` integer not null,
    `_is_current` integer not null default 1,
    `_current_natural_key_hash` varchar(64) generated always as (case when `_is_current` = 1 then `_natural_key_hash` else null end) stored,
    `_published_at` datetime(6),
    `_source_updated_at` datetime(6),
    `_observed_at` datetime(6) not null,
    `_valid_from` datetime(6),
    `_valid_to` datetime(6),
    `_payload_hash` varchar(64) not null,
    `l1_code` longtext,
    `l1_name` longtext,
    `l2_code` longtext,
    `l2_name` longtext,
    `l3_code` longtext,
    `l3_name` longtext,
    `ts_code` longtext,
    `name` longtext,
    `in_date` date,
    `out_date` date,
    `is_new` longtext,
    unique(`_natural_key_hash`,`_revision_no`),
    unique(`_current_natural_key_hash`),
    check (`_revision_no` > 0),
    check (`_is_current` in (0,1)),
    check (`_valid_to` is null or `_valid_from` is null or `_valid_to` >= `_valid_from`)
);

create index if not exists `idx_src_tushare_ci_index_member_current`
    on `src_tushare_ci_index_member`(`_natural_key_hash`,`_is_current`);
create index if not exists `idx_src_tushare_ci_index_member_observed`
    on `src_tushare_ci_index_member`(`_observed_at`);

create table if not exists `src_tushare_ci_daily` (
    `_observation_id` varchar(64) primary key,
    `_batch_id` varchar(64) not null,
    `_natural_key_hash` varchar(64) not null,
    `_revision_no` integer not null,
    `_is_current` integer not null default 1,
    `_current_natural_key_hash` varchar(64) generated always as (case when `_is_current` = 1 then `_natural_key_hash` else null end) stored,
    `_published_at` datetime(6),
    `_source_updated_at` datetime(6),
    `_observed_at` datetime(6) not null,
    `_valid_from` datetime(6),
    `_valid_to` datetime(6),
    `_payload_hash` varchar(64) not null,
    `ts_code` longtext,
    `trade_date` date,
    `open` decimal(38,8),
    `low` decimal(38,8),
    `high` decimal(38,8),
    `close` decimal(38,8),
    `pre_close` decimal(38,8),
    `change` decimal(38,8),
    `pct_change` decimal(38,8),
    `vol` decimal(38,8),
    `amount` decimal(38,8),
    unique(`_natural_key_hash`,`_revision_no`),
    unique(`_current_natural_key_hash`),
    check (`_revision_no` > 0),
    check (`_is_current` in (0,1)),
    check (`_valid_to` is null or `_valid_from` is null or `_valid_to` >= `_valid_from`)
);

create index if not exists `idx_src_tushare_ci_daily_current`
    on `src_tushare_ci_daily`(`_natural_key_hash`,`_is_current`);
create index if not exists `idx_src_tushare_ci_daily_observed`
    on `src_tushare_ci_daily`(`_observed_at`);

create table if not exists `src_tushare_index_global` (
    `_observation_id` varchar(64) primary key,
    `_batch_id` varchar(64) not null,
    `_natural_key_hash` varchar(64) not null,
    `_revision_no` integer not null,
    `_is_current` integer not null default 1,
    `_current_natural_key_hash` varchar(64) generated always as (case when `_is_current` = 1 then `_natural_key_hash` else null end) stored,
    `_published_at` datetime(6),
    `_source_updated_at` datetime(6),
    `_observed_at` datetime(6) not null,
    `_valid_from` datetime(6),
    `_valid_to` datetime(6),
    `_payload_hash` varchar(64) not null,
    `ts_code` longtext,
    `trade_date` date,
    `open` decimal(38,8),
    `close` decimal(38,8),
    `high` decimal(38,8),
    `low` decimal(38,8),
    `pre_close` decimal(38,8),
    `change` decimal(38,8),
    `pct_chg` decimal(38,8),
    `swing` decimal(38,8),
    `vol` decimal(38,8),
    `amount` decimal(38,8),
    unique(`_natural_key_hash`,`_revision_no`),
    unique(`_current_natural_key_hash`),
    check (`_revision_no` > 0),
    check (`_is_current` in (0,1)),
    check (`_valid_to` is null or `_valid_from` is null or `_valid_to` >= `_valid_from`)
);

create index if not exists `idx_src_tushare_index_global_current`
    on `src_tushare_index_global`(`_natural_key_hash`,`_is_current`);
create index if not exists `idx_src_tushare_index_global_observed`
    on `src_tushare_index_global`(`_observed_at`);

create table if not exists `src_tushare_idx_factor_pro` (
    `_observation_id` varchar(64) primary key,
    `_batch_id` varchar(64) not null,
    `_natural_key_hash` varchar(64) not null,
    `_revision_no` integer not null,
    `_is_current` integer not null default 1,
    `_current_natural_key_hash` varchar(64) generated always as (case when `_is_current` = 1 then `_natural_key_hash` else null end) stored,
    `_published_at` datetime(6),
    `_source_updated_at` datetime(6),
    `_observed_at` datetime(6) not null,
    `_valid_from` datetime(6),
    `_valid_to` datetime(6),
    `_payload_hash` varchar(64) not null,
    `ts_code` longtext,
    `trade_date` date,
    `open` decimal(38,8),
    `high` decimal(38,8),
    `low` decimal(38,8),
    `close` decimal(38,8),
    `pre_close` decimal(38,8),
    `change` decimal(38,8),
    `pct_change` decimal(38,8),
    `vol` decimal(38,8),
    `amount` decimal(38,8),
    `asi_bfq` decimal(38,8),
    `asit_bfq` decimal(38,8),
    `atr_bfq` decimal(38,8),
    `bbi_bfq` decimal(38,8),
    `bias1_bfq` decimal(38,8),
    `bias2_bfq` decimal(38,8),
    `bias3_bfq` decimal(38,8),
    `boll_lower_bfq` decimal(38,8),
    `boll_mid_bfq` decimal(38,8),
    `boll_upper_bfq` decimal(38,8),
    `brar_ar_bfq` decimal(38,8),
    `brar_br_bfq` decimal(38,8),
    `cci_bfq` decimal(38,8),
    `cr_bfq` decimal(38,8),
    `dfma_dif_bfq` decimal(38,8),
    `dfma_difma_bfq` decimal(38,8),
    `dmi_adx_bfq` decimal(38,8),
    `dmi_adxr_bfq` decimal(38,8),
    `dmi_mdi_bfq` decimal(38,8),
    `dmi_pdi_bfq` decimal(38,8),
    `downdays` decimal(38,8),
    `updays` decimal(38,8),
    `dpo_bfq` decimal(38,8),
    `madpo_bfq` decimal(38,8),
    `ema_bfq_10` decimal(38,8),
    `ema_bfq_20` decimal(38,8),
    `ema_bfq_250` decimal(38,8),
    `ema_bfq_30` decimal(38,8),
    `ema_bfq_5` decimal(38,8),
    `ema_bfq_60` decimal(38,8),
    `ema_bfq_90` decimal(38,8),
    `emv_bfq` decimal(38,8),
    `maemv_bfq` decimal(38,8),
    `expma_12_bfq` decimal(38,8),
    `expma_50_bfq` decimal(38,8),
    `kdj_bfq` decimal(38,8),
    `kdj_d_bfq` decimal(38,8),
    `kdj_k_bfq` decimal(38,8),
    `ktn_down_bfq` decimal(38,8),
    `ktn_mid_bfq` decimal(38,8),
    `ktn_upper_bfq` decimal(38,8),
    `lowdays` decimal(38,8),
    `topdays` decimal(38,8),
    `ma_bfq_10` decimal(38,8),
    `ma_bfq_20` decimal(38,8),
    `ma_bfq_250` decimal(38,8),
    `ma_bfq_30` decimal(38,8),
    `ma_bfq_5` decimal(38,8),
    `ma_bfq_60` decimal(38,8),
    `ma_bfq_90` decimal(38,8),
    `macd_bfq` decimal(38,8),
    `macd_dea_bfq` decimal(38,8),
    `macd_dif_bfq` decimal(38,8),
    `mass_bfq` decimal(38,8),
    `ma_mass_bfq` decimal(38,8),
    `mfi_bfq` decimal(38,8),
    `mtm_bfq` decimal(38,8),
    `mtmma_bfq` decimal(38,8),
    `obv_bfq` decimal(38,8),
    `psy_bfq` decimal(38,8),
    `psyma_bfq` decimal(38,8),
    `roc_bfq` decimal(38,8),
    `maroc_bfq` decimal(38,8),
    `rsi_bfq_12` decimal(38,8),
    `rsi_bfq_24` decimal(38,8),
    `rsi_bfq_6` decimal(38,8),
    `taq_down_bfq` decimal(38,8),
    `taq_mid_bfq` decimal(38,8),
    `taq_up_bfq` decimal(38,8),
    `trix_bfq` decimal(38,8),
    `trma_bfq` decimal(38,8),
    `vr_bfq` decimal(38,8),
    `wr_bfq` decimal(38,8),
    `wr1_bfq` decimal(38,8),
    `xsii_td1_bfq` decimal(38,8),
    `xsii_td2_bfq` decimal(38,8),
    `xsii_td3_bfq` decimal(38,8),
    `xsii_td4_bfq` decimal(38,8),
    unique(`_natural_key_hash`,`_revision_no`),
    unique(`_current_natural_key_hash`),
    check (`_revision_no` > 0),
    check (`_is_current` in (0,1)),
    check (`_valid_to` is null or `_valid_from` is null or `_valid_to` >= `_valid_from`)
);

create index if not exists `idx_src_tushare_idx_factor_pro_current`
    on `src_tushare_idx_factor_pro`(`_natural_key_hash`,`_is_current`);
create index if not exists `idx_src_tushare_idx_factor_pro_observed`
    on `src_tushare_idx_factor_pro`(`_observed_at`);

create table if not exists `src_tushare_daily_info` (
    `_observation_id` varchar(64) primary key,
    `_batch_id` varchar(64) not null,
    `_natural_key_hash` varchar(64) not null,
    `_revision_no` integer not null,
    `_is_current` integer not null default 1,
    `_current_natural_key_hash` varchar(64) generated always as (case when `_is_current` = 1 then `_natural_key_hash` else null end) stored,
    `_published_at` datetime(6),
    `_source_updated_at` datetime(6),
    `_observed_at` datetime(6) not null,
    `_valid_from` datetime(6),
    `_valid_to` datetime(6),
    `_payload_hash` varchar(64) not null,
    `trade_date` date,
    `ts_code` longtext,
    `ts_name` longtext,
    `com_count` bigint,
    `total_share` decimal(38,8),
    `float_share` decimal(38,8),
    `total_mv` decimal(38,8),
    `float_mv` decimal(38,8),
    `amount` decimal(38,8),
    `vol` decimal(38,8),
    `trans_count` bigint,
    `pe` decimal(38,8),
    `tr` decimal(38,8),
    `exchange` longtext,
    unique(`_natural_key_hash`,`_revision_no`),
    unique(`_current_natural_key_hash`),
    check (`_revision_no` > 0),
    check (`_is_current` in (0,1)),
    check (`_valid_to` is null or `_valid_from` is null or `_valid_to` >= `_valid_from`)
);

create index if not exists `idx_src_tushare_daily_info_current`
    on `src_tushare_daily_info`(`_natural_key_hash`,`_is_current`);
create index if not exists `idx_src_tushare_daily_info_observed`
    on `src_tushare_daily_info`(`_observed_at`);

create table if not exists `src_tushare_sz_daily_info` (
    `_observation_id` varchar(64) primary key,
    `_batch_id` varchar(64) not null,
    `_natural_key_hash` varchar(64) not null,
    `_revision_no` integer not null,
    `_is_current` integer not null default 1,
    `_current_natural_key_hash` varchar(64) generated always as (case when `_is_current` = 1 then `_natural_key_hash` else null end) stored,
    `_published_at` datetime(6),
    `_source_updated_at` datetime(6),
    `_observed_at` datetime(6) not null,
    `_valid_from` datetime(6),
    `_valid_to` datetime(6),
    `_payload_hash` varchar(64) not null,
    `trade_date` date,
    `ts_code` longtext,
    `count` bigint,
    `amount` decimal(38,8),
    `vol` longtext,
    `total_share` decimal(38,8),
    `total_mv` decimal(38,8),
    `float_share` decimal(38,8),
    `float_mv` decimal(38,8),
    unique(`_natural_key_hash`,`_revision_no`),
    unique(`_current_natural_key_hash`),
    check (`_revision_no` > 0),
    check (`_is_current` in (0,1)),
    check (`_valid_to` is null or `_valid_from` is null or `_valid_to` >= `_valid_from`)
);

create index if not exists `idx_src_tushare_sz_daily_info_current`
    on `src_tushare_sz_daily_info`(`_natural_key_hash`,`_is_current`);
create index if not exists `idx_src_tushare_sz_daily_info_observed`
    on `src_tushare_sz_daily_info`(`_observed_at`);

create table if not exists `src_tushare_fut_basic` (
    `_observation_id` varchar(64) primary key,
    `_batch_id` varchar(64) not null,
    `_natural_key_hash` varchar(64) not null,
    `_revision_no` integer not null,
    `_is_current` integer not null default 1,
    `_current_natural_key_hash` varchar(64) generated always as (case when `_is_current` = 1 then `_natural_key_hash` else null end) stored,
    `_published_at` datetime(6),
    `_source_updated_at` datetime(6),
    `_observed_at` datetime(6) not null,
    `_valid_from` datetime(6),
    `_valid_to` datetime(6),
    `_payload_hash` varchar(64) not null,
    `ts_code` longtext,
    `symbol` longtext,
    `exchange` longtext,
    `name` longtext,
    `fut_code` longtext,
    `multiplier` decimal(38,8),
    `trade_unit` longtext,
    `per_unit` decimal(38,8),
    `quote_unit` longtext,
    `quote_unit_desc` longtext,
    `d_mode_desc` longtext,
    `list_date` date,
    `delist_date` date,
    `d_month` longtext,
    `last_ddate` date,
    `trade_time_desc` longtext,
    unique(`_natural_key_hash`,`_revision_no`),
    unique(`_current_natural_key_hash`),
    check (`_revision_no` > 0),
    check (`_is_current` in (0,1)),
    check (`_valid_to` is null or `_valid_from` is null or `_valid_to` >= `_valid_from`)
);

create index if not exists `idx_src_tushare_fut_basic_current`
    on `src_tushare_fut_basic`(`_natural_key_hash`,`_is_current`);
create index if not exists `idx_src_tushare_fut_basic_observed`
    on `src_tushare_fut_basic`(`_observed_at`);

create table if not exists `src_tushare_fut_trade_cal` (
    `_observation_id` varchar(64) primary key,
    `_batch_id` varchar(64) not null,
    `_natural_key_hash` varchar(64) not null,
    `_revision_no` integer not null,
    `_is_current` integer not null default 1,
    `_current_natural_key_hash` varchar(64) generated always as (case when `_is_current` = 1 then `_natural_key_hash` else null end) stored,
    `_published_at` datetime(6),
    `_source_updated_at` datetime(6),
    `_observed_at` datetime(6) not null,
    `_valid_from` datetime(6),
    `_valid_to` datetime(6),
    `_payload_hash` varchar(64) not null,
    `exchange` longtext,
    `cal_date` date,
    `is_open` bigint,
    `pretrade_date` date,
    unique(`_natural_key_hash`,`_revision_no`),
    unique(`_current_natural_key_hash`),
    check (`_revision_no` > 0),
    check (`_is_current` in (0,1)),
    check (`_valid_to` is null or `_valid_from` is null or `_valid_to` >= `_valid_from`)
);

create index if not exists `idx_src_tushare_fut_trade_cal_current`
    on `src_tushare_fut_trade_cal`(`_natural_key_hash`,`_is_current`);
create index if not exists `idx_src_tushare_fut_trade_cal_observed`
    on `src_tushare_fut_trade_cal`(`_observed_at`);

create table if not exists `src_tushare_fut_daily` (
    `_observation_id` varchar(64) primary key,
    `_batch_id` varchar(64) not null,
    `_natural_key_hash` varchar(64) not null,
    `_revision_no` integer not null,
    `_is_current` integer not null default 1,
    `_current_natural_key_hash` varchar(64) generated always as (case when `_is_current` = 1 then `_natural_key_hash` else null end) stored,
    `_published_at` datetime(6),
    `_source_updated_at` datetime(6),
    `_observed_at` datetime(6) not null,
    `_valid_from` datetime(6),
    `_valid_to` datetime(6),
    `_payload_hash` varchar(64) not null,
    `ts_code` longtext,
    `trade_date` date,
    `pre_close` decimal(38,8),
    `pre_settle` decimal(38,8),
    `open` decimal(38,8),
    `high` decimal(38,8),
    `low` decimal(38,8),
    `close` decimal(38,8),
    `settle` decimal(38,8),
    `change1` decimal(38,8),
    `change2` decimal(38,8),
    `vol` decimal(38,8),
    `amount` decimal(38,8),
    `oi` decimal(38,8),
    `oi_chg` decimal(38,8),
    `delv_settle` decimal(38,8),
    unique(`_natural_key_hash`,`_revision_no`),
    unique(`_current_natural_key_hash`),
    check (`_revision_no` > 0),
    check (`_is_current` in (0,1)),
    check (`_valid_to` is null or `_valid_from` is null or `_valid_to` >= `_valid_from`)
);

create index if not exists `idx_src_tushare_fut_daily_current`
    on `src_tushare_fut_daily`(`_natural_key_hash`,`_is_current`);
create index if not exists `idx_src_tushare_fut_daily_observed`
    on `src_tushare_fut_daily`(`_observed_at`);

create table if not exists `src_tushare_fut_weekly_monthly` (
    `_observation_id` varchar(64) primary key,
    `_batch_id` varchar(64) not null,
    `_natural_key_hash` varchar(64) not null,
    `_revision_no` integer not null,
    `_is_current` integer not null default 1,
    `_current_natural_key_hash` varchar(64) generated always as (case when `_is_current` = 1 then `_natural_key_hash` else null end) stored,
    `_published_at` datetime(6),
    `_source_updated_at` datetime(6),
    `_observed_at` datetime(6) not null,
    `_valid_from` datetime(6),
    `_valid_to` datetime(6),
    `_payload_hash` varchar(64) not null,
    `ts_code` longtext,
    `trade_date` date,
    `end_date` date,
    `freq` longtext,
    `open` decimal(38,8),
    `high` decimal(38,8),
    `low` decimal(38,8),
    `close` decimal(38,8),
    `pre_close` decimal(38,8),
    `settle` decimal(38,8),
    `pre_settle` decimal(38,8),
    `vol` decimal(38,8),
    `amount` decimal(38,8),
    `oi` decimal(38,8),
    `oi_chg` decimal(38,8),
    `exchange` longtext,
    `change1` decimal(38,8),
    `change2` decimal(38,8),
    unique(`_natural_key_hash`,`_revision_no`),
    unique(`_current_natural_key_hash`),
    check (`_revision_no` > 0),
    check (`_is_current` in (0,1)),
    check (`_valid_to` is null or `_valid_from` is null or `_valid_to` >= `_valid_from`)
);

create index if not exists `idx_src_tushare_fut_weekly_monthly_current`
    on `src_tushare_fut_weekly_monthly`(`_natural_key_hash`,`_is_current`);
create index if not exists `idx_src_tushare_fut_weekly_monthly_observed`
    on `src_tushare_fut_weekly_monthly`(`_observed_at`);

create table if not exists `src_tushare_ft_mins` (
    `_observation_id` varchar(64) primary key,
    `_batch_id` varchar(64) not null,
    `_natural_key_hash` varchar(64) not null,
    `_revision_no` integer not null,
    `_is_current` integer not null default 1,
    `_current_natural_key_hash` varchar(64) generated always as (case when `_is_current` = 1 then `_natural_key_hash` else null end) stored,
    `_published_at` datetime(6),
    `_source_updated_at` datetime(6),
    `_observed_at` datetime(6) not null,
    `_valid_from` datetime(6),
    `_valid_to` datetime(6),
    `_payload_hash` varchar(64) not null,
    `ts_code` longtext,
    `trade_time` datetime(6),
    `open` decimal(38,8),
    `close` decimal(38,8),
    `high` decimal(38,8),
    `low` decimal(38,8),
    `vol` bigint,
    `amount` decimal(38,8),
    `oi` decimal(38,8),
    unique(`_natural_key_hash`,`_revision_no`),
    unique(`_current_natural_key_hash`),
    check (`_revision_no` > 0),
    check (`_is_current` in (0,1)),
    check (`_valid_to` is null or `_valid_from` is null or `_valid_to` >= `_valid_from`)
);

create index if not exists `idx_src_tushare_ft_mins_current`
    on `src_tushare_ft_mins`(`_natural_key_hash`,`_is_current`);
create index if not exists `idx_src_tushare_ft_mins_observed`
    on `src_tushare_ft_mins`(`_observed_at`);

create table if not exists `src_tushare_rt_fut_min` (
    `_observation_id` varchar(64) primary key,
    `_batch_id` varchar(64) not null,
    `_natural_key_hash` varchar(64) not null,
    `_revision_no` integer not null,
    `_is_current` integer not null default 1,
    `_current_natural_key_hash` varchar(64) generated always as (case when `_is_current` = 1 then `_natural_key_hash` else null end) stored,
    `_published_at` datetime(6),
    `_source_updated_at` datetime(6),
    `_observed_at` datetime(6) not null,
    `_valid_from` datetime(6),
    `_valid_to` datetime(6),
    `_payload_hash` varchar(64) not null,
    `code` longtext,
    `freq` longtext,
    `time` datetime(6),
    `open` decimal(38,8),
    `close` decimal(38,8),
    `high` decimal(38,8),
    `low` decimal(38,8),
    `vol` bigint,
    `amount` decimal(38,8),
    `oi` decimal(38,8),
    unique(`_natural_key_hash`,`_revision_no`),
    unique(`_current_natural_key_hash`),
    check (`_revision_no` > 0),
    check (`_is_current` in (0,1)),
    check (`_valid_to` is null or `_valid_from` is null or `_valid_to` >= `_valid_from`)
);

create index if not exists `idx_src_tushare_rt_fut_min_current`
    on `src_tushare_rt_fut_min`(`_natural_key_hash`,`_is_current`);
create index if not exists `idx_src_tushare_rt_fut_min_observed`
    on `src_tushare_rt_fut_min`(`_observed_at`);

create table if not exists `src_tushare_rt_fut_min_daily` (
    `_observation_id` varchar(64) primary key,
    `_batch_id` varchar(64) not null,
    `_natural_key_hash` varchar(64) not null,
    `_revision_no` integer not null,
    `_is_current` integer not null default 1,
    `_current_natural_key_hash` varchar(64) generated always as (case when `_is_current` = 1 then `_natural_key_hash` else null end) stored,
    `_published_at` datetime(6),
    `_source_updated_at` datetime(6),
    `_observed_at` datetime(6) not null,
    `_valid_from` datetime(6),
    `_valid_to` datetime(6),
    `_payload_hash` varchar(64) not null,
    `code` longtext,
    `freq` longtext,
    `time` datetime(6),
    `open` decimal(38,8),
    `close` decimal(38,8),
    `high` decimal(38,8),
    `low` decimal(38,8),
    `vol` bigint,
    `amount` decimal(38,8),
    `oi` decimal(38,8),
    unique(`_natural_key_hash`,`_revision_no`),
    unique(`_current_natural_key_hash`),
    check (`_revision_no` > 0),
    check (`_is_current` in (0,1)),
    check (`_valid_to` is null or `_valid_from` is null or `_valid_to` >= `_valid_from`)
);

create index if not exists `idx_src_tushare_rt_fut_min_daily_current`
    on `src_tushare_rt_fut_min_daily`(`_natural_key_hash`,`_is_current`);
create index if not exists `idx_src_tushare_rt_fut_min_daily_observed`
    on `src_tushare_rt_fut_min_daily`(`_observed_at`);

create table if not exists `src_tushare_fut_wsr` (
    `_observation_id` varchar(64) primary key,
    `_batch_id` varchar(64) not null,
    `_natural_key_hash` varchar(64) not null,
    `_revision_no` integer not null,
    `_is_current` integer not null default 1,
    `_current_natural_key_hash` varchar(64) generated always as (case when `_is_current` = 1 then `_natural_key_hash` else null end) stored,
    `_published_at` datetime(6),
    `_source_updated_at` datetime(6),
    `_observed_at` datetime(6) not null,
    `_valid_from` datetime(6),
    `_valid_to` datetime(6),
    `_payload_hash` varchar(64) not null,
    `trade_date` date,
    `symbol` longtext,
    `fut_name` longtext,
    `warehouse` longtext,
    `wh_id` longtext,
    `pre_vol` bigint,
    `vol` bigint,
    `vol_chg` bigint,
    `area` longtext,
    `year` longtext,
    `grade` longtext,
    `brand` longtext,
    `place` longtext,
    `pd` bigint,
    `is_ct` longtext,
    `unit` longtext,
    `exchange` longtext,
    unique(`_natural_key_hash`,`_revision_no`),
    unique(`_current_natural_key_hash`),
    check (`_revision_no` > 0),
    check (`_is_current` in (0,1)),
    check (`_valid_to` is null or `_valid_from` is null or `_valid_to` >= `_valid_from`)
);

create index if not exists `idx_src_tushare_fut_wsr_current`
    on `src_tushare_fut_wsr`(`_natural_key_hash`,`_is_current`);
create index if not exists `idx_src_tushare_fut_wsr_observed`
    on `src_tushare_fut_wsr`(`_observed_at`);

create table if not exists `src_tushare_fut_settle` (
    `_observation_id` varchar(64) primary key,
    `_batch_id` varchar(64) not null,
    `_natural_key_hash` varchar(64) not null,
    `_revision_no` integer not null,
    `_is_current` integer not null default 1,
    `_current_natural_key_hash` varchar(64) generated always as (case when `_is_current` = 1 then `_natural_key_hash` else null end) stored,
    `_published_at` datetime(6),
    `_source_updated_at` datetime(6),
    `_observed_at` datetime(6) not null,
    `_valid_from` datetime(6),
    `_valid_to` datetime(6),
    `_payload_hash` varchar(64) not null,
    `ts_code` longtext,
    `trade_date` date,
    `settle` decimal(38,8),
    `trading_fee_rate` decimal(38,8),
    `trading_fee` decimal(38,8),
    `delivery_fee` decimal(38,8),
    `b_hedging_margin_rate` decimal(38,8),
    `s_hedging_margin_rate` decimal(38,8),
    `long_margin_rate` decimal(38,8),
    `short_margin_rate` decimal(38,8),
    `offset_today_fee` decimal(38,8),
    `exchange` longtext,
    unique(`_natural_key_hash`,`_revision_no`),
    unique(`_current_natural_key_hash`),
    check (`_revision_no` > 0),
    check (`_is_current` in (0,1)),
    check (`_valid_to` is null or `_valid_from` is null or `_valid_to` >= `_valid_from`)
);

create index if not exists `idx_src_tushare_fut_settle_current`
    on `src_tushare_fut_settle`(`_natural_key_hash`,`_is_current`);
create index if not exists `idx_src_tushare_fut_settle_observed`
    on `src_tushare_fut_settle`(`_observed_at`);

create table if not exists `src_tushare_futures_tick_file` (
    `_observation_id` varchar(64) primary key,
    `_batch_id` varchar(64) not null,
    `_natural_key_hash` varchar(64) not null,
    `_revision_no` integer not null,
    `_is_current` integer not null default 1,
    `_current_natural_key_hash` varchar(64) generated always as (case when `_is_current` = 1 then `_natural_key_hash` else null end) stored,
    `_published_at` datetime(6),
    `_source_updated_at` datetime(6),
    `_observed_at` datetime(6) not null,
    `_valid_from` datetime(6),
    `_valid_to` datetime(6),
    `_payload_hash` varchar(64) not null,
    `instrumentid` longtext,
    `bidprice1` decimal(38,8),
    `bidvolume1` bigint,
    `askprice1` decimal(38,8),
    `askvolume1` bigint,
    `lastprice` decimal(38,8),
    `volume` bigint,
    `turnover` decimal(38,8),
    `openinterest` bigint,
    `upperlimitprice` decimal(38,8),
    `lowerlimitprice` decimal(38,8),
    `openprice` decimal(38,8),
    `presettlementprice` decimal(38,8),
    `precloseprice` decimal(38,8),
    `preopeninterest` bigint,
    `tradingday` longtext,
    `updatetime` datetime(6),
    unique(`_natural_key_hash`,`_revision_no`),
    unique(`_current_natural_key_hash`),
    check (`_revision_no` > 0),
    check (`_is_current` in (0,1)),
    check (`_valid_to` is null or `_valid_from` is null or `_valid_to` >= `_valid_from`)
);

create index if not exists `idx_src_tushare_futures_tick_file_current`
    on `src_tushare_futures_tick_file`(`_natural_key_hash`,`_is_current`);
create index if not exists `idx_src_tushare_futures_tick_file_observed`
    on `src_tushare_futures_tick_file`(`_observed_at`);

create table if not exists `src_tushare_fut_holding` (
    `_observation_id` varchar(64) primary key,
    `_batch_id` varchar(64) not null,
    `_natural_key_hash` varchar(64) not null,
    `_revision_no` integer not null,
    `_is_current` integer not null default 1,
    `_current_natural_key_hash` varchar(64) generated always as (case when `_is_current` = 1 then `_natural_key_hash` else null end) stored,
    `_published_at` datetime(6),
    `_source_updated_at` datetime(6),
    `_observed_at` datetime(6) not null,
    `_valid_from` datetime(6),
    `_valid_to` datetime(6),
    `_payload_hash` varchar(64) not null,
    `trade_date` date,
    `symbol` longtext,
    `broker` longtext,
    `vol` bigint,
    `vol_chg` bigint,
    `long_hld` bigint,
    `long_chg` bigint,
    `short_hld` bigint,
    `short_chg` bigint,
    `exchange` longtext,
    unique(`_natural_key_hash`,`_revision_no`),
    unique(`_current_natural_key_hash`),
    check (`_revision_no` > 0),
    check (`_is_current` in (0,1)),
    check (`_valid_to` is null or `_valid_from` is null or `_valid_to` >= `_valid_from`)
);

create index if not exists `idx_src_tushare_fut_holding_current`
    on `src_tushare_fut_holding`(`_natural_key_hash`,`_is_current`);
create index if not exists `idx_src_tushare_fut_holding_observed`
    on `src_tushare_fut_holding`(`_observed_at`);

create table if not exists `src_tushare_fut_index_daily` (
    `_observation_id` varchar(64) primary key,
    `_batch_id` varchar(64) not null,
    `_natural_key_hash` varchar(64) not null,
    `_revision_no` integer not null,
    `_is_current` integer not null default 1,
    `_current_natural_key_hash` varchar(64) generated always as (case when `_is_current` = 1 then `_natural_key_hash` else null end) stored,
    `_published_at` datetime(6),
    `_source_updated_at` datetime(6),
    `_observed_at` datetime(6) not null,
    `_valid_from` datetime(6),
    `_valid_to` datetime(6),
    `_payload_hash` varchar(64) not null,
    `ts_code` longtext,
    `trade_date` date,
    `close` decimal(38,8),
    `open` decimal(38,8),
    `high` decimal(38,8),
    `low` decimal(38,8),
    `pre_close` decimal(38,8),
    `change` decimal(38,8),
    `pct_chg` decimal(38,8),
    `vol` decimal(38,8),
    `amount` decimal(38,8),
    unique(`_natural_key_hash`,`_revision_no`),
    unique(`_current_natural_key_hash`),
    check (`_revision_no` > 0),
    check (`_is_current` in (0,1)),
    check (`_valid_to` is null or `_valid_from` is null or `_valid_to` >= `_valid_from`)
);

create index if not exists `idx_src_tushare_fut_index_daily_current`
    on `src_tushare_fut_index_daily`(`_natural_key_hash`,`_is_current`);
create index if not exists `idx_src_tushare_fut_index_daily_observed`
    on `src_tushare_fut_index_daily`(`_observed_at`);

create table if not exists `src_tushare_fut_mapping` (
    `_observation_id` varchar(64) primary key,
    `_batch_id` varchar(64) not null,
    `_natural_key_hash` varchar(64) not null,
    `_revision_no` integer not null,
    `_is_current` integer not null default 1,
    `_current_natural_key_hash` varchar(64) generated always as (case when `_is_current` = 1 then `_natural_key_hash` else null end) stored,
    `_published_at` datetime(6),
    `_source_updated_at` datetime(6),
    `_observed_at` datetime(6) not null,
    `_valid_from` datetime(6),
    `_valid_to` datetime(6),
    `_payload_hash` varchar(64) not null,
    `ts_code` longtext,
    `trade_date` date,
    `mapping_ts_code` longtext,
    unique(`_natural_key_hash`,`_revision_no`),
    unique(`_current_natural_key_hash`),
    check (`_revision_no` > 0),
    check (`_is_current` in (0,1)),
    check (`_valid_to` is null or `_valid_from` is null or `_valid_to` >= `_valid_from`)
);

create index if not exists `idx_src_tushare_fut_mapping_current`
    on `src_tushare_fut_mapping`(`_natural_key_hash`,`_is_current`);
create index if not exists `idx_src_tushare_fut_mapping_observed`
    on `src_tushare_fut_mapping`(`_observed_at`);

create table if not exists `src_tushare_fut_weekly_detail` (
    `_observation_id` varchar(64) primary key,
    `_batch_id` varchar(64) not null,
    `_natural_key_hash` varchar(64) not null,
    `_revision_no` integer not null,
    `_is_current` integer not null default 1,
    `_current_natural_key_hash` varchar(64) generated always as (case when `_is_current` = 1 then `_natural_key_hash` else null end) stored,
    `_published_at` datetime(6),
    `_source_updated_at` datetime(6),
    `_observed_at` datetime(6) not null,
    `_valid_from` datetime(6),
    `_valid_to` datetime(6),
    `_payload_hash` varchar(64) not null,
    `exchange` longtext,
    `prd` longtext,
    `name` longtext,
    `vol` bigint,
    `vol_yoy` decimal(38,8),
    `amount` decimal(38,8),
    `amout_yoy` decimal(38,8),
    `cumvol` bigint,
    `cumvol_yoy` decimal(38,8),
    `cumamt` decimal(38,8),
    `cumamt_yoy` decimal(38,8),
    `open_interest` bigint,
    `interest_wow` decimal(38,8),
    `mc_close` decimal(38,8),
    `close_wow` decimal(38,8),
    `week` longtext,
    `week_date` date,
    unique(`_natural_key_hash`,`_revision_no`),
    unique(`_current_natural_key_hash`),
    check (`_revision_no` > 0),
    check (`_is_current` in (0,1)),
    check (`_valid_to` is null or `_valid_from` is null or `_valid_to` >= `_valid_from`)
);

create index if not exists `idx_src_tushare_fut_weekly_detail_current`
    on `src_tushare_fut_weekly_detail`(`_natural_key_hash`,`_is_current`);
create index if not exists `idx_src_tushare_fut_weekly_detail_observed`
    on `src_tushare_fut_weekly_detail`(`_observed_at`);

create table if not exists `src_tushare_ft_limit` (
    `_observation_id` varchar(64) primary key,
    `_batch_id` varchar(64) not null,
    `_natural_key_hash` varchar(64) not null,
    `_revision_no` integer not null,
    `_is_current` integer not null default 1,
    `_current_natural_key_hash` varchar(64) generated always as (case when `_is_current` = 1 then `_natural_key_hash` else null end) stored,
    `_published_at` datetime(6),
    `_source_updated_at` datetime(6),
    `_observed_at` datetime(6) not null,
    `_valid_from` datetime(6),
    `_valid_to` datetime(6),
    `_payload_hash` varchar(64) not null,
    `trade_date` date,
    `ts_code` longtext,
    `name` longtext,
    `up_limit` decimal(38,8),
    `down_limit` decimal(38,8),
    `m_ratio` decimal(38,8),
    `cont` longtext,
    `exchange` longtext,
    unique(`_natural_key_hash`,`_revision_no`),
    unique(`_current_natural_key_hash`),
    check (`_revision_no` > 0),
    check (`_is_current` in (0,1)),
    check (`_valid_to` is null or `_valid_from` is null or `_valid_to` >= `_valid_from`)
);

create index if not exists `idx_src_tushare_ft_limit_current`
    on `src_tushare_ft_limit`(`_natural_key_hash`,`_is_current`);
create index if not exists `idx_src_tushare_ft_limit_observed`
    on `src_tushare_ft_limit`(`_observed_at`);

create table if not exists `src_tushare_opt_basic` (
    `_observation_id` varchar(64) primary key,
    `_batch_id` varchar(64) not null,
    `_natural_key_hash` varchar(64) not null,
    `_revision_no` integer not null,
    `_is_current` integer not null default 1,
    `_current_natural_key_hash` varchar(64) generated always as (case when `_is_current` = 1 then `_natural_key_hash` else null end) stored,
    `_published_at` datetime(6),
    `_source_updated_at` datetime(6),
    `_observed_at` datetime(6) not null,
    `_valid_from` datetime(6),
    `_valid_to` datetime(6),
    `_payload_hash` varchar(64) not null,
    `ts_code` longtext,
    `symbol` longtext,
    `exchange` longtext,
    `name` longtext,
    `per_unit` longtext,
    `opt_code` longtext,
    `opt_type` longtext,
    `call_put` longtext,
    `exercise_type` longtext,
    `exercise_price` decimal(38,8),
    `opt_multiplier` decimal(38,8),
    `s_month` longtext,
    `maturity_date` date,
    `list_price` decimal(38,8),
    `list_date` date,
    `delist_date` date,
    `last_edate` date,
    `last_ddate` date,
    `quote_unit` longtext,
    `min_price_chg` longtext,
    unique(`_natural_key_hash`,`_revision_no`),
    unique(`_current_natural_key_hash`),
    check (`_revision_no` > 0),
    check (`_is_current` in (0,1)),
    check (`_valid_to` is null or `_valid_from` is null or `_valid_to` >= `_valid_from`)
);

create index if not exists `idx_src_tushare_opt_basic_current`
    on `src_tushare_opt_basic`(`_natural_key_hash`,`_is_current`);
create index if not exists `idx_src_tushare_opt_basic_observed`
    on `src_tushare_opt_basic`(`_observed_at`);

create table if not exists `src_tushare_opt_daily` (
    `_observation_id` varchar(64) primary key,
    `_batch_id` varchar(64) not null,
    `_natural_key_hash` varchar(64) not null,
    `_revision_no` integer not null,
    `_is_current` integer not null default 1,
    `_current_natural_key_hash` varchar(64) generated always as (case when `_is_current` = 1 then `_natural_key_hash` else null end) stored,
    `_published_at` datetime(6),
    `_source_updated_at` datetime(6),
    `_observed_at` datetime(6) not null,
    `_valid_from` datetime(6),
    `_valid_to` datetime(6),
    `_payload_hash` varchar(64) not null,
    `ts_code` longtext,
    `trade_date` date,
    `exchange` longtext,
    `pre_settle` decimal(38,8),
    `pre_close` decimal(38,8),
    `open` decimal(38,8),
    `high` decimal(38,8),
    `low` decimal(38,8),
    `close` decimal(38,8),
    `settle` decimal(38,8),
    `vol` decimal(38,8),
    `amount` decimal(38,8),
    `oi` decimal(38,8),
    unique(`_natural_key_hash`,`_revision_no`),
    unique(`_current_natural_key_hash`),
    check (`_revision_no` > 0),
    check (`_is_current` in (0,1)),
    check (`_valid_to` is null or `_valid_from` is null or `_valid_to` >= `_valid_from`)
);

create index if not exists `idx_src_tushare_opt_daily_current`
    on `src_tushare_opt_daily`(`_natural_key_hash`,`_is_current`);
create index if not exists `idx_src_tushare_opt_daily_observed`
    on `src_tushare_opt_daily`(`_observed_at`);

create table if not exists `src_tushare_opt_mins` (
    `_observation_id` varchar(64) primary key,
    `_batch_id` varchar(64) not null,
    `_natural_key_hash` varchar(64) not null,
    `_revision_no` integer not null,
    `_is_current` integer not null default 1,
    `_current_natural_key_hash` varchar(64) generated always as (case when `_is_current` = 1 then `_natural_key_hash` else null end) stored,
    `_published_at` datetime(6),
    `_source_updated_at` datetime(6),
    `_observed_at` datetime(6) not null,
    `_valid_from` datetime(6),
    `_valid_to` datetime(6),
    `_payload_hash` varchar(64) not null,
    `ts_code` longtext,
    `trade_time` datetime(6),
    `open` decimal(38,8),
    `close` decimal(38,8),
    `high` decimal(38,8),
    `low` decimal(38,8),
    `vol` bigint,
    `amount` decimal(38,8),
    `oi` decimal(38,8),
    unique(`_natural_key_hash`,`_revision_no`),
    unique(`_current_natural_key_hash`),
    check (`_revision_no` > 0),
    check (`_is_current` in (0,1)),
    check (`_valid_to` is null or `_valid_from` is null or `_valid_to` >= `_valid_from`)
);

create index if not exists `idx_src_tushare_opt_mins_current`
    on `src_tushare_opt_mins`(`_natural_key_hash`,`_is_current`);
create index if not exists `idx_src_tushare_opt_mins_observed`
    on `src_tushare_opt_mins`(`_observed_at`);
