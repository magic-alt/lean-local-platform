# LEAN Local Platform 2026-07-24 独立整改复验摘要

## 最终硬门禁

```text
LEVEL3_PASS
LEVEL4_FAIL
LEVEL5_REPLAY_FAIL
LEVEL5_OPERATIONAL_NOT_READY
LIVE_NOT_READY
```

本次工作从提交 `f4a130106408b810eeff6e8c104c606701fe6728` 建立修改前
基线，然后修复审计入口鉴权/错误判定、建立隔离 MySQL integration lane、执行
真实 LEAN Level 4 batch、修复 production-like Playwright 鉴权，并补充未认证的
SLO/RPO/RTO 配置和 Level 5 runbook。旧审计及旧失败记录未删除或改写。

Level 3 在显式 production-like Compose API `127.0.0.1:8000` 上重新通过，
Level 3 Plus 同时通过；真实 Docker LEAN integration 为 `1 passed`。

Level 4 得到了新的真实证据：3×3 参数网格、三个 rolling window、现有
walk-forward 扩展和 dynamic PIT 的 17 个子任务均通过正式 API、MySQL、Celery
和 Docker LEAN 执行。严格 validator 仍将总体判为失败：当前 walk-forward
模型只有 train/test，
没有独立 validation/OOS 参数选择与防泄漏证据，也未完成 batch failure retry、
cancel/restart、全页面 browser 场景和独立重跑矩阵。

Level 5 Replay 明确失败。当前 21 日真实 LEAN session 有 21 个成功交易日、21 份
日报、21 个 snapshot、每日 reconciliation 为成功，并有真实成交；但同一 session
拒单数为 0。代码仍在 `finalize_walkforward_run()` 中将 LEAN fills 直接写入结果，
约束拒单来自另一条 `signal_simulation` 链。它不符合统一
intent → constraint → matching → ledger 状态机要求。

Level 5 Operational 未就绪。raw Docker socket 仍由通用 backtest worker 持有；
默认数据库/监控凭据未完成原子轮换；没有生产规模加密异卷恢复、完整故障矩阵、
可信镜像签名或强制 release gate。新增 runbook 和 SLO 文件明确标记为
`TARGET_NOT_YET_CERTIFIED`，不作为 PASS 证据。

## 评分

本次按用户给出的 100 分模型保守计为 **45/100**。分数不覆盖硬门禁；任何硬门禁
失败均保持对应 FAIL/NOT_READY。

## 当前允许范围

平台可继续作为有真实 LEAN、数据认证和可复现能力的研究生产平台使用。可在隔离
环境继续 Paper 整改和验收，但当前不批准 1–3 个月无人值守 Paper、不批准扩大到
20–50 标的，也不批准连接真实券商。

## 必答验收问题

1. **07-24 Level 3 PASS 是否仍成立：是。** 显式 Compose 8000 控制复验得到
   `LEVEL3_PASS/LEVEL3_PLUS_PASS`，默认入口已对齐 8000；当前真实 Docker LEAN
   integration JUnit 为 1 passed。
2. **Level 4 是否通过真实独立执行：否。** 17 个真实子任务执行成功，但
   walk-forward 只有 train/test，严格 validator 因缺 validation/OOS 而失败。
3. **是否完成真实 21 日 LEAN Paper：完成了 21 日真实执行，但没有完成合格的
   Level 5 Replay 验收。**
4. **同一 session 是否同时有成交和约束拒单：否。** filled=1，rejected=0。
5. **六阶段中断恢复是否无账本漂移：未证明。**
6. **重复调度是否幂等：仅证明重复末日 run-day 被阻断且计数稳定；完整 scheduler
   lease/六阶段幂等未证明。**
7. **是否具备无人值守运行：有 beat/scheduler 接口和代码，但没有合格的漏跑阻断、
   补偿与多日 production-like 证据，因此否。**
8. **告警和升级是否真实投递：没有完成 INFO 到 RESOLVED 及真实外部 Webhook 全链，
   因此否。**
9. **是否完成完整故障矩阵：否。**
10. **是否完成生产规模 DR：否。**
11. **是否完成默认凭据轮换：否。**
12. **Docker socket 风险是否关闭：否；通用 backtest worker 仍持有 raw socket。**
13. **是否具备 SLO、RPO、RTO 和 runbook：目标和 runbook 已版本化，但标记
    `TARGET_NOT_YET_CERTIFIED`，没有实测认证。**
14. **是否允许连续运行 1–3 个月 Paper：不允许作为无人值守生产 Paper；只允许
    隔离、有人值守的整改验收。**
15. **是否允许扩大到 20–50 标的：不允许，缺容量、动态 PIT、约束和故障证据。**
16. **是否允许连接真实券商：不允许。**
17. **最大三个可信度风险：** real LEAN fill 绕过统一 intent/constraint 链；
    walk-forward 无 validation/OOS 防泄漏证明；官方 CSI300 早期 PIT coverage gap。
18. **最大三个运维风险：** raw Docker socket 主机级权限；默认凭据/无完整轮换；
    无生产规模 DR 和完整故障矩阵。
