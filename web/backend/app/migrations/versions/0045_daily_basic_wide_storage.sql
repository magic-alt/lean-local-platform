-- description: Store TuShare daily_basic as one row per symbol and trade date
-- compatibility: additive table and compatibility views; legacy EAV rows remain readable
-- rollback: stop daily_basic writers, archive the wide table, then remove the views and table with a reviewed forward migration

create table if not exists daily_basic_values (
    symbol varchar(32) not null,
    trade_date varchar(16) not null,
    turnover_rate real,
    turnover_rate_float real,
    volume_ratio real,
    pe real,
    pe_ttm real,
    pb real,
    ps real,
    ps_ttm real,
    dividend_yield real,
    dividend_yield_ttm real,
    total_share_shares real,
    float_share_shares real,
    free_share_shares real,
    total_mv_cny real,
    circ_mv_cny real,
    source varchar(64) not null,
    batch_id varchar(64),
    created_at varchar(64) not null,
    primary key(symbol, trade_date, source)
);
create index if not exists idx_daily_basic_values_date_symbol
    on daily_basic_values(trade_date, symbol);

create view if not exists daily_basic_factor_values as
select symbol,trade_date,factor_name,value,source,batch_id,created_at
from factor_values f where f.source='tushare:daily_basic'
  and not exists (
      select 1 from daily_basic_values d
      where d.symbol=f.symbol and d.trade_date=f.trade_date and d.source=f.source
  )
union all select symbol,trade_date,'turnover_rate',turnover_rate,source,batch_id,created_at from daily_basic_values where turnover_rate is not null
union all select symbol,trade_date,'turnover_rate_float',turnover_rate_float,source,batch_id,created_at from daily_basic_values where turnover_rate_float is not null
union all select symbol,trade_date,'volume_ratio',volume_ratio,source,batch_id,created_at from daily_basic_values where volume_ratio is not null
union all select symbol,trade_date,'pe',pe,source,batch_id,created_at from daily_basic_values where pe is not null
union all select symbol,trade_date,'pe_ttm',pe_ttm,source,batch_id,created_at from daily_basic_values where pe_ttm is not null
union all select symbol,trade_date,'pb',pb,source,batch_id,created_at from daily_basic_values where pb is not null
union all select symbol,trade_date,'ps',ps,source,batch_id,created_at from daily_basic_values where ps is not null
union all select symbol,trade_date,'ps_ttm',ps_ttm,source,batch_id,created_at from daily_basic_values where ps_ttm is not null
union all select symbol,trade_date,'dividend_yield',dividend_yield,source,batch_id,created_at from daily_basic_values where dividend_yield is not null
union all select symbol,trade_date,'dividend_yield_ttm',dividend_yield_ttm,source,batch_id,created_at from daily_basic_values where dividend_yield_ttm is not null
union all select symbol,trade_date,'total_share_shares',total_share_shares,source,batch_id,created_at from daily_basic_values where total_share_shares is not null
union all select symbol,trade_date,'float_share_shares',float_share_shares,source,batch_id,created_at from daily_basic_values where float_share_shares is not null
union all select symbol,trade_date,'free_share_shares',free_share_shares,source,batch_id,created_at from daily_basic_values where free_share_shares is not null
union all select symbol,trade_date,'total_mv_cny',total_mv_cny,source,batch_id,created_at from daily_basic_values where total_mv_cny is not null
union all select symbol,trade_date,'circ_mv_cny',circ_mv_cny,source,batch_id,created_at from daily_basic_values where circ_mv_cny is not null;

create view if not exists all_factor_values as
select symbol,trade_date,factor_name,value,source,batch_id,created_at
from factor_values where source<>'tushare:daily_basic'
union all
select symbol,trade_date,factor_name,value,source,batch_id,created_at
from daily_basic_factor_values;
