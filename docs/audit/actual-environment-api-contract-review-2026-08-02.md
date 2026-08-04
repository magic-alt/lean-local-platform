# Actual-environment API contract review — 2026-08-02（第四次复审）

## 1. 结论

API 维度为 **8/8**。actual/source 均为 233 paths 和 migration 0043，OpenAPI hash、service release identity 与 worker generation 收敛。既定 PageEnvelope、巨型 alert-events payload、dependency-health异常和真实 timeout replay 均在 actual 环境关闭。剩余 Browser UI 与外部 webhook 观察不属于 API contract 缺失。

## 2. Release、schema 与 OpenAPI

| 对照项 | Source | Actual | 状态 |
| --- | --- | --- | --- |
| Git/release SHA | `2ebbd099499f916b67a4904166720087d431a9db` | 同 SHA | PASS |
| Release ID | current rollout | `2ebbd099…-acc872e0f8f3c2a7` | PASS |
| OpenAPI paths | 233 | 233 | PASS |
| OpenAPI hash | generated current | health/runtime相同 | PASS |
| Latest migration | `0043_p1_lineage_query_index` | 0043 applied | PASS |
| Workers | expected 5 | 5 pong、同 release | PASS |

release convergence verifier 总结果 `passed=true`；第三次复审缺失的 notification endpoints 已部署，不再有 actual missing paths。

## 3. 列表契约与 payload budget

既定 `/api/data/sync-runs`、`/api/data/parquet/datasets`、`/api/data/quality/reports`、`/api/workflows`、`/api/verifications` 持续返回 `{items,count,limit,offset}`。

`/api/alert-events` 本轮也标准化为 PageEnvelope：默认 `limit=20`、最大 100、支持 offset；每个 alert 返回最近最多 3 条 `deliveries` 和独立 `deliveryCount`。actual offset=20 页面为 32,569 B，第三次复审旧响应约 584,697 B；实际最大嵌入 delivery 数为 1。该项关闭 alert list contract/payload backlog。

| Endpoint/类别 | Actual | 状态 |
| --- | --- | --- |
| five primary lists | PageEnvelope、server bounded | PASS |
| backtests/tasks/QA summary | <200KB | PASS |
| alert-events | 32,569 B sampled page；delivery cap=3 | PASS |
| detail/result/artifact | explicit on-demand | PASS/PARTIAL |

## 4. Timeout、idempotency 与错误响应

对安全 refresh command 使用 1 ms 客户端 timeout，第一次客户端超时但服务端创建 resource `2da…`；使用相同 `Idempotency-Key` 和相同 payload 重放返回 200、`replayed=true` 且 resource ID相同；使用同 key 但不同 payload 返回 409。`ACT-P2-003` 由实际网络行为关闭，不再仅依赖 middleware code review。

| Code | 第四次复审证据 | 状态 |
| --- | --- | --- |
| 200 | authenticated reads、replay、health | PASS |
| 401 | missing Bearer | PASS |
| 404 | absent resource | PASS |
| 409 | idempotency payload drift | PASS |
| 422 | Pydantic validation regression tests | PASS/PARTIAL |
| 429 | 未主动压测 rate limit | NOT_VERIFIED |
| 503 | dependency contract存在；未主动中断全部依赖 | PARTIAL |

dependency health 现可处理 worker timeout detail 为字符串的情况，返回 HTTP 200/degraded，并在 `workerError` 保留原因；不会因错误类型假设自身抛出 500。

## 5. Paper 与 WF contract

Paper candidate/session seed 对显式 `researchOnly=true`、`tradable=false`、`admissionEligible=false` 或 `strategyMode=SCREENING` 返回 fail-closed。现有两个账户的 Run-now duplicate 返回同一 cycle；失败 cycle可由相同 endpoint从 `failed` 重新进入 queued，不创建第二个 `(deployment,trading_date)` row。

actual acceptance 的 PASS marker为2×22，暂停窗口内已排队周期完成并最终 refresh为2×23；有非零 fill、risk rejection、ledger digest replay 与 certified cohort。collecting cohort只可在0 certified sessions时按显式 account→deployment map重绑 replacement deployment；已有证据后不可变。部署重启时，已有 successful restricted-runner evidence 的 queued/running backtest/task不再被 init_db终止；orphan reconciler会重派后处理并返回 `resumed` evidence。

WF batch `8ee62a11-d82a-47eb-ab6a-df64bdc4cda9` 的 certificate endpoint 返回 valid certificate，三个 child run FK/snapshot/result digest完整，leakage violations=0。

## 6. Notification API

`/api/alert-deliveries/health` 与 dead-letter requeue endpoint 已在 actual release，health 正确报告 degraded。degraded 原因是外部 webhook 仍为 placeholder且存在 dead letters，不是 endpoint 或 schema漂移。出于安全未向 `quant.example.com` requeue；需要先配置获批真实地址，再用持久化外部 2xx 和 24h有界 attempts关闭 `ACT-P1-007`。

## 7. Logs、Cursor 与 Browser边界

backend cursor contract 与 terminal state字段持续存在。当前 in-app Browser runtime没有可用 session/tab，无法验证 UI 的 earlier、follow、位置保持、terminal-stop polling、console/network和四视口。该项保持 `ACT-P2-002 OPEN_BROWSER_NOT_VERIFIED`；不影响 API 8/8，但阻止整体 Level 5签发。

## 8. 回归验证

| 验证 | 结果 |
| --- | --- |
| backend full suite | 604 passed、2 skipped |
| generated API reference `--check` | PASS |
| help docs | 33 articles PASS |
| release convergence | PASS，233/233、0043/0043 |
| timeout/idempotency replay | PASS，same resource + drift409 |
| alert-events actual payload | PASS，PageEnvelope + bounded deliveries |
| frontend production build | PASS，无 circular warning |

## 9. 剩余 API 相关验收

仅剩 actual Browser/Cursor journey，以及可选的 429/主动503故障场景。真实 webhook 2xx/24h 属于 unattended operations readiness；不得用本地 mock、占位域名或仅 endpoint 200 将其标记为成功投递。
