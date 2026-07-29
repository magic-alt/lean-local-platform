# 单次与批量回测

LEAN 是唯一正式回测执行器。Backtests 页现在只有一个 New Backtest 入口，由
`Run configuration` 中的运行范围决定提交单次还是批量；两者最终都进入相同的项目快照、
数据修复、preflight、LEAN worker、结果解析和可信度校验链路。

![Backtests 的单次回测配置和批量工作台](assets/backtest-workbench.png)

## 统一 New Backtest 入口

先使用页面右上角的运行范围配置：

| 运行范围 | 配置含义 | 提交 API | 适用场景 |
| --- | --- | --- | --- |
| 单次回测 | 一个项目、一个标的、一个连续窗口 | `POST /api/backtests/preflight` 后 `POST /api/backtests` | 策略冒烟、基线、逐笔检查 |
| 批量回测 | 项目、标的/PIT 股票池、窗口和参数的展开结果 | `POST /api/experiment-batches/preview` 后 `POST /api/experiment-batches` | 横截面对比、滚动稳定性、动态组合 |

运行范围本身也是配置，不靠项目名称或模板名称猜测。使用案例时，单股独立案例会自动切到
单次回测；带股票池、滚动窗口、动态组合或批量标签的案例会切到批量回测，仍可手动修改。

批量配置中的 `market`、`benchmarkSymbol`、`source`、`feeModel`、
`slippageModel` 和 `allowResearchSource` 会复制到每个展开后的子请求。子请求不会绕过单次
回测使用的 `prepare_backtest_request` 和数据质量门禁。因此，同一个项目从单次改成批量时，
执行口径不会因为入口不同而变化。

## 单次回测步骤

1. 在 Projects 创建或克隆一个项目。
2. 在 Backtests 选择 Project、标的、市场、日期、资金和基准。
3. 先运行 preflight，修复数据、基准、项目或参数问题。
4. 提交任务后在 Tasks 和 Run Detail 查看队列、日志和状态。
5. 成功后检查指标、图表、订单、持仓、Validation、Admission 和 Fingerprint。
6. 需要寻优时点击详情页的 **Optimize**；Optimization Center 会从服务端继承项目、DataScope、执行假设和模板参数，并保留 `sourceBacktestRunId` 血缘。
7. 需要归档时从 Reports 生成统一报告。

New Backtest 将 Project/名称、标的与行情、周期与执行、策略参数分组。Fee、Slippage 和
Data Source 保持在执行配置中，Docker Image 收入 Runtime environment；折叠高级区不改变
默认镜像或提交 payload。未认证或研究数据必须显式勾选 Research data override；此类运行
不得成为 LEAN Paper 的可信输入。

`projectId` 对 create 和 preflight 都是必填字段。worker 执行提交时复制的不可变项目快照，不使用默认 demo 算法。

## Preflight 检查

`POST /api/backtests/preflight` 不启动 LEAN 容器，主要检查：

- 项目存在、语言和入口文件有效；
- 日期、资金、参数和模板 Schema 合法；
- 标的、市场、Venue、Resolution 和 Data Type 组合可支持；
- 本地行情覆盖回测区间；
- A 股交易日历、真实基准、复权和交易状态满足门禁；
- PIT 股票池在目标日期存在历史覆盖。

preflight 失败应先修复根因。不要通过删除质量检查或使用未来数据绕过。

## 市场日历和数据覆盖

覆盖检查必须区分业务数据与 LEAN 自身的技术参考数据：

| 数据角色 | 使用的日历 | 例子 | 通过条件 |
| --- | --- | --- | --- |
| A 股/港股回测标的 | 请求的 `market/venue` | `000001/china`、`00700/hongkong` | 覆盖到对应市场在窗口内最后一个交易日 |
| A 股/港股业务基准 | `benchmarkMarket`，默认跟随请求市场 | `000300/china`、`02800/hongkong` | 真实行情存在，并覆盖该基准市场的预期交易日 |
| 其他 LEAN 标的 | 请求的 `market/venue` 和本地 LEAN 数据契约 | `AAPL/usa` | 通过对应资产、市场、分辨率和数据类型校验 |
| ResultsAnalyzer 技术参考 | 固定 `usa` | `SPY` | 覆盖到窗口内最后一个美股交易日 |

ResultsAnalyzer 的 SPY 不是把 A 股或港股策略改成按美股日历运行。它是 LEAN 结果分析器的
独立依赖；A 股标的和 `000300` 仍读取 `trade_calendar.market=china`，港股标的和 `02800`
仍读取 `trade_calendar.market=hongkong`。

例如请求结束日为 2026-07-25（周六）时：

- SPY 技术参考的 `expectedLastTradeDate` 是 2026-07-24；
- A 股和港股标的分别以各自日历在 2026-07-25 之前的最后一个开市日为准；
- 任一角色缺少自己市场的最后预期交易日，都应独立失败，不能用另一市场的行情证明覆盖。

SPY 刷新结果会返回 `market`、`requestedEndDate`、`expectedLastTradeDate` 和 `coverage`。
这几个字段用于判断是合法的周末/休市日，还是实际缺少交易日数据。

## 回测请求示例

```bash
curl -X POST http://127.0.0.1:8000/api/backtests/preflight \
  -H "Authorization: Bearer $(cat web/runtime/secrets/api_token)" \
  -H 'Content-Type: application/json' \
  -d '{
    "projectId":"my-ema-project",
    "symbol":"000001",
    "assetClass":"equity",
    "market":"china",
    "venue":"china",
    "resolution":"daily",
    "dataType":"trade",
    "start":"2024-01-02",
    "end":"2024-12-31",
    "cash":300000,
    "parameters":{"fast":10,"slow":30,"benchmarkSymbol":"000300"}
  }'
```

通过后将路径改为 `/api/backtests` 创建运行。

## 状态和取消

典型状态链为 `created/queued → running → success|failed|cancelled`。排队不等于容器已经启动：数据库调度租约会限制同时运行的 LEAN 数量。

取消通过 `POST /api/backtests/{run_id}/cancel` 进入统一服务链路，负责撤销 Celery、停止活动容器并更新数据库状态。不要直接删除容器来代替取消。

## 批量回测模式

### 独立矩阵

按“项目 × 股票 × 时间窗口”展开。每个单元有独立资金、LEAN 运行和结果，适合：

- 单策略覆盖股票池；
- 单股票比较多个策略；
- 多策略 × 多股票矩阵；
- 在多个窗口检查稳定性。

它回答“每个单元独立表现如何”，不能解释共享资金组合的真实表现。

### 滚动窗口

在相同项目和标的上生成多个时间窗口，观察收益、回撤、交易数和参数稳定性。窗口必须明确且不能使用未来窗口帮助过去决策。

### Walk-forward

`mode=walk_forward` 将每个 fold 严格拆成连续且互斥的三个阶段：

- `train` 只用于候选生成；
- `validation` 是唯一允许参与参数选择的阶段；
- `oos` 只评价已经选定的参数，不参与选择。

`testYears` 定义 validation + OOS 的总评价长度，默认各占一半；可用
`validationMonths` 调整切分，但必须给 OOS 留出非空窗口。每个 fold 和 phase 都写入
稳定 fingerprint，便于检查窗口边界、角色和重跑输入是否漂移。

### 动态 PIT 组合

一个多资产 LEAN 运行共享资金，在每个调仓日按历史有效成分调整。它适合回答“当时可知成分组成的组合会怎样”，不能和独立单股票排名混为一谈。

“A股指数技术面与基本面选股”案例在该模式下支持沪深300、中证500、中证1000和科创50。
它在每个调仓日逐股判断持续上涨、持续下跌或横盘震荡，技术面使用均线、20日收益、
RSI 和波动率评分，基本面使用公告后才可见的 ROE、增长、负债、估值和盈利字段评分。
默认只有持续上涨、技术分不低于70、基本面分不低于60且基本面覆盖不少于2项的股票
才进入候选，再按综合分选择 Top-N。基本面缺失不会自动通过。
运行前应在 Data 同步目标窗口的 `daily_basic`、`income`、`balancesheet` 和
`fina_indicator`；批次预览会在没有任何时点基本面时给出可操作的拒绝原因。

## 批次预览和上限

提交前调用 `POST /api/experiment-batches/preview`。页面显示展开工作单元数、`maxBatchRuns` 上限、有效并发、PIT 解析结果和警告。

批次核心区直接显示项目、标的来源、日期和资金；Optimization 的原始参数网格 JSON 只在高级优化设置中显示。先点“预览展开”，确认工作单元数量后再排队。

```json
{
  "kind": "backtest",
  "mode": "independent",
  "projectIds": ["project-a", "project-b"],
  "symbols": ["000001", "600519"],
  "start": "2022-01-01",
  "end": "2024-12-31"
}
```

股票池模式使用 `symbolSource=universe` 和 `universeCode=CSI300` 等配置。动态组合使用 `mode=dynamic_universe`。

批量任务只维护一个小的派发窗口，不会绕过 Settings 的 `maxConcurrentJobs`。

## 案例模板检查范围

Backtests 案例目录当前包含以下十一个案例。目录回归测试会逐项确认模板存在、生成的 Python
策略可编译，并保留真实基准 hard fail；执行时则由每个子回测的 preflight 检查实际数据。

| 案例 | 模板 | 默认运行范围 | 额外数据要求 |
| --- | --- | --- | --- |
| 单股买入持有基准 | `buy_hold` | 单次 | 单股、同市场真实基准 |
| 单股均线趋势 | `ema_cross` | 单次 | 指标 warm-up 行情 |
| 单股 RSI 均值回归 | `rsi_reversion` | 单次 | 指标 warm-up 行情 |
| 单股 Donchian 突破 | `donchian_breakout` | 单次 | 滚动窗口行情 |
| 单策略 × 股票池 | `ema_cross` | 批量独立矩阵 | 开始日 PIT 成分 |
| 单股票 × 多策略 | `ema_cross` 起始项目 | 批量独立矩阵 | 至少两个项目才形成多策略比较 |
| 多策略 × 多股票矩阵 | `ema_cross` 起始项目 | 批量独立矩阵 | 多项目和 PIT/显式股票列表 |
| 滚动窗口稳定性 | `ema_cross` | 批量滚动 | 每个窗口的数据覆盖 |
| 沪深300动态等权组合 | `dynamic_universe` | 批量动态组合 | 窗口内 PIT 成分调度 |
| 沪深300动量 Top-N | `dynamic_universe` | 批量动态组合 | PIT 成分、动量 warm-up |
| A股指数技术面与基本面选股 | `ashare_index_screening` | 研究型期末筛选 | 四选一指数 PIT、逐股行情、公告时点基本面、匹配指数基准 |

“模板可编译”不等于“任意日期都可运行”。例如未来结束日、未同步股票、缺少 PIT 成分或基准
缺口仍会由 preflight 拒绝。这样可以区分模板缺陷、配置缺陷和数据缺陷。

`ashare_index_screening` 使用所选区间形成均线、RSI、收益和波动率，在最后有效交易日一次性
评估当时股票池。全部达标股票进入“合格”层，综合分最高的 `topN` 股票额外标记为“精选”；
该模板为 `researchOnly`，不会提交订单、构建持仓或进入策略准入。

普通多标的交易回测的价格图提供证券选择器。`chart-data?symbol=000792` 只返回盐湖股份的
K 线和该股票的订单标记，订单、成交和持仓中的 A 股代码保持六位并同时显示证券名称。

## 失败、重试和导出

- 个别子任务失败不会立即终止整个批次。
- 批次可能是 `success`、`partial`、`failed` 或 `cancelled`。
- `POST /api/experiment-batches/{id}/retry-failed` 只重试失败项，不重复成功项。
- 取消会停止活动项目并取消未派发项目。
- `POST /api/experiment-batches/{id}/restart` 只恢复已取消批次的未完成项，保留已成功子项和原运行关联。
- `GET /api/experiment-batches/{id}/export.csv` 导出子任务及指标。

重启后协调任务从数据库恢复批次，不依赖浏览器页面保持打开。

## SPY 覆盖报错排障

看到 `lean_results_analyzer_spy_refresh...` 时按以下顺序检查：

1. 读取错误中的 `market`。ResultsAnalyzer SPY 应始终是 `usa`，不能据此推断策略市场。
2. 比较 `requestedEnd` 和 `expectedLastTradeDate`。周末或美股休市日允许后者早于自然结束日。
3. 比较 `coverage.lastDate`。它必须不早于 `expectedLastTradeDate`；若更早，说明刷新结果确实缺失。
4. 再检查回测 validation 中标的和业务基准的 `endCoverage`。A 股看 `china`，港股看
   `hongkong`，两者与 SPY 技术参考分别判定。
5. 若单次可运行而批量失败，导出批次 CSV，检查失败子项是否继承了相同的市场、来源、基准和
   Research data override；统一入口生成的新批次会保留这些字段。

旧错误：

```text
LEAN results analyzer SPY refresh did not cover the requested backtest window:
{'firstDate':'1993-01-29','lastDate':'2026-07-24',...}
```

若请求结束日是 2026-07-25，这属于自然日与最后交易日混淆。修复后的判定应显示
`market=usa`、`requestedEnd=2026-07-25`、`expectedLastTradeDate=2026-07-24`，并通过
SPY 技术参考检查；A 股或港股业务数据仍需分别通过自己的日历门禁。

## 结果可信度

至少同时检查：

| 维度 | 重点 |
| --- | --- |
| Performance | 收益、Sharpe、Calmar、最大回撤、交易数 |
| Execution | 订单、成交、费用、滑点、持仓和拒单 |
| Data | 行情、基准、交易状态、日期覆盖和质量报告 |
| Reproducibility | 项目快照、参数、镜像、数据版本和 fingerprint |
| Admission | 基线、样本集、门禁、评价状态和 Paper 资格 |

完整响应和产物格式见 [Backtest Result Format](../backtest_result_format.md)。
