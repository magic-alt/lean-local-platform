# 任务、监控与故障排查

先保存证据，再确定故障域。不要同时重启全部组件；RabbitMQ 消息、PostgreSQL 业务状态和 Parquet 文件需要分别判断。

## 首轮检查

```bash
python scripts/platformctl.py --mode docker --profile full status
python scripts/platformctl.py --mode docker --profile full logs
curl http://127.0.0.1:8000/api/health/dependencies
web/backend/.venv/bin/python scripts/db_migrate.py --status
```

重点记录 trace/workflow ID、任务 ID、队列、worker、最近 heartbeat/checkpoint、数据库错误码和 Parquet manifest。

## PostgreSQL

连接类 SQLSTATE `08xxx`、`53300`、`57P01`、`57P02`、`57P03` 属于基础设施故障候选。API 在有界重试后返回可重试的 `DATABASE_UNAVAILABLE`；不要把它当作业务校验失败。

```bash
docker compose ps postgres
docker compose exec postgres pg_isready -U postgres -d postgres
docker compose logs --tail=200 postgres migration api
```

检查连接数、磁盘、重启/OOM、migration 结果和角色/数据库初始化。恢复后先确认 migration checksum 和关键业务不变量，再恢复调度。

## RabbitMQ 与 queued 任务

```bash
docker compose ps rabbitmq worker data-worker data-lineage-worker data-demand-worker backtest-worker
docker compose exec rabbitmq rabbitmq-diagnostics -q ping
docker compose logs --tail=200 rabbitmq worker backtest-worker
```

检查 AMQP 认证、vhost `lean`、目标 queue、consumer 数、queue depth、publisher confirm、heartbeat 和 worker 是否监听正确队列。RabbitMQ 恢复后由 PostgreSQL 中的权威非终态任务对账，禁止手工制造第二个业务任务绕过 idempotency/lease。

## 数据同步不推进

检查 sync run 的 dataset、checkpoint、heartbeat、水位、manifest 和最近错误。活动同步期间不要替换 data worker；取消时等待干净 checkpoint。Parquet 发布必须原子完成，临时文件或不完整分区不能手工改名冒充 current。

## Paper waiting、重复或 projection 异常

- `waiting_data`：检查交易日、source certification、bar watermark、QA、PIT/reference 和 benchmark。
- `queued`：检查 backtest worker、RabbitMQ consumer 和全局 LEAN lease。
- `running/finalizing` 超时：检查六阶段 checkpoint 和 orphan recovery；重投同一幂等请求，不创建第二套订单。
- projection 异常：比较 ledger sequence/checkpoint digest 后重建 projection，禁止直接改 cash/positions。

Paper 事实位于 PostgreSQL append-only ledger；RabbitMQ 不拥有资金或持仓。P9/live activation 仍禁用。

## LEAN runner 与镜像

确认 restricted runner 健康、运行时/镜像 identity 已 pin、镜像在 allowlist、挂载只读且数据目录可见。不要用 `:latest` 排障或临时放宽网络/挂载边界。

## 恢复顺序

1. 停止新的调度/提交并保存证据。
2. 恢复 PostgreSQL，验证迁移和权威业务状态。
3. 恢复 Parquet/object store 并验证 manifest、hash 和 DuckDB 可读性。
4. 恢复 RabbitMQ 与 workers，通过对账重投非终态任务。
5. 恢复 LEAN runner，再解除调度门禁。

完整操作见 [Level 5 Runbook](../operations/level5-runbook.md) 和 [Deployment](../deployment.md)。
