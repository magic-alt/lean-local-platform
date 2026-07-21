# Paper 模拟交易

Paper 页面提供 `lean_walkforward` 和 `signal_simulation` 两种模式。它们都只在本地模拟，不连接真实券商，也不会自动发出实盘订单。

![Paper 会话创建、状态和每日运行区域](assets/paper-sessions.png)

## 模式区别

| 模式 | 输入 | 行为 |
| --- | --- | --- |
| `lean_walkforward` | Project + 可信 Backtest | 每个交易日运行隔离 LEAN 窗口并保存每日证据 |
| `signal_simulation` | 手工或 Insights 信号 | 按执行规则模拟目标仓位、订单和持仓 |

LEAN Paper 必须同时提供 `projectId` 和 `sourceBacktestId`。候选接口只返回满足项目关联和可信度要求的历史运行。

## 创建 LEAN Paper

1. 在 Projects 确认策略代码和参数。
2. 完成可信历史回测并检查 admission、基准和数据证据。
3. 在 Paper 选择 Project 和 Trusted Backtest。
4. 配置市场、资金、基准、持仓上限、现金下限和黑白名单。
5. 创建后按交易日顺序运行。

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
  "minCash": 20000
}
```

## 逐日运行

`POST /api/paper/{session_id}/run-day` 对 LEAN Paper 创建一个新的 walk-forward 子运行；信号模拟模式则进行当日撮合。

```json
{"tradeDate":"2026-07-21","autoSignal":true}
```

LEAN Paper 必须按交易日顺序推进。`replay` 对该模式只允许开始日等于结束日，不能一次跨越多个日期并跳过每日状态。

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
| `POST` | `/api/paper/{id}/run-day` | 推进一个交易日 |
| `POST` | `/api/paper/{id}/replay` | 信号模拟回放或单日 LEAN 运行 |
| `GET` | `/api/paper/{id}/reports` | 每日报告列表 |

Paper 仍是研究和运维验证工具，不等同于实盘交易系统。
