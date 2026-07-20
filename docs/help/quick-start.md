# 快速开始

LEAN Local 是本地运行的量化研究、回测和模拟交易工作台。推荐顺序是：在 Data 完成建库或增量更新，在 Projects 从模板创建策略，在 Backtests 先做单次验证，再使用批量回测，最后进入 Optimization 和 Research。

大型任务提交前都会显示展开数量。任务实际并发由 Settings 的 `maxConcurrentJobs` 控制，批量上限由 `maxBatchRuns` 控制。

## 基本流程

1. Data：确认日线、复权因子、停牌、涨跌停、指数成分和交易日历可用。
2. Projects：从案例或策略模板创建可编辑副本。
3. Backtests：配置日期、资金、基准和数据来源，先运行少量样本。
4. Batch：确认股票池成分日期、展开数量和数据覆盖后排队。
5. Results：检查收益、回撤、Sharpe、交易记录、验证状态和原始产物。

所有A股生产回测必须使用真实基准和质量门禁；缺少数据时不会静默使用常数收益代替。
