# 配置与运行资源

Settings 保存网页默认值，`.env` 和 Compose 环境变量控制服务、存储和资源。密钥只放在本地环境或 secrets，不提交到 Git。

## Web Settings

页面按 Market defaults、Backtest defaults、Task capacity 和 Runtime environment 分组。Docker 与 Research Image 位于默认折叠的 Runtime environment；保存仍提交完整的已编辑设置，折叠不会清空值。

| 设置 | 说明 |
| --- | --- |
| `defaultAssetClass` | 新建项目/表单的默认资产类别 |
| `defaultMarket`、`defaultVenue` | 默认市场和交易 Venue |
| `defaultResolution`、`defaultDataType` | 默认分辨率和数据类型 |
| `defaultProvider`、`defaultAdjust` | 默认 Provider 和复权方式 |
| `defaultStrategyTemplate` | 新项目默认策略模板 |
| `defaultCash`、`defaultStart`、`defaultEnd` | 新任务表单默认资金和日期 |
| `dockerImage` | LEAN 回测镜像 |
| `researchImage` | Jupyter Research 镜像 |
| `chartPointLimit` | 图表返回点数上限 |
| `maxConcurrentJobs` | 同时运行的 LEAN 容器数，范围 1–8 |
| `maxBatchRuns` | 单批次允许展开的最大工作单元，默认 5000 |
| `jobTimeoutSeconds` | 单个 LEAN 任务超时 |
| `logLevel` | 服务日志级别 |

Settings 更新只接受白名单字段，未知键会被忽略。它不会保存 TuShare 或 LLM API Key。

## 服务与存储变量

| 环境变量 | 作用 |
| --- | --- |
| `LEAN_DATABASE_URL` / `DATABASE_URL` | MySQL 运行事实库连接 |
| `REDIS_URL` | Celery broker/backend |
| `LEAN_DATA_DIR` | LEAN 行情缓存根目录 |
| `LEAN_HOST_DATA_DIR` | Docker 可挂载的宿主机数据路径 |
| `LEAN_PARQUET_DIR` | Parquet 派生数据目录 |
| `LEAN_PARQUET_MAX_THREADS` | Parquet/Polars 最大并行线程，默认 `4` |
| `LEAN_PARQUET_PARTITION_ROWS` | 每个年度 Parquet part 的目标行数，默认 `100000` |
| `LEAN_DATA_DEMAND_WORKER_CPUS` | data-demand worker 的 Docker CPU 上限，默认 `4.0` |
| `LEAN_DOCKER_IMAGE` | 默认 LEAN 镜像 |
| `LEAN_ALLOWED_DOCKER_IMAGES` | 额外允许的、以 digest 固定的 LEAN 镜像 |
| `LEAN_RESEARCH_IMAGE` | 默认 Research 镜像，必须以 digest 固定 |
| `LEAN_ALLOWED_RESEARCH_IMAGES` | 额外允许的 Research 镜像 |
| `LEAN_API_AUTH_REQUIRED` | API Bearer Token 门禁；正式运行默认开启 |
| `LEAN_MAINTENANCE_READ_ONLY` | 设为 `1` 时拒绝所有 `/api/` 写请求（健康检查除外）；用于直接市场数据重建窗口 |
| `LEAN_API_TOKEN` | API Token；启动脚本默认生成到 `web/runtime/secrets/api_token` |
| `LEAN_API_TOKEN_FILE` | API Token 文件；用于 Docker/主机重启后恢复认证，默认 `web/runtime/secrets/api_token` |
| `BACKTEST_MAX_CONCURRENT_JOBS` | 数据库调度租约上限 |
| `BACKTEST_JOB_TIMEOUT_SECONDS` | LEAN 任务超时 |
| `TUSHARE_TOKEN` | TuShare Pro Token |

Provider、LLM 和外部服务凭据必须同时提供给需要它们的 API/worker 容器。

## MySQL 配置

| 环境变量 | 默认/作用 |
| --- | --- |
| `LEAN_MYSQL_BUFFER_POOL_SIZE` | Compose 工作站默认 `1G` |
| `LEAN_MYSQL_REDO_LOG_CAPACITY` | 默认 `256M` |
| `LEAN_MYSQL_CONNECT_ATTEMPTS` | 短暂连接故障的有界重试，默认 5 |
| `LEAN_MYSQL_CONNECT_RETRY_DELAY_SECONDS` | 重试基础间隔，默认 0.5 秒 |
| `LEAN_MYSQL_ON_DEMAND_MAX_DATABASE_GB` | 单次按需 MySQL 写入估算上限，默认 50 GiB；不与含全量同步数据的实例总大小比较 |
| `LEAN_OBJECT_STORE_MODE` | `filesystem`（Compose 默认）或 `database`；控制二进制对象有效载荷位置 |
| `LEAN_FILE_OBJECT_STORE_DIR` | 文件对象根目录；Compose 默认 `/workspace/Data/object-store`，必须纳入 Data 备份 |
| `LEAN_ASHARE_CANONICAL_WRITES` | 设为 `1` 后仅写入 `market_*`；Compose 默认启用，A 股兼容视图由受确认的维护流程创建 |

一键更新不受 50 GiB 单次按需写入上限限制；所有写入仍服从磁盘安全线。Data 和 Monitoring 显示 MySQL 物理分配空间，不能与按需缓存占用、单表逻辑内容或有效载荷大小混为一谈。

## 数据同步调优

| 环境变量 | 说明 |
| --- | --- |
| `LEAN_TUSHARE_CALLS_PER_MINUTE` | TuShare 限速；5000 积分账户不超过 500/min |
| `LEAN_TUSHARE_FETCH_CONCURRENCY` | 通用有界并发预取；同时控制股票主数据状态分片、指数历史窗口及指数/期货/期权市场目录分片 |
| `LEAN_TUSHARE_TYPED_SOURCE_WRITES` | 默认 `1`；将已注册的低频 TuShare 响应同时写入契约生成的版本化来源表。仅排障时临时关闭，不影响高频 columnar 路由 |
| `LEAN_DAILY_BASIC_FETCH_CONCURRENCY` | `daily_basic` 历史预取并发，默认 32；仍受全局 500/min 限速器约束 |
| `LEAN_DIVIDEND_FETCH_CONCURRENCY` | `dividend` 首次历史预取并发，默认 32；增量改为按除权日拉取全市场 |
| `LEAN_STK_LIMIT_FETCH_CONCURRENCY` | `stk_limit` 初始历史预取并发 |
| `LEAN_SUSPEND_FETCH_CONCURRENCY` | `suspend_d` 初始历史预取并发 |
| `LEAN_DATA_SYNC_BATCH_UNITS` | 通用状态数据每次聚合提交工作单元，默认 32 |
| `LEAN_DATA_SYNC_CHUNK_ROWS` | SQL/归档分块行数 |
| `LEAN_DAILY_SYNC_BATCH_UNITS` | `daily` 每次聚合股票数，默认 64 |
| `LEAN_DAILY_SYNC_CHUNK_ROWS` | `daily` 单批行数上限，默认 500,000 |
| `LEAN_DAILY_INCREMENT_BATCH_DATES` | `daily` 全市场增量每次聚合提交的交易日数，默认 16 |
| `LEAN_RAW_ARCHIVE_GZIP_LEVEL` | raw archive 压缩等级，默认 1；提高会节省少量空间但增加同步 CPU 时间 |

不要仅提高并发。先观察 Provider 等待、MySQL 写入、CPU、内存、Docker I/O 和磁盘增长。

## 队列与 worker

完整栈包含 default、data、data-demand、backtest worker 和 beat：

- default：协调任务和一般后台作业；
- data：一键同步；
- data-demand：按需数据；
- backtest：LEAN 回测和相关执行；
- beat：恢复、协调和定时任务。

多个 worker 仍受数据库 scheduler lease 和 `maxConcurrentJobs` 约束。

## 目录边界

```text
web/runtime/projects/      可编辑项目副本
web/runtime/runs/          回测执行和调试缓存
web/runtime/reports/       生成报告
web/runtime/research/      Research 工作区
$LEAN_DATA_DIR             LEAN 可读行情缓存
$LEAN_PARQUET_DIR          可重建 Parquet 数据
Docker volumes             MySQL、Redis、ClickHouse 等持久卷
```

根目录不能重新引入 `runs/`、`results/`、`Data/` 或 `parquet/` 运行产物。详细规则见 [Repository Layout](../repository_layout.md)。

## 启动、构建和备份

- 普通重启：`./scripts/start_web_single_instance.sh`
- 依赖、Dockerfile 或前端构建输入改变后：增加 `--build`
- 迁移状态：`web/backend/.venv/bin/python scripts/db_migrate.py --status`
- 仓库卫生：`python3 scripts/check_repository_hygiene.py`

## 告警与自动 Paper

- `LEAN_PAPER_WALKFORWARD_HOUR` / `LEAN_PAPER_WALKFORWARD_MINUTE`：Paper 自动逐日调度时间。
- `LEAN_PAPER_ORDER_PIPELINE_V2_ENABLED`：允许创建统一 intent/constraint/matching/ledger 的 LEAN Paper session；默认 `1`。显式设为 `0` 会在依赖健康接口中标记 `legacy_degraded`。
- `LEAN_SCHEDULED_AUTOMATION_ENABLED`：是否启用计划任务；默认 `1`。启用时必须配置外部告警通道，否则平台依赖健康状态为 Critical/degraded。
- `LEAN_MYSQL_BACKUP_HOUR` / `LEAN_MYSQL_BACKUP_MINUTE`：每日 MySQL 逻辑备份时间，默认 `03:00`（Asia/Shanghai）。
- `LEAN_ALERT_WEBHOOK_URL`：运维告警 Webhook；自动调度启用时为必需配置。未配置时告警仍会持久化，但平台不会报告 operational ready。
- `LEAN_ALERT_WEBHOOK_BEARER_TOKEN`：Webhook Bearer 凭据，只能保存在本地环境或秘密管理器。
- `LEAN_ALERT_MIN_SEVERITY`：外发最低等级，默认 `error`；Paper `cycle_failed` 固定为 `critical`。
- `LEAN_ALERT_ESCALATE_AFTER`：相同 Paper 调度警告累计到该次数后升级为 Critical，默认 `3`。
- `LEAN_ALERT_COOLDOWN_SECONDS`：成功外发后的去重冷却时间，默认 `900` 秒。

投递状态、尝试次数和错误可通过 `/api/alert-events` 查看。只有外部通道返回
2xx 才算 delivered；通道恢复后，Beat 会补投尚无成功 delivery 的 open alert。
Webhook URL 的查询参数不会写入投递审计记录。

数据库备份、Docker Desktop 内存、端口和安全配置见 [Deployment](../deployment.md)。

## 安全

- API 默认启用本地 Bearer Token，Compose 端口默认只绑定 `127.0.0.1`；仍不得暴露到不可信网络。
- Docker socket 等同主机高权限访问。
- 不提交 `.env`、Token、数据库密码、下载市场数据和运行产物。
- 生产化前应增加网络边界、认证、secrets、备份演练和镜像 digest 固定。
