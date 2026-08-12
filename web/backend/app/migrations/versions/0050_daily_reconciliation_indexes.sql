-- description: Bound full-rebuild daily reconciliation by source and trade-date indexes
-- compatibility: additive indexes only; canonical rows and synchronization checkpoints are unchanged
-- rollback: keep the indexes during rollback unless full-rebuild reconciliation is permanently disabled

create index if not exists idx_market_status_source_date_symbol
    on market_trade_status(source, trade_date, symbol);

create index if not exists idx_market_daily_source_date_symbol
    on market_daily_bars(source, trade_date, symbol);
