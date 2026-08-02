# Actual-environment feature matrix — 2026-08-02

状态只表示本轮证据。`Web=存在` 表示路由/组件存在，不等于实际浏览器通过；内置浏览器不可用使视觉检查保持 `NOT_VERIFIED`。

| Domain | Feature | Web | API | Service | Database | Actual Data | Test Result | Evidence | Status | Gap |
| ------ | ------- | --- | --- | ------- | -------- | ----------- | ----------- | -------- | ------ | --- |
| Projects | 项目列表 | 存在 | `/api/projects` | projects | `projects` | 4 | authenticated GET | 4.9KB paged | PASS | 无 |
| Projects | 创建项目 | 存在 | POST projects | projects | `projects` | 未创建 | 代码/contract | 最小写入原则 | CODE_ONLY | 实际 journey 未测 |
| Projects | 打开/文件列表 | 存在 | project/file APIs | projects | `projects` | 4 projects | 只读检查 | route/component | PARTIAL | 浏览器未测 |
| Projects | 编辑/保存文件 | 存在 | PUT file | projects | project workspace | 未写 | 代码检查 | editor component | CODE_ONLY | 实际保存未测 |
| Projects | 克隆 | 存在 | clone API | projects | `projects` | 未克隆 | 代码检查 | 避免重复项目 | CODE_ONLY | 当前环境未测 |
| Projects | 删除保护 | 确认 UI | DELETE project | projects | projects/runs | 未删除 | 代码检查 | 禁止真实删除 | CODE_ONLY | 依赖保护未实测 |
| Strategies | 模板/示例实例化 | 存在 | examples/templates | projects | projects/files | 4 项目 | 文件检查 | templates/examples | PARTIAL | 未实例化 |
| Strategies | 参数配置 | 存在 | backtest request | validation | run JSON | 3 runs | raw/DB 检查 | 参数入 fingerprint | PASS | list payload 过大 |
| Strategies | 策略版本/快照 | 详情存在 | run/project APIs | fingerprint | runs/stored objects | 3 | 当前 artifact | git/project snapshot | PARTIAL | certificate 不完整 |
| Strategies | 历史运行关联 | 存在 | project/backtests | backtests | projects/runs | 3 | DB join | 全部 project FK 存在 | PASS | 无 |
| Data | 数据源列表/availability | 存在 | data providers | data catalog | provider tables | 多 provider | actual GET | ~20KB availability | PASS | metadata 与 executable 未统一 |
| Data | 数据目录/资产 | 存在 | data catalog/assets | catalog | instruments | 8,103 | SQL/API | equity 8095/index 8 | PARTIAL | 跨资产缺失 |
| Data | 数据预览 | 存在 | preview | market repository | daily bars | 19.2M | 600519 抽样 | 最新 OHLC 正常 | PASS | 浏览器图表未测 |
| Data | 股票主数据 | 存在 | securities | A-share repository | securities/instruments | 5,551+/8,095 | SQL | 名称 UTF-8 正常 | PASS | count 模型不同 |
| Data | 交易日历 | 存在 | calendar | calendar service | trade_calendar | 8,610+ | health/gate | end 2026-07-30 | PASS | 无 |
| Data | 指数 | 存在 | catalog/preview | data service | instruments/bars | 8 indices | SQL | 000300 instrument | PASS | 名称/venue 元数据简化 |
| Data | ETF | 页面能力 | catalog | provider | instruments | 独立 ETF 0 | SQL | name LIKE ETF 无样本 | FAIL | canonical 未建模 |
| Data | 期货 | 页面能力 | catalog/providers | futures service | future tables | 0 | SQL/raw archive | metadata archive ≠ bars | FAIL | 不可执行 |
| Data | 期权 | 页面能力 | catalog/providers | options service | option tables | 0 | SQL/raw archive | metadata archive ≠ bars | FAIL | 不可执行 |
| Data | 可转债 | 文档/研究 | catalog | data service | instruments/bars | 0 | SQL | 无 asset class | FAIL | 不可执行 |
| Data | 分钟/tick | 页面能力 | resolution | data service | minute/tick tables | 0 | SQL | 无 canonical rows | FAIL | 不可执行 |
| Data | 公司行动 | 间接 | quality/preflight | A-share repository | corporate_actions | 59 / 3 symbols | SQL sample | 000001 dividend | PARTIAL | 覆盖严重偏窄 |
| Data | 复权因子 | 间接 | preflight | cache/writer | adjustment factors | ~19.2M | DB inventory | 大规模存在 | PARTIAL | 本轮未全量 hash |
| Data | 停牌 | 间接 | preflight | status repository | market_trade_status | 大规模 | SQL sample | 002348 blocked | PASS | 多 source 行需治理 |
| Data | ST/退市 | 间接 | preflight | security master | securities/status | ST 557/delisted 366 | SQL | 实际样本 | PASS | 无 |
| Data | PIT universe | 存在 | PIT APIs | universe service | membership/watermarks | 299,610 | SQL | CSI300 1,225 | PASS | 部分 universe partial |
| Data | benchmark | 存在 | preflight/result | result analyzer | index bars/results | 000300 | raw/DB | run1 6.2461% | PASS | 当前只少数 index |
| Data | 数据同步 | 存在 | sync-runs | data_sync | sync/checkpoints | 历史多 run | GET/SQL | 近期有失败与成功 | PARTIAL | 维护不稳定 |
| Data | checkpoint/watermark | 存在 | data/health | maintenance | watermarks | 4 derived ready | SQL | equity/index Parquet/CH | PASS | 状态系统分裂 |
| Data | validation/quarantine | 存在 | quality/verifications | QA | QA/raw issues | 37 quarantined issues | GET/health | orphan raw=0 | PASS | 当前全量未重跑 |
| Data | certification | 存在 | health/preflight | source gate | parquet datasets | 2 certified | degraded→ok | 05:28 UTC 恢复 | PASS | version authority 分裂 |
| Data | Parquet/DuckDB | 存在 | parquet datasets | maintenance | parquet datasets/files | 17.7M + 44.7K | watermark/health | ready/certified | PASS | 未全量 consistency 重建 |
| Data | ClickHouse | 存在 | health | maintenance | derived watermark | equity 17.7M/index 5,960 | health/SQL | ready | PARTIAL | index scope 比 Parquet 小 |
| Data | CSV import | 存在 | import API | importer | import batches | 历史记录 | 代码检查 | 未执行写入 | CODE_ONLY | 实际导入未测 |
| Data | on-demand | 存在 | data request | demand worker | sync/request tables | worker 在线 | worker ping | 无审计下载 | PARTIAL | 未发请求 |
| Backtest | Preflight | 存在 | POST preflight | validation/source gate | read-only | existing project | actual 400 | structured fail-closed | PASS | 恢复后成功响应未留输出 |
| Backtest | 单次真实 LEAN | 存在 | create/run | worker/runner | runs/results | 3 existing | raw artifact | LEAN digest-pinned | PASS | 新 run 未创建 |
| Backtest | 批量回测 | 存在 | batches | experiment service | batches/items | 2×1 child | DB/API | dynamic PIT success | PARTIAL | 无矩阵证据 |
| Backtest | 状态/日志 | 存在 | status/logs | task service | runs/tasks | 3/9 | API/code | cursor backend | PARTIAL | UI 不用 cursor |
| Backtest | 取消 | 存在 | cancel | backtest service | runs/tasks | 未取消 | 代码/测试审查 | 禁止影响任务 | CODE_ONLY | 竞态未实测 |
| Backtest | 结果/图表 | 存在 | result | parser/report | results | 3 | raw/DB | run1 对账 | PASS | 浏览器图表未测 |
| Backtest | 订单/成交/持仓 | 存在 | result | parser | result JSON | 134/134/10 | raw/DB/API | run1 | PASS | UI 未点击 |
| Backtest | 指标/benchmark/excess | 存在 | result | analyzer | results | run1 完整 | 四方对账 | -9.625/6.246/-15.871% | PASS | 无 |
| Backtest | artifact/report | 存在 | artifact/reports | object store/report | stored_objects/reports | 3 reports | hash抽样 | raw object hash 匹配 | PARTIAL | manifest hash 不全 |
| Backtest | version/fingerprint | 存在 | detail | fingerprint | runs | 3 | SQL | input/canonical hash | PARTIAL | image/cache hash null |
| Backtest | 最终数据 gate | trust panel | detail | worker validation | runs | 异常 run 1 | SQL | success + critical | FAIL | Critical TOCTOU |
| Backtest | 失败详情 | 存在 | errors/detail | error mapping | runs/tasks | 历史失败少 | API errors | structured error | PARTIAL | current failure journey 未测 |
| Backtest | 历史筛选/分页 | 存在 | list | backtests | runs | 3 | API | paged envelope | PARTIAL | 23.3MB payload |
| Research | Research run | 存在 | `/api/research/runs` | research service | research_runs | 3 | GET/SQL | 1 success/2 stale running | FAIL | 状态不收敛 |
| Research | Workspace/Jupyter | 存在 | workspaces | runner | workspace rows/files | 无当前活动证据 | 代码检查 | restricted runner path | CODE_ONLY | 未启动 |
| Research | Factor evaluation | 存在 | research templates | research service | factors/values | ~8M values | DB inventory | 当前 run 未专项验证 | PARTIAL | UI 未测 |
| Experiment | Optimization | 存在 | optimizations | experiment service | batches/experiments | 0 | actual GET | count=0 | NOT_VERIFIED | 当前无资源 |
| Experiment | 参数网格 | 存在 | batch preview/create | batch service | batch/items | 0 current | 历史文件仅参考 | 未造数 | NOT_VERIFIED | 无 3×3 当前证据 |
| Experiment | 多标的/多策略 | 存在 | batches | batch service | batches/items | 2 single-child | DB | dynamic universe | PARTIAL | 无 multi-strategy |
| Experiment | rolling | 存在 | batch mode | batch service | batch/items | 0 current | 代码/历史证据 | 非当前事实 | CODE_ONLY | 无实际记录 |
| Experiment | Walk-Forward | 存在 | WF APIs | WF service | WF runs/windows | 1 run/2 folds | SQL | 三段边界 | FAIL | 父资源断裂 |
| Experiment | dynamic PIT | 存在 | batches | universe service | batches/membership | 2 batches | DB | mode dynamic_universe | PASS | child 各 1 |
| Experiment | retry/cancel/restart | 存在 | action APIs | batch service | batches/items | 无当前动作 | 代码审查 | 未写入 | CODE_ONLY | 实际幂等未测 |
| Experiment | CSV/ranking/heatmap | 存在 | export/result | aggregator | batch results | 无矩阵 | 代码检查 | 当前不可验证 | CODE_ONLY | 无数据 |
| Experiment | Train/Validation/OOS | 存在 | WF detail | WF service | windows | 2 folds | SQL | 时间不重叠 | PARTIAL | selection/OOS lineage 断裂 |
| Paper | 旧 Paper Session | 无主导航 | legacy compatibility | paper service | paper_sessions | 0 | SQL | jobs orphan | FAIL | 边界清理不完整 |
| Paper | Paper Account 列表 | 存在 | accounts | paper_accounts | paper_accounts | 0 | actual GET | count=0 | NOT_VERIFIED | 无账户 |
| Paper | 多账户/资金/持仓 | 存在 | overview/compare | projection | account/ledger | 0 | SQL | 无事实 | NOT_VERIFIED | L5 阻断 |
| Paper | deployment freeze | 存在 | deployments | deployment service | deployments | 0 | 代码检查 | 版本字段存在 | CODE_ONLY | 当前无部署 |
| Paper | daily cycle/Run-now | 存在 | cycles/run-now | scheduler | cycles/jobs | account cycles 0 | 代码检查 | legacy job 143 orphan | NOT_VERIFIED | 无安全终态账户 |
| Paper | signal/intent/transition | 存在 | account detail | v2 pipeline | signal/intent/transition | 0 | schema/code | immutable design | CODE_ONLY | 无实际记录 |
| Paper | constraint/order/fill | 存在 | detail APIs | pipeline | constraint/order/fill | 0 | schema/code | 无事实 | CODE_ONLY | 无实际记录 |
| Paper | ledger/projection | 存在 | performance | projection writer | ledger/projection | 0 | SQL | 无法重算 | NOT_VERIFIED | L5 阻断 |
| Paper | report/notification/audit | 存在 | reports/audit | outbox/audit | report/outbox/audit | 0 current | schema/code | historical file only | CODE_ONLY | 无当前送达 |
| Paper | dataTrust | 告警 UI | accounts/performance | trust loader | runtime evidence | stale | actual GET | 0 account still trusted | FAIL | dangling evidence |
| Operations | Dashboard | 存在 | aggregates/health | services | 多表 | 当前 counts | HTTP/API | data health ok | PARTIAL | 浏览器未测 |
| Operations | Tasks | 存在 | `/api/tasks` | task service | tasks | 9 success | GET | 5.2MB | PARTIAL | 不含 derived maintenance |
| Operations | Scheduler/Beat | 监控存在 | health | scheduler | leases/jobs | Beat online | Docker/Celery | queues 0 | PASS | domain orphan |
| Operations | Recovery | 状态 UI | actions | recovery services | 多状态表 | stale/orphan | SQL | 2+143+139 | FAIL | ownership 不统一 |
| Operations | Reports | 存在 | reports | report service | reports | 3 | GET | synthesized from runs | PASS | 与 result 职责相邻 |
| Operations | Docs | 存在 | help APIs | docs service | files | 33 articles | docs check | PASS | API/architecture 局部漂移 |
| Operations | Settings | 存在 | settings | config service | config/env | 当前可读 | GET/code | secrets 未打印 | PARTIAL | 浏览器未测 |
| Operations | Health/Metrics | 存在 | health/metrics | monitoring | runtime | all core ok | actual health | source recovered | PASS | DB latency 7.5s 偏高 |
| Operations | 错误/空/加载状态 | 存在 | structured errors | hooks/components | n/a | API errors | code/API | trace/retryable | PARTIAL | 视觉未验证 |
| Operations | 移动导航 | 存在 | n/a | React/CSS | n/a | n/a | static review | 390/768 tests defined | NOT_VERIFIED | 浏览器不可用 |
