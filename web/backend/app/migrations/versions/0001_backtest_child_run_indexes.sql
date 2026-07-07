-- description: Add indexes for optimization child backtest runs
create index if not exists idx_backtest_runs_task_created
    on backtest_runs(task_id, created_at desc);

create index if not exists idx_backtest_runs_project_status_created
    on backtest_runs(project_id, status, created_at desc);
