-- description: Make the existing Parquet lake authoritative and retire SQL quote stores
-- rollback: irreversible; restore quote tables only from a reviewed backup if the Parquet cutover is abandoned

drop view if exists current_market_daily_bars_v2;
drop view if exists all_factor_values;
drop view if exists daily_basic_factor_values;

drop table if exists market_daily_bar_selections_v2;
drop table if exists market_daily_metrics_v2;
drop table if exists market_trading_status_v2;
drop table if exists market_daily_bars_v2;
drop table if exists daily_basic_values;

drop table if exists market_trade_status;
drop table if exists market_intraday_bars;
drop table if exists market_daily_bars;
drop table if exists adjustment_factors;

create table if not exists market_lake_cutovers (
    id varchar(64) primary key,
    status varchar(32) not null,
    parquet_root text not null,
    verification_json text not null,
    dropped_tables_json text not null,
    created_at varchar(64) not null
);
