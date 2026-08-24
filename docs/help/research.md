# 研究工作台

Research 在平台内不再承载执行链路；平台仅保留 Artifact Contract v2 的导入与执行验证边界。

## 统一流程

1. 外部系统提交 `/api/research/imports/qlib`，上传 Artifact Contract v2 载荷。
2. 平台写入 `research_runs` 记录并完成签名、目标、指标映射。
3. 平台收到 `lean` 验证结果后，通过 `/api/research/runs/{run_id}/lean-validation` 完成执行边界闭环。

当前运行链路、Notebook Workspace、快照创建、策略预检由外部研究平台承载。

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

`POST /api/data/resolve` 仍用于 scope 解析；Research 导入与验证边界使用同一数据边界输入。

## 主要接口

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `POST` | `/api/research/imports/qlib` | Artifact Contract v2 导入 |
| `POST` | `/api/research/runs/{run_id}/lean-validation` | 记录 LEAN 验证 |
