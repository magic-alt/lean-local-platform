# LEAN Runner

The production backtest runner is `web/backend/app/runners/lean_runner.py`. It wraps LEAN Docker execution and keeps run workspaces isolated.

## Key Files

- `web/backend/app/runners/lean_runner.py`: workspace preparation, config writing, A-share helper writing, result/report/manifest collection.
- `web/backend/app/runners/docker_runner.py`: subprocess execution, stdout/stderr streaming, timeout handling, container stop.
- `web/backend/app/lean.py`: LEAN `config.json` generation, Docker command and mount construction, result extraction helpers.
- `web/backend/app/tasks/worker.py`: async task lifecycle, pre-run gates, cache restoration, status persistence.

## Workspace Layout

Every run uses:

```text
web/runtime/runs/<run_id>/
  config.json
  ashare_execution.py              # only when ashareRules=true
  ashare_trade_status.json         # only when ashareRules=true
  results/
    stdout.log
    <run_id>.json
    <run_id>-summary.json
    <run_id>-order-events.json
    <run_id>-log.txt
    report.html
    data-monitor-report-*.json
    succeeded-data-requests-*.txt
    failed-data-requests-*.txt
    artifact-manifest.json
```

`stdout.log` is a per-run tee of Docker/LEAN console output. The same lines still go to the task log for live UI viewing.

`artifact-manifest.json` is written even when LEAN fails or times out, as long as the runner reaches manifest writing. It records run id, container name, exit code, timeout flag, error text, and every discovered input/output artifact, including `stdout.log`.

## Docker Mounts

`docker_command()` mounts:

```text
config.json                      -> /Lean/Launcher/bin/Debug/config.json:ro
LEAN_DATA_DIR                    -> /Lean/Data:ro
results/                         -> /Lean/Results
OBJECT_STORE_DIR                 -> /Lean/Launcher/bin/Debug/storage
immutable project snapshot       -> /Lean/Project:ro
run directory                    -> /Lean/Run:ro, only for A-share support files
```

Host path resolution uses `LEAN_HOST_PLATFORM_DIR` and `LEAN_HOST_DATA_DIR` when the backend itself runs in Docker and needs to pass host-visible paths to the sibling LEAN container.

## Config Generation

`base_config()` writes a LEAN backtesting config with:

- `environment=backtesting`
- `algorithm-type-name`
- `algorithm-language`
- `algorithm-location`
- `/Lean/Data` data folder
- `/Lean/Results` results folder
- local disk map/factor providers
- file system data feed
- parameters from `lean_job_parameters(parameters)`
- `/Lean/Run` in `python-additional-paths` when `ashareRules=true`

## A-Share Support

When `ashareRules=true`, `write_ashare_execution_artifacts()` writes:

- `ashare_execution.py`: fee model, slippage model, T+1, lot rounding, buy/sell blocking helper.
- `ashare_trade_status.json`: per-symbol/per-date status from canonical `market_trade_status`.

The generated strategy template imports `AShareExecutionHelper` and calls it instead of raw `set_holdings()` for A-share execution. Production backtests always execute a versioned project snapshot; the standalone Docker demo is not a runner fallback.

## Output Contract

`LeanRunner.run_backtest()` returns:

```python
{
    "exit_code": int,
    "timed_out": bool,
    "container_name": str,
    "work_dir": str,
    "results_dir": str,
    "result_json_path": str | None,
    "summary_json_path": str | None,
    "report_html_path": str | None,
    "artifact_manifest_path": str,
    "stdout_log_path": str,
    "statistics": dict,
    "error": str | None,
}
```

The worker maps this into `backtest_runs` and task status.

## Error Types

Current implementation reports errors as task/backtest `error` strings. Important classes:

- Docker command missing: `LeanPlatformError`.
- Docker unavailable or container exit non-zero: failed run with exit code.
- Timeout: `timed_out=true`, container stop attempted, failed run.
- Missing result JSON: failed run even if container exits.
- A-share preflight failure: failed before Docker when data, QA gate, or benchmark is missing.
- Cancellation: `cancel_backtest()` revokes Celery task when possible and stops the named container. `cancel_task()` extends this behavior to optimization child backtests, research sessions, reports, and generic Celery tasks.

Future improvement: formalize error codes such as `DOCKER_NOT_FOUND`, `LEAN_TIMEOUT`, `RESULT_MISSING`, `DATA_QA_BLOCKED`, `BENCHMARK_MISSING`.

## Artifact Archiving

`result_service.archive_backtest_artifacts()` stores raw outputs into `stored_objects` with namespace `backtest-results`. Important object keys:

```text
<run_id>/result.json
<run_id>/summary.json
<run_id>/artifacts/<filename>
```

This makes parsed results reproducible and keeps LEAN raw outputs available through reports.
