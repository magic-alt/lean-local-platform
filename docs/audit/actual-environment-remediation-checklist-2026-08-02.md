# Actual-environment remediation checklist — 2026-08-02

来源：[actual-environment-system-review-2026-08-02.md](actual-environment-system-review-2026-08-02.md)。当前判定 `LEVEL5_FAIL`，48/100。本清单不包含数据库备份、恢复、灾难恢复、隔离数据库或全量数据重导；这些事项属于本轮明确排除项。

通用完成条件：代码、migration、OpenAPI、前端类型和文档同步；单元/集成测试通过；最终复审仅使用当前实际环境并生成新日期证据。涉及历史异常记录只允许 additive trust/quarantine 标记，不删除或改写原始事实。

## Wave 0 — 事实错误和 Critical

| Issue ID | 任务 | 涉及文件 | 数据影响 | 测试 | 验收 | 回滚 | 完成定义 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| ACT-CRIT-001 | 冻结 execution dataset release/hash；将最终 Source/QA/PIT/benchmark gate、artifact digest、run/task terminal status 放入同一 finalization Unit of Work；历史异常 success 增 `trustStatus=invalid` | `tasks/worker.py`, source gate, backtest service, migration, TS types | additive 列/证书；不改 raw artifact | certification 在运行中切换的竞态集成测试；final gate critical 测试 | SQL `success AND final_passed=false`=0；启动/最终 release id 相同；异常历史不再显示 trusted | 回退代码与 additive API 字段；保留新增事实列，不删除证据 | 任何 critical gate 都无法进入 success，且版本冻结 |

## Wave 1 — 数据与回测可信度

| Issue ID | 任务 | 涉及文件 | 数据影响 | 测试 | 验收 | 回滚 | 完成定义 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| ACT-P1-005 | 建立单一 immutable Dataset Release；Parquet、LEAN cache、run、QA/certification 都引用 release FK | data governance services, migration, API/TS | 把现有 production Parquet 认证迁入 release；原表保留兼容 | release 唯一性、FK、过期/撤销、并发 recertification | 每个 production dataset 精确一个 active certified release；每个 success run FK 有效 | 双写兼容期间切回旧读取；不删除 release | `dataset_versions` 与 Parquet 不再形成两套 version 权威 |
| ACT-P1-002 | 把 Parquet recertification 拆为有界分区、checkpoint resume 和唯一 active lease；MySQL 长查询使用分页/服务端游标 | `derived_maintenance.py`, `data_sync.py`, task/recovery | additive checkpoint/attempt；不重建全量 | 连接中断、worker restart、同 scope 重复调度 | 一次维护从 checkpoint 收敛；无 orphan active；7 日无 2013 | 关闭新 orchestrator feature flag，保留水位 | 自动认证无需依赖多次 worker 重启 |
| ACT-P1-006 | 创建 fetchable Reproducibility Certificate，包含 image digest、project snapshot、release、LEAN zip/factor、config、orders/fills/equity/canonical digest | fingerprint/artifact services, stored object, migration | additive certificate/stored object | 两次同 input 最小真实 LEAN run；允许 raw 非确定字段差异 | 当前 DB 可查 golden pair；关键 canonical digest 全一致且文件可下载 | 停发 certificate；保留历史 certificate | 相同输入的当前复现性可独立验证 |
| ACT-P1-004 | 引入资产 capability 状态 `metadata_only/data_ready/executable`，所有目录/UI/preflight 使用同一状态 | data catalog/provider/source gate/UI | additive capability；不导入新数据 | 各资产 0/metadata/full 三态 contract tests | futures/options/cbond/minute 等实际 0 行时明确不可运行 | 回退 UI 展示，保留字段 | 页面不会把 raw metadata 误报为可回测资产 |

## Wave 2 — Experiment 和 Walk-Forward

| Issue ID | 任务 | 涉及文件 | 数据影响 | 测试 | 验收 | 回滚 | 完成定义 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| ACT-P0-002 | 对 batch/project/OOS run 加删除保护或 immutable snapshot；将当前 orphan WF 标为 `lineage_broken`；持久化 selection inputs/outputs 与 OOS run FK | experiment services, migrations, API/UI | additive lineage/status；不删除 orphan | FK/soft archive、validation-only selection、embargo、OOS exclusion | orphan FK=0；每折从 Train→Validation decision→OOS artifact 可导航 | 关闭新写路径；保留 snapshot | WF 证据独立、完整、可复现 |
| ACT-P0-002 | 在前项完成后执行最小 2×2 grid、rolling 与至少两折 WF，使用当前认证数据和已有 project | audit runner/API（复审阶段） | 最少新 run，统一 audit 标签 | preview=child unique count、failed-only retry、CSV/ranking/heatmap | child 组合唯一；success 不被 retry；OOS 未参与选择 | 取消尚未运行 child；不删除已生成事实 | 当前环境有完整 Experiment/WF 证据 |

## Wave 3 — Paper 多账户

| Issue ID | 任务 | 涉及文件 | 数据影响 | 测试 | 验收 | 回滚 | 完成定义 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| ACT-P0-001 | 建立 durable Paper certification cohort，至少两个差异 opening balance 账户，冻结 deployment/release/risk/execution version，保留 21 certified sessions | Paper account/deployment/cycle services, migration, API/UI | 创建最少两个正式审计账户和周期；append-only | account isolation、run-now/Beat 幂等、six checkpoint、no-signal/waiting/failed/recovered | ledger 独立；fill/fee 不重复；projection 重算 digest 一致 | pause cohort 和 deployment；不得删除 ledger | 当前库可导航并重算两个账户完整事实链 |
| ACT-P1-001 | dataTrust 改为按 account+generation+release 计算，验证资源存在、TTL、checkpoint/result 数量 | `paper_accounts.py`, API/TS/UI, certification table | additive certification row | 账户归档/代次变化/证据过期 | count=0 时不返回 trusted；dangling account evidence=0 | feature flag 切回只读兼容，默认 false | trust 只代表当前存在的账户事实 |
| ACT-P0-003 | 为 legacy Paper jobs/reconciliation 建 quarantine 与父资源完整性约束；禁止 orphan READY 被调度 | Paper scheduler/recovery, migration | 143/139 只标记 quarantine，不删除 | legacy migration、due scheduler、duplicate beat | orphan READY=0；quarantine 不参与 dispatch | 关闭 filter 但保留 quarantine 字段 | 旧 Paper 与 Account v2 边界明确且不影响调度 |

## Wave 4 — 架构和 API

| Issue ID | 任务 | 涉及文件 | 数据影响 | 测试 | 验收 | 回滚 | 完成定义 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| ACT-P2-004 | 拆分 Data Release、Run Orchestration、Paper Ledger/Projection 的 command/query/repository；声明每张状态表唯一 writer | `data_sync.py`, `paper_accounts.py`, `worker.py`, `api/data.py` | 无 schema 前提；逐步内部重构 | characterization + dependency tests | route 仅 validation/delegation；状态写者清单可自动检查 | 按模块 feature flag 回退 | 不再由超大 service 同时拥有 HTTP、调度和多表状态 |
| ACT-P2-001 | 统一 primary list envelope；从 OpenAPI 生成 API reference；Research 旧路由明确 deprecated/removed | routers, schemas, `docs/api.md`, frontend types | 无 | OpenAPI snapshot、client contract | 所有 list `{items,count,limit,offset}`；docs/TS/actual 相同 | 保留限时 legacy query/adapter | 契约无四种结构漂移 |
| ACT-P2-003 | UI command 创建稳定 operation id，网络重试复用同一 Idempotency-Key | `frontend/src/api/client.ts`, write callers | 复用现有 idempotency 表 | timeout/retry、同 key 异 payload 409 | 同一 command 两次请求返回同 resource/response | 回退 caller 层，服务端机制不变 | 关键 POST 的客户端重试语义成立 |

## Wave 5 — Web 流程和 UI

| Issue ID | 任务 | 涉及文件 | 数据影响 | 测试 | 验收 | 回滚 | 完成定义 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| ACT-P1-003 | 新建 list summary DTO/字段选择；大 schedule/fingerprint/validation 只在 detail 请求返回；前端改真实分页 | backtest/task/QA schemas, API, `api/index.ts`, pages | 无 | payload budget、分页、slow-network UI | backtests 3 条 <200KB；tasks 9 条 <200KB；页面不全量 `limit=1000` | 版本化旧 detail/full endpoint | 列表响应有硬上限且移动端可操作 |
| ACT-P2-002 | 前端实现 cursor 日志“更早/跟随/停止”，保留位置并在 terminal 停 poll | api types, operations/run detail pages | 无 | 长日志 cursor、route return、terminal polling | 可访问 tail 之前首行；无无限 polling | 隐藏新 UI，保留后端 cursor | 完整日志可诊断 |
| ACT-P3-002 | 修正 ECharts manualChunks 循环；建立 bundle budget | Vite config/chart imports | 无 | build/bundle smoke | build 无 circular chunk warning | 合并为单 ECharts chunk | chunk 图稳定 |
| ACT-P3-001 | 文档 migration/version 改生成或取消硬编码 | `docs/architecture.md`, docs checks | 无 | docs check | 实际 migration 与文档一致 | 回退文案 | 不再出现 0035/0038 漂移 |
| WEB-NV-001 | 在可用 in-app Browser 中复审 Dashboard→项目→preflight→run detail、history、batch、Paper 以及 1440/1280/768/390 | Playwright/browser evidence | 复用现有资源；仅缺证据时创建最少审计 run | console/network/screenshot/route state/accessibility | 关键页面无白屏；错误可恢复；四视口可操作 | 不适用（只读为主） | 27 个 NOT_VERIFIED 中 Web 项全部有当前证据 |

## Wave 6 — 调度和运行稳定性

| Issue ID | 任务 | 涉及文件 | 数据影响 | 测试 | 验收 | 回滚 | 完成定义 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| ACT-P0-003 | 建立通用 run registry/reconciler：owner、heartbeat、lease、domain/task mapping、terminalization reason | scheduler/task/research/derived/Paper services, migration | additive registry；历史 stale 标 reason | worker restart、task lost、container missing、cancel/finalize race | stale research=0；task/domain mismatch=0；单 scope 单 active | feature flag 回退，各域原状态保留 | 所有任务在 SLA 内收敛且 UI 给出操作 |
| ACT-P1-002 | 对维护失败配置指数退避、最大尝试、外部 alert 和可见 checkpoint；禁止快速 orphan chain | Beat/Celery/monitoring | additive attempt/alert | 连接抖动/重启（非生产故障注入环境） | 一次故障仅一个 active，恢复不重复全量工作 | 调整 beat route/feature flag | 数据维护稳定且不会无限重派 |

## Wave 7 — 复审

| Issue ID | 任务 | 涉及文件 | 数据影响 | 测试 | 验收 | 回滚 | 完成定义 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| ALL | 在当前实际环境重跑非破坏审计；安全复用项目/数据/账户；生成新日期六份报告与证据 | `docs/audit`, `web/runtime/audit` | 仅最少审计 run；统一标签 | backend tests 使用获批现有 MySQL lane；frontend build；in-app Browser；LEAN golden；Paper 21 日；WF | 总分≥90、Critical=0、P0=0、关键 NOT_VERIFIED=0 | 报告不可回写；失败保持 FAIL | 满足用户 Level 5 全部 gate 后才可给 PASS |

## P1 实施状态（审计后）

六项 P1 的代码、migration、API/TS 和回归测试已实现，统一标记为 `CODE_FIXED_REVALIDATION_REQUIRED`，不以临时 SQLite 单测替代实际 MySQL/LEAN/Paper 验收。

| Issue ID | 代码状态 | 主要落点 | 下一验收动作 |
| --- | --- | --- | --- |
| ACT-P1-001 | CODE_FIXED_REVALIDATION_REQUIRED | `paper_account_trust_certifications`、`paper_accounts.py` | 当前 cohort 重算、过期/归档/代次变化实测 |
| ACT-P1-002 | CODE_FIXED_REVALIDATION_REQUIRED | maintenance attempt/checkpoint/heartbeat/backoff/alert，同 run resume | 7 日稳定性观察与强制连接断开恢复 |
| ACT-P1-003 | CODE_FIXED_REVALIDATION_REQUIRED | summary list、200 hard limit、QA detail、Web server pagination | authenticated payload budget 与 slow-network UI |
| ACT-P1-004 | CODE_FIXED_REVALIDATION_REQUIRED | `asset_capabilities`、catalog/API/TS、preflight gate | 当前 8 个 scope 的 API/UI/SQL 对账 |
| ACT-P1-005 | CODE_FIXED_REVALIDATION_REQUIRED | `dataset_releases` 及 Parquet/dataset version/backtest FK-like references | MySQL migration + equity/index recertification |
| ACT-P1-006 | CODE_FIXED_REVALIDATION_REQUIRED | `reproducibility_certificates`、stored object、golden-pair API | 当前 certified release 最小真实 LEAN 双跑 |

## P2 实施状态（审计后）

四项 P2 已实现并统一标记为 `CODE_FIXED_REVALIDATION_REQUIRED`；原始实际环境证据与 `LEVEL5_FAIL` 不被代码测试覆盖。

| Issue ID | 代码状态 | 主要落点 | 下一验收动作 |
| --- | --- | --- | --- |
| ACT-P2-001 | CODE_FIXED_REVALIDATION_REQUIRED | `PageEnvelope`、sync/Parquet/QA/workflow/verification endpoints、生成式 API reference | 部署后 authenticated contract snapshot |
| ACT-P2-002 | CODE_FIXED_REVALIDATION_REQUIRED | `CursorLogViewer.tsx`、Backtest/Task cursor API types | >64 KiB 真实日志浏览器首尾与终态停 poll |
| ACT-P2-003 | CODE_FIXED_REVALIDATION_REQUIRED | `client.ts` operation ID + network retry | timeout/replay 与异 payload 409 |
| ACT-P2-004 | CODE_FIXED_REVALIDATION_REQUIRED | data sync commands、Paper command/query、state ownership manifest/test | 实际 sync/backtest/Paper characterization |

验证命令：`cd web/backend && .venv/bin/python -m pytest -q`、`cd web/frontend && npm run build`、`scripts/generate_help_api_reference.py --check --json`。

## 依赖与优先级

1. ACT-CRIT-001 是所有新回测、Experiment、Paper candidate 的前置。
2. ACT-P1-005 为 ACT-P1-006、ACT-P0-002 和 Paper deployment 冻结提供统一 release。
3. ACT-P0-003 必须先于生产式 Paper 自动调度。
4. Wave 7 不得用历史 JSON 代替当前事实，也不得因总分高而忽略 Critical/P0。
