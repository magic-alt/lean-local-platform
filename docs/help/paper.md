# Paper 多账户模拟券商工作台

`/paper` 现在以 Paper Account 为中心。每个账户拥有独立的初始资金
Opening Ledger、持仓、收益、风险配置、策略部署、执行 checkpoint 和 projection。
旧的 Session/Replay 页面和接口已下线；未被 Paper Accounts 关联的旧记录由
迁移清理，不再作为可读兼容数据保留。

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
3. 策略步骤从 `/api/paper/accounts/candidates` 选择成功、认证、验证通过且冻结的 Backtest。
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

## 可信候选与账户接口

Paper Accounts 只接受已成功、已认证、验证通过且保留冻结策略快照的 Backtest。
候选接口为 `GET /api/paper/accounts/candidates?projectId=...`。旧的 session、
replay、手工 signal 和逐日推进接口已下线，不再提供兼容入口。

账户级执行固定使用 next-open。`same_close` 与旧 override 均不受支持；
行情、benchmark 或 Source Gate 不完整时，cycle 必须 fail closed，不能写入
fill、ledger 或绩效 projection。

常用接口：

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `GET/POST` | `/api/paper/accounts` | 账户列表和创建 |
| `GET` | `/api/paper/accounts/candidates?projectId=...` | 可信历史候选 |
| `GET` | `/api/paper/accounts/{id}/overview` | 账户总览与信任状态 |
| `GET/POST` | `/api/paper/accounts/{id}/deployments` | 冻结部署列表和创建 |
| `POST` | `/api/paper/deployments/{id}/run-now` | 补跑下一个缺失交易日 |
| `GET` | `/api/paper/accounts/{id}/performance` | 认证后的净值、benchmark 与超额收益 |
| `GET` | `/api/paper/accounts/{id}/audit` | 账户审计事件 |

历史净值只有在正式库迁移、按历史 as-of 重算、checkpoint 校验和 Source Gate
重新认证均通过后才会返回 `dataTrust.valuationTrusted=true`。未通过时 UI 持续
显示不可忽略的警告，不应把旧绩效用于交易判断。

## 每日检查

每个交易日应检查：

- Daily Runs 是否成功以及关联回测；
- Signals 的来源、理由和目标仓位；
- Orders 的状态、价格、数量、费用和拒绝原因；
- Positions、现金和 NAV；
- Daily Report 的基准、质量门禁、警告和 fingerprint。

Paper 仍是研究和运维验证工具，不等同于实盘交易系统或实时行情终端。
