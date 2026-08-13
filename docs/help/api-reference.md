# 完整 API 端点索引

> 本文由 `scripts/generate_help_api_reference.py` 根据 FastAPI OpenAPI 确定性生成。
> 业务语义、完整示例和错误处理请参阅 [API 使用指南](../api.md)。

当前共收录 **272** 个公开业务操作。交互式 Schema 以 `/docs` 和 `/openapi.json` 为准。

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
| `GET` | `/api/backtests` | Backtests | `name` (query)<br>`status` (query)<br>`projectId` (query)<br>`symbol` (query)<br>`market` (query)<br>`fromDate` (query)<br>`toDate` (query)<br>`limit` (query)<br>`offset` (query)<br>`paged` (query) | `200` - |
| `POST` | `/api/backtests` | Create Backtest | body `BacktestRequest` | `200` - |
| `POST` | `/api/backtests/preflight` | Preflight Backtest | body `BacktestRequest` | `200` - |
| `GET` | `/api/backtests/reproducibility/golden-pairs` | Reproducibility Golden Pairs | `limit` (query) | `200` - |
| `DELETE` | `/api/backtests/{run_id}` | Delete | `run_id` (path, required) | `200` - |
| `GET` | `/api/backtests/{run_id}` | Detail | `run_id` (path, required) | `200` - |
| `GET` | `/api/backtests/{run_id}/admission` | Admission | `run_id` (path, required)<br>`profile` (query) | `200` - |
| `GET` | `/api/backtests/{run_id}/artifacts/{name}` | Artifact | `run_id` (path, required)<br>`name` (path, required) | `200` - |
| `POST` | `/api/backtests/{run_id}/cancel` | Cancel | `run_id` (path, required) | `200` - |
| `GET` | `/api/backtests/{run_id}/chart-data` | Chart Data | `run_id` (path, required)<br>`symbol` (query) | `200` - |
| `GET` | `/api/backtests/{run_id}/logs` | Logs | `run_id` (path, required)<br>`offset` (query)<br>`cursor` (query)<br>`limit` (query) | `200` - |
| `GET` | `/api/backtests/{run_id}/optimization-draft` | Optimization Draft | `run_id` (path, required) | `200` - |
| `GET` | `/api/backtests/{run_id}/reproducibility-certificate` | Reproducibility Certificate | `run_id` (path, required) | `200` - |
| `GET` | `/api/backtests/{run_id}/result` | Result | `run_id` (path, required) | `200` - |
| `GET` | `/api/backtests/{run_id}/screening` | Screening | `run_id` (path, required) | `200` - |
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
| `POST` | `/api/cbond/daily` | Import Daily | body `CBondDailyImport` | `200` - |
| `POST` | `/api/cbond/terms` | Import Terms | body `CBondTermImport` | `200` - |

## data

| Method | Path | Summary | Input | Success |
| --- | --- | --- | --- | --- |
| `GET` | `/api/asset-classes` | Available Asset Classes | - | `200` - |
| `GET` | `/api/data-assets` | Data Assets | `status` (query)<br>`includeSuperseded` (query)<br>`limit` (query)<br>`offset` (query)<br>`paged` (query) | `200` - |
| `GET` | `/api/data/capabilities` | Data Capabilities | - | `200` - |
| `GET` | `/api/data/catalog` | Data Catalog | - | `200` - |
| `GET` | `/api/data/contracts` | Data Contracts | `assetClass` (query)<br>`status` (query)<br>`includeFields` (query) | `200` - |
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
| `GET` | `/api/data/parquet/datasets` | Parquet Datasets | `limit` (query)<br>`offset` (query) | `200` `PageEnvelope` |
| `GET` | `/api/data/providers` | Providers | `includeAvailability` (query) | `200` - |
| `GET` | `/api/data/providers/availability` | Data Provider Availability | `provider` (query) | `200` - |
| `POST` | `/api/data/quality/ashare/daily/compare` | Compare Ashare Daily Data | body `AshareDailyCompareRequest` | `200` - |
| `POST` | `/api/data/quality/ashare/daily/compare-batch` | Compare Ashare Daily Data Batch | body `AshareDailyCompareBatchRequest` | `200` - |
| `GET` | `/api/data/quality/cross-asset` | Cross Asset Quality Status | - | `200` - |
| `GET` | `/api/data/quality/reports` | Data Quality Reports | `limit` (query)<br>`offset` (query) | `200` `PageEnvelope` |
| `GET` | `/api/data/quality/reports/{report_id}` | Data Quality Report | `report_id` (path, required) | `200` - |
| `GET` | `/api/data/query` | Query Data | `symbol` (query, required)<br>`assetClass` (query)<br>`venue` (query)<br>`market` (query)<br>`resolution` (query)<br>`dataType` (query)<br>`source` (query)<br>`providerSource` (query)<br>`providerMode` (query)<br>`allowResearchSource` (query)<br>`adjust` (query)<br>`startDate` (query)<br>`endDate` (query)<br>`limit` (query) | `200` - |
| `POST` | `/api/data/query` | Query Data Scope | body `DataQueryRequest` | `200` - |
| `GET` | `/api/data/releases` | Dataset Releases | `status` (query)<br>`limit` (query)<br>`offset` (query) | `200` - |
| `POST` | `/api/data/resolve` | Resolve Data Scope | body `DataScope` | `200` - |
| `GET` | `/api/data/sync-runs` | Data Sync Runs | `limit` (query)<br>`offset` (query) | `200` `PageEnvelope` |
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
| `GET` | `/api/experiment-batches/{batch_id}/walk-forward-certificate` | Walk Forward Certificate | `batch_id` (path, required) | `200` - |

## factors

| Method | Path | Summary | Input | Success |
| --- | --- | --- | --- | --- |
| `POST` | `/api/factors/values` | Import Values | body `FactorValueImport` | `200` - |

## futures

| Method | Path | Summary | Input | Success |
| --- | --- | --- | --- | --- |
| `POST` | `/api/futures/contracts` | Import Contracts | body `FuturesContractImport` | `200` - |
| `POST` | `/api/futures/daily` | Import Daily | body `FuturesDailyImport` | `200` - |
| `POST` | `/api/futures/fee-schedules` | Set Fee Schedule | body `FuturesFeeScheduleRequest` | `200` - |
| `GET` | `/api/futures/fee-schedules/{exchange}/{product}` | Fee Schedule | `exchange` (path, required)<br>`product` (path, required) | `200` - |
| `POST` | `/api/futures/main-mapping` | Refresh Main Mapping | body `FuturesMainMappingRequest` | `200` - |
| `POST` | `/api/futures/main-rules` | Set Main Rule | body `FuturesMainRuleRequest` | `200` - |
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
| `GET` | `/api/insights/ashare-tech/agent-runs/{run_id}` | Agent Run Detail | `run_id` (path, required) | `200` - |
| `GET` | `/api/insights/ashare-tech/capabilities` | Read Capabilities | - | `200` - |
| `GET` | `/api/insights/ashare-tech/evaluations` | Prediction Evaluations | `horizonDays` (query)<br>`symbol` (query)<br>`provider` (query)<br>`model` (query)<br>`promptVersion` (query)<br>`limit` (query) | `200` - |
| `POST` | `/api/insights/ashare-tech/evaluations/refresh` | Refresh Prediction Evaluations | - | `202` - |
| `GET` | `/api/insights/ashare-tech/evaluations/summary` | Prediction Evaluation Summary | `horizonDays` (query)<br>`provider` (query)<br>`model` (query)<br>`promptVersion` (query) | `200` - |
| `POST` | `/api/insights/ashare-tech/model-diagnostics` | Model Diagnostics | body `ModelDiagnosticRequest` / `null` | `200` - |
| `GET` | `/api/insights/ashare-tech/production-profile` | Production Profile | - | `200` - |
| `PUT` | `/api/insights/ashare-tech/production-profile` | Update Production Profile | body `ProductionProfileRequest` | `200` - |
| `GET` | `/api/insights/ashare-tech/prompt-templates` | Prompt Templates | - | `200` - |
| `POST` | `/api/insights/ashare-tech/prompt-templates` | Create Prompt Template | body `PromptTemplateRequest` | `201` - |
| `GET` | `/api/insights/ashare-tech/prompt-templates/{template_key}/versions` | Prompt Template Versions | `template_key` (path, required) | `200` - |
| `POST` | `/api/insights/ashare-tech/prompt-templates/{template_key}/versions` | Create Prompt Template Version | `template_key` (path, required)<br>body `PromptTemplateRequest` | `201` - |
| `GET` | `/api/insights/ashare-tech/reports` | List Reports | `limit` (query)<br>`offset` (query) | `200` - |
| `POST` | `/api/insights/ashare-tech/reports` | Create Report | body `AshareTechReportRequest` | `202` - |
| `DELETE` | `/api/insights/ashare-tech/reports/{report_id}` | Delete Report | `report_id` (path, required)<br>`force` (query) | `200` - |
| `GET` | `/api/insights/ashare-tech/reports/{report_id}` | Report Detail | `report_id` (path, required) | `200` - |
| `GET` | `/api/insights/ashare-tech/reports/{report_id}/agent-runs` | Report Agent Runs | `report_id` (path, required) | `200` - |
| `GET` | `/api/insights/ashare-tech/watchlist` | Read Watchlist | - | `200` - |
| `POST` | `/api/insights/ashare-tech/watchlist/items` | Add Watchlist Item | body `WatchlistItemCreate` | `201` - |
| `DELETE` | `/api/insights/ashare-tech/watchlist/items/{code}` | Delete Watchlist Item | `code` (path, required) | `200` - |
| `PATCH` | `/api/insights/ashare-tech/watchlist/items/{code}` | Update Watchlist Item | `code` (path, required)<br>body `WatchlistItemUpdate` | `200` - |
| `POST` | `/api/insights/ashare-tech/watchlist/reset` | Reset Watchlist | - | `200` - |

## level3plus

| Method | Path | Summary | Input | Success |
| --- | --- | --- | --- | --- |
| `GET` | `/api/alert-deliveries/health` | Alert Delivery Health | - | `200` - |
| `POST` | `/api/alert-deliveries/requeue-dead-letter` | Requeue Alert Dead Letters | - | `200` - |
| `GET` | `/api/alert-events` | Alert Events | `status` (query)<br>`limit` (query)<br>`offset` (query) | `200` `PageEnvelope` |
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
| `GET` | `/api/optimizations` | List Optimizations | `limit` (query)<br>`offset` (query)<br>`paged` (query) | `200` - |
| `POST` | `/api/optimizations` | Create Optimization | body `OptimizationRequest` | `200` - |
| `POST` | `/api/optimizations/compare` | Compare | body `OptimizationCompareRequest` | `200` - |
| `POST` | `/api/optimizations/preview` | Preview | body `OptimizationRequest` | `200` - |
| `DELETE` | `/api/optimizations/{optimization_id}` | Delete | `optimization_id` (path, required) | `200` - |
| `GET` | `/api/optimizations/{optimization_id}` | Detail | `optimization_id` (path, required) | `200` - |
| `POST` | `/api/optimizations/{optimization_id}/archive` | Archive | `optimization_id` (path, required) | `200` - |
| `POST` | `/api/optimizations/{optimization_id}/cancel` | Cancel | `optimization_id` (path, required) | `200` - |
| `GET` | `/api/optimizations/{optimization_id}/export.csv` | Export | `optimization_id` (path, required) | `200` - |
| `POST` | `/api/optimizations/{optimization_id}/restart` | Restart | `optimization_id` (path, required) | `200` - |
| `POST` | `/api/optimizations/{optimization_id}/retry-failed` | Retry Failed | `optimization_id` (path, required) | `200` - |

## paper-accounts

| Method | Path | Summary | Input | Success |
| --- | --- | --- | --- | --- |
| `GET` | `/api/paper/accounts` | List Accounts | `status` (query)<br>`market` (query)<br>`strategy` (query)<br>`keyword` (query)<br>`hasActiveDeployment` (query)<br>`health` (query)<br>`sort` (query)<br>`direction` (query)<br>`limit` (query)<br>`offset` (query) | `200` - |
| `POST` | `/api/paper/accounts` | Create Account | body `AccountCreate` | `201` - |
| `GET` | `/api/paper/accounts/candidates` | Account Candidates | `projectId` (query, required) | `200` - |
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
| `GET` | `/api/paper/certification-cohorts` | Certification Cohorts | - | `200` - |
| `POST` | `/api/paper/certification-cohorts` | Create Certification Cohort | body `CertificationCohortCreate` | `201` - |
| `GET` | `/api/paper/certification-cohorts/{cohort_id}` | Certification Cohort | `cohort_id` (path, required) | `200` - |
| `POST` | `/api/paper/certification-cohorts/{cohort_id}/refresh` | Refresh Certification Cohort | `cohort_id` (path, required) | `200` - |
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

## portfolio-optimizations

| Method | Path | Summary | Input | Success |
| --- | --- | --- | --- | --- |
| `GET` | `/api/portfolio-optimizations` | Runs | `limit` (query)<br>`offset` (query)<br>`paged` (query) | `200` - |
| `POST` | `/api/portfolio-optimizations` | Create | body `PortfolioOptimizationRequest` | `200` - |
| `GET` | `/api/portfolio-optimizations/candidates` | Candidates | `limit` (query) | `200` - |
| `POST` | `/api/portfolio-optimizations/preview` | Preview | body `PortfolioOptimizationRequest` | `200` - |
| `DELETE` | `/api/portfolio-optimizations/{run_id}` | Delete | `run_id` (path, required) | `200` - |
| `GET` | `/api/portfolio-optimizations/{run_id}` | Detail | `run_id` (path, required) | `200` - |
| `POST` | `/api/portfolio-optimizations/{run_id}/archive` | Archive | `run_id` (path, required) | `200` - |

## projects

| Method | Path | Summary | Input | Success |
| --- | --- | --- | --- | --- |
| `GET` | `/api/projects` | List Projects | `limit` (query)<br>`offset` (query)<br>`paged` (query) | `200` - |
| `POST` | `/api/projects` | Create Project | body `ProjectCreate` | `200` - |
| `DELETE` | `/api/projects/{project_id}` | Delete Project | `project_id` (path, required) | `200` - |
| `GET` | `/api/projects/{project_id}` | Get Project | `project_id` (path, required) | `200` - |
| `PUT` | `/api/projects/{project_id}` | Update Project | `project_id` (path, required)<br>body `ProjectUpdate` | `200` - |
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
| `POST` | `/api/research/imports/qlib` | Import Qlib Run | body `QlibImportRequest` | `200` - |
| `GET` | `/api/research/runs` | List Runs | `limit` (query)<br>`offset` (query)<br>`paged` (query) | `200` - |
| `POST` | `/api/research/runs` | Create Run | body `ResearchRunRequest` | `200` - |
| `POST` | `/api/research/runs/preview` | Preview Run | body `ResearchRunRequest` | `200` - |
| `DELETE` | `/api/research/runs/{run_id}` | Delete Run | `run_id` (path, required) | `200` - |
| `GET` | `/api/research/runs/{run_id}` | Run Detail | `run_id` (path, required) | `200` - |
| `GET` | `/api/research/runs/{run_id}/artifacts/{artifact_key}` | Research Artifact | `run_id` (path, required)<br>`artifact_key` (path, required) | `200` - |
| `GET` | `/api/research/runs/{run_id}/backtest-draft` | Backtest Draft | `run_id` (path, required) | `200` - |
| `POST` | `/api/research/runs/{run_id}/cancel` | Cancel Run | `run_id` (path, required) | `200` - |
| `GET` | `/api/research/runs/{run_id}/export.csv` | Export Run | `run_id` (path, required) | `200` - |
| `POST` | `/api/research/runs/{run_id}/retry` | Retry Run | `run_id` (path, required) | `200` - |
| `GET` | `/api/research/templates` | Templates | - | `200` - |
| `GET` | `/api/research/workspaces` | List Workspaces | `limit` (query)<br>`offset` (query)<br>`paged` (query) | `200` - |
| `POST` | `/api/research/workspaces` | Create Workspace | body `WorkspaceRequest` | `200` - |
| `POST` | `/api/research/workspaces/snapshots` | Create Workspace Snapshot | body `SnapshotRequest` | `200` - |
| `DELETE` | `/api/research/workspaces/{workspace_id}` | Delete Workspace | `workspace_id` (path, required)<br>`purgeWorkspace` (query) | `200` - |
| `GET` | `/api/research/workspaces/{workspace_id}` | Workspace Detail | `workspace_id` (path, required) | `200` - |
| `GET` | `/api/research/workspaces/{workspace_id}/logs` | Workspace Logs | `workspace_id` (path, required) | `200` - |
| `POST` | `/api/research/workspaces/{workspace_id}/restart` | Restart Workspace | `workspace_id` (path, required) | `200` - |
| `POST` | `/api/research/workspaces/{workspace_id}/stop` | Stop Workspace | `workspace_id` (path, required) | `200` - |

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
| `POST` | `/api/tasks/{task_id}/cancel` | Cancel | `task_id` (path, required) | `200` - |
| `GET` | `/api/tasks/{task_id}/logs` | Logs | `task_id` (path, required)<br>`offset` (query)<br>`cursor` (query)<br>`limit` (query) | `200` - |

## universes

| Method | Path | Summary | Input | Success |
| --- | --- | --- | --- | --- |
| `GET` | `/api/universes/djia` | Djia | - | `200` - |

## workflows

| Method | Path | Summary | Input | Success |
| --- | --- | --- | --- | --- |
| `GET` | `/api/lineage/{resource_type}/{resource_id}` | Lineage | `resource_type` (path, required)<br>`resource_id` (path, required) | `200` - |
| `GET` | `/api/verifications` | Verifications | `limit` (query)<br>`offset` (query) | `200` `PageEnvelope` |
| `GET` | `/api/verifications/{run_id}` | Verification | `run_id` (path, required) | `200` - |
| `GET` | `/api/workflows` | Workflows | `limit` (query)<br>`offset` (query)<br>`status` (query) | `200` `PageEnvelope` |
| `GET` | `/api/workflows/{workflow_id}` | Workflow | `workflow_id` (path, required) | `200` - |
