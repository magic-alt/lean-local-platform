# Paper 多账户模拟券商工作台

`/paper` 现在以 Paper Account 为中心。每个账户拥有独立的初始资金
Opening Ledger、持仓、收益、风险配置、策略部署、执行 checkpoint 和 projection。
旧的 Session/Replay 页面保留在 `/paper/legacy`，历史记录不会自动迁移、删除或
改写。

## 核心对象

| 对象 | 含义 | 是否资金事实 |
| --- | --- | --- |
| Paper Account | 账户身份、状态、市场、币种、benchmark 和 generation | 否 |
| Deployment | 冻结的 Project/Backtest/策略/参数/数据/风险版本与计划 | 否 |
| Execution Cycle | 某 deployment 在某交易日的一次正式执行和恢复边界 | 否 |
| Signal | LEAN 在 T 日收盘后产生的结构化观察或目标 | 否 |
| Intent | 可执行信号进入既有不可变订单链后的意图 | 否 |
| Order Transition | 既有 13-state 状态机的追加式状态证据 | 否 |
| Fill | 确定性撮合结果和费用拆分 | 是 |
| Ledger | Opening balance、成交本金、手续费、税费和持仓变动 | 是，canonical |
| Projection | 从 ledger/fill/认证收盘价重建的账户快速预览 | 否，可删除重建 |

初始资金只写一次 `CASH_DEPOSIT` opening ledger。当前现金和持仓不会作为可编辑
字段写回事实库。需要“重置”时，应克隆账户或创建新的 account generation；不要
删除旧成交。Active 账户不能删除，只能暂停后归档。

## 创建第二个模拟账户

1. 在 Paper Accounts 选择“新建模拟账户”。
2. 账户步骤填写名称、CNY 初始资金和 benchmark。
3. 策略步骤从 `/api/paper/candidates` 选择成功、认证、验证通过且冻结的 Backtest。
4. 执行步骤选择自动运行、`Asia/Shanghai`、`paper_execute` 和 next-open。
5. 风险步骤确认最大持仓、单标的/单行业权重、成交量参与率、回撤熔断、
   现金下限、订单金额、日换手和 blacklist。
6. 确认页核对冻结 fingerprint 后创建。第二个账户会生成独立 shadow session、
   opening ledger、generation、risk profile 和 checkpoint，不共享任何现金或订单。

第一版 UI 引导一个账户对应一个主策略。同一账户最多只有一个 active
`paper_execute` deployment；其他部署可使用 `signal_only`。修改策略、参数、
universe 或执行语义时，服务端禁用旧 deployment 并创建新 version，不覆盖冻结
历史。

## 每日执行语义

每日自动运行不是普通全量 Backtest，也不会把 LEAN 的输出直接写成账户成交：

```text
Beat -> due deployment -> 交易日/数据/QA/PIT/reference/benchmark gate
     -> account checkpoint -> restricted LEAN -> Signal -> immutable Intent
     -> A 股约束 -> 13-state Order -> next-session Fill -> Ledger
     -> projection -> daily report -> notification outbox
```

交易日 T 的收盘数据完成并认证后，策略在 T 收盘后计算信号。需要交易的 Intent
标记下一交易日执行，并按 T+1 认证开盘价匹配。停牌、涨跌停、现金不足、现金
下限、最大持仓、单标的/行业上限、容量上限、回撤熔断和 T+1 不可卖都会保留
原始信号与明确原因。`hold`、
`observe_only` 和 `no_signal` 不会变成可成交 Intent。

无信号代表策略成功检查了该交易日，因此 cycle 是 `succeeded`，同时保存
`no_signal` 观察。存在信号不代表一定成交；Signals 页的“为什么没有交易”会显示
`observe_only`、`suspended`、`limit_up`、`limit_down`、`t1_blocked`、
`insufficient_cash`、`cash_floor`、`qa_failed`、`benchmark_missing`、
`stale_data` 或 `next_session_pending` 等原因。

行情未达到 watermark 或门禁失败时，cycle 使用 `waiting_data` 或结构化失败，
不会用旧行情冒充新交易日，也不会改变 ledger。周末和休市日按交易所日历跳过，
不会因为缺少自然日行情报警。

## Run now、暂停、克隆

Run now 只补跑 deployment 缺失的下一个交易日。deployment + trading date 有唯一
约束，API 重试、Beat 重投和 worker 重启都会返回同一 cycle；已经成功的日期不会
重复成交、扣费或覆写 ledger。

- “暂停策略”停止 deployment 调度，但保留账户、资金、持仓和全部审计。
- “暂停账户”阻止账户上所有正式写状态 cycle。
- “恢复”从下一个缺失交易日继续，不静默补跑暂停期间的全部自然日。
- “克隆账户”复制账户、风险和 deployment 配置，创建新的 opening ledger；不会
  复制成交、持仓、cycle 或 checkpoint 历史。

## 页面解读

Positions 的价格列明确叫“最新认证价格”或“最新收盘价”，并显示
timestamp/trading date；它不是实时价。`stale` 或 `missing` 表示估值需要等待
认证数据。Orders 复用既有 13-state 状态机。Trades 将本金、commission、stamp
duty、transfer fee 和 slippage 分列，避免 replay 重复计费。Automation 显示
下一运行、最后成功/失败、watermark、QA、checkpoint 和连续失败次数。多账户
比较仅对齐共同区间和估值日；不同币种会标记不可比，不静默合并金额。

## Legacy Session/Replay

Legacy 页面提供 `lean_walkforward` 和 `signal_simulation` 两种模式，并保留
`lean_walkforward_v2` 历史接口。它们都只在本地模拟，不连接真实券商，也不会
自动发出实盘订单。

![Paper 会话创建、状态和每日运行区域](assets/paper-sessions.png)

## 模式区别

| 模式 | 输入 | 行为 |
| --- | --- | --- |
| `lean_walkforward` | Project + 可信 Backtest | 每个交易日运行隔离 LEAN 窗口并保存每日证据 |
| `lean_walkforward_v2` | Project + 可信 Backtest | 将 LEAN 输出作为 intent，经统一约束、撮合、fill 和 ledger 管线处理 |
| `signal_simulation` | 手工或 Insights 信号 | 按执行规则模拟目标仓位、订单和持仓 |

LEAN Paper 必须同时提供 `projectId` 和 `sourceBacktestId`。候选接口只返回满足项目关联和可信度要求的历史运行。

Legacy `lean_walkforward_v2` 的功能开关仍适用于直接创建 session。Paper Account
内部 shadow session 固定使用已验收的 v2 管线，但不在前端暴露为可编辑 session。
旧 session 不会自动迁移或改写。

## 创建 LEAN Paper

1. 在 Projects 确认策略代码和参数。
2. 完成可信历史回测并检查 admission、基准和数据证据。
3. 在 Paper 选择 Project 和 Trusted Backtest。
4. 配置市场、资金、基准、持仓上限、现金下限和黑白名单。
5. 创建后按交易日顺序运行。

Create Paper Session 只展示当前模式需要的字段：LEAN Walk-forward 显示 Project 与 Trusted Backtest，Signal Simulation 显示 Market、Symbol 与 Initial Cash；切换模式不会产生另一模式的隐藏必填校验。

```json
{
  "name": "EMA walk-forward",
  "mode": "lean_walkforward",
  "projectId": "ema-project",
  "sourceBacktestId": "trusted-run-id",
  "symbol": "000001",
  "market": "china",
  "venue": "china",
  "cash": 300000,
  "benchmarkSymbol": "000300",
  "maxPositionWeight": 0.2,
  "maxIndustryWeight": 0.4,
  "maxVolumeParticipation": 0.1,
  "circuitBreakerDrawdown": 0.15,
  "minCash": 20000
}
```

`same_close` 与旧 `allowSameDayClose` override 已永久下线；历史请求返回
HTTP 410 `SAME_CLOSE_REMOVED`。Paper 只允许 next-open、next-close 或
next-vwap，其中账户级正式执行固定为 next-open。

## 逐日运行

`POST /api/paper/{session_id}/run-day` 对 LEAN Paper 创建一个新的 walk-forward 子运行；信号模拟模式则进行当日撮合。

```json
{"tradeDate":"2026-07-21","autoSignal":true}
```

LEAN Paper 必须按交易日顺序推进。`replay` 对该模式只允许开始日等于结束日，不能一次跨越多个日期并跳过每日状态。

v2 将每条 LEAN 订单输出先持久化为不可变 intent，再按合法状态图追加 transition。
约束通过后才允许写 fill 和 ledger；约束失败会在同一来源链上形成带原因的 rejected
order。开仓现金与持仓、成交本金、手续费均写入 append-only ledger；会话现金和
持仓只是从该账本重建的读模型，重试同一 intent 不会再次成交或扣费。`intent_capture`、`constraint_validation`、`matching`、`ledger`、
`snapshot_report` 和 `reconciliation` 六个 checkpoint 都带稳定 digest，重复完成
同一阶段时若 payload 漂移会直接失败。

## 信号模拟

手工信号接口接收交易日、方向、标的、目标仓位、强度、原因和来源。服务端执行规则拥有最终决定权；无效方向、不可交易标的、风险上限或缺失行情会产生拒绝原因。

Insights 产生的候选信号不会自动进入 Paper。用户必须显式调用 handoff，且当前只支持 equity 和现货 crypto 会话。

## 每日检查

每个交易日应检查：

- Daily Runs 是否成功以及关联回测；
- Signals 的来源、理由和目标仓位；
- Orders 的状态、价格、数量、费用和拒绝原因；
- Positions、现金和 NAV；
- Daily Report 的基准、质量门禁、警告和 fingerprint。

## 常用接口

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `GET/POST` | `/api/paper` | 会话列表和创建 |
| `GET` | `/api/paper/candidates?projectId=...` | 可信历史候选 |
| `GET` | `/api/paper/{id}` | 会话、信号、订单、持仓和运行 |
| `GET` | `/api/paper/{id}/intents` | v2 不可变订单意图 |
| `GET` | `/api/paper/{id}/intents/{intent_id}/transitions` | v2 订单状态迁移证据 |
| `POST` | `/api/paper/{id}/run-day` | 推进一个交易日 |
| `POST` | `/api/paper/{id}/replay` | 信号模拟回放或单日 LEAN 运行 |
| `GET` | `/api/paper/{id}/reports` | 每日报告列表 |

Paper 仍是研究和运维验证工具，不等同于实盘交易系统或实时行情终端。
