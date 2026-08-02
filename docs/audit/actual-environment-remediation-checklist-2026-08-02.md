# Actual-environment remediation checklist — 2026-08-02（第二次审计）

来源：[主报告](actual-environment-system-review-2026-08-02.md)。当前判定 `LEVEL5_FAIL`，51/100。第一次审计后 P0/P1/P2 三批代码修复均已纳入；`0039` 的状态收敛和 Paper 开户层已在实际环境验证，P1/P2 因实际进程/schema 未部署而不能关闭。

通用约束：不删除或重写历史事实；历史错误只加 trust/quarantine 标记；不以 mock、SQLite、文档或单测替代 actual MySQL/LEAN/Paper 证据；不要求备份、恢复、隔离环境或全量数据重导。

## Wave 0 — 事实错误和 Critical

| Issue ID | 任务 | 涉及文件 | 数据影响 | 测试 | 验收 | 回滚 | 完成定义 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| ACT-P0-004 | 在获批变更窗口应用 `0040`，按 migration→API→workers→Beat 顺序滚动，同一 release manifest 暴露 git SHA/schema/OpenAPI hash | Compose/release scripts、health、migration 0040 | additive 四表；不改历史交易事实 | migration smoke、actual OpenAPI diff、worker ping | actual=source 230 paths；0040 applied；5 新 endpoints 可用；所有进程同 SHA | 回滚应用镜像；保留 additive 表，不 downgrade/delete | 实际代码、schema、API、frontend 单一代次 |
| ACT-CRIT-001 | 部署 frozen Dataset Release/finalization 修复；将历史 critical-success additive 标记 `trustStatus=invalid`；禁止任何 final critical 进入 success | backtest worker/finalizer/source gate、0040、API/TS | 新 release/certificate/trust 字段；保留 raw artifact/status 历史 | certification race、final gate critical、事务回滚 | SQL `success AND final_passed=false AND trusted=true`=0；新 run 启动/最终 release一致 | 停发新证书并回退代码；不删除证据 | 任何可信 success 的最终 critical gates 全 pass |

## Wave 1 — 数据与回测可信度

| Issue ID | 任务 | 涉及文件 | 数据影响 | 测试 | 验收 | 回滚 | 完成定义 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| ACT-P1-005 | 对现有 equity/index 做增量 release 认证，使 Parquet、run、cache、QA 引用同一 immutable release | release/recertification/source gate | 增加 release/FK-like refs；不 rebuild Parquet | release唯一性、过期/撤销、并发recertify | 两个 production scope 各一 active certified release | 停用新读取，保留 release rows | 不再有两套 version authority |
| ACT-P1-006 | 复用现有 project 做最小真实 LEAN 双跑并生成 Reproducibility Certificate | fingerprint/certificate/object store | 最少 2 runs；统一审计标签 | 同 input 两次；canonical/orders/fills/equity digest | Golden pair API 可查、证书可下载、关键 digest 相同 | 取消未开始任务；完成事实不删除 | 当前可独立复核相同输入复现性 |
| ACT-P1-002 | 启用 maintenance checkpoint/single-active/backoff，观察 7 日 | derived maintenance/data sync/Beat | 仅 checkpoint/attempt/heartbeat | 连接瞬断和 worker restart 应在获批窗口执行 | 7日无 MySQL2013/orphan chain；同 scope 单 active | feature flag 回退，保留水位 | 自动认证有界恢复 |
| ACT-P1-004 | 把 actual capability API/UI 与 canonical 行数、certification 对账 | catalog/capability/preflight/UI | 无数据导入 | 0/metadata/data-ready/executable 三态 | future/option/cbond/minute 0行时明确不可执行 | 回退 UI 字段，默认 unavailable | 页面不把 metadata 冒充可回测 |

## Wave 2 — Experiment 和 Walk-Forward

| Issue ID | 任务 | 涉及文件 | 数据影响 | 测试 | 验收 | 回滚 | 完成定义 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| ACT-P0-002 | 保留当前 broken row 作历史证据；用现有 project/release 创建最小新 WF，持久化 train/validation/OOS snapshot、selection input/output、PIT manifest、OOS run FK | experiment/WF services、API/UI | 最少新 batch/folds；不覆盖旧 row | Validation-only selection、embargo、PIT、删除保护 | 每折可从 decision 导航到 OOS artifact；OOS不参与选参 | 取消未开始 child；已完成事实保留 | 当前库有完整、无泄漏的三段 WF certificate |
| ACT-P0-002 | 创建最小 2×2 grid/rolling 证据并验证 failed-only retry、CSV/ranking/heatmap | experiment scheduler/UI | bounded child runs | preview=unique child count、retry 不覆盖 success | 组合唯一、进度/导出/比较一致 | cancel pending children | Optimization/rolling 由 actual evidence 支撑 |

## Wave 3 — Paper 多账户

| Issue ID | 任务 | 涉及文件 | 数据影响 | 测试 | 验收 | 回滚 | 完成定义 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| ACT-P1-001 | 0040 后按当前 account+generation+release 重建 trust；旧 deleted account evidence 失效 | Paper trust/API/UI | additive certification；不改 ledger | archive/generation/TTL/release expiry | actual trust 只引用当前两个账户；无 dangling ID | trust 默认 false | trust 与当前事实绑定 |
| ACT-P0-001 | 复用现有两个账户和 deployment 完成 21 certified sessions；先纠正 past-due scheduler 状态 | Paper scheduler/cycle/order pipeline/report | append-only cycles/ledger；不新建重复账户 | duplicate Beat/Run-now、no-signal/waiting/recovery、fill/fee uniqueness | 两账户各21 sessions；无跨账户 row；重复调用同 cycle/fill/fee | pause deployment；不删除 ledger | 多账户资金、持仓、订单、成交和账本可重算 |
| ACT-P0-001 | 独立只读 replay ledger，与 projection/overview/performance/report/UI 五方对账 | ledger replay/query/UI | 只读 | cash/position/NAV/day P&L recompute | digest 和金额一致，误差规则明确 | 不适用 | projection 可由 ledger 重建 |

## Wave 4 — 架构和 API

| Issue ID | 任务 | 涉及文件 | 数据影响 | 测试 | 验收 | 回滚 | 完成定义 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| ACT-P2-001 | 部署 PageEnvelope 和 generated docs；提供旧 envelope 兼容窗口 | routers/schemas/docs/TS | 无 | actual OpenAPI snapshot/client contract | primary lists 结构一致 | legacy adapter | docs/TS/OpenAPI/response一致 |
| ACT-P2-004 | 部署并实际走通 ownership manifest/command-query surfaces | state ownership、data sync、Paper、worker | 无 | dependency + characterization | API/task entrypoint 不直接写 orchestration state | 模块 feature flag | 每张状态表只有声明 writer |
| ACT-P2-003 | 对关键 POST 做真实 timeout replay | frontend API client、idempotency middleware | 最少受控请求；优先 no-signal terminal cycle | 同 command 同 key、异 payload 409 | 同一操作只生成一个 resource/cycle | 停止测试代理 | 客户端重试语义成立 |

## Wave 5 — Web 流程和 UI

| Issue ID | 任务 | 涉及文件 | 数据影响 | 测试 | 验收 | 回滚 | 完成定义 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| ACT-P1-003 | 部署 summary DTO/分页并设置 payload budget | backtest/task/QA schemas、pages | 无 | content-length/slow network | backtests/tasks list 各 <200KB | legacy full detail endpoint | 列表响应有硬上限 |
| ACT-P2-002 | 在可用 Browser 中验证 cursor viewer、terminal stop polling | cursor viewer/pages | 无 | >64KiB真实日志 | 首尾可达、位置保持、终态不poll | 隐藏UI不回退API | 日志完整可诊断 |
| WEB-NV-001 | 实际 Browser 完成 Dashboard→Project→preflight→history→batch→Paper 四视口 journey | Playwright/browser evidence | 复用现有资源 | console/network/a11y/route state | 无白屏/无限loading；错误可恢复；四视口可操作 | 不适用 | 主要Web流程有当前证据 |
| ACT-P3-002 | 清除 ECharts circular chunks、建立 bundle budget | Vite/chart imports | 无 | build/smoke | build无循环warning | 合并vendor chunk | bundle图稳定 |
| ACT-P3-001 | architecture migration 信息改为动态/不硬编码 | docs/check scripts | 无 | docs check | runtime与文档不漂移 | 回退文本 | latest migration 单一事实源 |

## Wave 6 — 调度和运行稳定性

| Issue ID | 任务 | 涉及文件 | 数据影响 | 测试 | 验收 | 回滚 | 完成定义 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| ACT-P1-007 | notification delivery 加 health probe、max attempts、jitter backoff、dedupe 和 DLQ；修正示例 webhook | notification outbox/Beat/health | additive terminal/dead-letter state | 永久失败/瞬时失败/恢复 | channel失败时health degraded；attempt有界；无每分钟风暴 | disable channel、保留outbox | 送达状态真实且可操作 |
| ACT-P1-008 | 先部署小 DTO，再按容器采集 RSS/heap，调并发和memory limit | metrics/Compose/workers/API | 无业务数据影响 | 24h soak、payload/load | memory低于critical阈值且无OOM/抖动 | 回滚concurrency值 | 有明确容量SLO和余量 |
| ACT-P0-003 | 保留 0039 quarantine/reconciler 回归 | recovery/scheduler | 不删除历史 | restart/orphan regression（获批窗口） | stale/orphan READY 持续为0 | 不回滚quarantine事实 | 已解决问题不复发 |

## Wave 7 — 复审

| Issue ID | 任务 | 涉及文件 | 数据影响 | 测试 | 验收 | 回滚 | 完成定义 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| ALL | 在同一 actual 环境复审并生成新日期六份产物 | `docs/audit`,`web/runtime/audit` | 仅上面批准的最小runs/cycles | migration/OpenAPI、LEAN Golden、WF、Paper、Browser、SRE | score≥90、Critical=0、P0=0、关键NV=0 | 报告只追加新快照 | 满足所有Level5 gates后才给PASS |

## 当前依赖顺序

1. ACT-P0-004 是所有 P1/P2 actual 验收前置。
2. ACT-CRIT-001 与 ACT-P1-005 是新 Experiment/Paper candidate 前置。
3. ACT-P1-006 的 Golden Pair 是回测可信度前置。
4. ACT-P0-002 完成后才能声明无未来数据泄漏。
5. ACT-P0-001 必须以现有账户完成，不重复开户。
6. ACT-P1-007/P1-008 在长期 Paper 自动运行前关闭。

## 已关闭项

`ACT-P0-003` 已由 `0039` 在实际环境关闭：stale Research run=0，143 legacy Paper jobs 和 139 reconciliations 全部 quarantine，orphan READY=0。关闭不代表删除历史；Wave 6 保留回归门禁。
