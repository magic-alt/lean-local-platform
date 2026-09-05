# 配置

当前架构和支持矩阵见 [Current State](../current-state.md)。Settings 保存网页白名单默认值；`.env`、Compose/native 配置控制服务、存储与资源。密钥只放在本地环境或 secrets 中。

## 核心运行配置

| 变量 | 作用 |
| --- | --- |
| `LEAN_DATABASE_URL` | PostgreSQL `lean_platform` 控制平面 |
| `CELERY_BROKER_URL` | RabbitMQ AMQP broker，默认 vhost `lean` |
| `CELERY_RESULT_BACKEND` | PostgreSQL `lean_celery` 结果元数据 |
| `LEAN_MLFLOW_DATABASE_URL` | PostgreSQL `lean_mlflow` |
| `LEAN_DATA_DIR` | 数据湖根目录，默认 `<repo>/data` |
| `LEAN_MARKET_DATA_DIR` | 权威行情 Parquet 根目录，默认同 `LEAN_DATA_DIR` |
| `LEAN_PARQUET_DIR` | 派生 Parquet，默认 `$LEAN_DATA_DIR/output/parquet` |
| `LEAN_FILE_OBJECT_STORE_DIR` | 报告/归档对象，默认 `$LEAN_DATA_DIR/object-store` |

示例：

```dotenv
LEAN_DATA_DIR=./data
LEAN_MARKET_DATA_DIR=./data
LEAN_PARQUET_DIR=./data/output/parquet
LEAN_FILE_OBJECT_STORE_DIR=./data/object-store
```

Windows 外置盘可使用 `D:\MarketData\platform\data`。不要把个人绝对路径写入通用文档或提交配置。

## Web Settings

Settings 页保存浏览器工作流允许调整的非密钥默认值，例如默认市场、策略、资金、任务超时与批量上限。`maxConcurrentJobs`、`maxBatchRuns`、`jobTimeoutSeconds` 等字段属于应用级 guardrail；它们不会替代 Compose/Native 的 CPU、内存、worker concurrency 或 broker 配置。生产容量调整必须同时通过容量与稳定性验收。

## 存储边界

- Parquet 保存股票日线、分钟/Tick、复权、每日指标和交易状态等市场事实。
- PostgreSQL 保存任务、调度、registry、manifest、水位、质量、认证、DataRelease、回测、Paper、OMS/Risk 和审计。
- DuckDB 直接查询 Parquet，不是运行数据库。
- RabbitMQ 仅运输 Celery 消息，不是业务事实或备份来源。
- ClickHouse 是可选异步镜像；SQLite 仅用于隔离测试。

旧 `LEAN_MYSQL_*`、`MYSQL_BACKUP_*` 和 `REDIS_URL` 在 strict runtime v2 中拒绝，不做隐式翻译。

## 数据与 Provider

`TUSHARE_TOKEN` 等 Provider 凭据仅在启用相应来源时配置。`LEAN_TUSHARE_TYPED_SOURCE_WRITES=0` 必须保持默认：市场时序不得写入 PostgreSQL。同步并发、批次和节流以 `.env.example` 为准，调整前观察 Provider 配额、Parquet 原子发布、CPU、内存和数据盘空间。

## 执行环境

`LEAN_DEPLOYMENT_MODE` 与 `LEAN_EXECUTION_BACKEND` 是独立选择。Docker 回测镜像必须 digest pin 并在 `LEAN_ALLOWED_DOCKER_IMAGES` 中；正式 API 示例通常省略 `dockerImage`，由平台受控默认值决定。

Windows Dockerless 开发默认使用 local process manager。SCM 部署需显式 `LEAN_NATIVE_MANAGER=windows-scm`；生产模式还需要有效的主机绑定认证。

## 备份与恢复

完整恢复集包括：

```text
$LEAN_DATA_DIR                  Parquet facts、修订、质量、LEAN cache 与对象载荷
PostgreSQL lean_platform       控制平面
PostgreSQL lean_mlflow         MLflow 元数据
项目与策略源码                  可审计输入
```

`lean_celery` 可由权威任务状态对账重建，RabbitMQ 队列不作为恢复事实。使用 `platformctl backup` 创建校验后的 PostgreSQL 逻辑备份；恢复只能进入新的 `lean_restore_*` 隔离命名空间。

## 安全

- 不提交、输出、截图或分享 `.env`、Token、密码和 Broker 凭据。
- 浏览器不能直连 PostgreSQL、RabbitMQ、Broker 或数据目录。
- Research 环境不持有实盘权限。
- Compose 服务端口默认只绑定回环地址。
