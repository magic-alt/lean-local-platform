-- description: Bound production lineage aggregation with a covering scope and batch index
-- compatibility: additive index only; canonical market rows and certification evidence are unchanged
-- rollback: keep the index during rollback unless an operator confirms lineage certification is disabled

create index idx_market_daily_lineage
    on market_daily_bars(asset_class, market, source, batch_id, symbol);
