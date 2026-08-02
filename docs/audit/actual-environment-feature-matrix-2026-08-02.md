# Actual-environment feature matrix — 2026-08-02（第二次审计）

`Web=存在` 仅表示路由/组件存在。内置 Browser 无可用实例，视觉、交互和四视口不能判 PASS。`SOURCE_FIXED` 表示 P1/P2 已进入仓库源码，但 actual API/worker/schema 未部署。

| Domain | Feature | Web | API | Service | Database | Actual Data | Test Result | Evidence | Status | Gap |
| ------ | ------- | --- | --- | ------- | -------- | ----------- | ----------- | -------- | ------ | --- |
| Projects | 项目列表 | 存在 | `/api/projects` | project service | `projects` | 4 | authenticated GET | paged response | PASS | 浏览器未测 |
| Projects | 创建项目 | 存在 | POST projects | project service | `projects` | 本轮0新建 | code/contract | 最小写入原则 | CODE_ONLY | 实际journey未测 |
| Projects | 打开/文件 | 存在 | project/file APIs | project service | project workspace | 4 projects | read-only API/code | files/routes存在 | PARTIAL | Editor浏览器未测 |
| Projects | 编辑/保存 | 存在 | PUT file | project service | workspace/snapshot | 未写 | code review | editor component | CODE_ONLY | 实际保存未测 |
| Projects | 克隆 | 存在 | clone API | project service | `projects` | 未克隆 | code review | 避免重复资源 | CODE_ONLY | 实际未测 |
| Projects | 删除保护 | confirm UI | DELETE | dependency guards | projects/runs | 未删除 | code review | 禁止真实删除 | CODE_ONLY | DB约束历史不足 |
| Strategies | 模板/示例 | 存在 | template/example APIs | project service | files | 多模板；4项目 | file inventory | templates/examples | PARTIAL | 未实例化 |
| Strategies | 参数配置 | 存在 | preflight/create | validation | run JSON | 3 runs | actual preflight | ready=true | PASS | UI form未测 |
| Strategies | 版本/快照 | 详情存在 | run versions | fingerprint | runs/objects | 3 | artifact/DB | project snapshot | PARTIAL | certificate actual缺失 |
| Strategies | 历史运行关联 | 存在 | project/backtests | backtest service | project/run FK | 3 | DB join | project均存在 | PASS | 无 |
| Data | Provider availability | 存在 | providers/catalog | catalog | provider metadata | 多provider | actual GET | source health | PASS | executable状态旧API不清 |
| Data | 资产目录 | 存在 | asset classes/catalog | catalog | `instruments` | 8,103 | API/SQL | 8,095 equity+8 index | PARTIAL | capability endpoint actual 404 |
| Data | 数据预览 | 存在 | preview | market repository | daily bars | 19.2M | existing sample | A股OHLC正常 | PASS | 浏览器图表NV |
| Data | 股票主数据 | 存在 | securities | reference service | securities/instruments | 5,902/8,095 | reference coverage | lifecycle存在 | PASS | 两模型需说明 |
| Data | 交易日历 | 存在 | calendar | calendar service | trade calendar | 8,693 | actual coverage | 1990-12-19..2026-07-30 | PASS | 无 |
| Data | 指数 | 存在 | catalog/preview | data service | instruments/bars | 8 instruments | SQL/API | 000300可用 | PASS | 仅少数index |
| Data | ETF | 泛资产入口 | catalog | provider | instruments | 独立0 | SQL/QA | 无executable样本 | FAIL | capability需部署 |
| Data | 期货 | 泛资产入口 | providers/asset classes | futures | raw metadata | canonical 0 | cross-asset QA | fut_basic metadata only | FAIL | 不可回测 |
| Data | 期权 | 泛资产入口 | providers/asset classes | options | raw metadata | canonical 0 | cross-asset QA | opt_basic metadata only | FAIL | 不可回测 |
| Data | 可转债 | 文档/入口 | catalog | data service | cb tables | canonical 0 | cross-asset QA | cb datasets missing | FAIL | 不可回测 |
| Data | 分钟/tick | resolution UI | preview/preflight | data service | minute/tick | 0 | inventory | no canonical rows | FAIL | 不可回测 |
| Data | 公司行动 | 间接 | quality/preflight | reference service | corporate actions | 59/3 symbols | sample+coverage | action样本存在 | PARTIAL | 覆盖严重偏窄 |
| Data | 复权因子 | 间接 | preflight | LEAN cache/data | factor data | 大规模 | gate/artifact | run可执行 | PARTIAL | run级SHA为空 |
| Data | 停牌 | 间接 | preflight/reference | status repository | trade status | 18,302,220 | actual coverage | 141,551 suspended days | PASS | 多源语义需文档 |
| Data | ST | 间接 | preflight/reference | status repository | securities/status | 557 symbols | actual sample | ST样本 | PASS | ST-days统计仅1需复核 |
| Data | 退市 | 间接 | reference | security master | securities | 366 | sample | 国华退等 | PASS | 无 |
| Data | PIT universe | 存在 | PIT APIs | universe service | memberships | 299,610 | health/SQL | CSI300 1,225 | PASS/PARTIAL | 其他universe partial |
| Data | Benchmark | 存在 | preflight/result | analyzer | index bars/results | 000300 | raw/DB/report | 6.2461%真实收益 | PASS | 覆盖有限 |
| Data | 数据同步 | 存在 | sync-runs | data sync | sync/checkpoint | 20 latest可查 | API/SQL | success/partial/fail历史 | PARTIAL | 恢复fix未部署 |
| Data | Checkpoint/watermark | 存在 | health/watermarks | maintenance | watermarks | 4 ready | actual GET | Parquet/CH | PASS | ClickHouse index窄scope |
| Data | Validation/quarantine | 存在 | QA/verifications | QA | QA/raw issues | QA20；37 quarantine | actual GET | 16ok/2warn/2critical | PASS/PARTIAL | 报告含历史critical |
| Data | Certification | 存在 | health/preflight | source gate | parquet datasets | 2 certified | actual health | recert success | PASS | Dataset Release未部署 |
| Data | Dataset Release | 新源码有 | `/api/data/releases` | release service | 0040 table | 0/表不存在 | actual 404/schema | source vs runtime diff | CODE_ONLY | P0-004 |
| Data | Parquet/DuckDB | 存在 | parquet datasets | maintenance | parquet datasets | 7；2 production | watermark/manifest | equity17.7M,index44.7K | PASS | 全量独立rehash NV |
| Data | ClickHouse | 存在 | health | maintenance | watermarks | equity17.7M,index5,960 | actual health | ready | PARTIAL | index scope较窄 |
| Data | CSV import | 存在 | import APIs | importer | import runs | 历史能力 | code/API | 本轮未写 | CODE_ONLY | 实际幂等未测 |
| Data | On-demand download | 存在 | demand APIs | data-demand worker | tasks/archive | worker在线 | queue/code | 无新下载 | PARTIAL | 未触发 |
| Backtest | Preflight | 存在 | POST preflight | validation/source gate | read-only | reused project | actual 200 | ready=true,17.129s | PASS | benchmark display 0 rows易误解 |
| Backtest | 单次真实LEAN | 存在 | create/detail | backtest worker | runs/results | 3 | existing artifact | runner/raw result | PASS/PARTIAL | final gate Critical |
| Backtest | 批量回测 | 存在 | batches | experiment | batches/children | 2×1 child | actual GET | dynamic PIT | PARTIAL | 非参数grid |
| Backtest | 状态/任务 | 存在 | run/task APIs | worker/recovery | runs/tasks | 3/9 success | SQL/API | 无current queued | PASS/PARTIAL | 新生命周期UI NV |
| Backtest | 日志/cursor | 存在 | logs | task service | file/object | 296,777 bytes | actual cursor | tail/offset正确 | PASS/PARTIAL | UI cursor NV |
| Backtest | 取消 | 存在 | cancel | cancel service | run/task | 未执行 | code only | 禁止影响任务 | CODE_ONLY | race NV |
| Backtest | 结果/图表 | 存在 | result/chart | parser | results | 3 | actual 200 | run1对账 | PASS | payload大 |
| Backtest | 订单/成交/持仓 | 存在 | detail/result | parser | result JSON | 134/134/10(run1) | raw/DB/API | 四方一致 | PASS | UI表格NV |
| Backtest | Metrics/benchmark/excess | 存在 | result | analyzer | results | 3 | raw/report | run1指标一致 | PASS | excess UI NV |
| Backtest | Artifact/report | 存在 | downloads/reports | object/report | objects/reports | 68 backtest objects | SHA/API/file | raw先保存 | PASS | per-file cert缺 |
| Backtest | Version/fingerprint | 存在 | versions | fingerprint | run JSON | 3 | actual GET | image/project/data字段 | PARTIAL | release/cache SHA缺 |
| Backtest | Final gate | 详情显示 | validation | finalizer | runs | 1矛盾 | SQL/API | success+critical | FAIL | ACT-CRIT-001 |
| Backtest | Reproducibility | 新源码有 | certificate/golden | cert service | 0040 table | 0 | actual 404 | no duplicate input | CODE_ONLY | 无Golden Pair |
| Backtest | 历史筛选/分页 | 存在 | list filters | query service | runs | 3 | HTTP/code | actual list23.3MB | PARTIAL | browser/URL state NV |
| Experiment | Parameter grid | 存在 | preview/create | scheduler | batch/children | 0 current | inventory | 无实际grid | CODE_ONLY | actual证据缺 |
| Experiment | Dynamic PIT | 存在 | batch detail | experiment | batches | 2×1 success | API/SQL | child success | PASS/PARTIAL | 规模极小 |
| Experiment | Rolling | 存在 | batch types | experiment | batches | 0 | inventory | 无current run | CODE_ONLY | actual证据缺 |
| Experiment | Walk-Forward | 存在 | WF APIs | WF service | WF run/windows | 1/2 windows | SQL | lineage_broken | FAIL | P0-002 |
| Experiment | Train/Validation/OOS | 存在 | WF detail | WF service | window fields | 两折日期 | SQL | 三段边界存在 | PARTIAL | selection/OOS link NULL |
| Experiment | Retry/cancel/restart | 存在 | command APIs | scheduler | batch/task | 未执行 | code review | 最小写入原则 | CODE_ONLY | actual竞态NV |
| Experiment | CSV export | 存在 | export | experiment query | child results | 1 row | actual GET | 200/305 bytes | PASS | 小样本 |
| Experiment | Ranking/heatmap | 存在 | aggregate APIs | analytics | results | 无grid数据 | code | UI未测 | CODE_ONLY | 无实际热力图 |
| Research | Runs/workspaces | 存在 | research APIs | research service | research runs | 3 | SQL/API | 1success/2failed | PASS/PARTIAL | 无current running |
| Research | 日志/停止/重启 | 存在 | command/log APIs | worker | tasks/runs | 无active | code/history | stale已收敛 | PARTIAL | actual命令NV |
| Factors | Evaluation | 存在 | factor APIs | factor service | factor values | 大规模research | code/inventory | 未专项复算 | PARTIAL | 浏览器NV |
| Paper | Legacy Session | 存在 | legacy Paper API | legacy service | paper sessions/jobs | 2 sessions；旧orphan quarantined | SQL | 边界仍双轨 | PARTIAL | deprecate需明确 |
| Paper | Account开户 | 存在 | accounts | account service | accounts | 2 | actual API/SQL | 1m/3m | PASS | 均draft |
| Paper | Opening ledger | 存在 | overview | ledger pipeline | ledger entries | 2 | readonly reconcile | sequence1 exact | PASS | 仅开户 |
| Paper | Projection | 存在 | overview/compare | projection | projections | 2 | readonly reconcile | cash/equity exact | PASS | 无交易日序列 |
| Paper | Deployment freeze | 存在 | deployments | deployment | deployments | 2 active | API/SQL | fingerprints不同 | PARTIAL | actual trust/release旧 |
| Paper | Certification cohort | 间接 | cohort APIs | certification | cohort/members | 1/2 | SQL | collecting,0/21 | PARTIAL | 未运行 |
| Paper | Daily cycle | 存在 | cycles/run-now | scheduler/cycle | cycles | 0 | SQL/API | latestCycle null | FAIL | past due deployment |
| Paper | Signal/intent | 存在 | signals | execution | signal/intent | 0 | SQL/API | empty | NOT_VERIFIED | 无cycle |
| Paper | Order/fill | 存在 | orders/trades | order pipeline | orders/fills | 0 | SQL/API | empty | NOT_VERIFIED | 幂等/next-session未证 |
| Paper | Position/cash/NAV | 工作台存在 | overview/performance | projection | positions/snapshots | opening only | reconcile | initial projection exact | PARTIAL | 无交易后事实 |
| Paper | Report/performance | 存在 | reports/performance | reporting | reports/snapshots | 0/empty | API | endpoints 200 empty | NOT_VERIFIED | 无daily cycles |
| Paper | Notification/audit | 存在 | notifications/audit | outbox/audit | events/outbox | account downstream 0 | API | empty | NOT_VERIFIED | global delivery失败 |
| Paper | 多账户比较 | 存在 | compare | query | projections | 2 | actual API | comparable=true | PASS/PARTIAL | 仅opening状态 |
| Paper | Trust | UI字段 | accounts | trust service | runtime/0040 absent | stale旧IDs | actual API/SQL | trust=true dangling | FAIL | P1-001 |
| Paper | 停止/删除保护 | 存在 | commands/delete | account service | dependencies | 未执行 | code review | 禁止真实破坏 | CODE_ONLY | actual保护NV |
| System | Dashboard | 存在 | aggregate APIs | query services | 多表 | current | HTTP/code | route/assets加载 | PARTIAL | 浏览器NV |
| System | Tasks | 存在 | tasks | task service | tasks | 9 success | actual GET | 5.2MB | PARTIAL | payload过大 |
| System | Reports | 存在 | reports | report service | reports/objects | existing | API/code | run report可读 | PASS/PARTIAL | UI NV |
| System | Docs | 存在 | docs/help | help generator | files | 33 articles | check scripts | PASS | PASS | runtime内容未逐页浏览 |
| System | Settings | 存在 | settings/health | config | env/runtime | current | code/HTTP | route存在 | PARTIAL | 权限失效UI NV |
| System | Health/Metrics | 存在 | health/resources | monitoring | samples/alerts | current | actual GET | DB/queues/resource | PARTIAL | notification false-ready |
| System | Error/loading/empty | components有 | structured errors | API client | n/a | actual empty Paper tabs | HTTP/code | endpoints 200 | PARTIAL | 浏览器体验NV |
| System | Notification outbox | 间接 | alerts | notification | deliveries | 33/33 failed | SQL/API/log | attempts70,260 | FAIL | P1-007 |
| System | Responsive/mobile | components有 | n/a | n/a | n/a | 4目标尺寸 | browser unavailable | mocks不算actual | NOT_VERIFIED | 四视口未验 |

## 结论

功能面“存在”明显高于“实际链路通过”。第二次审计新增的真实 PASS 是 P0 状态收敛、Paper 双账户开户/初始账本/投影和 comparison；未被代码修复覆盖的关键实际缺口仍是 final gate、部署代次、WF lineage、Paper 0 cycles、通知全失败和跨资产数据不可执行。
