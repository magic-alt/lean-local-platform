# Git 修复摘要记录

本文档用于记录每次 git 修复提交的摘要。每次提交后按时间倒序追加一节，包含日期、commit、标题和修复要点。

## 2026-07-05 - 本次提交 - Fix Level 3 paper stabilization P1 gaps

- 删除 A股策略模板中的常数 benchmark fallback，benchmark 缺失时回测 hard fail。
- 打通 Reports API 与 backtest report/result/stored_objects，并在前端 Reports 页显示 result 与 stored object 状态。
- 增加 Parquet host path 到当前 PARQUET_DIR 的可见路径重映射，DuckDB 查询和一致性报告统一使用解析后路径。
- 补齐 Paper daily report 的收益、超额、fingerprint、data source、warnings、position weights 和拒单原因字段。
- 增加 PIT API 的 000300/399300/CSI300 到 CSI300 映射。
- 增加 A股 reference data coverage API，显式暴露公司行动、退市、ST、停牌和 PIT 覆盖缺口。
- 增加对应后端与前端测试覆盖。

## 2026-07-05 - 8f2a446 - Fix Level 3 backtest P0 gates

- 修复 worker 启动 LEAN Docker 的 host path 挂载问题。
- 修复 A股 readiness 误判、2023 calendar fallback、空 LEAN Data 自动恢复。
- 增加 backtest QA critical gate。
- 补齐 run fingerprint 字段和失败路径落库。
- 支持 Paper 多标的和组合约束拒单原因。
- 增加对应测试覆盖。
