# Optimization Center

Optimization Center 将参数寻优、运行历史、组合权重和结果比较放在同一个工作区。所有策略候选都展开为标准 `backtest_runs`，因此与单次回测共享项目快照、数据 preflight、调度、取消、结果解析、验证和指纹链路。

旧 `/api/optimize` 独立 worker 和 `/api/portfolios/optimize` 一次性计算接口已移除。

## 推荐流程

Research、Backtest 和 Optimization 是可衔接但不强制的引导流程：

1. Research Run 固化嵌套 `DataScope`、`scopeHash` 和 `dataFingerprint`。
2. “转回测”从服务端读取 handoff draft；单标的进入单次回测，多标的或股票池进入批量回测。
3. Backtest 重新选择策略和执行假设，并验证 Research 数据指纹未漂移。
4. 成功回测可以从详情页进入 Optimization；服务端再次校验项目与数据指纹。
5. Optimization 的每个候选都是标准子回测。需要组合权重时，只能从已准入的成功回测中选择。

这些阶段也可以独立进入。血缘可通过 `GET /api/lineage/{resource_type}/{resource_id}` 查询。

## Create Optimization

请求使用一个稳定契约：

```json
{
  "name": "CSI300 EMA robustness",
  "mode": "universe_robust",
  "projectIds": ["ema-project"],
  "dataScope": {
    "asset": {
      "assetClass": "equity",
      "market": "china",
      "venue": "china",
      "resolution": "daily",
      "dataType": "trade"
    },
    "selection": {"type": "universe", "values": ["CSI300"]},
    "time": {"startDate": "2020-01-01", "endDate": "2025-12-31"},
    "price": {"adjust": "raw"},
    "provider": {
      "source": "tushare",
      "mode": "strict",
      "allowResearchSource": false
    }
  },
  "execution": {
    "cash": 300000,
    "benchmarkSymbol": "000300",
    "feeModel": "default",
    "slippageModel": "default",
    "dockerImage": "quantconnect/lean:latest"
  },
  "fixedParametersByProject": {
    "ema-project": {"fast": 10, "slow": 60}
  },
  "parameterGrids": {
    "ema-project": {"fast": [5, 10, 20], "slow": [30, 60, 120]}
  },
  "objective": "sharpe",
  "minCoverage": 0.8,
  "maxCandidates": 200
}
```

参数控件由项目模板 Schema 动态生成。网格支持逗号枚举，也支持 `start:end:step` 范围输入。点击“预览展开”可分别看到参数候选数和最终标准回测工作单元数。

## 模式

| 模式 | 展开与选择规则 |
| --- | --- |
| `single_symbol_grid` | 一个标的上比较参数组合 |
| `universe_robust` | 同一候选跨 PIT 股票池汇总覆盖率和指标分布 |
| `walk_forward` | validation 只用于选参，冻结后仅以 OOS 评价 |
| `multi_strategy` | 多项目各用自己的固定参数和参数网格 |

每次运行只能选择一个目标：`sharpe`、`return` 或 `drawdown`。收益和 Sharpe 取最大；回撤按绝对值取最小。低于 `minCoverage` 的候选不会成为最佳候选。

## Portfolio Builder

Portfolio Builder 不接受手工粘贴运行 ID。候选选择器只列出成功回测，并标明准入状态、账户币种、频率和净值点数。

服务端强制：

- 2–5 个唯一回测；
- 每个参数集已通过 strategy admission；
- 相同账户币种和数据频率；
- 至少 60 个重叠净值点；
- 权重步长能整除 1，候选不超过 100,000；
- 未定义 FX 归一化合同时禁止混合币种。

计算结果持久化到 `portfolio_optimization_runs`，保存输入指纹、约束、最优权重、指标、归一化净值曲线和回测血缘。归档不会删除证据。

## Compare Results

Optimization 比较以成功子回测的目标指标中位数排序，保留成功覆盖、最佳运行、参数敏感性和 Walk-forward fold 证据。

Backtest 比较只接受唯一、成功且已有解析结果的运行。不同币种时原始 NAV 不可比较，页面使用以 1 为起点的归一化曲线；不同频率会显示风险指标兼容性警告。

## 接口

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `POST` | `/api/optimizations/preview` | 校验契约并预览候选/工作单元 |
| `GET/POST` | `/api/optimizations` | 列表或创建优化 |
| `GET` | `/api/optimizations/{id}` | 运行、候选和子回测详情 |
| `POST` | `/api/optimizations/{id}/cancel` | 取消未完成子运行 |
| `POST` | `/api/optimizations/{id}/retry-failed` | 只重试失败项 |
| `POST` | `/api/optimizations/{id}/restart` | 重启已取消/跳过项 |
| `POST` | `/api/optimizations/{id}/archive` | 归档运行 |
| `GET` | `/api/optimizations/{id}/export.csv` | 导出候选证据 |
| `POST` | `/api/optimizations/compare` | 比较 2–10 个优化 |
| `GET` | `/api/portfolio-optimizations/candidates` | 可选回测 |
| `POST` | `/api/portfolio-optimizations/preview` | 校验组合输入 |
| `GET/POST` | `/api/portfolio-optimizations` | 历史或创建持久化组合运行 |

Optimization 的输出是研究与验证证据，不会自动修改项目参数或创建 Paper 部署。
