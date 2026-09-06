# Research Interop

LEAN Local Platform 不再承载模型研究执行或 Notebook Workspace。Research Plane 由外部 `qlib-platform` 负责；本平台只保留研究产物的不可变导入、只读预览、lineage/hash 验证和官方 LEAN 执行验证。

这不是删除 LEAN 的 Research/算法能力。平台的原则是：**QuantConnect LEAN 保持上游执行引擎权威，本地 Web 只提供经过治理的控制面；模型研究工作流单独由 qlib-platform 承担。**

## 所有权

| 能力 | Owner | 本平台状态 |
| --- | --- | --- |
| 特征、因子、标签 | qlib-platform | 不执行 |
| 模型训练、walk-forward、研究诊断 | qlib-platform | 不执行 |
| 研究选股、TargetPortfolio | qlib-platform | 通过 Artifact Contract v2 导入 |
| DataRelease、PIT、QA、lineage | lean-local-platform | 权威控制面 |
| 导入结果预览 | lean-local-platform | 只读 |
| 回测、订单/组合仿真、执行验证 | QuantConnect LEAN via lean-local-platform | 权威执行路径 |
| Paper / OMS / broker / ledger | lean-local-platform | 受独立准入和认证门禁约束 |

历史 `app/research/`、旧 worker task、历史表以及少量 service-level Research example helper 可以继续保留，用于读取旧证据、迁移或兼容测试；它们不是新的产品入口。新 UI、公开 Example API、Experiment Batch 和公开 Research API 都不得创建本地研究任务。

## 标准闭环

```text
lean-local-platform publishes immutable DataRelease
  -> qlib-platform resolves the same release
  -> feature/factor/model/walk-forward research
  -> Artifact Contract v2 / QLIB_RESEARCH_BUNDLE
  -> POST /api/research/imports/qlib
  -> hash + lineage + active DataRelease verification
  -> GET /api/research/imports for read-only preview
  -> TargetPortfolio bound to an authoritative LEAN backtest
  -> POST /api/research/runs/{run_id}/lean-validation
  -> LEAN_VALIDATED evidence
```

导入成功只表示 artifact contract 与平台数据身份通过校验，不表示 Paper、生产或实盘准入。

## API

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `GET` | `/api/research/capabilities` | 官方 LEAN、A/HK localization 和 Research ownership 的机器可读契约 |
| `GET` | `/api/research/imports` | 分页列出已导入 qlib 研究结果和最新 TargetPortfolio/LEAN validation 摘要 |
| `GET` | `/api/research/imports/{import_id}` | 查看单次导入的 manifest、artifact 摘要和 lineage 预览 |
| `POST` | `/api/research/imports/qlib` | 导入 Artifact Contract v2 `QLIB_RESEARCH_BUNDLE` |
| `POST` | `/api/research/runs/{run_id}/lean-validation` | 将成功且通过 execution-validation 的 LEAN run 绑定为研究目标的执行验证 |

旧 `/templates`、本地 `/runs` 创建/预览/重试/取消和 `/workspaces` 路由为退役面，保持 OpenAPI-hidden，并稳定返回 `404 Not Found`。这使调用方不会把历史实现误认为仍受支持的产品 API。

## Research 页面

Research 页面是交付与验证视图，不是研究 IDE。它展示：

- QuantConnect LEAN 上游继承策略；
- A股和港股 localization 状态；
- 最近导入的 qlib-platform bundle；
- DataRelease、TargetPortfolio 数量/交易日和 LEAN validation 状态；
- Data、Backtest 和本帮助文档入口。

页面不会创建模型、运行 Notebook、启动本地 research container 或重新解释 qlib 的研究结果。

## A股与港股

当前 Artifact Contract v2 的 `TARGET_PORTFOLIO` instrument 校验使用 `SH` / `SZ` / `BJ` A股约定，LEAN validation artifact 也仍采用 A股的 CNY / Asia/Shanghai 执行语义。因此当前 qlib handoff 是 **A股优先**。

港股已有本地 symbol/data layout profile，但被明确标记为 `partial` / `preview_only`。港股参数、数据覆盖和本地交易规则可以用于 preflight/preview；真正生成 LEAN 执行配置时仍 fail-closed。在扩展 qlib artifact instrument contract、逐证券 board lot / tick-size、交易日历、费用模型和独立 LEAN 验证证据前，不应把港股研究 bundle 或港股执行称为已认证。

## 数据与执行不变量

- qlib bundle 必须引用已注册且 active 的不可变 DataRelease。
- payload SHA-256、artifact parent、root artifact、ModelRelease 和 TargetPortfolio lineage 必须完整。
- 一个 bundle 的 artifacts 必须绑定同一个 DataRelease。
- LEAN validation 必须绑定同一 DataRelease、TargetPortfolio artifact ID 和 targets SHA-256。
- LEAN backtest 必须成功且 execution-validation `passed=true`。
- Research import/preview 不拥有订单、fill、broker 或 ledger 写入权限。
- 当前 release certification 仍由 `docs/release-status.md` 的证据决定；本页显示成功不改变认证状态。
