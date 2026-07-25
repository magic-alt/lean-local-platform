# Level 5 Paper 与 Operational Safety Runbook

状态：`TARGET_NOT_YET_CERTIFIED`

适用范围：本地 production-like Paper，不包括真实券商、真实订单或真实资金。P1
稳定性、Paper 与告警验收可以独立通过，但在生产规模备份恢复、凭据和 restricted
runner 等全部 release gate 通过前，不得宣布 `LEVEL5_OPERATIONAL_PASS`。

## 值班入口与发布前检查

1. 检查 `GET /api/health`，确认 API 和 Redis 正常。
2. 检查 `GET /api/operational/resources`；disk、memory、CPU、queue 四项不得为
   critical，指标缺失也必须调查。
3. 检查 `GET /api/alert-events?status=open`，Critical 必须有负责人和处置记录。
4. 检查上一交易日 Paper completion marker、六个 checkpoint、日报和
   reconciliation 均已完成；前一日失败时禁止推进。
5. 检查数据 watermark、QA、benchmark、PIT/reference 和 source certification。
   任一 Critical 必须 fail closed。
6. 确认 LEAN 最大活动并发不超过 2、无陈旧 running task，且备份年龄小于 24
   小时。运行时预算以 `config/operational-slo.yaml` 为准。

所有 API 请求使用本机 API Token；不要把 Token、Webhook bearer 或数据库密码
写入命令历史和证据文件。

## 通知、升级与恢复通知

通知由 default worker 每 60 秒采样资源并写入 MySQL。配置位于 `.env`：

```dotenv
LEAN_ALERT_WEBHOOK_URL=https://primary.example/alerts
LEAN_ALERT_WEBHOOK_BEARER_TOKEN=...
LEAN_ALERT_ESCALATION_WEBHOOK_URL=https://oncall.example/escalate
LEAN_ALERT_ESCALATION_WEBHOOK_BEARER_TOKEN=...
LEAN_ALERT_MIN_SEVERITY=critical
LEAN_ALERT_ESCALATE_AFTER=3
LEAN_ALERT_ESCALATION_AFTER=1
LEAN_ALERT_COOLDOWN_SECONDS=900
LEAN_ALERT_WEBHOOK_TIMEOUT_SECONDS=5
```

- warning/error 同一 dedupe key 出现 3 次后升级为 critical。
- critical 第 1 次即送独立 escalation webhook；主通道被禁用不会禁用升级通道。
- cooldown 只抑制重复投递，不改变 MySQL 中的 count、last seen 或 open 状态。
- 指标恢复正常或人工 resolve 时，强制发送一条恢复通知，不受 cooldown 阻挡。
- 每个通道分别持久化 attempt count、响应码、最后错误和安全脱敏后的 endpoint。

查看和处理告警：

```bash
curl -fsS -H "Authorization: Bearer $LEAN_API_TOKEN" \
  "http://127.0.0.1:8000/api/alert-events?status=open"

curl -fsS -X POST -H "Authorization: Bearer $LEAN_API_TOKEN" \
  "http://127.0.0.1:8000/api/alert-events/ALERT_ID/acknowledge"

curl -fsS -X POST -H "Authorization: Bearer $LEAN_API_TOKEN" \
  "http://127.0.0.1:8000/api/alert-events/ALERT_ID/resolve"
```

acknowledge 表示已接单，不表示故障消失；只有指标恢复、账本对账和依赖健康均通过后
才能 resolve。

## 资源压力阈值与处置

默认阈值如下；warning/critical 必须满足 warning ≤ critical：

| 指标 | Warning | Critical | 首要动作 |
| --- | ---: | ---: | --- |
| 磁盘使用率 | 75% | 85% | 停止新任务，归档后执行 retention |
| 内存使用率 | 80% | 90% | 降低 LEAN 并发，检查 OOM/容器重启 |
| 1 分钟 CPU/核 | 85% | 95% | 停止扩容，确认 run 未超预算 |
| 任一 Celery 队列深度 | 20 | 50 | 冻结批量提交，检查 worker 和陈旧任务 |

环境变量为 `LEAN_RESOURCE_{DISK|MEMORY|CPU|QUEUE}_{WARNING|CRITICAL}`。
`LEAN_RESOURCE_MONITOR_PATHS` 可用冒号分隔需要采样的路径。内存优先读取 cgroup
v2/v1；无容器 limit 时回退 `/proc/meminfo`，响应中的 `source` 明确来源。

处置顺序：

1. 冻结 scheduler 和新任务，保留当前证据。
2. 将活动 LEAN 并发降至 1 或 0，不得通过删除运行目录释放空间。
3. 磁盘仅删除已经校验并归档、超过 retention 的 artifact；先保存 manifest/hash。
4. 内存检查 `docker inspect` 的 OOMKilled/restart count 和 MySQL error log。
5. 队列检查 worker 在线数、Redis 可达性和 queued/running 数据库状态。
6. 服务恢复后对 in-flight Paper 日重跑 idempotency/reconciliation，再 resolve。

磁盘耗尽、OOM、网络分区、文件损坏和数据库删除只能在独立 Compose/卷注入，
不得在正式工作站数据卷执行。

## 五任务受控并发与取消

“五任务并发”定义为五个不同的真实 LEAN job 同时被平台接受，并按资源预算最多
运行两个、其余排队；不是同时启动五个无上限 LEAN 容器。

```bash
web/backend/.venv/bin/python scripts/run_p1_stability_acceptance.py \
  --project-id PROJECT_ID \
  --confirm RUN_P1_STABILITY \
  --execution-limit 2 \
  --output web/runtime/audit/p1-stability.json
```

验收必须同时证明：

- 五个 job 最终全部 success，采样期间 `maxRunning=2` 且 `maxQueued>=3`；
- queued job 可取消且从未进入 running；
- running job 可取消，另一 blocker 继续成功；
- worker、Redis、MySQL 逐一重启后 API 恢复，业务行数/终态不变量不漂移。

脚本会在 `finally` 恢复原 settings 和 worker replica 数。失败时先取消脚本创建的
非终态 run，再处理依赖；不要清理不属于本次 evidence 的任务。

## 21 日真实 LEAN Paper 与六阶段中断

基线 worker 必须关闭故障暂停：

```bash
export LEAN_PAPER_ORDER_PIPELINE_V2_ENABLED=1
export LEAN_FAULT_INJECTION_ENABLED=0
export LEAN_PAPER_CHECKPOINT_PAUSE_SECONDS=0
docker compose up -d --no-deps --force-recreate api worker backtest-worker

web/backend/.venv/bin/python scripts/run_level5_audit.py \
  --project-id PROJECT_ID \
  --source-backtest-id BACKTEST_ID \
  --start-date YYYY-MM-DD --days 21 \
  --session-overrides-json '{"blacklist":["SYMBOL"]}' \
  --require-reject-reason \
  --evidence-dir web/runtime/audit/level5 \
  --api-url http://127.0.0.1:8000
```

基线通过后，仅在隔离验收窗口重建 default worker，并启用 20 秒定点
checkpoint 暂停。变量必须 export 给整个审计进程，使脚本重建 worker 后仍保留：

```bash
export LEAN_FAULT_INJECTION_ENABLED=1
export LEAN_PAPER_CHECKPOINT_PAUSE_SECONDS=20
export LEAN_PAPER_FAULT_PAUSE_TARGETS=YYYY-MM-DD:intent_capture,YYYY-MM-DD:constraint_validation,YYYY-MM-DD:matching,YYYY-MM-DD:ledger,YYYY-MM-DD:snapshot_report,YYYY-MM-DD:reconciliation
docker compose up -d --no-deps --force-recreate worker

web/backend/.venv/bin/python scripts/run_level5_audit.py \
  --project-id PROJECT_ID \
  --source-backtest-id BACKTEST_ID \
  --start-date YYYY-MM-DD --days 21 \
  --session-overrides-json '{"blacklist":["SYMBOL"]}' \
  --require-reject-reason \
  --with-fault --fault-mode combined \
  --reuse-no-fault-evidence web/runtime/audit/level5/level5-replay-no-fault.json \
  --evidence-dir web/runtime/audit/level5 \
  --api-url http://127.0.0.1:8000
```

`LEAN_PAPER_FAULT_PAUSE_TARGETS` 中的六个日期必须与 `--fault-scenarios` 日期
一致；定点暂停避免让所有 21×6 个 checkpoint 都等待。combined 模式在不同
交易日交替重启 worker、Redis 和 MySQL，并覆盖
`intent_capture`、`constraint_validation`、`matching`、`ledger`、
`snapshot_report`、`reconciliation` 六个持久 checkpoint。每次注入必须记录
checkpoint digest、注入时 run 状态、故障动作、服务恢复结果和最终 run 终态。
轻量 checkpoint 探针将 checkpoint 与当前 run 状态在 MySQL 中联查；每次注入
必须记录 `runStatusAtInjection=running`，否则即使服务重启和最终结果成功也判
验收失败。
worker 注入使用 `SIGKILL + up` 证明真正的 worker loss 和 late-ack 重投，不允许
用 Celery warm shutdown 伪装中断；此动作只允许在该隔离验收命令中执行。验收器
立即派发 durable-finalization recovery，并记录 replacement task ID。日常运行由
beat 每 60 秒扫描 checkpoint 停滞超过
`LEAN_PAPER_FINALIZE_STALE_SECONDS`（默认 120 秒）的 run。旧 Redis 消息在
visibility timeout 后再投时，已成功的 finalization 直接 no-op。

通过条件包括 21 个真实 LEAN child success、21 日报、每日期六 checkpoint、
21 个 durable daily job 全部 `COMPLETED`、
重复 `run-day` 不新增业务行、同一 session 同时存在 fill 和有 reason 的 policy
reject、所有 reconciliation passed，以及 fault/no-fault canonical state SHA-256
完全相等。补充的 synthetic constraint probe 不能替代同一真实 session 的拒单。

2026-07-25 本地 production-like 验收记录：

- 五任务/取消/服务故障：
  `web/runtime/audit/p1-stability-2026-07-25.json`
- 无故障基线 session：`66b44a4e-993d-43dd-928e-63ba25d645bb`
- 六阶段故障 session：`33d4dac4-f470-4b40-8461-52432864fcc7`
- 汇总：`web/runtime/audit/level5-p1-2026-07-25/level5-audit.json`
- 基线：`web/runtime/audit/level5-p1-2026-07-25/level5-replay-no-fault.json`
- 故障链：
  `web/runtime/audit/level5-p1-2026-07-25/level5-replay-combined-six-phase.json`
- 两链 canonical SHA-256：
  `ff9d91a9cc99bdc1fed0631aa38d25971494278edc3ea91330c458a5d21d2427`

验收结束立即关闭：

```dotenv
LEAN_FAULT_INJECTION_ENABLED=0
LEAN_PAPER_CHECKPOINT_PAUSE_SECONDS=0
```

并执行 `docker compose up -d --no-deps --force-recreate worker`。故障暂停绝不能
留在日常 scheduler 环境。

## 服务恢复顺序

1. 冻结 scheduler/新任务，记录 alert、session、paper run 和 task ID。
2. 恢复 MySQL，验证 migration checksum、关键表计数和业务不变量。
3. 恢复 Redis，确认不存在两个 worker 同时领取同一业务 idempotency key。
4. 恢复 default worker、backtest worker 和 API，运行只读 health/resource 检查。
5. 对 in-flight 日检查六个 checkpoint digest；只允许从最后完整 phase 重入。
6. 重跑同一 `run-day`，确认订单、成交、费用、账本、snapshot、日报数量不增加。
7. reconciliation 完全一致后才允许推进下一交易日并发送 resolved。

## 备份恢复与发布边界

RPO 目标 15 分钟、RTO 目标 4 小时；生产规模 restore drill 仍是独立 P1
任务。恢复必须使用独立主机/卷，禁止覆盖 `lean_market`。dump、stored object、
LEAN result、report、log、snapshot 和审计证据均需加密、带 SHA-256，并验证
migration、表 count/checksum、业务不变量、API 启动和 Paper 引用。

任一 Critical、生产规模 restore、凭据验证、restricted runner 或 supply-chain
required gate 未通过，都必须阻断 release。不得用运行成功次数、signal
simulation 或人工改写 evidence 提升成熟度结论。
