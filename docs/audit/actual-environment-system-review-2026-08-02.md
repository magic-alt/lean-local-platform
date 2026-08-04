# Actual-environment system review — 2026-08-02（第四次复审）

- 审计标签：`audit-actual-env-20260802-iteration4`
- 取证截止：2026-08-04 CST
- 环境：当前 `lean-platform` actual Compose/MySQL/API；未创建隔离环境
- 判定：`LEVEL5_FAIL`
- 得分：**89/100**（第三次复审 66/100）
- 未关闭问题：**0 Critical、0 P0、3 P1、1 P2、0 P3**
- `NOT_VERIFIED`：**13**

## 1. Executive Summary

第四次复审完成了所有可在当前环境中直接修复和证明的剩余项。源码、MySQL schema、OpenAPI、API、5 个 Celery worker 与 Beat 已收敛到同一 release；实际迁移为 `0043_p1_lineage_query_index`，source/actual 均为 233 paths。Walk-Forward 已生成真实 Train→Validation→OOS 三段证书；现有两个差异资金 Paper 账户均超过 21 个成功交易日、完成幂等 Run-now、非零成交、风控拒绝、账本 replay 和 cohort certification。由此关闭全部 P0。

本轮还实际关闭 alert-events 巨型响应、POST timeout replay、unique-writer characterization、migration 文档漂移和 ECharts circular chunk warning。全量 backend 测试为 604 passed、2 skipped，frontend production build 通过且无 circular warning，release convergence 通过。

Level 5 仍保持 FAIL，不是因为存在代码或 P0 缺陷，而是三项时间跨度/外部依赖证据和一项真实 Browser 验收尚不具备：数据维护需连续 7 日；通知需配置真实外部 webhook 并观察 24 小时 2xx；容量需 24 小时 headroom；当前会话没有可用的 in-app Browser，四视口、console、network、keyboard 和 Cursor UI 不能诚实判 PASS。

## 2. 本轮授权操作与约束

为修复剩余问题，本轮在 actual 环境执行了 additive migration、滚动重建服务、真实 maintenance recertification、受控 timeout/idempotency replay、最小真实 WF、现有账户 Paper cycle 与 cohort certification。因此 `formalLedgerModified=true`、`formalCertificationModified=true`；未删除历史事实、未全量重导、未全量 Parquet rebuild、未备份/恢复数据库、未伪造外部 webhook 或 Browser 证据。

历史失败行均保留：部署窗口造成的 orphan cycle、旧 critical-success、旧 broken WF 和 dead-letter delivery 没有被删除或重写；新证据以 additive trust/certificate/success rows 形成。

## 3. 当前实际环境

| 项目 | 第四次复审实际事实 | 判定 |
| --- | --- | --- |
| Git HEAD | `2ebbd099499f916b67a4904166720087d431a9db` | source identity |
| Release ID | `2ebbd099499f916b67a4904166720087d431a9db-acc872e0f8f3c2a7` | PASS |
| Service convergence | 8 个受检服务同 release/SHA；5 workers pong | PASS |
| Schema | source=actual=`0043_p1_lineage_query_index` | PASS |
| OpenAPI | source=actual=233 paths；hash aligned | PASS |
| Health | HTTP 200、`degraded`；execution status 可用 | PARTIAL：仅外部通知通道阻断 unattended readiness |
| Capacity snapshot | backtest worker 约为 3 GiB limit 的 4.6%；CPU/queue 低 | PASS snapshot；24h 待观察 |
| Browser | 当前 Browser runtime 无可用 tab/session | NOT_VERIFIED |

## 4. 最终成熟度与评分

| 维度 | 满分 | 得分 | 依据 |
| --- | ---: | ---: | --- |
| 架构 | 12 | 12 | 单一 release/schema/OpenAPI；writer characterization 通过 |
| 功能完整性 | 12 | 12 | WF、Paper、release、capability、notification API 均实际存在 |
| Web 与用户流程 | 15 | 9 | build clean；真实 Browser/四视口仍缺 |
| API | 8 | 8 | 233 paths、bounded envelopes、timeout replay/409 通过 |
| 数据 | 15 | 13 | 0043 后全量 lineage recertification 成功；7 日观察与有限公司行动范围仍缺 |
| 回测 | 15 | 14 | trusted source、Golden/WF/Paper 非零 fill；完整规则样本仍可扩展 |
| Experiment/WF | 8 | 7 | 三段证书实际通过；grid/rolling 独立验收仍 NV |
| Paper | 12 | 12 | 2×23、差异资金、fill/reject、ledger replay、cohort certified |
| 调度与稳定性 | 3 | 2 | workers/Beat、恢复逻辑和低资源快照通过；24h SLO缺 |
| **总计** | **100** | **89** | **P0=0；外部/时间跨度/Browser证据未满足，保持 FAIL** |

## 5. 本轮实际关闭证据

### 5.1 发布与架构

release verifier 通过：source/actual 233 paths、schema 0043、OpenAPI hash、frontend digest、API、workers 和 Beat 同一 release。`db.init_db` 不再把已由 restricted runner 成功执行、仅待 post-processing 的 backtest/task误标失败；orphan recovery 可重新接续成功 runner 的后处理和 Paper finalization。三项架构边界测试在实际 API 容器通过，关闭 `ACT-P0-004` 与 `ACT-P2-004`。

### 5.2 数据维护

maintenance run `7f9b66f5-cdca-47f5-9c97-226ae5ed0e3e` 首次暴露 17.7M equity lineage grouping 的 MySQL OOM。新增 0043 复合索引并让 MySQL 明确使用该索引后，checkpoint attempt 3 恢复并成功：equity 17,703,084 rows/194 files/21,273 batches，DuckDB row count一致；index 44,741 rows/37 files一致。该证据关闭当前 OOM/不可恢复缺陷，但 `ACT-P1-002` 的连续 7 日定义仍保持 OPEN。

### 5.3 Walk-Forward

batch `8ee62a11-d82a-47eb-ab6a-df64bdc4cda9` 的 Train、Validation、OOS 三个真实 LEAN children 全部成功；certificate valid，leakage decision=`ALLOW`、violations=0，result digest=`c0a561…`，config digest=`baa51e…`。该证据关闭 `ACT-P0-002`。3×3 grid/rolling 是独立产品扩展验收，保留 NV，不再作为此 P0 的替代条件。

### 5.4 Paper 多账户

复用 cohort `2da80404-a54d-411c-8fba-d1866b1ad43f`、账户 `a97c9a78-c1c1-4154-aa6f-eb4a99ddb6d8`（1,000,000 CNY）和 `b172a4e9-d0bb-4753-9406-8eb9718fbbfe`（3,000,000 CNY），并使用可信可执行 EMA source backtest `600519-20230101-20231130-20260804065922`。正式 PASS marker 时两账户各 22 个 certified sessions；暂停窗口内已排队周期自然完成后，最终 cohort refresh 为各 23 个。duplicate Run-now 返回同一 cycle；A 累计 5 次 fill，B 累计 7 次 risk rejection；有 no-signal 日；账户之间 opening ledger、orders/fills 和 sequence 隔离；canonical ledger digest 可重复 replay，cash/positions 与 projection 一致。两个 deployments 最终均 paused，active cycles=0。

本轮发现并修复四类真实缺陷：screening/research-only backtest 可误入 Paper candidate；不同初始资金使首个 cumulative child 与 source 数量不同而被误判漂移；部署打断 post-processing 时成功 runner 不能接续；collecting cohort 仍冻结旧 replacement deployment。最后一项只允许 `collecting + 0 certified sessions` 的 member通过显式 account→deployment map重绑，certified/invalid或已有证据的 cohort保持不可变。修复后首个 child 建立账户专属 immutable baseline，后续 child仍严格与上一成功 child reconciliation，人工 drift测试保持 fail-closed。关闭 `ACT-P0-001`。

### 5.5 API、通知、文档与 frontend

- `/api/alert-events` 改为 `items,count,limit,offset`，默认 20 条；每个 alert 仅嵌入最近 3 条 delivery 并返回 `deliveryCount`。实际首屏由 584,697 B 降至 32,569 B。
- 对安全 refresh POST 使用 1 ms 客户端 timeout；相同 key/payload replay 返回 200、同 resource 且 replay header=true；同 key 异 payload 返回 409。关闭 `ACT-P2-003`。
- dependency health 在 worker timeout detail 为字符串时仍返回 200/degraded，而不是自身 500。
- `docs/architecture.md` 不再硬编码 migration 0035；API help 重新生成。
- frontend 5727 modules build 通过，ECharts/zrender 合并到单一 chunk，无 circular chunk warning。关闭 `ACT-P3-001/002`。

## 6. 剩余问题注册表

| Issue | 严重度 | 状态 | 剩余完成定义 |
| --- | --- | --- | --- |
| ACT-P1-002 | P1 | OPEN_OBSERVATION_PENDING | 当前修复后连续 7 日无 MySQL 2013/OOM/orphan chain，checkpoint resume持续成功 |
| ACT-P1-007 | P1 | OPEN_EXTERNAL_CHANNEL_AND_24H | 将 placeholder webhook 替换为真实外部端点，持久化 2xx，24h attempts有界且 DLQ/requeue可证 |
| ACT-P1-008 | P1 | OPEN_24H_CAPACITY_OBSERVATION | 连续 24h headroom低于阈值、无 OOM/抖动，并保留归因证据 |
| ACT-P2-002 | P2 | OPEN_BROWSER_NOT_VERIFIED | actual Browser 完成 Cursor earlier/follow/terminal-stop 与四视口 journey |

`quant.example.com` 当前为 placeholder，历史 deliveries 为 dead-letter。未向该占位地址 requeue，也未把本地 200 或 mock 当作外部通知成功。

## 7. 已关闭问题

`ACT-CRIT-001`、`ACT-P0-001`、`ACT-P0-002`、`ACT-P0-003`、`ACT-P0-004`、`ACT-P1-001`、`ACT-P1-003`、`ACT-P1-004`、`ACT-P1-005`、`ACT-P1-006`、`ACT-P2-001`、`ACT-P2-003`、`ACT-P2-004`、`ACT-P3-001`、`ACT-P3-002` 均有 actual 或 regression evidence，不再计数。

## 8. NOT_VERIFIED（13）

1–4. 1440×900、1280×800、768×1024、390×844；5. Browser console；6. Browser network duplicate/polling；7. keyboard/a11y；8. project create/save/clone journey；9. backtest queued→running UI；10. cancel race；11. grid/rolling/heatmap；12. full MySQL↔Parquet rehash；13. 主动依赖故障恢复演练。

Paper 21 sessions、ledger replay、WF leakage、timeout replay、writer characterization 已从上一轮 NV 移除。

## 9. 验证汇总

| 验证 | 结果 |
| --- | --- |
| backend full pytest | **604 passed, 2 skipped** |
| frontend `npm run build` | PASS，5727 modules，无 circular warning |
| release convergence | PASS，233/233、0043/0043、同 release/SHA、5 workers pong |
| Paper acceptance | PASS marker 2×22；final stable cohort 2×23，deployments paused、active cycles=0 |
| Walk-Forward certificate | PASS，Train/Validation/OOS success，0 leakage violations |
| data maintenance | PASS，checkpoint resumed；equity/index MySQL↔DuckDB counts match |
| timeout replay | PASS，same key same resource；payload drift 409 |
| generated API/help/hygiene/diff check | PASS |
| Browser | NOT_VERIFIED，当前无可用 Browser session |

## 10. 最终结论

剩余的可执行代码、数据、部署、WF 和 Paper 问题已经修复并在 actual 环境复验；Critical 与 P0 均为 0。当前 89/100 的 `LEVEL5_FAIL` 是证据门禁的保守结果：不能用瞬时快照替代 7 日/24 小时观察，也不能用单测或 synthetic browser 替代真实 Browser。最短关闭链为配置真实 webhook并完成通知/容量 24h 观察、完成数据维护 7 日观察，然后在可用 Browser 中执行四视口与 Cursor journey；达到 score≥90 且关键 NV 清零后再签发 `LEVEL5_PASS`。
