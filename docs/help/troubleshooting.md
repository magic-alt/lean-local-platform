# 任务、监控与故障排查

Tasks 展示 Celery 生命周期和日志；Monitoring 展示服务健康、队列和指标。页面进度来自数据库，不依赖浏览器刷新推进。

## 常见问题

- 长时间 queued：检查 `backtest-worker`、Redis 和有效并发槽。
- 页面进度不变：打开批次详情确认子任务状态，再检查 API 是否能读取最新数据库记录。
- LEAN 容器失败：查看 Run Detail 的 Logs 和 Raw Files。
- Research 无法启动：检查 Docker、端口、Research镜像以及宿主机路径配置。
- A股被预检阻止：检查基准、交易日历、行情覆盖和质量报告。
- 报告仍是旧布局：先确认该报告是否重新生成；旧静态 HTML 不会被代码更新自动重写。新文件响应已禁用缓存，可重新生成后再打开。
- 数据集 Preview 报错：记录数据集和控制台字段；预览错误应限制在预览区，若整个页面空白说明需要检查是否运行了最新前端构建。

## MySQL 连接中断（2006/2013）

如果 API、恢复任务和批次协调同时出现 `Lost connection to MySQL server during query`，通常是 MySQL 重启或 Docker 内存压力，不代表每个查询都各自有问题。

```bash
docker compose ps mysql
docker inspect lean-platform-mysql-1 --format '{{.State.Status}} {{.State.ExitCode}} {{.State.OOMKilled}}'
docker compose logs --tail=200 mysql
```

- `OOMKilled=true` 或退出码 137：停止遗留的 LEAN/Research/旧 Compose 容器，检查 Docker 总内存，再评估并发数。
- MySQL 正在恢复：API 会在有界重试后返回可重试 503 `DATABASE_UNAVAILABLE`，Celery 周期任务会重试。
- 不要用无限重试掩盖反复 OOM；默认 MySQL buffer pool 为 1 GiB、redo 为 256 MiB。
- 数据库迁移未完成：先检查 `scripts/db_migrate.py --status --json`，尤其是同步 heartbeat 和 experiment batch 迁移。

批次协调任务会从数据库恢复未完成项目。重启服务不会把成功项目重新执行；失败项目需显式点击“重试失败项”。

`scripts/start_web_single_instance.sh` 日常重启不需要 `--build`。只有依赖、Dockerfile 或前端构建输入改变时才构建；活动数据同步期间脚本会避免替换 data worker。
