# Git 修复摘要记录

本文档用于记录每次 git 修复提交的摘要。每次提交后按时间倒序追加一节，包含日期、commit、标题和修复要点。

## 2026-07-06 - 本次提交 - Stabilize Level 3 P1 paper and data paths

- 统一 API/worker 的 Parquet volume 配置，新增容器可见 `LEAN_PARQUET_DIR=/workspace/parquet`，默认映射本地 `../Data/parquet`。
- 将 Parquet dataset/file 入库路径改为 `parquet/...` 逻辑路径，避免保存容器不可见 host-only 绝对路径。
- 补齐 Paper daily report `schemaVersion` 和 API 顶层 camelCase 摘要字段，保持前端/API 可读。
- 在前端 Paper 页增加每日 replay report 查看入口，展示 NAV、benchmark、QA、拒单原因、warnings 和 fingerprint。
- 增加固定 Paper Replay 验收场景，同一 replay 中同时验证成交、blacklist、observe_only、ST block 和 max_positions 拒单。
- 修正 CSI300 research import 脚本文案，明确导入 MySQL canonical 表和可重建 LEAN cache。
- 增加 `adata` 后端依赖，并修复 CSI300 PIT public importer 对 `csindex-cache:` 本地缓存 manifest 的读取。
- 调整 free sample CLI 退出码，主 provider 成功时将 AData/Baostock 无数据记录为覆盖缺口而非核心导入失败。
- 修复 CSI300 PIT public importer 对 cached manifest 的 `manual_events` 和 `coverage_start` 兼容。
- 修复 CSIndex PIT 导入脚本在 MySQL 下派生表缺少 alias 的问题，cached PIT 写入可完成。

## 2026-07-05 - 本次提交 - Fix Level 3 runtime P0 regressions

- 修复 `init_db` 旧 schema 迁移顺序，先补 `data_assets.status` 再创建状态索引，恢复 API/import/Parquet/QA 启动链路。
- 增加 A股 benchmark 覆盖 hard fail，`benchmarkSymbol` 缺失或窗口内无行情时拒绝创建/执行 backtest。
- 在 worker 执行阶段重复校验 benchmark，防止旧任务绕过创建阶段 gate。
- 补齐创建/失败路径 run fingerprint 的本地 LEAN zip、factor、map hash 和 benchmark cache 状态。
- 增加旧 schema 迁移、benchmark missing、created fingerprint hash 的回归测试覆盖。
- 验证 API A/B 回测、free import、Parquet rebuild、多源 QA、后端全量测试、LEAN Docker 集成测试和前端 build。

## 2026-07-05 - 本次提交 - Fix efficiency and scalability P2 gaps

- 增加前端 Vite manual chunks，拆分 React、Ant Design、ECharts、zrender 和 Monaco 包。
- 增加数据源 provider availability 诊断，检查本地依赖、必需环境变量，并明确不依赖网络探测。
- 增加 stored_objects 查询分页、namespace/key 过滤和相关数据库索引。
- 增加 Reports API 分页、状态/run/source 过滤和相关数据库索引，默认数组响应保持兼容。
- 增加 data_assets lifecycle 字段，新资产写入后保留历史记录并标记旧记录为 superseded。
- 增加对应后端测试覆盖。

## 2026-07-05 - cd3a714 - Fix Level 3 paper stabilization P1 gaps

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
