# 配置与运行资源

Settings 保存网页默认值，`.env` 保存容器和数据服务配置。不要将 TuShare Token、数据库密码或其他密钥提交到 Git。

## 关键设置

| 设置 | 说明 |
| --- | --- |
| `dockerImage` | LEAN 回测镜像 |
| `researchImage` | Jupyter Research 镜像 |
| `maxConcurrentJobs` | 同时运行的 LEAN 容器数，范围 1–8 |
| `maxBatchRuns` | 单个批次允许展开的最大子运行数，默认 5000 |
| `jobTimeoutSeconds` | 单个 LEAN 任务超时 |
| `defaultCash` | 新表单的默认初始资金 |

## MySQL 与数据资源

| 环境变量 | 默认/作用 |
| --- | --- |
| `LEAN_MYSQL_BUFFER_POOL_SIZE` | Compose 默认 `1G`，需纳入 Docker 总内存预算 |
| `LEAN_MYSQL_REDO_LOG_CAPACITY` | Compose 默认 `256M` |
| `LEAN_MYSQL_CONNECT_ATTEMPTS` | 短暂连接故障的有界重试次数，默认 5 |
| `LEAN_MYSQL_CONNECT_RETRY_DELAY_SECONDS` | 重试基础间隔，默认 0.5 秒 |
| `LEAN_MYSQL_ON_DEMAND_MAX_DATABASE_GB` | 仅限制按需 MySQL 缓存，默认 50 GB |
| `LEAN_DATA_SYNC_BATCH_UNITS` | 一次同步提交聚合的工作单元数 |
| `LEAN_TUSHARE_FETCH_CONCURRENCY` | TuShare 有界并发预取数 |

一键更新不使用 50 GB 上限，只服从磁盘预留安全线。Monitoring 和 Data 进度显示 MySQL 物理分配空间，不能与单表逻辑数据量混为一谈。

批量并发不会绕过 `maxConcurrentJobs`。提高并发前应观察 CPU、内存和 Docker I/O；任务队列只会维持一个小的派发窗口。

启动脚本只有在依赖、Dockerfile或前端构建内容变化时需要 `--build`；日常重启无需重复构建。
