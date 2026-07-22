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
| `LEAN_DOCKER_IMAGE` | 默认 LEAN 镜像 |
| `LEAN_ALLOWED_DOCKER_IMAGES` | 额外允许的、以 digest 固定的 LEAN 镜像 |
| `LEAN_RESEARCH_IMAGE` | 默认 Research 镜像，必须以 digest 固定 |
| `LEAN_ALLOWED_RESEARCH_IMAGES` | 额外允许的 Research 镜像 |
| `LEAN_API_AUTH_REQUIRED` | API Bearer Token 门禁；正式运行默认开启 |
| `LEAN_API_TOKEN` | API Token；启动脚本默认生成到 `web/runtime/secrets/api_token` |
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
| `LEAN_MYSQL_ON_DEMAND_MAX_DATABASE_GB` | 仅限制按需 MySQL 缓存，默认 50 GB |

一键更新不受 50 GB 上限限制，只服从磁盘安全线。Data 和 Monitoring 显示 MySQL 物理分配空间，不能与单表逻辑内容或有效载荷大小混为一谈。

## 数据同步调优

| 环境变量 | 说明 |
| --- | --- |
| `LEAN_TUSHARE_CALLS_PER_MINUTE` | TuShare 限速；5000 积分账户不超过 500/min |
| `LEAN_TUSHARE_FETCH_CONCURRENCY` | 通用有界并发预取 |
| `LEAN_STK_LIMIT_FETCH_CONCURRENCY` | `stk_limit` 初始历史预取并发 |
| `LEAN_SUSPEND_FETCH_CONCURRENCY` | `suspend_d` 初始历史预取并发 |
| `LEAN_DATA_SYNC_BATCH_UNITS` | 通用状态数据每次聚合提交工作单元，默认 32 |
| `LEAN_DATA_SYNC_CHUNK_ROWS` | SQL/归档分块行数 |
| `LEAN_DAILY_SYNC_BATCH_UNITS` | `daily` 每次聚合股票数，默认 64 |
| `LEAN_DAILY_SYNC_CHUNK_ROWS` | `daily` 单批行数上限，默认 500,000 |
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

数据库备份、Docker Desktop 内存、端口和安全配置见 [Deployment](../deployment.md)。

## 安全

- 当前个人平台 API 默认无认证，不要暴露到不可信网络。
- Docker socket 等同主机高权限访问。
- 不提交 `.env`、Token、数据库密码、下载市场数据和运行产物。
- 生产化前应增加网络边界、认证、secrets、备份演练和镜像 digest 固定。
