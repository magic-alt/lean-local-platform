# Insights、因子与高级研究能力

本页汇总不属于基础回测链路的高级能力。部分能力以 API 为主，成熟度和质量门禁可能低于 A 股日线回测主链路。

## Insights

Insights 从 LEAN 所有的日线数据和可选历史回测生成结构化研究报告。支持 equity、crypto、crypto future 和 future，并可配置 DeepSeek、Zhipu、Kimi、OpenAI 或 Anthropic。

模型只生成叙述和候选信号；服务端规则拥有最终风险门禁。缺失数据、不支持的空头、无效价格计划或缺少证据都会使信号不可执行。

配置相应 Provider API Key 后，通过：

```text
GET  /api/insights/capabilities
GET  /api/insights
POST /api/insights
GET  /api/insights/{report_id}
```

API Key 不会通过 capabilities 返回，也不会写入 Settings 或报告。

## A 股科技日报

A 股科技日报是观察池内的每日截面研究，不是全市场自动选股，也不会创建 Paper 信号或订单。行情与复权来自 TuShare Pro，个股最新收盘价由东方财富交叉核验；板块优先使用 TuShare 的 DC/THS 指数，东方财富板块 K 线只作为显式降级。公告来自交易所，政策证据来自政府官方网站；财务与因子只读取分析日当时已经公告或生效的 PIT 记录。

配置 Insights Provider 后，默认在现有观察池上运行六阶段结构化 Agent：

1. 技术趋势 Agent 给出每只股票 1、5、20 个交易日的上涨、震荡、下跌概率。
2. PIT 基本面 Agent 评价质量、覆盖度、催化和风险，不允许使用分析日之后披露的数据。
3. 多头和空头 Agent 并行审阅前两阶段的事实。
4. 风险 Agent 检查公告、数据完整性、回撤等约束。
5. 最终选择 Agent 输出 Top 10 排名，其中 Top 5 是优先观察层。

每个阶段持久化 Provider、模型、Prompt 版本、输入指纹、引用 fact ID、结构化输出、耗时、用量和错误分类，不保存模型思维链。服务端硬风险门禁拥有最终否决权。模型未配置或单阶段失败时页面会明确显示 `deterministic` / `degraded`，并保留规则报告；技术 Agent 的降级概率不会进入模型效果统计。API Key 仅从 API、worker 和 beat 的运行环境读取。

预测在第 1、5、20 个实际 A 股交易日成熟，以前复权个股收盘价计算收益、以板块映射指数计算超额收益，并统计方向命中率、三分类 Brier 分数、平均收益和 Top 5 lift。评测从预测创建后开始，不反向伪造历史预测；样本少于 20 条时页面标记为样本不足。工作日 17:30 生成日报，18:45 刷新已成熟预测，也可以从页面手动触发。

Watchlist 项目必须先通过 TuShare 验证为在市 A 股，名称由系统数据填写。报告会保留来源冲突、降级和免责声明。

它与回测中的“A 股指数技术面与基本面分析”边界不同：科技日报面向可编辑科技股观察池，在单一分析日生成跨股票的模型概率、辩论、风险审核和排名；回测分析面向指定指数及其 PIT 成分股，按策略规则在完整历史区间逐日模拟交易，并计入费用、滑点、仓位和样本外结果。日报适合形成当日研究假设，回测用于验证规则在历史执行链路中的表现，两者的分数和收益不能直接互换。

```text
GET  /api/insights/ashare-tech/capabilities
POST /api/insights/ashare-tech/model-diagnostics
GET  /api/insights/ashare-tech/reports/{report_id}/agent-runs
GET  /api/insights/ashare-tech/agent-runs/{run_id}
GET  /api/insights/ashare-tech/evaluations
GET  /api/insights/ashare-tech/evaluations/summary
POST /api/insights/ashare-tech/evaluations/refresh
```

## 因子研究

因子研究模板支持：

- 查询可用引擎；
- 计算单因子值或因子矩阵；
- 评价 IC、Rank IC、分层收益等结果；
- 对多个因子或股票池批量评价；
- 使用 winsor z-score、稳健 z-score、rank、min-max 等模板做截面标准化；
- 按行业等分类去均值，并对市值、beta 等数值暴露做回归中性化；
- 保存标准化的评价结果、数据范围和数据指纹。

```text
POST /api/factors/values
POST /api/research/runs
POST /api/data/query
```

财务和指数成员必须使用 PIT 接口；当前值不能替代历史值。

## 组合优化

`POST /api/portfolio-optimizations/preview` 校验组合输入，`POST /api/portfolio-optimizations` 计算并固化组合权重。输入必须来自已准入成功回测，且币种、频率与至少 60 个重叠净值点一致；输出仍需通过持仓上限、流动性、交易规则和回测验证。

## 期货和可转债

期货和可转债的写入、规则、映射和费用维护接口仍属于数据管理。读取与分析统一从 Data Query 和 Research Run 进入。期货连续合约研究只输出主力映射、原始/调整价格、换月价差和展期收益，不输出订单、持仓、保证金、费用、滑点或交易盈亏。

需要验证交易成本和执行影响时，应将 Research Run 的 DataScope 显式交给 Backtest，再配置策略、费用、滑点和资金规则。

## Level 3+ 工作流

Level 3+ 路由提供 universe coverage、pipeline run、alert acknowledge/resolve 和 workflow verification。它们用于平台级管线和运维集成，完整端点见 [API 索引](api-reference.md)。

## 使用原则

- 先检查 capabilities、数据覆盖和质量状态。
- 高级输出必须保存输入日期、来源、参数和版本。
- 模型输出和因子排名不能绕过服务端风险规则。
- 所有 Paper handoff 都必须是用户显式操作。
- 未完成验收的跨资产能力必须在报告中标注限制。
