# LEAN Local Platform

这个平台不依赖 Lean CLI，直接使用你已经拉取的 `quantconnect/lean:latest` 镜像运行本地 Python 回测。它包含 CLI demo 和 Web 工作台，用来导入公开 OHLCV 数据、选择标的、运行 Docker LEAN 回测并生成 HTML 报告。

策略文件：

- `DockerDemoAlgorithm.py`：SPY 日线 10/30 EMA 交叉策略
- `config.json`：LEAN Launcher 配置
- `run.sh`：一键 Docker 运行脚本
- `local_platform.py`：本地数据导入、参数化回测和报告生成工具
- `DATA_SOURCES.md`：公开数据源和数据质量说明
- `web/`：FastAPI + React Web 平台
- `results/`：回测结果输出目录，运行后自动创建

默认数据目录是平台父目录下的 `Data`。当前机器上是 `/Users/kaermax/Data`，它链接到 `/Users/kaermax/Lean/Data`。如需换数据目录，启动脚本和 Web 后端都支持设置 `LEAN_DATA_DIR=/path/to/Data`。

运行：

```bash
cd /Users/kaermax/lean-platform
chmod +x run.sh
./run.sh
```

脚本会挂载：

- `$LEAN_DATA_DIR` 或 `/Users/kaermax/Data` 到容器 `/Lean/Data`
- `DockerDemoAlgorithm.py` 到容器 `/Lean/DockerDemoAlgorithm.py`
- `config.json` 到容器 `/Lean/Launcher/bin/Debug/config.json`
- `results` 到容器 `/Lean/Results`

回测结束后查看：

```bash
ls -la results
```

常见输出文件：

- `docker-demo-backtest.json`
- `docker-demo-backtest-summary.json`
- `docker-demo-backtest-log.txt`
- `docker-demo-backtest-order-events.json`

生成本地图表 HTML：

```bash
python3 plot_results.py
open results/report.html
```

图表脚本只使用 Python 标准库，不需要安装 `matplotlib`、`pandas` 或 Lean CLI。

## 本地平台用法

查看可用数据源建议：

```bash
python3 local_platform.py sources
```

查看本地已有可回测标的：

```bash
python3 local_platform.py symbols
```

运行参数化回测：

```bash
python3 local_platform.py backtest \
  --symbol SPY \
  --start 2013-01-01 \
  --end 2013-06-30 \
  --fast 10 \
  --slow 30 \
  --open
```

结果会写入：

```text
runs/{run-id}/results/
```

从 Alpha Vantage 下载日线数据并转换成 LEAN 格式：

```bash
export ALPHAVANTAGE_API_KEY="your-key"
python3 local_platform.py fetch-alpha-vantage MSFT --outputsize compact
python3 local_platform.py backtest --symbol MSFT --start 2026-01-01 --end 2026-07-01 --open
```

本地数据源密钥可以放在仓库根目录 `.env`，该文件已加入 `.gitignore`，不会提交到 git。TuShare Pro token 使用：

```bash
cp .env.example .env
# edit .env
TUSHARE_TOKEN=your_tushare_pro_token
```

当前 TuShare Pro adapter 已接入 A 股日线下载，最小权限只要求 `pro.daily()`：

```bash
cd web/backend
.venv/bin/python -c "import app.core.config; from app.services.tushare_adapter import TushareAdapter; print(len(TushareAdapter().daily_rows('600519','2024-01-02','2024-01-05')))"
```

`adj_factor`、`stk_limit`、`trade_cal`、`stock_basic` 会在 token 权限允许时使用；无权限时不会阻断 `pro.daily()` 日线导入。

沪深300 PIT 历史成分需要公告级调样记录，不等同于“当前 300 只股票历史行情”。当前 MySQL 主库可写入基于中证指数官网缓存附件重建的真实 `CSI300` PIT 成分：

```bash
web/backend/.venv/bin/python scripts/import_csindex_csi300_cached.py --dry-run
web/backend/.venv/bin/python scripts/import_csindex_csi300_cached.py --acknowledge-partial-coverage
```

导入结果保存到 `index_source_artifacts`、`index_membership_events`、`index_membership_pit` 和 `universe_membership`，并生成 `data_sources/csi300_pit_sources.json`。当前覆盖从 `2017-12-08` 起，包含 20 个官方缓存 source artifact、686 条调入/调出事件、643 条 PIT 成分区间；`CSI300_DEMO` 示例数据不会写入生产库。注意这仍不是 2005 年指数发布以来的完整全历史，`2017-12-08` 以前仍需继续补官方公告或专业数据源。

示例 manifest 只用于验证管线：

```bash
web/backend/.venv/bin/python scripts/import_csi300_pit_public.py --manifest data_sources/csi300_pit_sources.example.json --dry-run --validate
```

运行主库已切换为 MySQL；旧文件型本地库仅是历史迁移来源，不再作为默认库、测试模板或生产迁移目标。

默认连接：

```text
LEAN_DATABASE_URL=mysql+pymysql://lean:lean@127.0.0.1:3306/lean_market
```


历史行情数据保存机制采用分层模型：

- MySQL：运行事实源，保存证券主数据、交易日历、日线行情、交易状态、PIT 成分、回测任务、结果和对象归档。
- Parquet：派生的历史行情分析仓库，适合全市场扫描、分钟线/Tick 扩展和本地研究。
- DuckDB：嵌入式查询引擎，直接查询 Parquet，不替代 MySQL。
- LEAN `Data/`：回测执行缓存，由数据库行情或归档对象生成/恢复。

Parquet 默认目录是 `$LEAN_DATA_DIR/parquet`，可用 `LEAN_PARQUET_DIR` 覆盖；压缩默认 `zstd`，可用 `LEAN_PARQUET_COMPRESSION` 覆盖。导出已经入库的 A 股日线：

```bash
web/backend/.venv/bin/python scripts/export_market_parquet.py \
  --asset-class equity \
  --market china \
  --venue china \
  --source akshare \
  --adjust raw
```

通过 API 导出和查询：

```text
POST /api/data/parquet/export
GET  /api/data/query?source=duckdb&assetClass=equity&market=china&venue=china&symbol=600519&providerSource=akshare
GET  /api/data/parquet/datasets
```

新增的 `parquet_datasets` 和 `parquet_files` 表会记录 dataset key、分区文件、行数、日期范围、sha256、大小和导出元数据；Parquet 文件是 MySQL 标准行情表的可重建派生物，不是新的事实源。

全量重建已入库行情的 Parquet 派生仓并生成一致性报告：

```bash
web/backend/.venv/bin/python scripts/rebuild_market_parquet.py \
  --asset-class equity \
  --market china \
  --venue china \
  --resolution daily \
  --data-type trade \
  --adjust raw
```

该任务会按 `market_daily_bars` 中实际存在的 scope 重建 Parquet，随后比较 MySQL 行数/日期范围、`parquet_files.sha256` 和 DuckDB 读取结果，并把报告写入 `data_quality_reports.report_type=parquet_consistency`。若出现 critical 一致性问题，脚本以非 0 退出。对应 API：

```text
POST /api/data/parquet/rebuild
POST /api/data/parquet/consistency
```

A 股多源日线校验支持比较已入库的 `akshare`、`adata`、`baostock` 等来源：

```bash
web/backend/.venv/bin/python scripts/compare_ashare_sources.py 600519 \
  --sources akshare,baostock \
  --start-date 2026-01-01 \
  --end-date 2026-07-03
```

校验结果写入 `data_quality_reports`，记录覆盖率、缺失日期、OHLC 价差、成交量差异和 severity。AData/Baostock 是可选依赖 provider；未安装时不会影响平台启动。

批量多源 QA 可用于生成验收报告：

```bash
web/backend/.venv/bin/python scripts/compare_ashare_sources_batch.py \
  --symbols 600519,000001 \
  --sources akshare,baostock \
  --start-date 2026-01-01 \
  --end-date 2026-07-03
```

批量报告写入 `data_quality_reports.report_type=ashare_daily_multisource_batch`，汇总 `criticalSymbols`、`warningSymbols`、`passed` 和每个 symbol 的报告 ID；critical 场景自动生成验收报告并以非 0 退出。对应 API：

```text
POST /api/data/quality/ashare/daily/compare-batch
```

免费公开源验证阶段可以用批量编排脚本串联导入、交叉校验和 Parquet 刷新：

```bash
web/backend/.venv/bin/python scripts/import_ashare_free_sample.py \
  --symbols 600519,000001 \
  --start-date 2022-01-01 \
  --end-date 2026-07-04 \
  --providers akshare,baostock,adata
```

对应 API：

```text
POST /api/data/free/ashare/daily/import-sample
```

Paper Replay 支持连续交易日回放；如果 `data_quality_reports` 中存在覆盖当天的 `critical` 报告，撮合会拒单并记录 `qa_failed:{report_id}`：

```bash
web/backend/.venv/bin/python scripts/run_paper_replay.py <session-id> \
  --start-date 2026-06-01 \
  --end-date 2026-06-30
```

A 股 Paper 默认使用显式成交口径 `executionPolicy=next_open`，信号日和成交日分离；也支持 `next_close`、`next_vwap`。`same_close` 属于高风险口径，必须显式设置 `allowSameDayClose=true` 才允许使用。Paper 快照会记录 `benchmarkSymbol`、benchmark close 和 benchmark return；A 股默认 benchmark 为 `000300`。Paper 与 backtest 通过共享 A 股交易配置统一默认成本、滑点、交易日历、benchmark 和组合约束参数，策略层不应直接绕过这些配置。

Paper 每日撮合会持久化 `paper_daily_reports`，日报内容包含当日信号、待执行信号、订单、成交、拒单、拒单原因、持仓、NAV、benchmark 和 QA gate 状态。Paper 组合约束支持 `maxPositions`、`maxPositionWeight`、`minCash`、`blacklist`、`watchlist`、`observeOnlySymbols`，并默认禁止买入 ST，除非显式设置 `allowStBuy=true`。

导入沪深300 benchmark 行情并生成 LEAN cache：

```bash
web/backend/.venv/bin/python scripts/import_csi300_benchmark.py \
  --start-date 2005-01-01 \
  --end-date 2026-07-04
```

A 股增量导入只写 canonical DB，LEAN `Data/` zip/factor/map 会从数据库完整窗口重建并归档到 MySQL `stored_objects`。回测 worker 启动 LEAN 前会自动校验/恢复主标的和 benchmark 的 LEAN cache；`backtest_runs.fingerprint` 保存 git 状态、参数 hash、数据行数/batch、Parquet 文件 hash、LEAN cache object/hash 和 Docker image digest。

期货前期验证使用可选 TqSdk adapter。未安装 `tqsdk` 时平台仍可启动，调用该入口会返回明确错误：

```bash
web/backend/.venv/bin/python scripts/import_tqsdk_futures.py \
  --symbols DCE.m2409,KQ.m@SHFE.rb \
  --start-date 2024-01-01 \
  --end-date 2024-03-01 \
  --duration-seconds 86400
```

期货主力映射刷新 API：

```text
POST /api/futures/main-mapping
POST /api/futures/tqsdk/import
```

分钟线小样本验证入口：

```text
POST /api/data/intraday/import
```

当前不建议下载全市场多年分钟线，也不启用 vn.py DataRecorder 实盘录制。数据库只预留了 `market_intraday_bars`、`market_ticks`、`recording_jobs`、`recording_status` 和 `data_gaps`，用于后续扩展；这些扩展表为空不影响 A 股日线回测和 Paper 主流程。

导入任意 CSV：

```bash
python3 local_platform.py import-csv MSFT ~/Downloads/MSFT.csv
```

CSV 默认需要这些列：

```text
timestamp,open,high,low,close,volume
```

如果列名不同，可以用 `--date-col`、`--open-col`、`--high-col`、`--low-col`、`--close-col`、`--volume-col` 指定。

如果 Docker 报权限或 daemon 错误，先确认 Docker Desktop 正在运行：

```bash
open -a Docker
docker info
```

## Web 平台

Web 平台现在是一个本地多资产工作台：FastAPI 提供 API，React 提供浏览器界面，Redis + Celery 负责后台回测/优化/报告任务，MySQL 作为唯一运行主库保存项目、任务、结果索引、行情、PIT 成分和二进制对象。LEAN Docker 仍是唯一回测执行引擎，平台不依赖 Lean CLI 或 QuantConnect 付费账号。

新增的中型研究平台基础设施使用 Docker Compose 管理：

- Redis：Celery broker/result backend
- MySQL：运行事实源，保存 A 股专表、通用 `instruments/market_daily_bars/market_trade_status`、回测结果、对象分块和文件归档
- ClickHouse：可选标准化 OHLCV 镜像和查询加速，不再作为事实源
- Prometheus：抓取 `/metrics`
- Grafana：内部运维看板，默认 `admin/admin`

启动基础设施：

```bash
cd /Users/kaermax/lean-platform
docker compose up -d mysql redis clickhouse prometheus grafana
```

MySQL 是必需运行库，单独启动：

```bash
docker compose up -d mysql
```

打开：

```text
Prometheus: http://127.0.0.1:9090
Grafana:    http://127.0.0.1:3000
```

如需把 API 和 worker 也放进 Compose：

```bash
docker compose --profile app up -d --build
```

本机端口被占用时可以覆盖宿主端口；容器内部仍使用服务名互联：

```bash
LEAN_REDIS_PORT=6380 LEAN_API_PORT=8002 docker compose --profile app up -d --build mysql redis api worker
```

Level 3 shadow 验收入口：

```bash
web/backend/.venv/bin/python scripts/db_migrate.py --status --json
web/backend/.venv/bin/python scripts/import_instrument_identifiers.py \
  --symbols 600519,000001,300750,000300 \
  --source akshare \
  --json
web/backend/.venv/bin/python scripts/run_daily_shadow_pipeline.py \
  --symbols 600519,000001,300750 \
  --benchmark 000300 \
  --source akshare \
  --start-date 2026-06-01 \
  --end-date 2026-06-30 \
  --min-trading-days 10 \
  --json
web/backend/.venv/bin/python scripts/run_paper_constraints_acceptance.py \
  --symbols 600519,000001,300750 \
  --benchmark 000300 \
  --source akshare \
  --start-date 2026-06-01 \
  --end-date 2026-06-30 \
  --json
web/backend/.venv/bin/python scripts/run_level3_shadow_audit.py \
  --symbols 600519,000001,300750 \
  --benchmark 000300 \
  --source akshare \
  --start-date 2026-06-01 \
  --end-date 2026-06-30 \
  --min-trading-days 10 \
  --json
```

这些命令只针对 A 股日线小范围影子 Paper Replay，不连接真实券商、不发真实订单。默认生产 source 为 `akshare`；`test`、`baostock`、`adata` 等研究源必须显式传入 `allowResearchSource=true` 才能用于研究查询，不能进入生产 backtest/Paper 默认链路。

本地开发仍可只用下面的手动 API/worker/frontend 启动方式。

安装：

```bash
cd /Users/kaermax/lean-platform/web/backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cd ../frontend
npm install
npm run build
```

启动 Redis：

```bash
redis-server --port 6379
```

启动 API：

```bash
cd /Users/kaermax/lean-platform
scripts/start_hs300_web.sh
```

该脚本默认设置 `LEAN_DATABASE_URL=mysql+pymysql://lean:lean@127.0.0.1:3306/lean_market`。需要换端口时：

```bash
LEAN_WEB_PORT=8002 scripts/start_hs300_web.sh
```

启动 Celery worker：

```bash
cd /Users/kaermax/lean-platform/web/backend
source .venv/bin/activate
celery -A app.tasks.celery_app worker --loglevel=info --pool=solo
```

打开：

```text
http://127.0.0.1:8000
```

Web 端支持：

- 项目制工作区：项目概览、代码编辑、数据准备、回测提交、结果和任务日志在一个页面完成
- 多资产项目：`equity`、`crypto`、`crypto_future`、`future` 的 asset class、venue、resolution、data type 统一配置
- 创建/编辑本地 Python/C# 策略项目
- 策略模板选择：EMA Cross、SMA Cross、MACD、RSI Mean Reversion、Crypto Momentum、Futures Trend、Buy & Hold、Blank Custom
- Data Library：扫描本地 LEAN `Data/` 目录，展示股票、加密币、期货等 zip 数据文件和可回测 symbol
- 查看本地 LEAN 标的，支持美股、A 股、港股、Coinbase/Binance 等 crypto 样例和 COMEX/CME 等 futures 样例
- CSV 导入并转换成 LEAN 格式，支持股票、crypto daily、futures daily
- 当前道指 30 只成分股数据面板，支持批量选择缺失标的并下载到本地 LEAN 数据目录
- Yahoo Finance、Stooq、Alpha Vantage、新浪财经、东方财富、AKShare、同花顺日线数据导入
- Binance spot 日线 crypto OHLCV 导入
- 选择项目、市场、股票、日期、资金和策略参数并运行 Docker 回测
- 参数网格优化
- Paper Replay 会话管理：本地模拟会话登记、启动/暂停/停止状态管理，不连接真实券商、不发真实订单
- Research 容器启动
- Object Store 文件管理
- 后台任务和日志查看
- Settings 页配置默认市场、默认数据源、默认策略、Docker 镜像、资金和日期区间
- 项目删除，级联清理关联任务、回测、报告和 runtime 文件
- 查看状态、日志、指标、图表、订单和原始结果文件
- 回测曲线显示权益、基准、标的价格、EMA、回撤，并在权益/价格曲线上标记订单时间点
- 回测记录和图表按资产类型读取本地价格序列，crypto/future 样例可以和股票共用报告页

如果 `8000` 已被占用，可以先找出旧进程：

```bash
lsof -nP -iTCP:8000 -sTCP:LISTEN
```

也可以换端口启动 API，开发模式下通过 `VITE_API_PROXY_TARGET=http://127.0.0.1:8001 npm run dev` 指向新端口。

数据库连接可以在 Web 页面中检查：

- Monitoring 页会显示 MySQL engine、host、database、关键表计数和 `CSI300` membership 行数。
- A-Share Research 页的 `CSI300 PIT` 标签可以按日期查询 PIT 成分；当前覆盖从 `2017-12-08` 起，早于该日期应返回 0。

数据源注意：

- Yahoo Finance 和 Stooq 是免费公开端点，适合本地实验，但可能因网络、限流、验证码或服务条款变化而失败。
- Alpha Vantage 需要 API key，免费额度有限，但在公开 API 里通常更稳定，适合先搭建可靠的自动化下载流程。
- 东方财富直接用于 A 股和港股日线；新浪和 AKShare Provider 需要安装 `akshare`；同花顺第一版只支持 A 股日线入口。
- Crypto 第一版可通过 Binance spot 公共接口下载日线，也可以直接使用 `/Users/kaermax/Data/crypto` 中已有的 LEAN 样例。
- Futures 第一版优先使用本地 LEAN 格式数据或 CSV 导入；严肃期货研究需要校验合约乘数、mapping/factor 文件、保证金和连续合约规则。
- A 股和港股第一版只支持日线回测；平台会自动补 LEAN 本地 market-hours 和 symbol-properties 配置，不修改 LEAN 引擎源码。
- Web 平台会把下载后的日线数据写入 MySQL 通用行情表，同时生成 LEAN zip 作为回测缓存；回测时仍由 Docker 版 LEAN 读取本地 `Data/`。

运行主库：

```text
mysql+pymysql://lean:lean@127.0.0.1:3306/lean_market
```

Parquet/DuckDB 研究层是 MySQL 行情表的可重建派生物，不作为运行元数据库。

原始 LEAN JSON、日志和报告仍按 run 保存在文件系统缓存，同时归档到 MySQL `stored_objects/stored_object_chunks`：

```text
web/runtime/runs/
```
