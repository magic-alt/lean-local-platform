-- description: Add structured backtest failure metadata

alter table backtest_runs add column failure_json text;
