# 任务、监控与故障排查

Tasks 展示 Celery 生命周期和日志；Monitoring 展示依赖健康、指标和最近工作流失败。页面进度来自数据库，浏览器只是读取状态，不负责推动任务。

## 首轮检查

```bash
docker compose ps
docker compose logs --tail=200 mysql redis api worker data-worker backtest-worker beat
curl http://127.0.0.1:8000/api/health/dependencies
web/backend/.venv/bin/python scripts/db_migrate.py status
```

先确定问题属于浏览器、API、数据库、队列、worker、Docker 还是 Provider，不要同时重启所有组件而丢失证据。

## 任务长时间 queued

检查：

1. 对应 queue 的 worker 是否运行并监听正确队列。
2. Redis 是否可访问。
3. `maxConcurrentJobs` 和 scheduler lease 是否已用满。
4. 前序长任务是否仍占用 LEAN 容器。
5. Tasks 中是否已有 dispatch 或 dependency 错误。

队列等待时不要重复点击提交，否则可能创建多个独立任务。

## 数据同步进度不动

- 先请求 `GET /api/data/sync-runs/{run_id}`，确认数据库状态是否变化。
- 检查当前 dataset、checkpoint、heartbeat 和最近错误。
- 工作单元可能正在提交一个大批次；行数变化但股票计数暂时不变不一定是卡死。
- 大量空结果的数据集应继续推进工作单元；如果 heartbeat 也停止，再检查 worker。
- 活动同步期间不要替换 data worker。需要停止时使用取消接口，等待干净 checkpoint。

页面重复轮询不应触发 `/api/data/on-demand/storage-targets` 高频请求；该接口只应在按需下载对话框需要时加载。

## MySQL 2006/2013

如果 API、恢复任务和批次协调同时出现 `Lost connection to MySQL server during query`，通常是 MySQL 重启、OOM 或 Docker I/O 压力，不代表每个查询各自有问题。

```bash
docker compose ps mysql
docker inspect lean-platform-mysql-1 \
  --format '{{.State.Status}} {{.State.ExitCode}} {{.State.OOMKilled}}'
docker compose logs --tail=200 mysql
```

- `OOMKilled=true` 或退出码 137：停止遗留 LEAN/Research/旧 Compose 容器，检查 Docker 总内存并降低并发。
- MySQL 正在恢复：API 在有界重试后返回可重试 503 `DATABASE_UNAVAILABLE`，周期协调任务稍后重试。
- 迁移缺失：检查最新 migration，特别是 sync heartbeat 和 experiment batch 表结构。
- 不要用无限重试掩盖反复 OOM。

## Unknown column

出现 `Unknown column 'heartbeat_at'` 等错误说明代码和数据库 migration 不一致：

```bash
web/backend/.venv/bin/python scripts/db_migrate.py status --json
```

先完成迁移再重启 API、worker 和 beat。不要手工随意增加列而绕过 migration 记录。

## LEAN 回测失败

在 Run Detail 检查：

- preflight 是否通过；
- Logs 中的 Python/C#、Docker 和 LEAN 错误；
- Raw Files 是否包含结果 JSON；
- Data Evidence 是否覆盖日期、标的和真实基准；
- 是否超时、取消或因 scheduler lease 延迟。

没有结果 JSON 时不能生成伪造的成功指标。

## Research 无法启动

- 检查 Docker socket、Research 镜像和可用端口。
- 查看 worker 与 container logs。
- 确认宿主机 Project、Data 和 Parquet 路径能被 Docker 挂载。
- Docker Desktop 文件共享未包含路径时，容器可能启动但看不到数据。

## Preview 或文档页白屏

- 先记录 dataset/article、URL 和浏览器控制台错误。
- 单个 Preview/文档错误必须限制在内容区，不能让整个 Web 空白。
- 确认运行的是最新前端构建；依赖或构建输入变更后需要一次 `--build`。
- Preview 的未知 Provider 字段应由 JSON-safe formatter 展示，不应直接渲染对象。

## 报告仍是旧布局

旧静态 HTML 不会因代码更新自动变化。确认报告 ID 和生成时间，必要时重建：

```bash
web/backend/.venv/bin/python scripts/regenerate_backtest_reports.py --dry-run
```

报告响应已禁用缓存；重建后仍旧时检查实际文件和对象归档版本。

## Worker heartbeat 和时钟漂移

偶发 `missed heartbeat` 可能来自 CPU/I/O 阻塞；持续出现并伴随任务失联时检查容器负载。`Substantial drift` 表示发送和接收时钟差异，先确认宿主机与 Docker VM 时间同步。

## 无法退出启动脚本

单实例脚本应把退出信号转发给子进程并清理服务。第一次 Ctrl+C 后等待清理；重复信号只用于已有清理超时。若仍无法退出，记录脚本 PID、子进程和 Docker Compose 状态，不要直接删除数据卷。

## 恢复原则

- 数据同步从数据库 checkpoint 恢复，最多幂等重放一个小批次。
- Experiment batch 根据子任务状态协调，成功项不会重复运行。
- 报告和运行对象优先从对象归档恢复。
- 同一阻塞条件反复出现时先保留日志、状态和 migration 信息，再做变更。
