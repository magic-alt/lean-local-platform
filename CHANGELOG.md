# Git 修复摘要记录

本文档用于记录每次 git 修复提交的摘要。每次提交后按时间倒序追加一节，包含日期、commit、标题和修复要点。

## 2026-07-06 - 本次提交 - Close Level 3 P1 audit gaps

- 将 AKShare 公开参考数据导入错误持久化为 `ashare_reference_public_import` QA 报告，并在 reference coverage API 暴露 `warnings`/`referenceSources`，覆盖 `st_endpoint_unavailable`。
- 补齐 Paper reports API 顶层 `pendingSignals`、`rejectedOrders`、`rejectReasons`、benchmark 与 QA gate alias，保持前端/API 字段统一。
- 新增 `scripts/run_paper_replay_acceptance.py` 固定验收场景，创建同一 replay 中同时包含 fill 和 rejected 的 Paper session。
- 修正 run fingerprint dirty 判断，过滤运行产物类 untracked 噪声但保留源码类 untracked，并记录 raw git status hash。
- Backtest result summary 显式写入 Strategy/Benchmark/Excess Return，并在 Alpha/Beta 无法可靠计算时记录 benchmark metric status。
- 新增 `scripts/run_daily_pipeline.py` 日终流水线 CLI，串联 reference、multi-source QA、Parquet、benchmark coverage、Paper Replay 和 report summary。
- 增加对应后端回归测试；后端全量 pytest 与前端 build 均通过。
- 真实 MySQL 验证 Paper Replay acceptance：21 个交易日、1 笔成交、1 笔 `blacklisted` 拒单、21 份日报。

## 2026-07-06 - 本次提交 - Import public A-share reference data

- 新增 AKShare 公开参考数据导入脚本，写入退市证券、公司行动和停牌状态到 canonical MySQL 表。
- 增加 Eastmoney `stock_tfp_em` 停牌 fallback，并修复毫秒时间戳日期解析，避免停牌公开源断连时丢失覆盖。
- 补强 Tushare adapter：将 `nan`/`NaT` 视为空值，修复 dividend 空日期降级，并按证券名称推断 ST 标记。
- 实际导入 AKShare 退市 363 条、核心样本公司行动 59 条、2026-07-03 停牌 14 条；ST 实时端点仍记录为公开源可用性缺口。
- 验证 Parquet rebuild severity=ok，MySQL/DuckDB 行数一致，dataset/file 路径保持 `parquet/...` 逻辑路径。
- 验证 API app profile 在 Redis 6380/API 8002 下启动，health、Reports list/detail/file、Paper API 固定成交+拒单场景均通过。
- 增加公开参考数据导入和 Tushare 清洗的测试覆盖，后端全量 pytest 与前端 build 均通过。

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
