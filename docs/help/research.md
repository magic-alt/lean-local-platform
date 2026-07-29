# 研究工作台

Research 用于数据探索、股票池还原、因子评价和跨资产统计分析。它不模拟订单、持仓、资金、费用、滑点或交易盈亏；这些内容统一由 Backtest 验证。

## 统一流程

1. 选择标准模板。
2. 配置共同的 `DataScope`：资产、标的/股票池/品种、时间、价格口径和数据来源。
3. 执行数据预检，确认覆盖、来源认证、scope hash 和 data fingerprint。
4. 运行并固化 Research Run。
5. 查看表格、警告和导出，或把同一 DataScope 显式交给 Backtest。

当前标准模板包括市场探索、数据质量、PIT 股票池、因子评价、可转债双低筛选和期货连续合约研究。事件研究、回测敏感度和组合风险等开放式工作仍放在 Notebook。

## Run 与 Workspace

| 概念 | 用途 | 生命周期 |
| --- | --- | --- |
| Research Run | 固定输入、数据指纹和结果的标准分析 | 运行、重试、取消、导出、删除 |
| Notebook Workspace | 交互式探索和自定义代码 | 创建、打开、停止、重启、删除 |

Workspace 不是批次，也不是 Run 的别名。每个 Workspace 必须绑定由 Research Run 生成的内容寻址快照。容器禁用网络，不提供数据库或数据商凭据，并只读挂载 `/Lean/Snapshots`、`/Lean/Data` 和 `/Lean/Parquet`。

Notebook 中使用快照：

```python
from lean_research import ResearchData

data = ResearchData.open("snapshot-sha256")
history = data.history()
```

## 共享数据契约

```json
{
  "asset": {
    "assetClass": "equity",
    "market": "china",
    "venue": "china",
    "resolution": "daily",
    "dataType": "trade"
  },
  "selection": {"type": "symbols", "values": ["000001.SZ"]},
  "time": {
    "startDate": "2025-01-01",
    "endDate": "2025-12-31",
    "asOfDate": "2025-12-31"
  },
  "price": {"adjust": "raw"},
  "provider": {
    "source": "tushare",
    "mode": "strict",
    "allowResearchSource": false
  }
}
```

`POST /api/data/resolve` 只读解析范围和来源；`POST /api/data/query` 执行最多 1000 行的有界查询。Research 预检和 Backtest handoff 使用同一归一化范围和指纹输入。

## 主要接口

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `GET` | `/api/research/templates` | 标准模板 |
| `POST` | `/api/research/runs/preview` | 数据预检 |
| `GET/POST` | `/api/research/runs` | 运行历史或创建运行 |
| `GET/DELETE` | `/api/research/runs/{id}` | 运行详情或删除 |
| `POST` | `/api/research/runs/{id}/cancel` | 取消 |
| `POST` | `/api/research/runs/{id}/retry` | 以相同输入重试 |
| `GET` | `/api/research/runs/{id}/export.csv` | 导出预览表 |
| `GET` | `/api/research/runs/{id}/backtest-draft` | 创建显式回测交接草稿 |
| `POST` | `/api/research/workspaces/snapshots` | 创建冻结快照 |
| `GET/POST` | `/api/research/workspaces` | Workspace 列表或创建 |

从 Research 转到 Backtest 后仍必须选择策略项目并重新执行 preflight。Research 不推断交易执行参数。
