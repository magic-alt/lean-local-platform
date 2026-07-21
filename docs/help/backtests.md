# 单次与批量回测

LEAN 是唯一正式回测执行器。单次回测验证策略、数据和执行规则；批量回测复用同一可信链路，把项目、股票、参数或时间窗口展开成可恢复实验。

![Backtests 的单次回测配置和批量工作台](assets/backtest-workbench.png)

## 单次回测步骤

1. 在 Projects 创建或克隆一个项目。
2. 在 Backtests 选择 Project、标的、市场、日期、资金和基准。
3. 先运行 preflight，修复数据、基准、项目或参数问题。
4. 提交任务后在 Tasks 和 Run Detail 查看队列、日志和状态。
5. 成功后检查指标、图表、订单、持仓、Validation、Admission 和 Fingerprint。
6. 需要归档时从 Reports 生成统一报告。

New Backtest 将 Project/名称、标的与行情、周期与执行、策略参数分组。Fee、Slippage 和 Data Source 保持在执行配置中，Docker Image 收入 Runtime environment；折叠高级区不改变默认镜像或提交 payload。

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

## 回测请求示例

```bash
curl -X POST http://127.0.0.1:8000/api/backtests/preflight \
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

### 动态 PIT 组合

一个多资产 LEAN 运行共享资金，在每个调仓日按历史有效成分调整。它适合回答“当时可知成分组成的组合会怎样”，不能和独立单股票排名混为一谈。

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

## 失败、重试和导出

- 个别子任务失败不会立即终止整个批次。
- 批次可能是 `success`、`partial`、`failed` 或 `cancelled`。
- `POST /api/experiment-batches/{id}/retry-failed` 只重试失败项，不重复成功项。
- 取消会停止活动项目并取消未派发项目。
- `GET /api/experiment-batches/{id}/export.csv` 导出子任务及指标。

重启后协调任务从数据库恢复批次，不依赖浏览器页面保持打开。

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
