# Actual-environment remediation checklist — 2026-08-02（第四次复审）

来源：[主报告](actual-environment-system-review-2026-08-02.md)。当前判定 `LEVEL5_FAIL`，89/100；未关闭 0 Critical、0 P0、3 P1、1 P2、0 P3，另有 13 项 `NOT_VERIFIED`。

## 仍需完成

| 顺序 | Issue | 当前状态 | 下一任务 | 完成定义 |
| ---: | --- | --- | --- | --- |
| 1 | ACT-P1-007 | EXTERNAL_ENDPOINT_VERIFIED_24H_PENDING | 飞书签名端点已于 2026-08-13 返回 `code=0`；接通 LEAN 中转并观察 delivery/DLQ/requeue 24h | 有 persisted external 2xx；attempts有界；无重试风暴；health可从 degraded 恢复 |
| 2 | ACT-P1-008 | OPEN_24H_CAPACITY_OBSERVATION | 保持当前串行 backtest 默认与 Compose limits，采集 24h per-container/headroom/queue | 无 OOM/抖动；memory/CPU/queue低于阈值；归因字段完整 |
| 3 | ACT-P1-002 | OPEN_OBSERVATION_PENDING | 连续 7 日观察 0043 后 recertification/checkpoint/single-active | 无新 MySQL 2013/OOM/orphan chain；断点恢复成功；同 scope 单 active |
| 4 | ACT-P2-002 | OPEN_BROWSER_NOT_VERIFIED | 在可用 actual Browser 执行四视口主旅程和 Cursor 日志验收 | console/network无阻断；earlier/follow/terminal-stop正确；keyboard/a11y可用 |

通知端点已从 placeholder 替换为真实飞书 V2 机器人地址，使用
`FEISHU_WEBHOOK_SECRET` 的签名请求已成功投递测试消息；详见
[2026-08-13 验证记录](external-webhook-verification-2026-08-13.md)。该单点验证尚未产生
LEAN `alert_deliveries` 持久化成功记录，也未覆盖 24 小时 attempts、DLQ/requeue 和
health recovery，因此不得关闭 ACT-P1-007 或 requeue 历史 dead letters。7 日和
24 小时门禁必须由真实时间跨度证据完成，不以单点快照补签。

## 第四次复审已完成

| Issue | 关闭证据 | 回归门禁 |
| --- | --- | --- |
| ACT-P0-004 | release `2ebbd09…-acc872…`；233/233；0043/0043；5 workers pong | rollout verifier 必须 pass；全部 writer 同代次 |
| ACT-P0-002 | batch `8ee62a11-…` Train/Validation/OOS 均成功；valid certificate；0 leakage violations | completed snapshots immutable；OOS不得参与 selection |
| ACT-P0-001 | 原 cohort/两账户最终各23成功 session；fill/reject/no-signal；ledger replay；cohort certified | 不允许 research-only source；账户资金隔离；后续 child history reconciliation |
| ACT-P1-003 | alert-events 默认页 32,569 B；PageEnvelope；delivery history cap=3 | list默认<200KB；count/offset稳定 |
| ACT-P2-003 | 1 ms timeout 后同 key replay 200/同 resource/replayed=true；payload drift 409 | operation ID跨网络 retry保持稳定 |
| ACT-P2-004 | actual container architecture tests 3 pass；restart只恢复声明 writer | route仅validation/delegation；每张状态表单一 writer |
| ACT-P3-001 | architecture migration版本从文件/schema动态得出 | docs check不得硬编码最新编号 |
| ACT-P3-002 | frontend build 5727 modules，无 ECharts circular warning | ECharts/zrender保持同 chunk或证明无初始化环 |

## 数据修复记录

| 项目 | 结果 |
| --- | --- |
| Migration | `0043_p1_lineage_query_index` applied；rollback policy已声明 additive/compensating |
| Maintenance run | `7f9b66f5-cdca-47f5-9c97-226ae5ed0e3e` attempt 3 checkpoint resume success |
| Equity | 17,703,084 rows、194 files、21,273 batch groups；DuckDB match |
| Index | 44,741 rows、37 files；DuckDB match |
| Query behavior | bounded-memory lineage index/force-index避免原 17.7M grouping OOM |

## Paper 修复记录

| 缺陷 | 修复/验证 |
| --- | --- |
| Screening source promotion | candidate 与 session seed 对显式 `researchOnly`、`tradable=false`、`admissionEligible=false`、`SCREENING` fail-closed |
| 差异资本 reconciliation | 首个 cumulative child建立账户专属 immutable baseline；后续与上一成功 child严格比对；drift测试失败关闭 |
| Worker restart post-processing | 成功 restricted runner 不再被 init_db 误标 failed；orphan recovery重派后处理/finalization |
| Acceptance continuation | 支持 MySQL DECIMAL、error deployment恢复、保留字 alias、existing success/gap-only continuation |
| Collecting cohort replacement | 仅 0-session collecting member可按显式 map重绑 replacement deployment；已认证证据不可变 |
| Runner isolation | project/support staging只读；`/Lean/Project`、`/Lean/Run` tmpfs；support固定 allowlist；不递归复制 results |

## 验证门禁

```bash
cd web/backend && .venv/bin/python -m pytest -q
cd ../frontend && npm run build
cd ../.. && web/backend/.venv/bin/python scripts/verify_release_convergence.py
web/backend/.venv/bin/python scripts/run_paper_accounts_acceptance.py \
  --account-id a97c9a78-c1c1-4154-aa6f-eb4a99ddb6d8 \
  --account-id b172a4e9-d0bb-4753-9406-8eb9718fbbfe \
  --cohort-id 2da80404-a54d-411c-8fba-d1866b1ad43f \
  --days 21 --no-require-waiting-data
```

本次结果：pytest 604 passed/2 skipped；frontend PASS；convergence PASS；Paper PASS（最终2×23，deployments paused，active cycles=0）。下一轮不得重复开户、重复创建 cohort、删除旧 failed cycle、全量重导或重建 Parquet；应复用本轮正式事实并只补齐 observation/Browser evidence。

## Level 5 签发条件

1. Critical=0、P0=0 持续成立；
2. 三个 P1 时间跨度/外部证据关闭；
3. actual Browser 关键 journey与 Cursor验收通过；
4. score≥90，关键 `NOT_VERIFIED` 清零；
5. 六份审计产物来自同一 release/schema/观察窗口。
