# Web E2E Audit Report

Generated: 2026-07-08 23:17 CST

## 1. Test Environment

| Item | Value |
| --- | --- |
| OS | macOS 26.5.1 arm64 |
| Node / npm | Node v26.0.0 / npm 11.14.1 |
| Package manager | npm |
| Frontend | React 19, Vite 7, Ant Design 6, ECharts, HashRouter |
| Backend | FastAPI, Celery worker, MySQL, Redis, ClickHouse |
| Frontend URL | http://127.0.0.1:15173 |
| Backend URL | http://127.0.0.1:18080 |
| Backend start | `web/backend/.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 18080` |
| Worker start | `web/backend/.venv/bin/python -m celery -A app.tasks.celery_app worker --loglevel=info --pool=solo` |
| Docker infra | `docker compose up -d --wait mysql redis clickhouse` with E2E ports |
| Docker status | available, server 29.4.3 |
| LEAN image | `quantconnect/lean:latest`, image id `sha256:19e3633d2da1e8b378dd6af4b999b0ca6cf0660a1bf557a0518a2e43fc270823` |
| Test browsers | Chromium desktop 1440x900; Chromium desktop 1920x1080 smoke |
| Skipped by request | mobile Chromium, Firefox, WebKit |
| Test data | SPY copied from `/Users/kaermax/Lean/Data/equity/usa/daily/spy.zip`; A-share 510300/000300 deterministic E2E fixtures under `web/runtime/e2e-lean-data` |

## 2. Web Function Map

| Page | Route | Main functions / API | Automation status | Notes |
| --- | --- | --- | --- | --- |
| Dashboard | `/` | Overview cards, workflow links, `/api/health` | Covered | smoke screenshot |
| Workspace | `/workspace` | Project workspace entry, project file APIs | Covered | navigation/render |
| Projects | `/projects` | create/list/open project, templates, files | Covered | creates `E2E_MA_Cross_Test`, opens code editor |
| Data Library | `/data` | symbols/providers/import/query data APIs | Covered | navigation/render |
| Backtests | `/backtests` | configure/run/filter backtests, `/api/backtests` | Covered | form validation, run submit, history filters |
| Run Detail | `/runs/:id` | status/logs/result/chart/report APIs | Covered | metrics, logs, charts, records, refresh persistence |
| Compare | `/compare` | compare runs | Covered | navigation/render |
| Optimization | `/optimization` | optimization form/list | Covered | navigation/render |
| Paper | `/paper` | paper/replay controls | Covered | navigation/render |
| Research | `/research` | research helpers | Covered | navigation/render |
| A-Share Research | `/ashare-research` | factor/research workflows | Covered | navigation/render |
| Reports | `/reports` | list/export reports, `/api/reports` | Covered | report listing plus JSON/CSV/HTML/PDF export via API |
| Object Store | `/object-store` | stored object listing | Covered | navigation/render |
| Tasks | `/tasks` | task list/log status | Covered | navigation/render |
| Monitoring | `/monitoring` | dependency health, Docker/LEAN/data/results checks | Covered | checks API, Docker, LEAN image, runner, data dir, results dir |
| Settings | `/settings` | app settings | Covered | navigation/render |
| 404 | `*` | friendly missing route result | Covered | `/missing-e2e-route` |

## 3. Automation Files

Added/updated:

- `web/frontend/playwright.config.ts`
- `web/frontend/package.json`, `web/frontend/package-lock.json`
- `tests/e2e/global-setup.ts`, `tests/e2e/global-teardown.ts`
- `tests/e2e/fixtures/console.ts`, `tests/e2e/fixtures/seed_e2e_data.py`
- `tests/e2e/pages/*.page.ts`
- `tests/e2e/utils/*.ts`
- `tests/e2e/specs/01-smoke.spec.ts` through `09-resilience.spec.ts`
- `tests/e2e/README.md`
- Frontend/backend support changes in `web/frontend/src/*` and `web/backend/app/*`

## 4. Test Cases

| Case ID | Name | Coverage | Input | Expected | Actual |
| --- | --- | --- | --- | --- | --- |
| 01 | smoke/navigation | all desktop routes, 404, console/500 guard | route list | no white screen/errors | Pass |
| 02 | system status | API, Docker, LEAN image/runner, dirs | Monitoring page | all critical deps healthy | Pass |
| 03 | strategy management | project create, workspace, code editor persistence | `E2E_MA_Cross_Test` | project opens after refresh | Pass |
| 04 | config validation | project/symbol/date/cash validation | invalid/missing fields | clear validation errors | Pass |
| 05 | SPY MA cross | full Web -> API -> Docker/LEAN -> result chain | SPY 2020 daily | completed + metrics/charts/logs/history | Pass |
| 06 | A-share ETF | China ETF daily run | 510300 2024 daily, jqdata fixture | completed + market/source preserved | Pass |
| 07 | invalid symbol | failure path and history | `INVALID_SYMBOL_E2E` | failed, clear error, no white screen | Pass |
| 08 | history/export | search/status/market filters, report export | success + failed runs | history visible, exports non-empty | Pass |
| 09a | API 500 resilience | friendly error state | mocked `/api/backtests` 500 | no white screen | Pass |
| 09b | long logs | log rendering stability | 2000 log lines | Logs tab renders | Pass |
| 09c | duplicate submit | run button pending guard | double click run | one POST only | Pass |

Final command: `cd web/frontend && npm run test:e2e` -> 11 passed, 0 failed, 0 skipped, duration 79.7s.

## 5. Real Backtest Results

### Case A: SPY MA Cross

| Field | Value |
| --- | --- |
| Status | success |
| Backtest ID | `spy-20200101-20201231-20260708231649` |
| Initial cash | 100000 |
| Final equity | 120623.32 |
| Total return | 20.623% |
| Sharpe | 0.954 |
| Total trades | 5 |
| Screenshot | `tests/e2e/reports/artifacts/E2E_Backtest_MA_Cross_SPY_2020.png` |
| Exports | JSON, CSV, HTML, PDF under `tests/e2e/reports/artifacts/` |

### Case B: A-share ETF 510300

| Field | Value |
| --- | --- |
| Status | success |
| Data source | jqdata E2E fixture |
| Data exists | yes, 262 daily rows for 510300 and 000300, 2024-01-01 to 2024-12-31 |
| Backtest ID | `510300-20240101-20241231-20260708231703` |
| Final equity | 56514.77 |
| Total return | -43.485% |
| Max drawdown | 49.100% |
| Sharpe | -3.341 |
| Screenshot | `tests/e2e/reports/artifacts/E2E_Backtest_A_SHARE_ETF_510300_2024.png` |

### Case C: Invalid Symbol Error Handling

| Field | Value |
| --- | --- |
| Status | failed |
| Backtest ID | `invalidsymbole2e-20200101-20200301-20260708231720` |
| Error | Missing LEAN daily trade data for INVALID.SYMBOL.E2E (equity/usa). |
| Entered history | yes |
| Can return and modify | yes, run detail/history remain usable |
| White screen | no |
| Uncaught exception | no |
| Screenshot | `tests/e2e/reports/artifacts/E2E_Backtest_Invalid_Symbol_Error.png` |

## 6. Defects

Fixed:

| Severity | Defect | Fix |
| --- | --- | --- |
| High | Invalid/preflight backtests returned 400 and were not saved to history | backend now creates a failed backtest run with task log and clear error |
| High | System status did not verify LEAN image, LEAN runner, or results directory writeability | added dependency checks and UI assertions |
| High | Backtest form could not submit invalid symbol for failure-path testing | symbol field now accepts custom values |
| Medium | Initial cash `0` was coerced by the UI and could bypass intended validation | removed coercing min and added explicit validator |
| Medium | Duplicate run clicks could submit more than one request | added submit loading/disabled guard |
| Medium | History filters lacked name/market filtering and Clear did not reset controls | added filters and reset behavior |
| Medium | Result page missed stable assertions for metrics/charts/records/logs | added fields, records tab, chart test ids, and metric cards |
| Low | Missing route had no friendly 404 | added catch-all route |
| Low | Vite proxy target was fixed to port 8000 | added `VITE_API_PROXY_TARGET` for isolated E2E backend |

Open / accepted gaps:

| Severity | Gap | Recommendation |
| --- | --- | --- |
| Medium | Mobile, Firefox, WebKit skipped by request | re-enable after responsive layout and cross-browser triage |
| Medium | Strategy edit/delete/invalid-code validation not fully covered | add CRUD/editor assertions after product behavior is defined |
| Low | Export is verified through authenticated Playwright API calls after Web report listing | add direct UI download button assertions if/when export buttons are exposed |
| Low | A-share data uses deterministic fixture, not a live provider | add provider-backed nightly integration when data credentials are available |

## 7. Coverage Matrix

| Area | Coverage |
| --- | --- |
| Page coverage | 16/16 desktop routes covered |
| Form coverage | project, symbol, market, dates, cash, benchmark, fee, slippage, data source covered |
| API coverage | health, dependencies, projects, backtests, logs, results, charts, reports covered |
| Backtest chain | Web submit -> API create -> Celery -> Docker/LEAN -> logs/status -> parsed result -> history covered |
| Error handling | API 500, invalid symbol, long logs, duplicate submit, refresh persistence covered |
| Charts | equity/drawdown containers, data-point counts, hover/resize/tabs covered |
| History | success/failed persistence, name/status/market filters, open detail covered |
| Export | JSON/CSV/HTML/PDF non-empty exports covered |
| Compatibility | Chromium 1440 full suite, Chromium 1920 smoke covered; mobile/Firefox/WebKit skipped by request |

## 8. Conclusion

- Level Web E2E Pass: achieved.
- Level Web E2E Plus: partially achieved. Three real cases, HTML report, API resilience, history/export are covered; mobile/Firefox/WebKit were skipped by request.
- Continuous regression: allowed for desktop Chromium.
- CI integration: allowed for desktop Chromium after installing Playwright browsers and Docker/LEAN image in CI.
- Expansion readiness: ready to add more strategies/symbols using the same `E2E_` namespace and isolated data directory.

Useful artifacts:

- HTML report: `tests/e2e/reports/html/index.html`
- JSON result: `tests/e2e/reports/results.json`
- Environment: `tests/e2e/reports/environment.json`
- Data source: `tests/e2e/reports/data-source.json`
- Case summary: `tests/e2e/reports/e2e-case-results.json`
- API log: `tests/e2e/reports/api.log`
- Worker log: `tests/e2e/reports/worker.log`
- Final failure screenshots/traces: none; final run passed with trace/video retained only on failure.
