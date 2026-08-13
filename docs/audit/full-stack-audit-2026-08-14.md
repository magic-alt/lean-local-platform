# lean-platform 全栈专业审计报告

> 审计对象：基于 QuantConnect LEAN 二次开发、接入本地 A 股行情数据的回测平台
> 审计日期：2026-08-14
> 仓库：`main` @ `38535ec`（`make parquet lake authoritative`）
> 审计方法：静态代码审计 + 分模块深度审计（6 个并行子代理）+ 测试套件实跑 + 关键证据独立复核
> 本报告为全新独立审计，结论与既有 `docs/audit/` 历史审计互相印证但独立形成。

---

## 1. 执行摘要

平台整体成熟度**高**：这是一套有清晰分层、有强证据门禁、有 53 个版本化迁移、94 个测试文件、端到端可复现指纹的严肃工程系统，远超一般"二次开发"项目的完成度。**认证、SQL 注入防护、容器隔离（镜像摘要白名单 + `cap_drop ALL` + `network none` + 只读根文件系统 + 符号链接逃逸防护）、幂等性、不可变账本、PIT 成分股治理、A 股交易规则建模**等关键能力均达到生产级水准。

但本次审计发现 **1 个 Critical、约 9 个 High、约 25 个 Medium** 等级的问题，主要集中在四类风险：

1. **回测正确性（研究结论的可信度）**：回测收益率用"前复权/总回报"口径，基准却用"未复权价格指数"口径，系统性高估相对收益；退市日期在证券主数据更新时被无条件覆盖/清空，破坏幸存者偏差过滤；多数单标的策略模板使用"当日信号 + 当日市价单"而非平台自己主推的"次日开盘成交"模型，存在执行模型不一致与潜在的前视/乐观成交偏差。
2. **运行期可靠性**：生产（委托）模式下"取消"无法真正停掉 LEAN 容器；`run_id` 仅秒级精度、无熵，批量并发下会主键冲突；`running` 状态回测永不对账；崩溃后租约 TTL 最长阻塞调度槽位约 2 小时。
3. **安全与数据治理**：CSV 上传存在文件名路径穿越（可写任意文件）；第三方 provider 密钥明文入库；数据库/Redis 使用可预测默认凭据、Redis 无持久化/内存上限（单点故障）。
4. **性能与可观测性**：报告列表存在每行一次额外查询的 N+1；多个列表接口全量拉取后在 Python 内分页；MySQL 4G 缓冲池塞进 6G 容器且无 `max-connections`（正是其 Runbook 自述的 OOM/1040 故障模式）；Prometheus 仅导出 6 个指标、Grafana 仅 3 块面板，Runbook 依赖的队列深度/资源压力等核心信号根本未被采集。

此外，测试套件当前**并非全绿**：完整运行 `657 passed, 2 failed, 2 skipped`，2 个失败来自"默认结束日期"测试的跨沪市午夜边界竞态（详见 §8.2）。

历史认证状态（非本次新增结论）：`docs/audit/final-seal-certification-2026-08-04.md` 判定 `NOT_CERTIFIED / LEVEL5_FAIL`，遗留 P1×3 + P2×1；`docs/roadmap.md` 冻结生产边界为"本机单机 A 股日频 Research / LEAN 回测 / 优化 / 报告 / Paper 账户"，跨资产、实盘、分钟/Tick、不完整 PIT 均 fail-closed。

---

## 2. 审计范围与方法

| 维度 | 覆盖内容 |
| --- | --- |
| 架构 | 组件边界、主链路（回测/研究/优化/Paper/数据同步）、存储所有权、失败恢复边界 |
| 后端功能 | `web/backend/app/api`（约 30 路由）、`services`（约 150 服务）、`repositories`、认证中间件、幂等、错误语义 |
| 数据管线 | TuShare 接入、Bronze/Silver/Gold Parquet 湖、PIT、同步/校验/质量门禁、复权语义 |
| LEAN 执行 | `runners/`、`lean_engine/`、Celery `tasks/`、runner-service、调度租约、取消、恢复、Paper 账本 |
| 前端功能 | React 19 + Antd 6 + ECharts 6 + Monaco，全部页面、API client、轮询、错误处理、包体 |
| 策略 | 18 个策略模板、`ashare_execution` 交易规则、策略准入、实验泄漏检测、可复现性 |
| 性能/基础设施 | `docker-compose.yml` 资源与健康检查、MySQL 53 迁移/索引、Redis/Celery、可观测性、备份/DR、SLO |
| 测试 | 94 个测试文件、迁移测试、集成测试门控、测试隔离性 |

方法：以"证据 + 严重度 + 建议"为单位，逐条给出 `文件:行号` 证据；对高风险结论（CSV 路径穿越、基准复权口径、前端轮询、`run_id`、取消链路）由主代理独立复核代码确认。

---

## 3. 风险清单总表（按严重度）

| ID | 严重度 | 领域 | 问题 | 关键证据 |
| --- | --- | --- | --- | --- |
| SEC-01 | **Critical** | 安全 | CSV 上传文件名未净化，可路径穿越写任意文件 | `api/data.py:847-849` |
| DATA-01 | **High** | 数据正确性 | 回测(前复权/总回报) vs 基准(未复权价格指数) 口径不一致，系统性高估 alpha | `lean_engine/data_paths.py:224`；`services/benchmark.py:105,133` |
| DATA-02 | **High** | 数据正确性 | 退市日期被无条件覆盖/置空，破坏幸存者偏差与 PIT 过滤 | `services/ashare_repository.py:342`；`services/csi300_pit.py:1027-1034` |
| RUN-01 | **High** | 可靠性 | 委托模式下"取消"无法停止 LEAN 容器 | `services/backtest_service.py:381-385`；`runner_service.py` 无 `/stop` |
| RUN-02 | **High** | 可靠性 | `run_id` 秒级精度且无熵，并发下主键冲突 | `lean_engine/ids.py:7-8` |
| PERF-01 | **High** | 性能 | 报告列表每行一次额外 DB 查询（N+1） | `api/reports.py:251-271,73-95` |
| STRAT-01 | **High** | 策略正确性 | 单标的模板"当日收盘信号+当日市价单"，与平台 next-open 标准不一致 | 各模板 `body.py` + `services/ashare_execution.py:342,353` |
| FE-01 | **High** | 前端 | Monaco 编辑器从 CDN 加载，离线/断网即失效 | `pages/core.tsx:42`；`pages/operations.tsx:33` |
| INFRA-01 | **High** | 基础设施 | MySQL 4G 缓冲池进 6G 容器且无 `max-connections`，OOM/1040 | `docker-compose.yml:36-58` |
| INFRA-02 | **High** | 基础设施 | Redis 单实例，无 `maxmemory`/AOF/密码，最高风险 SPOF | `docker-compose.yml:12-25` |
| B-01 | Medium | 后端 | `POST /api/backtests` 裸 `except` 吞异常转 200 失败 | `api/backtests.py:155-161` |
| B-02 | Medium | 后端 | 订单列表无界 + 每行 6 个相关子查询 | `services/paper_accounts.py:2915-2956` |
| B-03 | Medium | 后端 | 列表接口全量拉取后 Python 分页（无 SQL LIMIT） | `repositories/backtest_repository.py:50-104` |
| B-04 | Medium | 后端 | 证券主数据非批量导入，逐行开连接 | `api/ashare.py:136-154`；`ashare_repository.py:243-273` |
| B-05 | Medium | 后端 | `create_backtest_job` 文件系统+DB 非原子 | `services/backtest_service.py:169-272` |
| B-06 | Medium | 安全 | 第三方 provider 密钥明文持久化到任务参数 | `api/data.py:795-810,340-348` |
| RUN-03 | Medium | 可靠性 | `running` 状态回测永不对账 | `tasks/worker.py:1233`；`services/run_reconciler.py:115-119` |
| RUN-04 | Medium | 可靠性 | 租约 TTL=`timeout+600s`，崩溃后阻塞槽位约 2h | `tasks/worker.py:1266-1272` |
| RUN-05 | Medium | 可靠性 | 取消/成功 TOCTOU，迟到的成功写覆盖 CANCELLED | `tasks/worker.py:1483-1490`；`repositories/backtest_repository.py:127` |
| RUN-06 | Medium | 可靠性 | Paper 周期重入把"已在运行"误判为硬失败 | `services/paper_accounts.py:1477-1488` |
| RUN-07 | Medium | 可靠性 | Research(Jupyter) `--network none` + 端口发布不可达 | `lean_engine/research.py:154-180` |
| DATA-03 | Medium | 数据正确性 | 缺 bar 被静默重分类为"停牌" | `services/data.py:889-903` |
| DATA-04 | Medium | 数据正确性 | `adj_factor` 缺失时因子文件静默回退未复权 | `services/lean_cache.py:310` |
| DATA-05 | Medium | 数据治理 | 非 bar 数据集校验仅为 advisory、不阻断 | `services/data_sync.py:4392-4408` |
| DATA-06 | Medium | 数据治理 | "已认证"源可仅凭文件存在满足 | `services/source_gate.py:390-416,495-497` |
| DATA-07 | Medium | 数据治理 | 冷启动双存储布局，首写落通用布局、与文档不一致 | `services/market_lake.py:972,150-157` |
| DATA-08 | Medium | 数据正确性 | PIT 成员为空时用最新指数权重回填（当前成分回填，仅 logged 不 blocked） | `services/csi300_data_pipeline.py:253-267` |
| STRAT-02 | Medium | 策略正确性 | `RAW` 未复权价用于动量/排序，除权除息扭曲 | `dynamic_universe/body.py:17,21` 等 |
| STRAT-03 | Medium | 策略准入 | gap 模板的 4 个准入门永不被生成 → 永不通过 | `gap_buy_ashare_next_open/manifest.json`；`backtest_execution_validation.py` |
| STRAT-04 | Medium | 策略准入 | 准入不校验 dataset 版本身份 | `services/strategy_admission.py:163-171` |
| STRAT-05 | Medium | 策略正确性 | US/加密/期货基准自指（用交易标的自身） | `services/strategies.py:130` |
| FE-02 | Medium | 前端 | 运行期 1s 轮询重拉全量图表+结果 | `pages/core.tsx:2438-2442,2395-2399` |
| FE-03 | Medium | 前端 | `api.backtests()` 上限 100，导致统计错误 | `api/index.ts:350-351` |
| FE-04 | Medium | 前端 | 约 218 行不可达死代码 | `pages/core.tsx:3123` |
| INFRA-03 | Medium | 可观测性 | 仅 6 个 Prometheus 指标、3 块面板，无队列/资源指标、无 Alertmanager | `observability/metrics.py`；`docker/grafana` |
| INFRA-04 | Medium | DR | RPO 15min 声明 vs 每日明文逻辑备份、无 binlog/加密/异地 | `config/operational-slo.yaml:66-75` |
| INFRA-05 | Medium | 架构 | 基础 schema 无外键；SQLite DDL 正则转 MySQL | `app/db.py` |
| 若干 | Low/Info | 各领域 | 散见 §5.3/§6.2/§7.2/§8.2/§9.2/§10.2/§11，含 cookie `secure=False`、默认凭据、CSV 公式注入、`chartPointLimit` 未降采样、`any` 滥用、死代码、`data.zip` 12GB 未忽略等 | — |

> 上表为最高优先级问题的压缩视图；完整分维度描述见 §4–§11，完整 Low/Info 项散见 §5.3/§6.2/§7.2/§8.2/§9.2/§10.2/§11。

---

## 4. 架构审计

### 4.1 总体评价：良好

架构边界清晰、文档与代码一致度高：

- **分层正确**：`api/`（仅校验与委派）→ `services/`（业务）→ `repositories/`（持久化）→ `runners/lean_engine/`（LEAN 执行），`architecture/state_ownership.py` 用机器可读方式声明"规范表唯一写者"，并有架构测试拒绝第二写者。
- **存储所有权正确**：Parquet 是行情时序事实层，MySQL 是控制平面事实层，SQLite 仅测试；`stored_objects` 为对象归档，`web/runtime` 为可重建缓存。这与 `docs/architecture.md`、`docs/data_pipeline.md` 完全对应。
- **命令/查询分离**：Paper 有 `paper_account_commands.py` / `paper_account_queries.py` 门面，写路径与读路径边界清晰。

### 4.2 架构问题

- **INFRA-05（Medium）— 无外键 + 正则方言翻译**：基础 schema（`db.py`）大量表未声明外键，参照完整性只靠少量新迁移（`0040`/`0046`）后补；且 DDL 由 SQLite 语法经正则（`?`→`%s`、`ON CONFLICT`→`ON DUPLICATE KEY`、`min(`→`least(`）翻译到 MySQL（`db.py:591-642`）。对覆盖到的形态可用，但对嵌套表达式等复杂形态脆弱，类型也不安全。长期建议迁移到 SQLAlchemy Core 或显式 query builder。
- **单体大文件**：`services/data_sync.py`(~249KB)、`services/paper.py`(~125KB)、`services/paper_accounts.py`(~135KB)、`app/db.py`(~74KB) 职责过重，不利于评审与测试。
- **发布边界冻结清晰（优点）**：跨资产=research/preview only、实盘=disabled、分钟/Tick=disabled、不完整 PIT=fail-closed，这些是"部署边界"而非"待补能力"，避免了以回退引擎或合成数据蒙混。这一工程纪律值得肯定。

---

## 5. 后端功能、API 与安全

### 5.1 优点

- **认证扎实**：全局中间件覆盖 `/api/*`、`/metrics`、`/openapi.json` 等；`secrets.compare_digest` 常量时间比较（`main.py:221-223`）；未配置 token 时 fail-closed 返回 503（`main.py:209-216`）；浏览器会话 cookie 由操作员 token 经 HMAC 派生、`HttpOnly + SameSite=Strict`（`main.py:49-56,192-201`）。无路由绕过。
- **错误语义一致**：统一信封（`detail`/`error_code`/`category`/`retryable`/`trace_id`/`workflow_id`），`DatabaseUnavailableError` 正确映射 `503 DATABASE_UNAVAILABLE + Retry-After:10`（`core/errors.py:44-84`；`main.py:297-312`）。
- **幂等真实有效**：payload 摘要 + DB 唯一键 + 完成响应重放 + 409 冲突 + ≥500 放弃（`services/api_idempotency.py`；`main.py:59-147`）。
- **SQL 注入防护到位**：全部查询参数化；表/列名仅来自固定 allowlist；路径包含用 `ensure_child_path`、报告根目录白名单、工件名守卫。

### 5.2 安全发现

- **SEC-01（Critical）— CSV 上传路径穿越**：`api/data.py:847` 用 `UPLOADS_DIR / f"{ts}-{file.filename}"` 拼接原始 multipart 文件名并 `write_bytes`（`:849`）。文件名形如 `../../../../etc/cron.d/x` 可逃逸上传目录、以服务进程用户写任意内容。`put_file` 只使用 `upload_path.name`，对象存储安全，但**文件写入本身不安全**。修复：`Path(file.filename).name` + 严格字符白名单。
- **B-06（Medium）— provider 密钥明文入库**：`api/data.py:795-810` 将 `request.apiKey` 写入任务参数、`create_task` 持久化到 `tasks.parameters_json`；按需下载路径持久化整个 `apiParameters`（`:340-348`）。第三方密钥落库明文。修复：持久化前脱敏或外置存储。
- **Low — cookie `secure=False` 硬编码**（`main.py:199`）：TLS 反代后凭据 cookie 会明文传输。建议从配置派生。
- **Low — 可预测默认凭据**：`core/config.py:71` 等内置 MySQL/ClickHouse `lean/lean`、Grafana `admin/admin` 默认值，若操作员未设置环境变量即为生产凭据。建议非本地环境强制显式。
- **Low — CSV 导出无公式注入防护**（`api/research.py:196-209`、`api/optimization.py:290-299`）：以 `=`/`+`/`-`/`@` 开头的单元格在表格软件中可执行。建议前缀转义。

### 5.3 功能/正确性发现

- **B-01（Medium）— `POST /api/backtests` 吞异常**：`api/backtests.py:155-161` 用裸 `except Exception` 把任何异常包装为 200 + 持久化失败回测。真实服务故障被伪装成正常响应，基于 HTTP 状态的告警永不触发，客户端无法区分用户错误与基础设施故障。建议收窄到特定领域异常、其余放 5xx。
- **B-05（Medium）— 创建回测非原子**：`services/backtest_service.py:169-272` 先 `shutil.copytree`/快照写文件、再 `create_task` 插入，`backtest_runs` 插入在后。中途失败会留下孤儿目录或孤儿 `tasks` 行。建议补偿清理或单一事务边界。
- **Low — preflight 全部失败硬编码 `retryable=True`**（`api/backtests.py:192-201`）：永久性校验失败也会被无限重试。
- **Low — 分页信封不一致**：部分接口返回 `PageEnvelope`，部分返回裸数组，部分在 Python 内切片（`api/common.py:20-38`）。

---

## 6. 数据管线与数据正确性

### 6.1 优点

- **PIT 治理真实**：CSI300 官方 PIT 自 2005-04-08 重建，禁止用当前成分回填历史；`startDate`/`endDate` 过滤 + `announce_date <= effective_date` 的基本面 PIT；幸存者偏差方面，退市名称被纳入日线回填。
- **发布原子性**：临时分区 + `os.replace` 原子发布、内容哈希不可变修订、幂等 diff、Redis Lua 限流 + 有界并发、可取消/可恢复 checkpoint。
- **读取边界清晰**：`source=parquet`/`source=duckdb`，移除的 `mysql`/`database`/`local` 别名 fail-closed；预览不因打开页面而调用 provider。

### 6.2 数据正确性发现（重点）

- **DATA-01（High）— 回测与基准复权口径不一致**：策略数据经因子文件 `price_factor = factor / latest_factor` 归一化到最新（前复权/总回报口径，`lean_engine/data_paths.py:224`），而 CSI300 基准以 `adjust="raw"` 导入（`services/benchmark.py:105,133`）——是**未复权价格指数**（不含分红收益）。二者相减，相对收益被系统性高估约等于基准股息率（CSI300 年化约 2–3%）。修复：基准改用总回报口径，或统一为同一复权基准。
- **DATA-02（High）— 退市日期被擦除**：`upsert_security` 无条件覆盖 `delisted_date`（`services/ashare_repository.py:342`），且 CSI300 PIT 物化器传 `delisted_date=None`（`services/csi300_pit.py:1027-1034`），会清空真实退市日期、把退市股重新标记为"上市中"，**直接破坏幸存者偏差/PIT 过滤**。修复：退市日期只在源提供时更新、缺失不得覆盖。
- **DATA-03（Medium）— 缺 bar 静默重分类为停牌**（`services/data.py:889-903`）：缺失数据可能被当成停牌，掩盖数据缺口。
- **DATA-04（Medium）— `adj_factor` 缺失静默回退未复权**（`services/lean_cache.py:310`）：复权因子缺失时因子文件静默退化为未复权，回测结果口径在无告警情况下改变。
- **DATA-05（Medium）— 非 bar 数据集校验不阻断**（`services/data_sync.py:4392-4408`）：校验为 advisory，坏数据可继续进入下游。
- **DATA-06（Medium）— "已认证"可仅凭文件存在满足**（`services/source_gate.py:390-416,495-497`）：文件在场即可能通过信任门，弱化"逐源哈希 + QA + DuckDB 可读性"证据链。
- **DATA-07（Medium）— 冷启动双存储布局**：`market_lake.py:972` 仅在 `silver/daily/current/trade_date=*/` 目录已存在时才走原生分区路径（`_native_available` 是目录存在性检查，`:150-157`）。全新安装的首批股票 bar 会落到通用 `year=/release=/part-*.parquet` 布局，列名（`vol` vs `volume`）与文档 `data_pipeline.md:22` 不一致，且随部署历史分叉。建议首写前显式引导创建原生根目录，或对受支持 scope 移除通用回退。
- **DATA-08（Medium）— PIT 成员为空时用最新指数权重快照回填**（`services/csi300_data_pipeline.py:253-267`，源 `tushare:index_weight:current`）：仅 forward（`start_date=end_date`）、不会在该日期前泄漏，但这是文档明令禁止用于生产信任的"当前成分回填"，仅记日志（`universe_materialized_from_latest_index_weight`）而非阻断。
- **Low — "无损 Bronze"实为归一化**：Bronze `daily` 经 `_native_patch` 已重命名列并把 `volume`×100、`amount`×1000（`tushare_adapter.py:996-997`；`market_lake.py:798-826,891-911`），`vol` 列是股数而非 TuShare 手数，任何按 TuShare `vol` 语义消费会读成 100 倍；真正无损字节只在 gzip `provider_raw_archives`。文档高估了 Bronze 保真度。
- **Low — 全湖扫描**：`candidate_symbols`（`universe_certification.py:38-56`）、`_source_coverage`（`provider_certification.py:41-58`）、`_latest_bars_by_symbol`（`data_sync.py:2026+`）无 `trade_date` 谓词，每次 universe/认证调用都 O(全湖)。
- **Info — 其余小项**：限流本地回退为进程级（Redis 不可用时多 worker 合计可能超配额，`tushare_rate_limit.py:89-106`）；重试退避线性无抖动（`data_sync.py:679-689`）；`AkshareAdapter`/`JqDataAdapter` 有装饰性 `production_certified=True`（`provider_adapters.py:87,134`，真实门为 `PRODUCTION_SOURCES={tushare}`）；ClickHouse `ReplacingMergeTree` 去重键缺 `source`（`market_data.py:171-173`）；`previous_trade_date` 无近 14 天开市日时回退到自然日而非交易日（`csi300_pit.py:884-890`）；B 股（`200%`/`900%`）被静默排除且未文档化（`data_sync.py:1995-1996`）。

---

## 7. LEAN 执行、Celery 编排与可靠性

### 7.1 优点（隔离与完整性，属本报告最强项之一）

- **镜像摘要白名单**：拒绝非 `ALLOWED_LEAN_DOCKER_IMAGES` 或非 `@sha256:` 的镜像，worker 与 runner 双侧校验（`lean_engine/docker.py:30-36`）。
- **容器加固**：`--cap-drop ALL`、`no-new-privileges`、`--pids-limit`、`--cpus/--memory`、`--tmpfs /tmp:rw,noexec,nosuid`、可选 `--read-only`；策略源码进 `noexec,nosuid,nodev` tmpfs 后再 `exec dotnet`。
- **网络 fail-closed**：`LEAN_DOCKER_NETWORK=none` 为默认，非 `none` 时 runner 拒绝任务（`runner_service.py:147-148`）。
- **Docker socket 收敛**：仅 `lean-runner` 挂 `/var/run/docker.sock`，且该服务自身 `read_only` + `cap_drop ALL` + `pids_limit:128` + `mem_limit:512m`。
- **挂载白名单 + 符号链接逃逸检查**（`runner_service.py:124-139,174-175`）。
- **Paper 账本**：intent/fill/checkpoint 幂等键与摘要、6 个摘要保护 checkpoint、只插不改账本、乐观 `version` + `LEGAL_TRANSITIONS` 状态机。
- **调度租约**：`unique(resource, holder_id)` + `unique(resource, slot_index)` insert-and-catch 串行化。

### 7.2 可靠性发现

- **RUN-01（High）— 委托模式取消无效**：`cancel_backtest` 调 `DockerRunner.stop_container` 包在 `try/except: pass`（`services/backtest_service.py:381-385`）；`stop_container` 依赖本地 `docker` CLI（`runners/docker_runner.py:124-136`），而 Compose 拓扑中仅 `lean-runner` 有 socket/CLI。`runner_service.py` 未暴露 `/v1/jobs/{id}/stop`（只有 research 有 stop）。`celery control.revoke(terminate=True)` 杀掉 worker 进程，但 lean-runner 仍同步运行容器直到 `timeoutSeconds`（默认 7200s）。**用户点了取消，容器继续烧 CPU/内存/写盘。** 修复：新增鉴权 `POST /v1/jobs/{run_id}/stop` 并让 `cancel_backtest` 走 runner RPC。
- **RUN-02（High）— `run_id` 无熵冲突**：`new_run_id = f"{symbol}-{start}-{end}-{time:%Y%m%d%H%M%S}"`（`lean_engine/ids.py:7-8`），作为 `backtest_runs.id` 主键、容器名、运行目录。实验批量 fan-out 或多账户同标的同秒启动会撞主键（未捕获 → 500）或同容器名"already in use"。修复：追加 `uuid4`/单调后缀。
- **RUN-03（Medium）— `running` 回测永不对账**：`run_backtest_task` 无 `acks_late`（`tasks/worker.py:1233`），`run_reconciler` 只处理 research/paper 孤儿、不碰 `backtest_runs`（`services/run_reconciler.py:115-119`）。worker 崩溃后行永远 `running`。修复：新增 beat 对账器。
- **RUN-04（Medium）— 租约 TTL 过长**：`ttl=timeout+600`（默认 7800s），清理只删过期租约和"持有者为终态"的租约（`services/scheduler.py:42-56`）。崩溃 worker 的行仍是 `running`，其租约不被回收，`maxConcurrentJobs=1` 下阻塞约 2 小时。
- **RUN-05（Medium）— 取消/成功 TOCTOU**：终态写 `update_backtest` 无 `WHERE status='running'` 前置条件（`repositories/backtest_repository.py:127`），取消若落在检查后、写前，会被迟到成功覆盖。修复：状态前置条件写。
- **RUN-06（Medium）— Paper 重入误判**：`acks_late + reject_on_worker_lost` 重投后，`begin_cycle` 把"该日已排队/运行中"异常归类为非 `waiting_data` → `fail_cycle`（`services/paper_accounts.py:1477-1488`）。瞬时 worker 抖动可能把健康周期打成 `failed`。修复：视为幂等 no-op。
- **RUN-07（Medium）— Research 不可达**：Jupyter 容器 `--network none` 且同时 `-p 127.0.0.1:{port}:8888`（`lean_engine/research.py:154-180`）。`none` 网络下端口发布无 veth/NAT 目标，返回的 URL 浏览器无法访问——功能静默失效。修复：显式文档化/禁用，或换受控 bridge + 仅 loopback 发布。
- **Low — 租约获取与释放 try/finally 之间有窗口**（`tasks/worker.py:1266-1283`）：`:1279-1282` 的日志/状态写若抛错会漏租约。
- **Low — `finalize_cycle` 并发双 finalize**：仅对 `succeeded` 提前返回，`finalizing` 与"慢 finalize + 120s 恢复"重叠会重复插入 `no_signal` 违反唯一约束。
- **Info — beat 调度文件在 tmpfs**（`docker-compose.yml:570,608`）：重启后所有周期任务重发一次（因任务幂等尚可容忍）。

---

## 8. 前端功能、性能与 UX

### 8.1 优点

- 包体控制好：`dist` 总 2.6MB，`vendor-echarts`(708K)/`docs`/`paper-accounts`/`insights`/`research` 等已懒加载分包。
- 竞态防护到位：`currentRunId.current` 请求序列守卫、`reloadInFlight` 去重、每 Tab 错误边界；`setInterval` 均正确清理。
- XSS 清洁：无 `dangerouslySetInnerHTML`，Markdown 用 `skipHtml`；无硬编码密钥；幂等键 + 重试 + 类型化 `ApiError` 封装好。
- 认证链路正确：生产由 FastAPI 直接服务前端 HTML 并下发 `SameSite=Strict` HttpOnly 会话 cookie，浏览器同源自动携带（`main.py:192-201`），**无需前端显式传凭据**（此前审计中"API client 未带凭据"并非缺陷）。

### 8.2 前端发现

- **FE-01（High）— Monaco 从 CDN 加载**：`@monaco-editor/react` 未配本地 `monaco-editor` 依赖、未 `loader.config`（`pages/core.tsx:42`、`pages/operations.tsx:33`）。编辑器离线失效，且每次会话拉第三方脚本。
- **FE-02（Medium）— 运行期 1s 轮询重拉全量**：`setInterval(reload, 1000)`（`pages/core.tsx:2438-2442`）中 `reload()` 每次重下 `chartData` + `backtestResult` + `screening`（`:2395-2399`）。虽有去重/竞态守卫，但长时间运行会持续重载全量图表+结果 JSON。建议轮询轻量状态、仅在状态变化/完成时拉重数据。
- **FE-03（Medium）— `api.backtests()` 上限 100**（`api/index.ts:350-351`）：dashboard/reports/projects 的计数与"最新"统计失真。
- **FE-04（Medium）— 约 218 行死代码**：`OptimizationPage` 提前 return（`pages/core.tsx:3123`），`:3124-3339` 的第二套优化/组合/对比 UI 不可达。
- **Medium — 约 24 个 API client 方法无 UI 调用**（因子评估、期货连续、可转债、对象存储、数据契约、PIT 成分等）：前后端功能面漂移，暗示后端功能未闭环到 UI。
- **Medium — 4 处 submit handler 缺 try/catch**（`operations.tsx:95,344`；`core.tsx:1088`；`research.tsx:589,609`）：静默未处理 rejection。
- **Low — `chartPointLimit` 仅存于设置、前端不降采样**（`config/defaults.ts:18`；`operations.tsx:372`）：无任何图表代码读取该值做 LTTB/抽样，大分钟级序列整段绘制。
- **Info — `useAsyncData` 无 `AbortController`**（`hooks.ts:64-93`）：卸载只移除监听，in-flight promise 结束后仍可能 `message.error`；全局缓存按 loader 弱引用取条目，当 loader 身份在渲染间变化时存在潜在写偏（当前均为稳定模块函数，未触发）。
- **Info — `DataPage` 残留已移除同步功能的死列**（`core.tsx:1557-1560,1707-1748`）：`syncItem` 恒为 `undefined`，进度/checkpoint 列永远走"可直接读取"分支。
- **Info — `any`/`Record<string, any>` 在热路径约 41 处**（表单 handler、图表 option 构造、`api/types.ts` 的 `summary`/`bestRun` 等）：类型安全被削弱，`OptimizationCenter`/`paper-accounts` 依赖 `as any` 强转。
- **Low — ECharts options 未 memo**（`components.tsx:305-413`；`charts/backtestAsset.ts:59`）：每次渲染重建。

---

## 9. 策略与 A 股交易规则

### 9.1 优点

- **A 股交易规则建模正确且真正接线**（`services/ashare_execution.py`）：费用模型（佣金 0.0001/最低 5 元、卖出印花税 0.0005、过户费 0.00001）、滑点（含参与度模型）、T+1（`buy_dates` 日期键 + 成交当日禁卖）、100 股整手取整、停牌/ST/涨跌停拒绝、次日开盘成交模型对一字涨跌停开盘取消成交。
- **PIT 与 warm-up 纪律**：绝大多数模板 `has_fresh_data`（拒绝前向填充）+ `is_warming_up` + `.is_ready`；`ashare_trend_pullback_portfolio` 用逐日 PIT 复权因子修正 OHLC（`body.py:410-413`），是唯一"收盘信号→次日开盘 MOO 成交"的日频模板。
- **可复现性**：策略确定性无 RNG；`canonical_result_sha256` 剔除不确定字段；参数/快照用排序键规范 JSON 哈希。

### 9.2 策略发现

- **STRAT-01（High，需核实执行时点）— 单标的模板"当日收盘信号 + 当日市价单"**：`sma_cross`/`ema_cross`/`macd`/`rsi_reversion`/`bollinger_reversion`/`donchian_breakout` 等模板读取当前 bar 收盘（已折叠进指标）后即 `market_order`/`set_holdings`（`services/ashare_execution.py:342,353`）。平台自建了 `ashare_no_same_bar_signal_fill` 准入门、且 trend-pullback/gap 模板明确用 next-open，却未覆盖这些简单模板。**关键点**：LEAN 对日频 `market_order` 的实际成交时点（当前收盘 vs 下一数据点）需要以真实成交报告核实；无论结论如何，这些模板与平台 next-open 标准不一致、存在潜在乐观成交偏差，应统一为 `market_on_open_order`/`target_percent_moo` 并显式声明成交假设。
- **STRAT-02（Medium）— `RAW` 未复权价用于排名**：`dynamic_universe` 用 `DataNormalizationMode.RAW` 算 `self.roc`（`body.py:17,21`）；`ashare_index_screening` 用原始 `data[symbol].close` 算 SMA/RSI/波动率；`turning_point`/`etf_rotation`/`risk_parity` 亦然。除权除息在回看窗口内制造假跳变、扭曲动量/波动率排名。修复：用复权价或像 trend-pullback 那样乘 PIT 复权因子。
- **STRAT-03（Medium）— gap 模板准入门永不通**：manifest 声明 4 个门（`ashare_intraday_data_coverage`/`ashare_no_same_bar_signal_fill`/`ashare_t_plus_one`/`ashare_partial_fill_volume_cap`），但 `backtest_execution_validation.py` 从未生成这 4 个门（只对中国权益生成 `no_short`/`cash_account`，对 trend-pullback 生成 `next_open`/`t_plus_one`），故 `_assert_admission_eligible` 永远拒绝。事实 fail-closed，但 `admissionEligible: true` 具误导性。修复：实现门，或标记 `admissionEligible: false`。
- **STRAT-04（Medium）— 准入不校验数据集身份**：`_load_run` 只选 `strategy_version_id`/`parameter_hash`、不含 `dataset_version_id`（`services/strategy_admission.py:163-171`）。两次不同数据快照（如修正后的 PIT/基本面）会被当"同一参数集"。修复：准入一致性加入 dataset 版本/快照 sha。
- **STRAT-05（Medium）— 非中国/港基准自指**：US/加密/期货用 `set_benchmark(lambda: self.securities[self.symbol].price)`（`services/strategies.py:130`），`buy_hold` 对 SPY 的 alpha≈0 是构造出来的；`etf_rotation` 等基准取第一个 universe 标的而非真实指数。修复：默认 SPX 等真实指数。
- **Low — `buy_hold` 被阻断不重试**（`body.py:5-7`）：无条件置 `has_bought=True`，忽略 `target_percent` 返回值；首 bar 停牌/涨停即永久持币。
- **Low — `next_open_gap_buffer_bps` 默认 2000bps（20%）**（`ashare_execution.py:184,310-313`）：MOO 买单现金预留 `1.20×`，严重欠配资金且未在 manifest 暴露。
- **Low — `gap_buy_ashare_next_open` 无 warm-up**：自门控需 ~110 根 bar，静默截断起始窗口。
- **Info — 准入阈值偏松**（`min_sharpe=0.20`/`min_calmar=0.15` 等，`strategy_admission.py:46-52`），易被优化过拟合样本通过。
- **Info — `dynamic_universe` 等权 + 100 股整手**：`0.95/len(selected)` 在 A 股大 universe 下常产生不足 100 股 → 实际空仓；`topN` 在 equal 模式被忽略（`body.py:37-46`）。
- **Info — LLM agent 输出未设 seed/temperature**（`ashare_tech_agents.py`）：研究类报告可接受，但不可复现，建议文档化。

---

## 10. 性能、基础设施与可观测性

### 10.1 性能发现（后端）

- **PERF-01（High）— 报告列表 N+1**：`api/reports.py:251-271` 每行调用 `_backtest_report_from_rows` → `_stored_objects_for_run`（每次新开 `db()` 连接查 `stored_objects`）。500 行 ≈ 500 次额外往返。修复：单条按 `run_id` 分组的 `WHERE namespace='backtest-results'` 查询。
- **B-02/B-03（Medium）— 无界列表 + Python 分页**：`list_orders` 6 个相关子查询 + 状态过滤在 Python 内做、无 `LIMIT`；`list_backtests`/`list_batches`/`list_projects` 全量拉取后 `api/common.py:20-38` 切片。数据增长后这些接口会持续劣化。修复：SQL `LIMIT/OFFSET` + JOIN。
- **B-04（Medium）— 证券主数据逐行导入**：`api/ashare.py:136-154` 未用 `bulk=True`，落入 `ashare_repository.py:243-273` 逐行 `upsert_security` + `upsert_universe_membership`，每个都自开 `db()` 连接。数千只 A 股 = 数千连接/提交。已有 `executemany` 批量路径，应切过去。

### 10.2 基础设施发现

- **INFRA-01（High）— MySQL 内存失衡**：`innodb-buffer-pool-size=4G` + 容器 `mem_limit=6g`（`docker-compose.yml:36-58`），无 `max-connections`。缓冲池 + 连接开销 + 大 `max-allowed-packet=256M` 会在满载时逼近/超出 6G，触发 OOM exit 137 与 1040（Runbook 与 final-seal 审计已实际观测到该故障）。建议缓冲池降到 1–2G（SLO 文件 `operational-slo.yaml` 本身写的是 `bufferPool: 1g`）或提升容器上限并显式设 `max-connections`。
- **INFRA-02（High）— Redis 单点**：单实例，无 `maxmemory`/`maxmemory-policy`、无 AOF、无密码（`docker-compose.yml:12-25`），同时承担 Celery broker + result backend + 锁。这是全平台最高风险 SPOF。建议 AOF + `maxmemory` + 密码 + 独立 broker/backend 实例。
- **INFRA-03（Medium）— 可观测性不足**：仅 6 个 Prometheus 指标、3 块 Grafana 面板；**Runbook 依赖的队列深度、资源压力、MySQL/Redis 健康等核心信号未被导出**；无 Alertmanager。告警 Webhook 出站链路成熟，但度量采集远滞后于告警设计。
- **INFRA-04（Medium）— DR 声明与实现漂移**：SLO 声明 RPO 15min/RTO 240min、增量/binlog 15min、加密 + 独立存储（`operational-slo.yaml:66-75`），但实际是每日明文逻辑备份，无 binlog 同步、无加密、无异地。`certificationStatus: NOT_YET_PROVEN_AT_PRODUCTION_SCALE` 已自认，但应把"未满足的加密/异地"作为 P1 显式跟踪。
- **Medium — 日期列以 `varchar(32)` 字符串存储**（base schema `app/db.py`）：大量日期字段为字符串而非 MySQL `DATE` 类型，无法利用日期索引/范围优化与时间函数下推，范围比较依赖字符串序，且类型语义（时区/非法值）失去数据库层约束。
- **Medium — worker 默认并发=1 是吞吐瓶颈**（`docker-compose.yml` 的 default/data-bulk/data-lineage 队列 `--concurrency=1`）：批量同步与血缘串行处理，制约"10x 摄取目标"的扩展上限；`backtest-worker` 串行是 Python.NET 稳定性权衡（Compose 有注释说明），属合理，但数据队列串行应可提升。
- **Medium — `retention_policy.yaml` 未纳入 beat 自动执行**：保留策略（`config/retention_policy.yaml`）仅由临时脚本触发，无周期强制，存在数据/工件/日志过期清理漂移风险。
- **Low — SLO 资源预算与 Compose 默认值漂移**：`operational-slo.yaml:77-93`（mysql `bufferPool:1g`、api 1g、defaultWorker 2g、`maxConcurrentLeanJobs:2`）与 compose 默认（mysql 4G/6g、api 2g、defaultWorker 3g、backtest `concurrency=1`）不一致，建议单源化配置。
- **Info — `factor_values`/`financial_facts` 为 EAV 宽表（迁移 0045 过渡中）**：CHANGELOG 已说明 `daily_basic` 改为"一 symbol/日期一行"宽表并保留 EAV 兼容读；EAV 查询昂贵，属待收敛过渡态。
- **Low — Grafana 默认 `admin/admin`、ClickHouse `lean/lean`**（`docker-compose.yml:156-157,124-125`）：仅绑定 127.0.0.1 缓解了暴露面，但生产化时应改密（与 §5.2 默认凭据同类）。
- **Low — `data.zip` 12GB 未忽略**：仓库根 12GB `data.zip` 处于 untracked 且未被 `.gitignore` 覆盖（`data/` 因 macOS 大小写不敏感被 `/Data/` 规则意外忽略），`git add -A` 会尝试纳入。建议加入 `.gitignore` 并移出仓库根。

---

## 11. 测试审计

- **规模与门控良好**：94 个测试文件；Docker/LEAN 集成测试用 `integration` 标记默认跳过；MySQL 集成走独立 profile；`conftest.py` 为每个测试隔离 SQLite 与隔离 Parquet 湖，防止污染开发者 `data/`。
- **当前并非全绿**：完整运行 **`657 passed, 2 failed, 2 skipped`**（约 10 分钟）。
  - 2 个失败均来自 `tests/test_settings_defaults.py`：`DEFAULT_SETTINGS["defaultEnd"]` 在**模块导入时**用 `datetime.now(Asia/Shanghai)` 求值（`services/settings.py:20`），而断言在测试运行时重新求值"今天"。完整套件跨沪市午夜边界（本次实测 23:55 → 00:02 上海）时二者不同 → 失败；单独运行该文件则通过（已复核复现）。
  - 这既是**时间敏感的 flaky 测试**，也暴露一个**生产微缺陷**：长驻 API 进程跨午夜不重启时，`defaultEnd` 不会推进到新交易日（仅特殊值 `"2026-07-13"` 会被推进）。
  - 修复：`defaultEnd` 改为调用时求值（而非模块级常量），并让断言接受"导入时 vs 运行时同日期"语义。
- **覆盖率盲点**：`optimization_runs` 表在 `db.py:1373-1385` 创建又在 `:1843` 删除，无代码引用，仅为兼容旧迁移保留。

---

## 12. 优点总结（值得保留的工程资产）

1. **认证与安全纵深**：常量时间 token 比较、fail-closed、HMAC 会话 cookie、参数化 SQL、路径/工件名守卫。
2. **容器隔离**：镜像摘要白名单、`cap_drop ALL` + `no-new-privileges` + `network none` fail-closed、socket 收敛、符号链接逃逸防护、策略进 `noexec` tmpfs。
3. **Paper 账本完整性**：摘要保护 checkpoint、只增不可变账本、乐观锁状态机、命令/查询分离。
4. **PIT 与数据治理**：官方 CSI300 PIT 重建、退市名称纳入回填、原子分区发布 + 不可变修订、来源认证证据链（虽有 §6 的边角削弱）。
5. **可复现性**：运行指纹、不可变项目快照、确定性哈希、数据集/实验版本化。
6. **错误与幂等**：统一错误信封、DB 唯一键幂等、调度租约、MySQL 咨询锁。
7. **A 股交易规则**：费用/滑点/T+1/整手/涨跌停/停牌/ST 完整建模且真正接线（非仅定义）。
8. **文档与发布纪律**：`docs/` 完整、SLO/DR/发布门禁机器可读、历史审计 append-only、迁移有回滚策略、提交强制 CHANGELOG。

---

## 13. 优先整改建议（分级）

### P0（立即）

1. **SEC-01**：净化 CSV 上传文件名（`Path(file.filename).name` + 白名单）。
2. **DATA-02**：退市日期覆盖保护（缺失不得清空 `delisted_date`）。
3. **DATA-01**：统一回测与基准复权口径（基准改总回报或同口径），并重跑黄金对（Golden Pair）验证。
4. **INFRA-01/02**：MySQL 缓冲池/`max-connections` 收敛，Redis 加 AOF/`maxmemory`/密码。

### P1（尽快）

5. **RUN-01/RUN-02/RUN-03/RUN-04**：runner 增加 `/v1/jobs/{id}/stop`；`run_id` 加熵；新增 `backtest_runs` 对账器；缩短租约 TTL。
6. **STRAT-01**：单标的模板统一 next-open 执行（或显式声明成交假设），关闭同 bar 成交缺口。
6b. **DATA-08**：PIT 成员为空时不得用最新指数权重回填，改为 fail-closed（或显式阻断并保留证据）。
7. **PERF-01 + B-02/B-03/B-04**：报告/列表/订单 SQL 分页与去 N+1；证券主数据切批量。
8. **B-01**：`POST /api/backtests` 收窄异常吞并。
9. **B-06**：provider 密钥脱敏后持久化。
10. **INFRA-03/04**：补齐 Prometheus 指标（队列深度/资源/MySQL/Redis）+ Alertmanager；DR 加密/异地落实或下调 SLO 声明。

### P2（计划内）

11. 前端：本地化 Monaco、运行期轮询改轻量状态、修复 `api.backtests()` 上限、删死代码、补齐 submit try/catch。
12. 策略：`RAW`→复权价排名（STRAT-02）、gap 准入门实现或标记不可准入（STRAT-03）、准入加 dataset 身份（STRAT-04）、真实 US 基准（STRAT-05）。
13. 数据：缺 bar 停牌语义显式化（DATA-03）、`adj_factor` 缺失告警而非静默回退（DATA-04）、非 bar 校验阻断（DATA-05）、冷启动统一原生布局（DATA-07）。
14. 测试：修复 `test_settings_defaults.py` 时间边界；清理 `optimization_runs` 死表；`data.zip` 移出/忽略。

---

## 14. 附录：证据与复核说明

- **独立复核（主代理直接读码确认）**：SEC-01（`api/data.py:847-849`）、DATA-01（`data_paths.py:224` vs `benchmark.py:105,133`）、FE-02（`core.tsx:2438-2442`）、RUN-01（`backtest_service.py:381-385`）、`run_id`（`ids.py:7-8`）、认证 cookie 链路（`main.py:175-230`）、A 股规则（`ashare_execution.py` 全文）、测试失败根因（`settings.py:20` + `conftest.py` + 单文件重跑复现）。
- 其余条目为 6 个并行深度审计子代理给出、附 `文件:行号` 证据；本报告汇总时已按严重度去重并统一术语。
- 与历史审计一致性：`INFRA-01`（MySQL OOM）与 `docs/audit/final-seal-certification-2026-08-04.md` 的 `ACT-P1-002` 一致；`INFRA-04` 与其 `ACT-P1-007`（外部通道）互补但不重复；本报告新增的 `SEC-01`、`DATA-01/02`、`RUN-01/02`、`STRAT-01` 等为本次新发现，建议并入既有 issue ledger 跟踪。

---

*本报告仅基于静态代码审计与本地测试实跑，未执行生产环境压测、破坏性故障注入或外部通道验证；涉及回测成交时点（STRAT-01）与基准口径（DATA-01）的结论建议以 LEAN 真实成交报告与黄金对重跑做最终确认。*
