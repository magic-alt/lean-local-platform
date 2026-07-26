# 完整 API 端点索引

> 本文由 `scripts/generate_help_api_reference.py` 根据 FastAPI OpenAPI 确定性生成。
> 业务语义、完整示例和错误处理请参阅 [API 使用指南](../api.md)。

当前共收录 **270** 个公开业务操作。交互式 Schema 以 `/docs` 和 `/openapi.json` 为准。

## ashare

| Method | Path | Summary | Input | Success |
| --- | --- | --- | --- | --- |
| `POST` | `/api/ashare/adjustment-factors/import` | Import Adjustments | body `AdjustmentFactorImport` | `200` - |
| `GET` | `/api/ashare/adjustment-factors/{symbol}` | Ashare Adjustments | `symbol` (path, required)<br>`start` (query)<br>`end` (query) | `200` - |
| `POST` | `/api/ashare/corporate-actions/import` | Import Actions | body `CorporateActionImport` | `200` - |
| `GET` | `/api/ashare/corporate-actions/{symbol}` | Ashare Actions | `symbol` (path, required)<br>`start` (query)<br>`end` (query) | `200` - |
| `GET` | `/api/ashare/reference-data/coverage` | Ashare Reference Data Coverage | `indexCode` (query) | `200` - |
| `POST` | `/api/ashare/securities/import` | Import Securities | body `SecurityMasterImport` | `200` - |
| `GET` | `/api/ashare/securities/{symbol}/status` | Ashare Security Status | `symbol` (path, required)<br>`date` (query, required) | `200` - |
| `POST` | `/api/ashare/trade-status/import` | Import Status | body `TradeStatusImport` | `200` - |
| `POST` | `/api/ashare/tushare/securities/import` | Import Tushare Securities | body `TushareStockBasicImport` | `200` - |
| `POST` | `/api/ashare/tushare/trade-calendar/import` | Import Tushare Calendar | body `TushareTradeCalendarImport` | `200` - |
| `GET` | `/api/ashare/universe/{universe_code}` | Ashare Universe | `universe_code` (path, required)<br>`date` (query, required) | `200` - |
| `GET` | `/api/ashare/universe/{universe_code}/tradable` | Ashare Tradable Universe | `universe_code` (path, required)<br>`date` (query, required)<br>`minListedDays` (query)<br>`excludeSt` (query) | `200` - |
| `GET` | `/api/data/batches` | Import Batches | - | `200` - |
| `GET` | `/api/data/batches/{batch_id}` | Import Batch | `batch_id` (path, required) | `200` - |
| `GET` | `/api/data/qa/{batch_id}` | Import Batch Qa | `batch_id` (path, required) | `200` - |

## backtests

| Method | Path | Summary | Input | Success |
| --- | --- | --- | --- | --- |
| `GET` | `/api/backtests` | Backtests | `status` (query)<br>`projectId` (query)<br>`symbol` (query)<br>`fromDate` (query)<br>`toDate` (query)<br>`limit` (query)<br>`offset` (query)<br>`paged` (query) | `200` - |
| `POST` | `/api/backtests` | Create Backtest | body `BacktestRequest` | `200` - |
| `POST` | `/api/backtests/preflight` | Preflight Backtest | body `BacktestRequest` | `200` - |
| `DELETE` | `/api/backtests/{run_id}` | Delete | `run_id` (path, required) | `200` - |
| `GET` | `/api/backtests/{run_id}` | Detail | `run_id` (path, required) | `200` - |
| `GET` | `/api/backtests/{run_id}/admission` | Admission | `run_id` (path, required)<br>`profile` (query) | `200` - |
| `GET` | `/api/backtests/{run_id}/artifacts/{name}` | Artifact | `run_id` (path, required)<br>`name` (path, required) | `200` - |
| `POST` | `/api/backtests/{run_id}/cancel` | Cancel | `run_id` (path, required) | `200` - |
| `GET` | `/api/backtests/{run_id}/chart-data` | Chart Data | `run_id` (path, required) | `200` - |
| `GET` | `/api/backtests/{run_id}/logs` | Logs | `run_id` (path, required)<br>`offset` (query)<br>`cursor` (query)<br>`limit` (query) | `200` - |
| `GET` | `/api/backtests/{run_id}/result` | Result | `run_id` (path, required) | `200` - |
| `GET` | `/api/backtests/{run_id}/results` | Results | `run_id` (path, required) | `200` - |
| `GET` | `/api/backtests/{run_id}/status` | Status | `run_id` (path, required) | `200` - |
| `GET` | `/api/backtests/{run_id}/validation` | Validation | `run_id` (path, required) | `200` - |
| `GET` | `/api/backtests/{run_id}/versions` | Versions | `run_id` (path, required) | `200` - |

## compare

| Method | Path | Summary | Input | Success |
| --- | --- | --- | --- | --- |
| `POST` | `/api/compare/backtests` | Compare Backtests | body `BacktestCompareRequest` | `200` - |

## convertible-bonds

| Method | Path | Summary | Input | Success |
| --- | --- | --- | --- | --- |
| `POST` | `/api/cbond/call-events` | Import Call Events | body `CBondCallEventImport` | `200` - |
| `GET` | `/api/cbond/call-risk` | Call Risk | `date` (query, required) | `200` - |
| `POST` | `/api/cbond/daily` | Import Daily | body `CBondDailyImport` | `200` - |
| `GET` | `/api/cbond/double-low` | Double Low | `date` (query, required)<br>`maxDoubleLow` (query)<br>`excludeCallRisk` (query)<br>`limit` (query) | `200` - |
| `POST` | `/api/cbond/terms` | Import Terms | body `CBondTermImport` | `200` - |

## data

| Method | Path | Summary | Input | Success |
| --- | --- | --- | --- | --- |
| `GET` | `/api/asset-classes` | Available Asset Classes | - | `200` - |
| `GET` | `/api/data-assets` | Data Assets | `status` (query)<br>`includeSuperseded` (query)<br>`limit` (query)<br>`offset` (query)<br>`paged` (query) | `200` - |
| `GET` | `/api/data/catalog` | Data Catalog | - | `200` - |
| `GET` | `/api/data/coverage/ashare` | Data Coverage Ashare | `symbols` (query, required)<br>`benchmark` (query)<br>`source` (query)<br>`startDate` (query)<br>`endDate` (query) | `200` - |
| `GET` | `/api/data/coverage/benchmark/{symbol}` | Data Coverage Benchmark | `symbol` (path, required)<br>`source` (query)<br>`startDate` (query)<br>`endDate` (query) | `200` - |
| `GET` | `/api/data/coverage/symbol/{symbol}` | Data Coverage Symbol | `symbol` (path, required)<br>`source` (query)<br>`startDate` (query)<br>`endDate` (query) | `200` - |
| `GET` | `/api/data/dataset-preview/{dataset}` | Preview Dataset | `dataset` (path, required)<br>`keyword` (query)<br>`startDate` (query)<br>`endDate` (query)<br>`limit` (query)<br>`offset` (query) | `200` - |
| `POST` | `/api/data/derived/maintenance` | Start Derived Layer Maintenance | body `DerivedMaintenanceRequest` | `200` - |
| `GET` | `/api/data/derived/watermarks` | Derived Layer Watermarks | - | `200` - |
| `POST` | `/api/data/fetch` | Fetch Data | body `DataFetchRequest` | `200` - |
| `POST` | `/api/data/fetch-alpha-vantage` | Fetch Alpha Vantage | body `AlphaVantageRequest` | `200` - |
| `POST` | `/api/data/fetch-batch` | Fetch Batch | body `BatchDataFetchRequest` | `200` - |
| `GET` | `/api/data/files` | Data Files | `assetClass` (query)<br>`venue` (query) | `200` - |
| `POST` | `/api/data/free/ashare/daily/import-sample` | Import Free Ashare Daily Sample | body `AshareDailySampleImportRequest` | `200` - |
| `GET` | `/api/data/identifiers/coverage` | Data Identifier Coverage | `symbols` (query) | `200` - |
| `GET` | `/api/data/identifiers/{symbol}` | Data Identifiers | `symbol` (path, required) | `200` - |
| `POST` | `/api/data/import-csv` | Import Csv | body `Body_import_csv_api_data_import_csv_post` | `200` - |
| `GET` | `/api/data/import-csv/template` | Import Csv Template | - | `200` - |
| `POST` | `/api/data/intraday/import` | Import Intraday Data | body `IntradayImportRequest` | `200` - |
| `POST` | `/api/data/on-demand/downloads` | Create On Demand Download | body `OnDemandDatasetDownloadRequest` | `200` - |
| `GET` | `/api/data/on-demand/storage-targets` | On Demand Storage Targets | - | `200` - |
| `POST` | `/api/data/parquet/consistency` | Parquet Consistency | body `ParquetConsistencyRequest` | `200` - |
| `GET` | `/api/data/parquet/datasets` | Parquet Datasets | - | `200` - |
| `POST` | `/api/data/parquet/export` | Export Parquet Data | body `ParquetExportRequest` | `200` - |
| `POST` | `/api/data/parquet/rebuild` | Rebuild Parquet Data | body `ParquetRebuildRequest` | `200` - |
| `GET` | `/api/data/providers` | Providers | `includeAvailability` (query) | `200` - |
| `GET` | `/api/data/providers/availability` | Data Provider Availability | `provider` (query) | `200` - |
| `POST` | `/api/data/quality/ashare/daily/compare` | Compare Ashare Daily Data | body `AshareDailyCompareRequest` | `200` - |
| `POST` | `/api/data/quality/ashare/daily/compare-batch` | Compare Ashare Daily Data Batch | body `AshareDailyCompareBatchRequest` | `200` - |
| `GET` | `/api/data/quality/cross-asset` | Cross Asset Quality Status | - | `200` - |
| `GET` | `/api/data/quality/reports` | Data Quality Reports | `limit` (query) | `200` - |
| `GET` | `/api/data/query` | Query Data | `symbol` (query, required)<br>`assetClass` (query)<br>`venue` (query)<br>`market` (query)<br>`resolution` (query)<br>`dataType` (query)<br>`source` (query)<br>`providerSource` (query)<br>`providerMode` (query)<br>`allowResearchSource` (query)<br>`adjust` (query)<br>`startDate` (query)<br>`endDate` (query)<br>`limit` (query) | `200` - |
| `GET` | `/api/data/sync-runs` | Data Sync Runs | `limit` (query) | `200` - |
| `POST` | `/api/data/sync-runs` | Create Data Sync Run | body `DataSyncRequest` | `200` - |
| `GET` | `/api/data/sync-runs/{run_id}` | Data Sync Run | `run_id` (path, required) | `200` - |
| `POST` | `/api/data/sync-runs/{run_id}/cancel` | Cancel Data Sync Run | `run_id` (path, required) | `200` - |
| `POST` | `/api/data/sync-runs/{run_id}/resume` | Resume Data Sync Run | `run_id` (path, required) | `200` - |
| `GET` | `/api/data/sync-runs/{run_id}/validation` | Data Sync Validation | `run_id` (path, required)<br>`limit` (query) | `200` - |
| `GET` | `/api/markets` | Available Markets | - | `200` - |
| `GET` | `/api/securities/search` | Search Securities | `market` (query)<br>`keyword` (query)<br>`limit` (query) | `200` - |
| `GET` | `/api/securities/{symbol}/profile` | Get Security Profile | `symbol` (path, required)<br>`market` (query) | `200` - |
| `GET` | `/api/symbols` | Symbols | `market` (query)<br>`assetClass` (query)<br>`venue` (query)<br>`resolution` (query)<br>`dataType` (query) | `200` - |

## examples

| Method | Path | Summary | Input | Success |
| --- | --- | --- | --- | --- |
| `GET` | `/api/examples` | Catalog | `kind` (query)<br>`q` (query) | `200` - |
| `GET` | `/api/examples/{kind}/{key}` | Detail | `kind` (path, required)<br>`key` (path, required) | `200` - |
| `POST` | `/api/examples/{kind}/{key}/instantiate` | Instantiate | `kind` (path, required)<br>`key` (path, required)<br>body `ExampleInstantiateRequest` | `200` - |

## experiment-batches

| Method | Path | Summary | Input | Success |
| --- | --- | --- | --- | --- |
| `GET` | `/api/experiment-batches` | Batches | `limit` (query)<br>`offset` (query)<br>`paged` (query) | `200` - |
| `POST` | `/api/experiment-batches` | Create | body `ExperimentBatchRequest` | `200` - |
| `POST` | `/api/experiment-batches/compare` | Compare | body `ExperimentBatchCompareRequest` | `200` - |
| `POST` | `/api/experiment-batches/preview` | Preview | body `ExperimentBatchRequest` | `200` - |
| `DELETE` | `/api/experiment-batches/{batch_id}` | Delete | `batch_id` (path, required) | `200` - |
| `GET` | `/api/experiment-batches/{batch_id}` | Detail | `batch_id` (path, required) | `200` - |
| `POST` | `/api/experiment-batches/{batch_id}/cancel` | Cancel | `batch_id` (path, required) | `200` - |
| `GET` | `/api/experiment-batches/{batch_id}/export.csv` | Export | `batch_id` (path, required) | `200` - |
| `POST` | `/api/experiment-batches/{batch_id}/restart` | Restart Cancelled | `batch_id` (path, required) | `200` - |
| `POST` | `/api/experiment-batches/{batch_id}/retry-failed` | Retry Failed | `batch_id` (path, required) | `200` - |

## factors

| Method | Path | Summary | Input | Success |
| --- | --- | --- | --- | --- |
| `GET` | `/api/factors/engines` | Engines | - | `200` - |
| `POST` | `/api/factors/evaluate` | Evaluate | body `FactorEvaluateRequest` | `200` - |
| `POST` | `/api/factors/evaluate-batch` | Evaluate Batch | body `FactorBatchEvaluateRequest` | `200` - |
| `GET` | `/api/factors/evaluations` | Evaluations | `limit` (query) | `200` - |
| `POST` | `/api/factors/matrix` | Matrix | body `FactorMatrixRequest` | `200` - |
| `POST` | `/api/factors/portfolio` | Construct Portfolio | body `FactorPortfolioRequest` | `200` - |
| `GET` | `/api/factors/templates` | Templates | - | `200` - |
| `POST` | `/api/factors/transform` | Transform | body `FactorTransformRequest` | `200` - |
| `POST` | `/api/factors/values` | Import Values | body `FactorValueImport` | `200` - |

## futures

| Method | Path | Summary | Input | Success |
| --- | --- | --- | --- | --- |
| `GET` | `/api/futures/agri-main` | Agri Main | `date` (query, required)<br>`products` (query) | `200` - |
| `POST` | `/api/futures/continuous-contracts` | Build Continuous Contract | body `FuturesContinuousRequest` | `200` - |
| `GET` | `/api/futures/continuous-contracts/{build_id}` | Continuous Contract | `build_id` (path, required) | `200` - |
| `POST` | `/api/futures/contracts` | Import Contracts | body `FuturesContractImport` | `200` - |
| `POST` | `/api/futures/daily` | Import Daily | body `FuturesDailyImport` | `200` - |
| `POST` | `/api/futures/fee-schedules` | Set Fee Schedule | body `FuturesFeeScheduleRequest` | `200` - |
| `GET` | `/api/futures/fee-schedules/{exchange}/{product}` | Fee Schedule | `exchange` (path, required)<br>`product` (path, required) | `200` - |
| `POST` | `/api/futures/main-mapping` | Refresh Main Mapping | body `FuturesMainMappingRequest` | `200` - |
| `POST` | `/api/futures/main-rules` | Set Main Rule | body `FuturesMainRuleRequest` | `200` - |
| `GET` | `/api/futures/main/{product}` | Main Contract | `product` (path, required)<br>`date` (query, required)<br>`exchange` (query) | `200` - |
| `POST` | `/api/futures/tqsdk/import` | Import Tqsdk | body `TqSdkImportRequest` | `200` - |

## health

| Method | Path | Summary | Input | Success |
| --- | --- | --- | --- | --- |
| `GET` | `/api/health` | Health | - | `200` - |
| `GET` | `/api/health/database` | Database | - | `200` - |
| `GET` | `/api/health/dependencies` | Dependencies | - | `200` - |

## help

| Method | Path | Summary | Input | Success |
| --- | --- | --- | --- | --- |
| `GET` | `/api/help/articles` | Articles | `q` (query) | `200` - |
| `GET` | `/api/help/articles/{slug}` | Article | `slug` (path, required) | `200` - |

## insights

| Method | Path | Summary | Input | Success |
| --- | --- | --- | --- | --- |
| `GET` | `/api/ashare-tech-insights/capabilities` | Read Capabilities | - | `200` - |
| `GET` | `/api/ashare-tech-insights/reports` | List Reports | `limit` (query)<br>`offset` (query) | `200` - |
| `POST` | `/api/ashare-tech-insights/reports` | Create Report | body `AshareTechReportRequest` | `202` - |
| `DELETE` | `/api/ashare-tech-insights/reports/{report_id}` | Delete Report | `report_id` (path, required)<br>`force` (query) | `200` - |
| `GET` | `/api/ashare-tech-insights/reports/{report_id}` | Report Detail | `report_id` (path, required) | `200` - |
| `GET` | `/api/ashare-tech-insights/watchlist` | Read Watchlist | - | `200` - |
| `POST` | `/api/ashare-tech-insights/watchlist/items` | Add Watchlist Item | body `WatchlistItemCreate` | `201` - |
| `DELETE` | `/api/ashare-tech-insights/watchlist/items/{code}` | Delete Watchlist Item | `code` (path, required) | `200` - |
| `PATCH` | `/api/ashare-tech-insights/watchlist/items/{code}` | Update Watchlist Item | `code` (path, required)<br>body `WatchlistItemUpdate` | `200` - |
| `POST` | `/api/ashare-tech-insights/watchlist/reset` | Reset Watchlist | - | `200` - |
| `GET` | `/api/insights` | List Insights | `assetClass` (query)<br>`symbol` (query)<br>`status` (query)<br>`limit` (query)<br>`offset` (query) | `200` - |
| `POST` | `/api/insights` | Create Insight | body `InsightRequest` | `202` - |
| `GET` | `/api/insights/ashare-tech` | List Reports | `limit` (query)<br>`offset` (query) | `200` - |
| `POST` | `/api/insights/ashare-tech` | Create Report | body `AshareTechReportRequest` | `202` - |
| `GET` | `/api/insights/ashare-tech/capabilities` | Read Capabilities | - | `200` - |
| `GET` | `/api/insights/ashare-tech/{report_id}` | Report Detail | `report_id` (path, required) | `200` - |
| `GET` | `/api/insights/capabilities` | Read Capabilities | - | `200` - |
| `DELETE` | `/api/insights/{report_id}` | Delete Insight | `report_id` (path, required) | `200` - |
| `GET` | `/api/insights/{report_id}` | Insight Detail | `report_id` (path, required) | `200` - |
| `POST` | `/api/insights/{report_id}/paper-signals` | Handoff To Paper | `report_id` (path, required)<br>body `PaperHandoffRequest` | `200` - |

## level3plus

| Method | Path | Summary | Input | Success |
| --- | --- | --- | --- | --- |
| `GET` | `/api/alert-events` | Alert Events | `status` (query)<br>`limit` (query) | `200` - |
| `POST` | `/api/alert-events/{alert_id}/acknowledge` | Acknowledge Alert | `alert_id` (path, required) | `200` - |
| `POST` | `/api/alert-events/{alert_id}/resolve` | Resolve Alert | `alert_id` (path, required) | `200` - |
| `GET` | `/api/operational/resources` | Operational Resources | - | `200` - |
| `GET` | `/api/pipeline-runs` | Pipeline Runs | `limit` (query) | `200` - |
| `GET` | `/api/pipeline-runs/{run_id}` | Pipeline Run | `run_id` (path, required) | `200` - |
| `GET` | `/api/universes/{universe_code}` | Certified Universe | `universe_code` (path, required) | `200` - |
| `GET` | `/api/universes/{universe_code}/coverage` | Certified Universe Coverage | `universe_code` (path, required) | `200` - |

## maintenance

| Method | Path | Summary | Input | Success |
| --- | --- | --- | --- | --- |
| `POST` | `/api/maintenance/cleanup-queued` | Cleanup Queued | body `CleanupQueuedRequest` | `200` - |
| `POST` | `/api/maintenance/clear-history` | Clear History | body `ClearHistoryRequest` | `200` - |

## object-store

| Method | Path | Summary | Input | Success |
| --- | --- | --- | --- | --- |
| `GET` | `/api/object-store` | List Items | - | `200` - |
| `GET` | `/api/object-store/_stored-objects` | List Stored Objects | `namespace` (query)<br>`objectKey` (query)<br>`limit` (query)<br>`offset` (query) | `200` - |
| `DELETE` | `/api/object-store/{key}` | Delete Item | `key` (path, required) | `200` - |
| `GET` | `/api/object-store/{key}` | Get Item | `key` (path, required) | `200` - |
| `POST` | `/api/object-store/{key}` | Put Item | `key` (path, required)<br>body `Body_put_item_api_object_store__key__post` | `200` - |

## observability

| Method | Path | Summary | Input | Success |
| --- | --- | --- | --- | --- |
| `GET` | `/metrics` | Metrics | - | `200` - |

## optimization

| Method | Path | Summary | Input | Success |
| --- | --- | --- | --- | --- |
| `GET` | `/api/optimize` | List Optimizations | `limit` (query)<br>`offset` (query)<br>`paged` (query) | `200` - |
| `POST` | `/api/optimize` | Create Optimization | body `OptimizationRequest` | `200` - |
| `DELETE` | `/api/optimize/{optimization_id}` | Delete | `optimization_id` (path, required) | `200` - |
| `GET` | `/api/optimize/{optimization_id}` | Detail | `optimization_id` (path, required) | `200` - |

## paper

| Method | Path | Summary | Input | Success |
| --- | --- | --- | --- | --- |
| `GET` | `/api/paper` | List Sessions | `limit` (query)<br>`offset` (query)<br>`paged` (query) | `200` - |
| `POST` | `/api/paper` | Create Session | body `PaperSessionCreate` | `200` - |
| `GET` | `/api/paper/candidates` | Candidates | `projectId` (query, required) | `200` - |
| `DELETE` | `/api/paper/{session_id}` | Delete | `session_id` (path, required) | `200` - |
| `GET` | `/api/paper/{session_id}` | Detail | `session_id` (path, required) | `200` - |
| `GET` | `/api/paper/{session_id}/checkpoints` | Checkpoints | `session_id` (path, required)<br>`tradeDate` (query)<br>`phase` (query) | `200` - |
| `GET` | `/api/paper/{session_id}/constraint-decisions` | Constraint Decisions | `session_id` (path, required) | `200` - |
| `GET` | `/api/paper/{session_id}/daily-jobs` | Daily Jobs | `session_id` (path, required) | `200` - |
| `GET` | `/api/paper/{session_id}/fills` | Fills | `session_id` (path, required) | `200` - |
| `GET` | `/api/paper/{session_id}/intents` | Order Intents | `session_id` (path, required) | `200` - |
| `GET` | `/api/paper/{session_id}/intents/{intent_id}/transitions` | Order Intent Transitions | `session_id` (path, required)<br>`intent_id` (path, required) | `200` - |
| `GET` | `/api/paper/{session_id}/ledger` | Ledger | `session_id` (path, required) | `200` - |
| `GET` | `/api/paper/{session_id}/orders` | Orders | `session_id` (path, required) | `200` - |
| `GET` | `/api/paper/{session_id}/positions` | Positions | `session_id` (path, required) | `200` - |
| `GET` | `/api/paper/{session_id}/reconciliations` | Reconciliations | `session_id` (path, required) | `200` - |
| `POST` | `/api/paper/{session_id}/replay` | Replay | `session_id` (path, required)<br>body `PaperReplayRequest` | `200` - |
| `GET` | `/api/paper/{session_id}/reports` | Reports | `session_id` (path, required)<br>`light` (query)<br>`limit` (query)<br>`offset` (query)<br>`paged` (query) | `200` - |
| `GET` | `/api/paper/{session_id}/reports/{trade_date}` | Report | `session_id` (path, required)<br>`trade_date` (path, required) | `200` - |
| `POST` | `/api/paper/{session_id}/run-day` | Run Day | `session_id` (path, required)<br>body `PaperRunDayRequest` | `200` - |
| `GET` | `/api/paper/{session_id}/runs` | Walkforward Runs | `session_id` (path, required) | `200` - |
| `GET` | `/api/paper/{session_id}/signals` | Signals | `session_id` (path, required) | `200` - |
| `POST` | `/api/paper/{session_id}/signals` | Create Signal | `session_id` (path, required)<br>body `PaperSignalCreate` | `200` - |
| `GET` | `/api/paper/{session_id}/snapshots` | Snapshots | `session_id` (path, required) | `200` - |
| `POST` | `/api/paper/{session_id}/status` | Update Status | `session_id` (path, required)<br>body `PaperStatusUpdate` | `200` - |

## paper-accounts

| Method | Path | Summary | Input | Success |
| --- | --- | --- | --- | --- |
| `GET` | `/api/paper/accounts` | List Accounts | `status` (query)<br>`market` (query)<br>`strategy` (query)<br>`keyword` (query)<br>`hasActiveDeployment` (query)<br>`health` (query)<br>`sort` (query)<br>`direction` (query)<br>`limit` (query)<br>`offset` (query) | `200` - |
| `POST` | `/api/paper/accounts` | Create Account | body `AccountCreate` | `201` - |
| `GET` | `/api/paper/accounts/compare` | Compare Accounts | `accountId` (query)<br>`startDate` (query)<br>`endDate` (query) | `200` - |
| `DELETE` | `/api/paper/accounts/{account_id}` | Delete Account | `account_id` (path, required) | `200` - |
| `GET` | `/api/paper/accounts/{account_id}` | Get Account | `account_id` (path, required) | `200` - |
| `PATCH` | `/api/paper/accounts/{account_id}` | Update Account | `account_id` (path, required)<br>body `AccountUpdate` | `200` - |
| `POST` | `/api/paper/accounts/{account_id}/activate` | Activate Account | `account_id` (path, required) | `200` - |
| `POST` | `/api/paper/accounts/{account_id}/archive` | Archive Account | `account_id` (path, required) | `200` - |
| `GET` | `/api/paper/accounts/{account_id}/audit` | Account Audit | `account_id` (path, required)<br>`limit` (query)<br>`offset` (query) | `200` - |
| `POST` | `/api/paper/accounts/{account_id}/clone` | Clone Account | `account_id` (path, required)<br>body `AccountClone` / `null` | `201` - |
| `GET` | `/api/paper/accounts/{account_id}/cycles` | Account Cycles | `account_id` (path, required)<br>`startDate` (query)<br>`endDate` (query)<br>`status` (query)<br>`deploymentId` (query)<br>`limit` (query)<br>`offset` (query) | `200` - |
| `GET` | `/api/paper/accounts/{account_id}/daily-reports` | Account Daily Reports | `account_id` (path, required)<br>`startDate` (query)<br>`endDate` (query)<br>`deploymentId` (query)<br>`limit` (query)<br>`offset` (query) | `200` - |
| `GET` | `/api/paper/accounts/{account_id}/deployments` | List Deployments | `account_id` (path, required) | `200` - |
| `POST` | `/api/paper/accounts/{account_id}/deployments` | Create Deployment | `account_id` (path, required)<br>body `DeploymentCreate` | `201` - |
| `GET` | `/api/paper/accounts/{account_id}/orders` | Account Orders | `account_id` (path, required)<br>`startDate` (query)<br>`endDate` (query)<br>`symbol` (query)<br>`side` (query)<br>`status` (query)<br>`deploymentId` (query)<br>`limit` (query)<br>`offset` (query) | `200` - |
| `GET` | `/api/paper/accounts/{account_id}/overview` | Account Overview | `account_id` (path, required) | `200` - |
| `POST` | `/api/paper/accounts/{account_id}/pause` | Pause Account | `account_id` (path, required) | `200` - |
| `GET` | `/api/paper/accounts/{account_id}/performance` | Account Performance | `account_id` (path, required)<br>`startDate` (query)<br>`endDate` (query) | `200` - |
| `GET` | `/api/paper/accounts/{account_id}/positions` | Account Positions | `account_id` (path, required)<br>`symbol` (query)<br>`limit` (query)<br>`offset` (query) | `200` - |
| `POST` | `/api/paper/accounts/{account_id}/resume` | Resume Account | `account_id` (path, required) | `200` - |
| `GET` | `/api/paper/accounts/{account_id}/signals` | Account Signals | `account_id` (path, required)<br>`startDate` (query)<br>`endDate` (query)<br>`symbol` (query)<br>`status` (query)<br>`deploymentId` (query)<br>`limit` (query)<br>`offset` (query) | `200` - |
| `GET` | `/api/paper/accounts/{account_id}/trades` | Account Trades | `account_id` (path, required)<br>`startDate` (query)<br>`endDate` (query)<br>`symbol` (query)<br>`side` (query)<br>`deploymentId` (query)<br>`limit` (query)<br>`offset` (query) | `200` - |
| `GET` | `/api/paper/deployments/{deployment_id}` | Get Deployment | `deployment_id` (path, required) | `200` - |
| `PATCH` | `/api/paper/deployments/{deployment_id}` | Update Deployment | `deployment_id` (path, required)<br>body `DeploymentUpdate` | `200` - |
| `POST` | `/api/paper/deployments/{deployment_id}/activate` | Activate Deployment | `deployment_id` (path, required) | `200` - |
| `GET` | `/api/paper/deployments/{deployment_id}/next-runs` | Next Runs | `deployment_id` (path, required)<br>`count` (query) | `200` - |
| `POST` | `/api/paper/deployments/{deployment_id}/pause` | Pause Deployment | `deployment_id` (path, required) | `200` - |
| `POST` | `/api/paper/deployments/{deployment_id}/resume` | Resume Deployment | `deployment_id` (path, required) | `200` - |
| `POST` | `/api/paper/deployments/{deployment_id}/run-now` | Run Now | `deployment_id` (path, required)<br>body `RunNowRequest` / `null` | `200` - |
| `GET` | `/api/paper/execution-cycles` | Global Cycles | `accountId` (query)<br>`deploymentId` (query)<br>`status` (query)<br>`limit` (query)<br>`offset` (query) | `200` - |
| `GET` | `/api/paper/signals` | Global Signals | `accountId` (query)<br>`deploymentId` (query)<br>`symbol` (query)<br>`status` (query)<br>`limit` (query)<br>`offset` (query) | `200` - |

## pit-data

| Method | Path | Summary | Input | Success |
| --- | --- | --- | --- | --- |
| `POST` | `/api/pit/financial-factors` | Financial Factors | body `FinancialFactorRequest` | `200` - |
| `POST` | `/api/pit/financials` | Import Financials | body `FinancialStatementImport` | `200` - |
| `GET` | `/api/pit/financials/{symbol}/as-of/{as_of_date}` | Financials As Of | `symbol` (path, required)<br>`as_of_date` (path, required)<br>`statementType` (query) | `200` - |
| `POST` | `/api/pit/index-members` | Import Index Members | body `IndexMemberImport` | `200` - |
| `GET` | `/api/pit/index-members/{universe_code}/as-of/{as_of_date}` | Index Members As Of | `universe_code` (path, required)<br>`as_of_date` (path, required) | `200` - |
| `GET` | `/api/pit/index-members/{universe_code}/as-of/{as_of_date}/tushare` | Index Members Tushare As Of | `universe_code` (path, required)<br>`as_of_date` (path, required)<br>`lookbackDays` (query) | `200` - |
| `GET` | `/api/pit/universes/coverage` | Offered Universe Coverage | - | `200` - |

## portfolios

| Method | Path | Summary | Input | Success |
| --- | --- | --- | --- | --- |
| `POST` | `/api/portfolios/optimize` | Optimize | body `PortfolioOptimizationRequest` | `200` - |

## projects

| Method | Path | Summary | Input | Success |
| --- | --- | --- | --- | --- |
| `GET` | `/api/projects` | List Projects | `limit` (query)<br>`offset` (query)<br>`paged` (query) | `200` - |
| `POST` | `/api/projects` | Create Project | body `ProjectCreate` | `200` - |
| `DELETE` | `/api/projects/{project_id}` | Delete Project | `project_id` (path, required) | `200` - |
| `GET` | `/api/projects/{project_id}` | Get Project | `project_id` (path, required) | `200` - |
| `PUT` | `/api/projects/{project_id}` | Update Project | `project_id` (path, required)<br>body `ProjectUpdate` | `200` - |
| `DELETE` | `/api/projects/{project_id}/` | Delete Project | `project_id` (path, required) | `200` - |
| `POST` | `/api/projects/{project_id}/clone` | Clone Project | `project_id` (path, required)<br>body `ProjectClone` | `200` - |
| `GET` | `/api/projects/{project_id}/file` | Read File | `project_id` (path, required)<br>`path` (query, required) | `200` - |
| `PUT` | `/api/projects/{project_id}/file` | Write File | `project_id` (path, required)<br>body `FileWrite` | `200` - |
| `GET` | `/api/projects/{project_id}/files` | File Tree | `project_id` (path, required) | `200` - |

## reports

| Method | Path | Summary | Input | Success |
| --- | --- | --- | --- | --- |
| `GET` | `/api/reports` | List Reports | `limit` (query)<br>`offset` (query)<br>`paged` (query)<br>`source` (query)<br>`status` (query)<br>`runId` (query)<br>`detail` (query) | `200` - |
| `POST` | `/api/reports` | Create Report | body `ReportRequest` | `200` - |
| `DELETE` | `/api/reports/{report_id}` | Delete | `report_id` (path, required) | `200` - |
| `GET` | `/api/reports/{report_id}` | Detail | `report_id` (path, required) | `200` - |
| `GET` | `/api/reports/{report_id}/export` | Export Report | `report_id` (path, required)<br>`format` (query) | `200` - |
| `GET` | `/api/reports/{report_id}/file` | Report File | `report_id` (path, required) | `200` - |
| `GET` | `/api/reports/{report_id}/objects` | Report Objects | `report_id` (path, required)<br>`limit` (query)<br>`offset` (query) | `200` - |
| `GET` | `/api/reports/{report_id}/objects/{object_id}` | Report Object | `report_id` (path, required)<br>`object_id` (path, required) | `200` - |

## research

| Method | Path | Summary | Input | Success |
| --- | --- | --- | --- | --- |
| `GET` | `/api/research` | List Sessions | `limit` (query)<br>`offset` (query)<br>`paged` (query) | `200` - |
| `POST` | `/api/research` | Start Session | body `ResearchRequest` | `200` - |
| `DELETE` | `/api/research/{session_id}` | Delete Session | `session_id` (path, required)<br>`purgeWorkspace` (query) | `200` - |
| `GET` | `/api/research/{session_id}` | Detail | `session_id` (path, required) | `200` - |
| `POST` | `/api/research/{session_id}/checks` | Run Checks | `session_id` (path, required)<br>body `ResearchCheckRequest` | `200` - |
| `GET` | `/api/research/{session_id}/logs` | Logs | `session_id` (path, required) | `200` - |
| `POST` | `/api/research/{session_id}/restart` | Restart Session | `session_id` (path, required) | `200` - |
| `POST` | `/api/research/{session_id}/stop` | Stop Session | `session_id` (path, required) | `200` - |

## settings

| Method | Path | Summary | Input | Success |
| --- | --- | --- | --- | --- |
| `GET` | `/api/settings` | Read Settings | - | `200` - |
| `PUT` | `/api/settings` | Save Settings | body `SettingsUpdate` | `200` - |

## strategies

| Method | Path | Summary | Input | Success |
| --- | --- | --- | --- | --- |
| `GET` | `/api/strategies` | List Strategies | - | `200` - |
| `POST` | `/api/strategies` | Create Strategy | body `StrategyCreate` | `200` - |
| `GET` | `/api/strategies/admission/config` | Get Admission Config | - | `200` - |
| `GET` | `/api/strategies/templates` | Templates | - | `200` - |
| `DELETE` | `/api/strategies/{strategy_id}` | Delete Strategy | `strategy_id` (path, required) | `200` - |
| `GET` | `/api/strategies/{strategy_id}` | Get Strategy | `strategy_id` (path, required) | `200` - |
| `PUT` | `/api/strategies/{strategy_id}` | Update Strategy | `strategy_id` (path, required)<br>body `StrategyUpdate` | `200` - |
| `DELETE` | `/api/strategies/{strategy_id}/` | Delete Strategy | `strategy_id` (path, required) | `200` - |
| `GET` | `/api/strategies/{strategy_id}/admission` | Admission Detail | `strategy_id` (path, required)<br>`parametersSha256` (query, required)<br>`profile` (query) | `200` - |
| `POST` | `/api/strategies/{strategy_id}/admissions` | Create Admission | `strategy_id` (path, required)<br>body `AdmissionRequest` | `200` - |
| `POST` | `/api/strategies/{strategy_id}/baselines` | Create Baseline | `strategy_id` (path, required)<br>body `BaselineRequest` | `200` - |
| `POST` | `/api/strategies/{strategy_id}/paper-validations` | Create Paper Validation | `strategy_id` (path, required)<br>body `PaperValidationRequest` | `200` - |

## tasks

| Method | Path | Summary | Input | Success |
| --- | --- | --- | --- | --- |
| `GET` | `/api/tasks` | Tasks | `limit` (query)<br>`offset` (query)<br>`paged` (query) | `200` - |
| `DELETE` | `/api/tasks/{task_id}` | Delete | `task_id` (path, required) | `200` - |
| `GET` | `/api/tasks/{task_id}` | Task Detail | `task_id` (path, required) | `200` - |
| `DELETE` | `/api/tasks/{task_id}/` | Delete | `task_id` (path, required) | `200` - |
| `POST` | `/api/tasks/{task_id}/cancel` | Cancel | `task_id` (path, required) | `200` - |
| `GET` | `/api/tasks/{task_id}/logs` | Logs | `task_id` (path, required)<br>`offset` (query)<br>`cursor` (query)<br>`limit` (query) | `200` - |

## universes

| Method | Path | Summary | Input | Success |
| --- | --- | --- | --- | --- |
| `GET` | `/api/universes/djia` | Djia | - | `200` - |

## workflows

| Method | Path | Summary | Input | Success |
| --- | --- | --- | --- | --- |
| `GET` | `/api/verifications` | Verifications | `limit` (query) | `200` - |
| `GET` | `/api/verifications/{run_id}` | Verification | `run_id` (path, required) | `200` - |
| `GET` | `/api/workflows` | Workflows | `limit` (query)<br>`status` (query) | `200` - |
| `GET` | `/api/workflows/{workflow_id}` | Workflow | `workflow_id` (path, required) | `200` - |
