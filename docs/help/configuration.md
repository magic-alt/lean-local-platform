# 配置

Settings 保存网页默认值，`.env` 和 Compose 环境变量控制服务、存储和资源。密钥只放在本地环境或 secrets，不提交到 Git。

## 核心存储配置

| 变量 | 作用与默认值 |
| --- | --- |
| `LEAN_DATABASE_URL` / `DATABASE_URL` | MySQL 控制平面：任务、注册、质量、认证、账户、订单和审计；不保存股票行情 |
| `LEAN_DATA_DIR` | 数据根目录，默认仓库下 `data/` |
| `LEAN_MARKET_DATA_DIR` | 股票 Parquet 数据湖根目录，默认等于 `LEAN_DATA_DIR` |
| `LEAN_PARQUET_DIR` | 平台生成的分析/ML Parquet，默认 `$LEAN_DATA_DIR/output/parquet` |
| `LEAN_HOST_DATA_DIR` | Docker 容器挂载所对应的宿主机数据根目录 |
| `LEAN_HOST_PARQUET_DIR` | Docker 容器挂载所对应的派生 Parquet 目录 |
| `LEAN_FILE_OBJECT_STORE_DIR` | 报告/归档对象目录，默认 `$LEAN_DATA_DIR/object-store` |

推荐本地配置：

```dotenv
LEAN_DATA_DIR=/Users/kaermax/lean-platform/data
LEAN_MARKET_DATA_DIR=/Users/kaermax/lean-platform/data
LEAN_PARQUET_DIR=/Users/kaermax/lean-platform/data/output/parquet
LEAN_HOST_DATA_DIR=/Users/kaermax/lean-platform/data
LEAN_HOST_PARQUET_DIR=/Users/kaermax/lean-platform/data/output/parquet
```

不要把 `LEAN_MARKET_DATA_DIR` 指向 Qlib 仓库。平台只通过数据目录读取现有 Qlib 派生文件，不修改 Qlib 源码或仓库。

## 目录契约

```text
$LEAN_MARKET_DATA_DIR/
├── bronze/tushare/current
├── bronze/tushare/revisions
├── silver/daily/current
├── silver/reference/current
├── gold
├── qlib
├── lean
├── registry
└── quality

$LEAN_PARQUET_DIR/
└── ml、feature-set、training-run 等平台派生产物
```

运行态不使用仓库根目录的 `Data/`、`parquet/`、`runs/` 或 `results/`。小写 `data/` 是本项目已经采用的明确数据湖根目录。

## TuShare 和下载

| 变量 | 作用 |
| --- | --- |
| `TUSHARE_TOKEN` | TuShare Pro Token |
| `LEAN_TUSHARE_SYNC_*` | 同步并发、分片、重试和节流参数 |
| `LEAN_TUSHARE_TYPED_SOURCE_WRITES` | 参考类 typed source 兼容写入，默认 `0` |
| `LEAN_DATA_MIN_FREE_BYTES` | 数据下载前的绝对可用空间安全线 |
| `LEAN_DATA_MIN_FREE_RATIO` | 数据下载前的比例安全线 |

股票日线下载直接发布到 Bronze/Silver Parquet；不存在“按需写入 MySQL 行情表”的容量上限。旧的 `LEAN_MYSQL_ON_DEMAND_MAX_DATABASE_GB` 不再控制股票行情保存，不应作为数据湖容量指标。

`LEAN_TUSHARE_TYPED_SOURCE_WRITES=1` 仅用于尚未迁移的参考数据契约。不要用它重建 `market_daily_bars`、`market_intraday_bars`、`market_trade_status`、`adjustment_factors` 或 `daily_basic_values`。

## Parquet 与 DuckDB

| 变量 | 作用 |
| --- | --- |
| `LEAN_PARQUET_COMPRESSION` | Parquet 压缩，推荐/默认 `zstd` |
| `LEAN_PARQUET_MAX_THREADS` | Polars/DuckDB 最大并行度 |
| `LEAN_PARQUET_PARTITION_ROWS` | 非原生日分区派生产物的目标 part 行数 |

DuckDB 是 Parquet 查询引擎，不是运行数据库，也不生成新的股票主副本。API 的行情来源使用 `parquet` 或 `duckdb`；`mysql` / `database` 已禁用。

## MySQL

MySQL 仍是平台控制平面的强依赖，配置、连接池、备份和恢复规则继续适用。它保存：

- 用户、权限、任务、调度和 worker 状态；
- dataset registry、manifest 摘要、水位、质量和认证；
- 项目、策略、实验、回测、Paper、OMS/Risk 和审计；
- 小型参考元数据及兼容对象目录。

它不保存 OHLCV、分钟线、复权因子、每日指标或交易状态时序。监控中的 MySQL 大小代表控制平面占用，不能用来估算 `data/` 股票数据量。

## LEAN、Qlib 与 ClickHouse

- LEAN 数据缓存从 Silver/Gold 生成，默认位于 `$LEAN_DATA_DIR/lean` 或配置的 LEAN data mount。
- `data/qlib` 和 `gold/qlib_staging` 是只读消费输入；lean-platform 不写它们。
- ClickHouse 默认可关闭。启用时它只是可重建查询镜像，Parquet 仍是事实层。

## Worker 与任务

FastAPI 不执行长训练、长回测或大规模下载。使用独立 worker 队列：

```text
api -> Redis/Celery -> data-worker / data-lineage-worker / data-demand-worker / backtest-worker / ml-worker
```

调整并发前先观察 Provider 等待、Parquet 写入、CPU、内存、Docker I/O 和 `data/` 磁盘增长。数据分区写入是原子操作，但同一分区仍应由队列/锁避免并发发布。

Settings 中的 `maxBatchRuns` 控制单个批次允许展开的最大子任务数；它是任务容量保护，不改变数据下载分区或 Parquet 读取并行度。

## Web Settings

页面设置只接受白名单字段，未知键会被忽略。页面不会保存 TuShare Token、数据库密码或 Broker 凭据。Docker image、资源上限和研究容器设置属于运行环境配置，修改后可能需要重启对应服务。

## 备份

至少分别备份：

```text
$LEAN_DATA_DIR            股票事实层、修订、质量、LEAN/Qlib 派生数据
MySQL                     控制平面逻辑备份
Docker volumes            Redis/ClickHouse/Grafana 等需要保留的服务状态
项目与策略目录            可审计源码和快照
```

只备份 MySQL 无法恢复股票行情；只备份 `data/` 也无法恢复账户、任务和审计状态。恢复演练必须同时验证两者以及文件 SHA-256。

## 安全

- 不提交 `.env`、Token、数据库密码、Broker 凭据和下载数据。
- 浏览器不能直接访问 Broker、MySQL 或数据目录。
- 研究环境不持有实盘权限。
- Compose 端口默认只绑定回环地址；生产环境使用 secrets 和最小权限账号。

