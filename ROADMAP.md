# 修复后回测平台能力复审与 ROADMAP

审计/修复日期：2026-07-04  
仓库：`/Users/kaermax/lean-platform`  
当前分支：`main`  
基准 commit：`8e51ae4 Add P2 factor, cbond, and futures research support`  
当前状态：工作区包含本次 P0 修复、本地 TuShare Pro token 配置支持、AKShare 沪深300日线导入脚本、沪深300 PIT 成分导入管线，以及 MySQL 运行主库切换。默认运行库已从 SQLite 改为 `mysql+pymysql://lean:lean@127.0.0.1:3306/lean_market`；`web/runtime/HS300.sqlite3` 只作为迁移源/备份。MySQL 已全量导入 `HS300.sqlite3`，并补充通用 `instruments`、`market_daily_bars`、`market_trade_status` 和 `stored_objects/stored_object_chunks`，但 `CSI300` PIT 覆盖仍从 `2017-12-08` 起，尚不是 2005 年指数发布以来的完整全历史。

## 1. 总体结论

本次 P0 修复后，平台在代码机制上已经补齐上一轮最影响回测可信度的 5 个缺口：历史股票池 as-of 查询、上市/退市过滤、复权因子 factor 文件生成、官方交易状态优先、A 股 benchmark 参数、真实 LEAN 订单事件集成断言。  

需要严格区分两件事：

- 代码层能力：本次已实现并有单测/集成测试覆盖。
- 生产数据层能力：仓库当前没有 TuShare Pro/JQData/RQData 凭据，也没有全 A 批量历史数据文件，因此实际运行库仍需要导入证券主数据、全 A 历史池、指数行情、官方停复牌/涨跌停/ST、复权因子和公司行动。

当前平台已经更接近 Level 2 个人研究级中上沿，可以继续做受控数据下的 A 股日线研究。正式模拟盘仍不建议马上开始，除非只做小范围影子跟踪，并明确标记数据覆盖边界。下一阶段优先级不是大规模重构，而是接入 TuShare Pro 数据、补数据版本指纹、扩大 LEAN 端到端夹具。

## 2. 本次实现摘要

### MySQL 运行主库与本地数据数据库化

实现内容：

- 新增 MySQL 8.4 Docker Compose 服务，API/worker 默认使用 `LEAN_DATABASE_URL=mysql+pymysql://lean:lean@mysql:3306/lean_market`。
- `app.db` 增加 MySQL 连接、DDL/占位符/upsert 兼容层；SQLite 仅保留为迁移源和测试隔离后端。
- 新增通用市场数据表：`instruments`、`instrument_identifiers`、`market_daily_bars`、`market_trade_status`，覆盖股票、可转债、加密币、期货的扩展模型。
- 新增数据库对象表：`stored_objects`、`stored_object_chunks`，Object Store、LEAN zip/factor 文件、回测 result/summary、上传 CSV、runtime 文件均可入库保存。
- 新增迁移脚本 `scripts/migrate_hs300_sqlite_to_mysql.py`，支持重建目标库、复制 SQLite 全部表、回填通用行情表、归档本地文件。
- A 股、可转债、期货和 CSV/Provider 导入会同步写通用行情表；数据查询预览默认读 MySQL `market_daily_bars`。

2026-07-05 验证结果：

- `docker compose config` 通过。
- MySQL `lean_market` 已用 `--recreate-database` 重建并导入。
- SQLite -> MySQL 表计数一致：`ashare_daily_bars=1,215,591`、`adjustment_factors=1,215,591`、`ashare_trade_status=1,215,554`、`securities=584`、`universe_membership=1,240`、`index_membership_events=686`、`data_assets=608`。
- 通用表回填：`instruments=584`、`market_daily_bars=1,215,591`、`market_trade_status=1,215,554`。
- 文件归档：`stored_objects=2,206`、`stored_object_chunks=2,311`；其中 LEAN Data 2,041 文件、runtime runs 161 文件、object-store 2 文件已入 MySQL，object-store 文件同时归档到 API 使用的 `object-store` 命名空间。
- MySQL 健康检查 `ok=True`，`/api/health/database` 关键表不缺失；`query_database_bars(600519)` 可从 MySQL 返回上市日起行情。

剩余边界：

- 生产运行已不再依赖 SQLite，但测试仍用临时 SQLite 隔离。
- ClickHouse 仍是可选镜像/加速层，当前不是事实源。
- LEAN 回测执行仍读取本地 `Data/` 文件缓存；MySQL 已保存文件原文，后续可补“从 MySQL 恢复/生成 LEAN Data 缓存”的启动前导出步骤。

### P0-001：全 A 历史股票池缺失，幸存者偏差未闭环

实现内容：

- 新增证券主数据导入函数 `import_security_master`。
- `universe_as_of` 改为必须 join `securities`，并按 `listed_date`、`delisted_date`、`announce_date`、`effective_date` 做 as-of 过滤。
- 新增 `tradable_universe_as_of`，支持新股过滤、ST 排除、退市后不可交易。
- `is_tradeable` 增加上市前、退市后、非活跃状态拒绝。
- 新增 API：`POST /api/ashare/securities/import`、`GET /api/ashare/universe/{universe_code}/tradable`。
- 单测覆盖上市前不可交易、新股过滤、退市前可出现、退市后不可交易、ST 排除。

剩余边界：

- 没有凭据时无法把真实全 A 历史证券池导入本地库。
- 需要后续用 TuShare Pro `stock_basic`、历史指数成分/权重、退市字段批量填充。
- 2026-07-05 已新增沪深300 PIT 成分公开数据管线：`index_source_artifacts`、`index_membership_events`、`index_membership_pit`、`scripts/import_csi300_pit_public.py`、`scripts/import_csindex_csi300_pit.py`、`scripts/import_csindex_csi300_cached.py`、`data_sources/csi300_pit_sources.example.json`。
- 该管线已支持公告日、生效日、调入/调出事件、原始文件 hash、批次号和 `universe_as_of()` 查询。
- 2026-07-05 已将原 `web/runtime/lean_web.sqlite3` 复制为 `web/runtime/HS300.sqlite3`，新库继承当前 300 个 securities、1,215,591 行 A 股日线和既有 CSI300/ALL_A membership。
- 2026-07-05 已基于中证指数官网缓存附件写入真实 `CSI300` PIT：20 个 source artifact、686 条调入/调出事件、643 条 PIT 区间，active 成分在 `2017-12-08` 和 `2026-07-03` 均为 300；`CSI300_DEMO` 在 `universe_membership`、`index_membership_events`、`index_membership_pit`、`index_source_artifacts` 中均为 0 行。
- 覆盖边界：当前真实 PIT 从 `2017-12-08` 起，`2017-12-08` 以前不返回伪造 membership；仍需补 2005-2017 官方公告或专业数据源，才能称为完整全历史。

### P0-002：复权与公司行动未闭环

实现内容：

- 新增 `corporate_actions` 表和索引。
- 新增复权因子导入函数 `import_adjustment_factors`。
- 新增公司行动导入/查询函数 `upsert_corporate_actions`、`corporate_actions`。
- 新增 `write_equity_factor_file`，从 `adj_factor` 生成 LEAN factor file。
- `import_ashare_research_data` 现在写入日线 zip 后同步生成 factor file，并在 metadata 保存 `factor_file`。
- 新增 API：`POST /api/ashare/adjustment-factors/import`、`GET /api/ashare/adjustment-factors/{symbol}`、`POST /api/ashare/corporate-actions/import`、`GET /api/ashare/corporate-actions/{symbol}`。
- 单测覆盖复权因子转换和 factor file 输出。

剩余边界：

- 真实分红、送转、配股、代码变更仍需供应商数据。
- 当前 factor file 基于 `adj_factor/latest_factor` 生成价格因子，适合 raw 价格进入 LEAN 时使用；qfq/hfq 口径需要在数据导入契约中继续明确。

### P0-003：停牌、涨跌停、ST、退市状态依赖推断

实现内容：

- `normalize_ashare_daily_rows` 保留官方状态字段：`is_suspended`、`limit_up`、`limit_down`、`is_limit_up`、`is_limit_down`、`is_one_word_limit_up`、`is_one_word_limit_down`、`can_buy`、`can_sell`。
- `build_ashare_trade_status` 优先使用官方字段，缺失时才用 OHLCV fallback 推断。
- 数据 QA warning 标记 `trade_status_official_fields_used` 或 `trade_status_inferred_from_ohlcv`。
- 新增 `import_trade_status` 和 `POST /api/ashare/trade-status/import`。
- `trade_status_as_of` 返回 Python bool，避免 SQLite 0/1 泄漏到 API。
- 单测覆盖官方状态覆盖推断、缺失交易状态默认拒绝交易。
- 真实 LEAN 集成测试覆盖涨停不可买、跌停不可卖、停牌不可买。

剩余边界：

- 真实官方状态数据仍需接入 TuShare Pro `stk_limit`、停复牌、ST/退市风险字段，或用 RQData/JQData 补齐。

### P0-004：A 股基准缺失

实现内容：

- A 股回测参数默认写入 `benchmarkSymbol=000300`、`benchmarkMarket=china`。
- `DockerDemoAlgorithm.py` 和策略模板对中国市场尝试添加 benchmark equity，成功时使用真实 benchmark，失败时回退常数 benchmark 并写 debug。
- 回测请求参数会保存 benchmark symbol。
- 单测覆盖 A 股 job 参数注入。

剩余边界：

- 本地库仍需导入 `000300`、中证全指或其他指数行情，才能得到有效 Alpha/Beta/Information Ratio/Excess Return。

### P0-005：关键交易约束缺少真实 LEAN 集成断言

实现内容：

- A 股 helper 新增 `on_order_event`，按真实 filled buy 事件记录买入日期。
- `DockerDemoAlgorithm.py` 和策略模板将 LEAN `on_order_event` 转发给 helper。
- 修复 T+1 的关键边界：日线 market order 被 LEAN 转成次日开盘成交时，T+1 按成交日而不是下单日计算。
- 新增 `tests/test_ashare_lean_integration.py`，通过真实 Docker/LEAN 回测断言订单事件。
- 新增 `pytest.ini` 登记 `integration` marker。

验收结果：

- 2024-01-02 涨停买入被拒。
- 2024-01-03 发出买单，2024-01-04 开盘成交。
- 2024-01-04 同日卖出被 T+1 拦截。
- 2024-01-05 跌停卖出被拒。
- 2024-01-08 发出卖单，2024-01-09 开盘成交。
- 2024-01-10 停牌买入被拒。

## 3. P0 修复验收表

| 编号 | 问题 | 当前状态 | 证据 | 剩余风险 | 后续动作 |
| --- | --- | --- | --- | --- | --- |
| P0-001 | 全 A 历史股票池缺失 | 代码机制已修复；`CSI300` 已写入 2017-12-08 起真实官方缓存 PIT；全 A 和 2005-2017 沪深300仍待补 | `import_security_master`、`universe_as_of`、`tradable_universe_as_of`、`scripts/import_csindex_csi300_cached.py`、`data_sources/csi300_pit_sources.json`、`test_security_master_restores_history_and_filters_new_and_delisted`、`test_csi300_pit_materialization_respects_effective_date` | 不能恢复 2017-12-08 以前沪深300成分，也不能恢复全 A 历史池 | 接 TuShare Pro `stock_basic`、退市字段、指数成分；补 2005-2017 中证指数公告或 JQData/RQData |
| P0-002 | 复权与公司行动未闭环 | 代码机制已修复，真实公司行动数据待导入 | `corporate_actions` 表、`write_equity_factor_file`、`test_adjustment_factors_write_factor_file_and_corporate_actions` | qfq/hfq/raw 生产口径仍需数据契约约束 | 接 `adj_factor`、分红送转配股表，补口径校验 |
| P0-003 | 停牌/涨跌停/ST 依赖推断 | 已修复为官方字段优先，推断 fallback 保留 | `import_trade_status`、QA warning、`test_official_trade_status_overrides_inferred_rules_and_missing_status_rejects`、LEAN 集成测试 | 官方状态源未批量接入前仍有数据缺口 | 接 `stk_limit`、停复牌、ST 状态 |
| P0-004 | A 股 benchmark 缺失 | 代码已支持，真实指数行情待导入 | `benchmarkSymbol=000300` 注入、算法/模板 add benchmark、单测覆盖 | 若本地无指数数据，会回退常数 benchmark | 导入沪深300/中证全指日线并加示例回测 |
| P0-005 | 缺少真实 LEAN 订单事件断言 | 已修复并通过真实 Docker/LEAN 集成测试 | `RUN_LEAN_DOCKER_INTEGRATION=1 .venv/bin/python -m pytest -q tests/test_ashare_lean_integration.py`，结果 `1 passed` | 集成夹具仍是单票极端样本，需扩展现金不足/100 股端到端断言 | 增加多场景 LEAN fixtures |

## 4. 已验证命令

```bash
cd web/backend
.venv/bin/python -m pytest -q
```

结果：`33 passed, 1 skipped, 3 warnings in 0.81s`。

```bash
web/backend/.venv/bin/python scripts/import_csindex_csi300_cached.py --dry-run
web/backend/.venv/bin/python scripts/import_csindex_csi300_cached.py --acknowledge-partial-coverage
```

结果：成功；写入 `web/runtime/HS300.sqlite3`，覆盖从 `2017-12-08` 起，source artifact 20 个、调入/调出事件 686 条、PIT 区间 643 条，active 成分在 `2017-12-08` 和 `2026-07-03` 均为 300。

```bash
sqlite3 web/runtime/HS300.sqlite3 "select universe_code,count(*) from universe_membership where universe_code like 'CSI300%' group by universe_code; select index_code,count(*) from index_membership_events where index_code like 'CSI300%' group by index_code; select index_code,count(*) from index_membership_pit where index_code like 'CSI300%' group by index_code;"
```

结果：`CSI300` membership/events/PIT 分别为 `643/686/643`；`CSI300_DEMO` 在 `universe_membership`、`index_membership_events`、`index_membership_pit`、`index_source_artifacts` 中均为 0 行。

```bash
web/backend/.venv/bin/python -m pytest web/backend/tests/test_csi300_pit.py
```

结果：`4 passed in 0.18s`。

```bash
web/backend/.venv/bin/python scripts/import_csi300_pit_public.py --manifest data_sources/csi300_pit_sources.example.json --dry-run --validate
```

结果：成功；示例 manifest 解析 2 条调入/调出事件，构造 4 条 PIT 区间，`2024-05-20` 和 `2024-06-01` 均验证为 3 个成员。该命令只验证管线，不代表生产 `CSI300` 历史成分已经导入。

```bash
cd web/backend
RUN_LEAN_DOCKER_INTEGRATION=1 .venv/bin/python -m pytest -q tests/test_ashare_lean_integration.py
```

结果：`1 passed, 1 warning in 3.41s`。

```bash
cd web/frontend
npm run build
```

结果：成功；仍有 Vite chunk size warning。

```bash
docker compose config
```

结果：成功解析。

## 5. 当前关键模块

- `web/backend/app/db.py`：新增 `corporate_actions` 表。
- `web/backend/app/services/ashare_repository.py`：证券主数据、历史股票池、交易状态、复权因子、公司行动、可交易性判断。
- `web/backend/app/services/csi300_pit.py`：沪深300公告级 PIT 成分解析、事件落库、区间生成和审计 artifact 记录。
- `web/backend/app/services/data_quality.py`：A 股日线标准化、官方交易状态保留、fallback 推断。
- `web/backend/app/services/data.py`：A 股研究数据导入、QA warning、LEAN zip/factor file 写入。
- `web/backend/app/lean.py`：LEAN 数据目录、日线 zip、factor/map 文件生成。
- `web/backend/app/services/ashare_execution.py`：A 股费用、滑点、100 股、涨跌停/停牌/T+1 helper。
- `DockerDemoAlgorithm.py`：A 股 benchmark、order event 转发。
- `web/backend/app/services/strategies.py`：策略模板 benchmark 和 order event 转发。
- `web/backend/app/api/ashare.py`：A 股主数据、交易状态、复权因子、公司行动、股票池 API。
- `web/backend/tests/test_ashare_p0.py`：P0 单元测试。
- `web/backend/tests/test_ashare_lean_integration.py`：真实 Docker/LEAN 集成测试。
- `web/backend/tests/test_csi300_pit.py`：公告调入/调出解析、PIT 区间和 `universe_as_of()` 生效日测试。
- `scripts/import_csi300_pit_public.py`：按 manifest 下载/读取公开公告、记录 hash、解析事件并生成本地 PIT 成分表。
- `scripts/import_csindex_csi300_pit.py`：中证指数官网公告抓取、附件缓存、调样事件解析和 PIT 重建脚本；当前官网详情接口存在 WAF 阻断，保留为后续补源入口。
- `scripts/import_csindex_csi300_cached.py`：从本地中证指数官方缓存附件重建真实 `CSI300` PIT，并写入 `HS300.sqlite3`。
- `data_sources/csi300_pit_sources.json`：本地生产 manifest，记录 2017-12-08 起的真实官方缓存 source、hash、覆盖边界和初始重建成员。
- `data_sources/csi300_pit_sources.example.json`：公开公告 manifest 示例，仅用于验证导入管线，不写入生产库。

## 6. 当前平台等级

当前等级：Level 2，个人研究级中上沿。  
是否达到个人研究级：是，前提是使用已导入且 QA 通过的数据。  
是否达到模拟盘级：否。  
是否达到小资金实盘前验证级：否。  

距离 Level 3 还差：

- 自动化数据更新和 QA 阻断。
- 全 A/指数/交易状态/复权/财务 PIT 的真实批量数据。
- 回测结果绑定 git commit、数据 hash、Docker image digest。
- 每日 Paper Replay 链路和日报。
- 更完整的组合约束、风控、告警。

## 7. 数据接口结论

现在不必须购买 iFinD、Choice 或 Wind。  

当前最适合优先接入 TuShare Pro：

- 成本低，覆盖当前最急需的证券主数据、日线、复权因子、涨跌停价、指数成分、估值和财务指标。
- 本次代码已经预留导入入口，适合先把数据治理链路跑顺。
- 本地 token 读取已支持仓库根目录 `.env` 中的 `TUSHARE_TOKEN`，`.env` 已加入 `.gitignore`，只提交 `.env.example`。
- 当前 token 已验证 `pro.daily()` 可用；证券主数据、交易日历、涨跌停价、指数行情等仍取决于后续权限。

iFinD/Choice/Wind 的购买触发条件：

- 平台稳定 Paper 运行 1-3 个月。
- 已证明策略需要公告、研报、宏观、产业链或终端型人工核验数据。
- 内部复现、日志、告警、报告、数据版本指纹已经成熟。

如果必须购买专业数据，优先顺序：

1. TuShare Pro
2. RQData 或 JQData
3. Choice 或 iFinD
4. Wind

## 8. 后续 Issue 清单

### P0：仍需闭环的可信度问题

#### P0-006：真实全 A 数据导入和覆盖率验收

- 问题：代码机制已有，但生产库没有真实全 A 历史池。
- 影响：全市场选股仍无法脱离样本偏差。
- 推荐方案：实现 TuShare Pro adapter，导入 `stock_basic`、上市/退市字段、全 A membership、指数成分。
- 验收标准：
  - 任意历史交易日 `ALL_A` 可恢复不少于合理数量级的证券池。
  - 随机抽样退市股在退市日前可出现，退市日后不可交易。
  - 导入批次保存 source、batch、更新时间、记录数、错误数。

#### P0-007：真实指数行情和 benchmark 验收

- 问题：benchmark 代码已接入，但本地仍可能没有 `000300` 等指数数据。
- 影响：Alpha/Beta/超额收益仍可能回退为无效常数基准。
- 推荐方案：导入沪深300、中证500、中证1000、中证全指日线；回测前校验 benchmark 数据覆盖。
- 验收标准：
  - 600519 示例回测可输出非空 benchmark 曲线。
  - 报告展示超额收益、Alpha、Beta、Information Ratio。

#### P0-008：复权口径强校验

- 问题：factor file 已可生成，但 qfq/hfq/raw 的策略配置契约仍需阻断混用。
- 影响：长期收益和成交价仍可能因口径混用失真。
- 推荐方案：回测参数必须显式保存 `adjust`，数据覆盖校验中匹配同一 adjust；报告展示复权口径。
- 验收标准：
  - raw/qfq/hfq 混用时回测创建失败。
  - 示例数据在除权日前后收益连续性测试通过。

#### P0-009：CSI300 2005-2017 PIT 成分缺口

- 问题：`HS300.sqlite3` 已写入真实中证指数官网缓存重建的 `CSI300` PIT，但覆盖从 `2017-12-08` 起；官网列表可发现 2005 年起公告 ID，详情接口当前返回 403，列表又不包含附件 URL。
- 影响：2017 年以前的沪深300增强、历史基准复制和 PIT 选股仍不能闭环，不能把当前库标记为“2005 至今全历史”。
- 推荐方案：继续补 2005-2017 中证指数官方公告附件；若官网详情持续 WAF 阻断，改用 JQData/RQData 的历史指数成分接口核验并生成同一 schema。
- 验收标准：
  - `index_membership_pit` 对 `2005-07-01` 到 `2017-12-07` 任意调样区间可返回 300 个真实成员。
  - 每个调样批次都有 `announce_date`、`effective_date`、source、hash、batch_id。
  - 早期区间不得用当前成分或反推结果冒充官方全历史。

### P1：进入模拟盘前必须完成

#### P1-001：数据和环境复现指纹

- 问题：结果没有完整绑定 git commit、dirty flag、数据文件 hash、data batch、Docker image digest。
- 推荐方案：创建 run fingerprint，保存到 `backtest_runs` 和报告。
- 验收标准：任意历史 run 可以定位代码版本、参数 hash、数据 hash、Docker image digest。

#### P1-002：Paper Replay 每日任务链

- 问题：已有 Paper 原型，但缺少每日自动更新、信号、撮合、持仓、日报闭环。
- 推荐方案：增加单命令每日任务，串联数据导入、QA、策略信号、模拟订单、组合快照、报告。
- 验收标准：连续 10 个交易日无人值守跑通，有异常日志和日报。

#### P1-003：组合级约束

- 问题：当前更偏单票约束，缺少最大持仓数、单票权重、行业权重、黑名单、观察池、现金下限。
- 推荐方案：定义统一 portfolio constraint config，回测和 Paper 共用。
- 验收标准：违反约束的订单被拒绝，并记录拒绝原因。

#### P1-004：数据 QA 升级为回测前置门禁

- 问题：已有基础 QA，但没有跨源、复权跳变、状态覆盖率、成交额异常门禁。
- 推荐方案：增加 QA severity；critical 失败时禁止回测。
- 验收标准：缺 benchmark、缺交易状态、缺复权因子、价格异常时创建回测失败。

#### P1-005：MySQL 到 LEAN Data 缓存导出闭环

- 问题：MySQL 已保存行情和 LEAN zip/factor/map 文件原文，但 LEAN 引擎实际运行仍直接读取本地 `Data/` 文件缓存。
- 推荐方案：回测前按 `data_assets.lean_object_id/factor_object_id` 或 `stored_objects` 从 MySQL 恢复所需 LEAN 文件；缓存缺失或 hash 不一致时自动重建。
- 验收标准：
  - 删除单个本地 LEAN zip 后，回测前可从 MySQL 自动恢复。
  - 恢复文件 hash 与 `stored_objects.sha256` 一致。
  - 回测结果 fingerprint 记录 MySQL object id、sha256、数据批次和导出时间。

### P2：提高效率和扩展性

#### P2-001：TuShare/JQData/RQData adapter 契约

- 问题：服务函数已存在，但外部 provider adapter 尚未统一。
- 推荐方案：定义 adapter interface：fetch、normalize、upsert、QA、batch metadata。
- 验收标准：新增一个数据源不改核心回测逻辑。

#### P2-002：多因子研究升级

- 问题：已有 IC/Rank IC/分层收益原型，但缺标准化、去极值、行业中性、组合构建、样本外。
- 推荐方案：增加 factor pipeline 和 portfolio builder。
- 验收标准：输出多因子组合净值、IC、Rank IC、分层收益、换手。

#### P2-003：可转债数据和撮合

- 问题：双低和强赎风险仍是原型。
- 推荐方案：导入转债日线、转股价、溢价率、剩余规模、评级、强赎/回售/下修、最后交易日；增加转债费率。
- 验收标准：能跑“双低 + 强赎避雷 + 正股趋势联动”策略。

#### P2-004：期货主力和保证金

- 问题：期货研究原型缺真实连续合约、保证金、手续费、换月收益校验。
- 推荐方案：导入合约元数据、乘数、最小变动价位、保证金、手续费、主力/次主力；生成连续合约。
- 验收标准：玉米、豆粕、豆油、棕榈油、白糖、棉花、生猪日线监控稳定输出。

#### P2-005：前端和报告优化

- 问题：前端构建成功但 bundle 偏大，报告对模拟盘异常高亮不足。
- 推荐方案：动态分包；报告突出数据异常、交易拒绝、回撤扩大、基准跑输。
- 验收标准：报告可直接用于盘后检查，前端 chunk warning 有处理或豁免。

## 9. 两周行动计划

| 时间 | 任务 | 验收标准 |
| --- | --- | --- |
| Day 1 | 落地 TuShare Pro adapter 契约和配置 | provider token 从环境变量读取；`pro.daily()` SDK 验证通过 |
| Day 2 | 用 `pro.daily()` 导入小股票池日线 | 20 只股票 1 年 raw 日线 QA 通过，LEAN zip 生成 |
| Day 3 | 申请/验证 `stock_basic`、`trade_cal`、`adj_factor`、`stk_limit` 权限 | `securities`、交易日历、factor file、官方涨跌停价可批量导入 |
| Day 4 | 导入涨跌停价、停复牌、ST 状态 | `ashare_trade_status` 官方字段覆盖率报告可见 |
| Day 5 | 导入沪深300/中证全指行情 | A 股回测 benchmark 不再回退常数 |
| Day 6 | 增加回测前置 QA 门禁 | 缺状态、缺 benchmark、缺复权因子时创建失败 |
| Day 7 | 扩展 LEAN 集成夹具 | 现金不足、100 股整数倍、benchmark、有费率断言 |
| Day 8 | 增加 run fingerprint | 报告和 `backtest_runs` 保存 git commit、dirty flag、data hash、Docker image digest |
| Day 9 | 建立小股票池回归样本 | 20 只股票、3 年回测结果可重复 |
| Day 10 | Paper Replay 单命令链路 | 生成信号、模拟订单、持仓快照、日报 |
| Day 11 | 组合约束 MVP | 最大持仓、单票权重、黑名单、现金下限生效 |
| Day 12 | 模拟盘日报模板 | 持仓、订单、拒单、净值、基准、回撤、异常完整 |
| Day 13 | 文档和 runbook | 数据导入、回测、Paper、故障处理步骤完整 |
| Day 14 | Level 3 复审 | 输出模拟盘准备度评分和剩余缺口 |

## 10. 最终判定

当前平台已经可以作为个人量化研究平台使用，但必须限定在“已导入、已 QA、口径明确”的数据范围内。  
当前不建议正式进入模拟盘，可以开始小范围影子 Paper Replay。  
当前不需要购买 iFinD、Choice 或 Wind；下一步最适合先接 TuShare Pro，并在数据治理和复现链路跑顺后再评估 RQData/JQData，最后才考虑 iFinD/Choice/Wind。
