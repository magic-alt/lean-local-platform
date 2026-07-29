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

A 股科技报告使用规则引擎计算指标、分类和风险门禁，可选 LLM 只能为已有 fact ID 添加说明。它不会创建 Paper 信号或订单。

Watchlist 项目必须先通过 TuShare 验证为在市 A 股，名称由系统数据填写。报告会保留来源冲突、降级和免责声明。

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

`POST /api/portfolios/optimize` 提供组合权重计算。输入收益/风险数据必须明确日期和成分口径，输出权重仍需通过持仓上限、流动性、交易规则和回测验证。

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
