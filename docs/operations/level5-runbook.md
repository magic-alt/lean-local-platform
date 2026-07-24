# Level 5 Paper 与 Operational Safety Runbook

状态：`TARGET_NOT_YET_CERTIFIED`
适用范围：本地 production-like Paper，不包括真实券商或真实资金。

本 runbook 定义目标和处置动作，不是成熟度 PASS 证据。机器可读目标位于
`config/operational-slo.yaml`。生产规模恢复、完整故障矩阵、凭据轮换和 restricted
runner 未独立验收前，结论必须保持 `LEVEL5_OPERATIONAL_NOT_READY`。

## 值班前检查

1. 确认上一交易日 Paper completion marker 为 completed 且 reconciliation passed。
2. 确认 MySQL/Redis/API/backtest worker/beat 健康，队列无过期 running task。
3. 确认数据 watermark、QA、benchmark、PIT/reference 和 source certification
   覆盖当日；任一 Critical 必须 fail closed。
4. 确认磁盘低于 75%、没有 OOM、backup age 小于 24 小时、最近 restore drill
   小于 90 天。
5. 确认 API token、Webhook secret 和服务凭据未过期；不得使用仓库已知默认值。

## Paper 日任务

- 正常交易日目标 20:30 前完成，scheduler P95 延迟不超过 120 秒。
- 非交易日只能记录 `SKIPPED_NON_TRADING_DAY`。
- 数据未准备好进入 `WAITING_FOR_DATA`；超过窗口进入 `BLOCKED` 并发 Critical。
- 前一交易日未完成或对账失败时禁止推进下一日。
- 重复 trigger 必须返回同一 completion marker，不能增加订单、成交、费用、持仓、
  snapshot 或日报。
- 手工补跑必须指定 session/date/idempotency key 并留下 operator/correlation ID。

## 告警处置

| 事件 | 初始等级 | 自动动作 | 人工动作 |
| --- | --- | --- | --- |
| data/QA/benchmark/reference missing | CRITICAL | 阻断 Paper | 修复数据并重新认证，不得绕过 |
| reconciliation failed | CRITICAL | 冻结 session | 比较 intent/order/fill/cash/position ledger |
| duplicate scheduler trigger | WARNING | 返回既有 marker | 检查 lease 和幂等键 |
| worker/Redis/MySQL unavailable | CRITICAL | 有界重试并停止推进 | 按服务恢复顺序处理 |
| disk warning/critical | WARNING/CRITICAL | 停止新任务 | 执行 retention；不得删除未归档证据 |
| OOM/capacity | CRITICAL | 终止受影响 run | 降低并发并验证账本不变量 |
| backup/restore validation failed | CRITICAL | 禁止 release | 修复备份链并重新演练 |
| credential nearing expiry | WARNING | 建立轮换工单 | 原子轮换并验证旧凭据失效 |

Critical 持续存在时 cooldown 只能去重投递，不能吞掉状态；恢复后必须产生
`RESOLVED` 并关联原 alert/session/run/task。

## 服务恢复顺序

1. 冻结 scheduler/新任务。
2. 恢复 MySQL 并验证 migration checksum、关键表计数和业务不变量。
3. 恢复 Redis，确认没有两个 worker 同时领取同一业务 idempotency key。
4. 恢复 worker/API，再运行只读 dependency health。
5. 对 in-flight Paper 日执行 reconciliation；只有完全一致才允许 finalize。
6. 产生 resolved alert，解除 scheduler 冻结。

不得在活动任务存在时对正式 Compose 注入故障。磁盘、OOM、网络分区、文件损坏和
数据库删除只能在独立 Compose/数据库/卷执行。

## 备份与恢复

目标 RPO 15 分钟、RTO 4 小时；当前状态未在接近生产规模的数据集上证明。

- 每日全量备份，binlog/增量间隔不超过 15 分钟，保留 30 天。
- dump、stored objects、manifest、LEAN results、reports、logs、snapshots、
  Paper daily reports、SBOM 和审计证据必须加密并带 SHA-256。
- 恢复到独立主机或卷，禁止覆盖 `lean_market`。
- 校验 migration、表级 count/checksum、关键业务不变量、API 启动和 Paper 引用。
- Parquet/ClickHouse 从 canonical 重建；重建后 certification 必须重新验证，
  不得继承旧认证。
- 每 90 天执行代表性规模恢复；记录 size、duration、RPO/RTO、数据丢失和手工步骤。

## 资源预算

默认预算以配置文件为准：LEAN 每 run 2 CPU、4 GiB、512 PID；最大并发 2；
MySQL buffer pool 1 GiB；磁盘 75% warning、85% critical；artifact 保留 90 天。
这些是发布目标，Compose 中未显式落地的服务预算视为未完成。

## Release Gate

PR、main、nightly 和 release 分层必须执行 `config/operational-slo.yaml` 中的
required 项。任一 Critical 失败必须阻断发布，不允许人工改写为通过。Release
证据必须包含命令、环境、数据库引擎、source/data version、LEAN image digest、
artifact checksum 和独立复验结果。

## 禁止事项

- 不接真实券商、不发真实订单。
- 不用 signal simulation 替代真实 LEAN Paper。
- 不用当前成分补历史 PIT。
- 不在正式卷做破坏性故障注入。
- 不删除失败、历史审计或未归档证据。
- raw Docker socket、默认凭据、未签名镜像或未通过生产规模恢复时不得宣布
  `LEVEL5_OPERATIONAL_PASS`。
