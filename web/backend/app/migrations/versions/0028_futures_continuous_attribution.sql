-- description: Add governed futures fee schedules, continuous contracts, margin and roll attribution

create table if not exists futures_fee_schedules (
    product varchar(32) not null,
    exchange varchar(32) not null,
    open_rate real not null default 0,
    close_rate real not null default 0,
    close_today_rate real not null default 0,
    per_contract real not null default 0,
    slippage_ticks real not null default 0,
    currency varchar(16) not null default 'CNY',
    version varchar(64) not null,
    source varchar(64) not null,
    updated_at varchar(64) not null,
    primary key (product, exchange)
);

create table if not exists futures_continuous_builds (
    id varchar(64) primary key,
    product varchar(32) not null,
    exchange varchar(32) not null,
    start_date varchar(16) not null,
    end_date varchar(16) not null,
    adjustment varchar(32) not null,
    contracts real not null,
    mapping_batch_id varchar(64) not null,
    fee_schedule_version varchar(64) not null,
    config_json longtext not null,
    summary_json longtext not null,
    created_at varchar(64) not null
);

create table if not exists futures_continuous_bars (
    build_id varchar(64) not null,
    trade_date varchar(16) not null,
    contract_code varchar(64) not null,
    raw_open real,
    raw_close real not null,
    adjusted_close real not null,
    adjustment_factor real not null,
    multiplier real not null,
    margin_rate real not null,
    notional real not null,
    margin_required real not null,
    variation_pnl real not null,
    commission real not null,
    slippage real not null,
    net_pnl real not null,
    cumulative_net_pnl real not null,
    is_roll integer not null default 0,
    roll_gap real,
    roll_yield real,
    primary key (build_id, trade_date)
);

create table if not exists futures_roll_events (
    id varchar(64) primary key,
    build_id varchar(64) not null,
    trade_date varchar(16) not null,
    from_contract varchar(64) not null,
    to_contract varchar(64) not null,
    from_price real not null,
    to_price real not null,
    roll_gap real not null,
    roll_yield real not null,
    market_pnl real not null,
    commission real not null,
    slippage real not null,
    net_pnl real not null
);

create index idx_futures_continuous_builds_lookup
    on futures_continuous_builds(product, exchange, created_at);
create index idx_futures_continuous_bars_build
    on futures_continuous_bars(build_id, trade_date);
create index idx_futures_roll_events_build
    on futures_roll_events(build_id, trade_date);
