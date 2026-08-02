# Changelog

本文档记录用户可见行为、架构、数据和运维变更。自 2026-07-21 起，每次提交必须在 `Unreleased` 中增加一条简明记录；提交自身的 hash 不写入同一提交，Git 历史是 hash 的权威记录。

## Unreleased

- Close the remaining actual-environment P0 code gaps with fail-closed additive backtest trust, final-gate and frozen-release certificate enforcement, deterministic multi-source PIT inputs and canonical Golden Pair digests, immutable completed Walk-Forward certificates, existing-account Paper acceptance with read-only ledger replay and cohort certification, and an ordered release rollout that verifies one SHA/release ID, migration level, OpenAPI hash, frontend digest, and worker generation across the local app stack.
- Fix the four remaining 2026-08-02 actual-environment P2 findings by standardizing audited primary list envelopes and generated OpenAPI reference output, replacing obsolete Research routes, adding cursor-aware earlier/follow/terminal-stop log UI, reusing one operation ID across network retries, and enforcing command/query plus unique state-writer architecture boundaries.
- Fix the six 2026-08-02 actual-environment P1 findings with account-generation/release/TTL-bound Paper trust, resumable single-lease derived maintenance with backoff and alerts, bounded summary list APIs plus server-paged Backtest history, canonical asset capability states and fail-closed preflight, immutable Dataset Releases shared by Parquet/run lineage, and fetchable stored-object reproducibility certificates with golden-pair digests.
- Preserve Walk-Forward parent, project, validation-selection, and OOS lineage with immutable snapshots and destructive-delete guards; add durable two-account/21-session Paper certification cohorts and UI status; quarantine orphan legacy Paper facts, converge ownerless Research runs, and schedule a domain reconciler without deleting historical evidence.
- Add the 2026-08-02 actual-environment, non-destructive system audit covering architecture, Web/API contracts, governed data, LEAN backtests, experiments, Paper accounts, scheduling, commercial-product gaps, remediation waves, and machine-readable evidence without backups, restores, isolated stacks, or full data reimports.
- Load complete index history into Data Preview candlestick charts so the initially recent window can be dragged to earlier dates, and remove redundant archive and local-source notices from the index list view.
- Fix Data Preview by reading complete canonical index history instead of the latest incremental archive, synchronizing the common A-share benchmark indices including `000001.SH`, normalizing non-finite index values before MySQL writes, making futures/options lifecycle preview states explicit, and skipping the unrelated full A-share legacy audit during targeted index/contract refreshes.
- Add a daily-bar-only gap event study that keeps sector proxies separate, uses exchange `prev_close`, standardizes gaps by prior volatility, reports low-open recovery and high-open giveback from OHLC, excludes company-action flags, and labels daily volume ratios as post-open descriptive data without claiming minute-path, VWAP, or fill-time evidence.
- Add an executable A-share PIT trend-pullback portfolio template for CSI300/500/1000 and STAR50 with A/B/C scoring variants, immutable adjustment/liquidity/industry/fundamental input snapshots, weekly close signals and next-open MOO fills, portfolio/turnover/capacity controls, structured decision artifacts, admission gates, and Paper-compatible cumulative replay.
- Add a point-in-time TuShare Pro A-share orderly-pullback candidate study with governed full-market preparation, 500-session path-risk and liquidity screening, A/B/C/Reject audit trails, asynchronous Research runs, reproducible HTML/CSV/Parquet artifacts, frozen run snapshots, and a Notebook case template.
- Add a reproducible TuShare Pro bank/insurance rotation study with daily, weekly, and monthly absolute-direction, relative-defense, threshold, HAC, rolling, winsorized, extreme-month exclusion, sample-window, data-quality, and HTML-report validation.
- Add a research-only CSI300 PIT cross-sectional ML workflow with governed TuShare historical-union preparation, 32 causal price/valuation/financial features, next-open five-day excess-return labels, purged walk-forward LightGBM ranking, a frozen final holdout, content-addressed Parquet artifacts, separate MLflow/MySQL tracking, an isolated `ml` worker, API/UI progress and quality diagnostics, and explicit blocking of unfinished LEAN signal export.
- Make index codes in Data Preview open their local daily candlestick chart, restrict futures and options Preview to contracts currently inside their listed trading lifecycle, and add a detailed options data, payoff, risk, expiry, and execution-boundary guide.
- Merge the generic structured Insight workflow into A-share Technology Daily, remove its routes, services, UI, tasks, tables, and stored data, and add selectable configured Provider/model pairs (including DeepSeek flash/pro on one key), immutable editable six-stage Prompt versions, a published schedule profile, full-pool per-stock candidate signals with server guardrails, structured stage/stock rendering, and provider-aware evaluation filters.
- Keep A-share Technology Insight details polling until their tasks reach a terminal state, so reports no longer remain visually stuck on `running`; record report/task completion after the optional Agent pipeline instead of backdating it to the market-data cutoff.
- Fix MySQL migration parsing so semicolons in leading SQL comments cannot prevent a pending schema migration from applying and break Insights refreshes with missing-table errors.
- Upgrade A-share Technology Daily from an opaque optional narrative into an auditable six-stage model workflow with environment-only DeepSeek-compatible diagnostics, PIT fundamentals, evidence-bound 1/5/20-trading-day forecasts, deterministic failover, hard server-side vetoes, Top-10/Top-5 selection, and scheduled direction/Brier/return evaluation in the Insights UI.
- Deduplicate indistinguishable project names in project-selection suggestions across Backtest, Optimization, Research, Batch, History, and Paper workflows while preserving every underlying record in project management.
- Split A-share index screening into a broad qualified pool and a stricter high-conviction shortlist using overall-score, RSI, volatility and risk-count gates before the Top-N cap; clarify that result-page refresh only reloads immutable run artifacts and does not rerun screening.
- Fix the Optimization Center's unstable portfolio-candidate loader, preventing an unavailable candidates endpoint from triggering an endless request/render loop and repeated red `Not Found` notifications; show one retryable inline error in Portfolio Builder instead.
- Replace the legacy optimization worker and split configuration pages with one Optimization Center backed by standard experiment-batch child backtests; add typed DataScope/execution/objective contracts, Research → Backtest → Optimization lineage and server-side handoff validation, persisted admission-gated portfolio optimization with currency/resolution/alignment safeguards, normalized run comparison, archival controls, and migration `0035` that retires `optimization_runs` and the old `/api/optimize` and `/api/portfolios/optimize` routes.
- Preserve authoritative A-share suspension evidence when `stk_limit` or inferred OHLC status rows are materialized later, preventing legitimate no-bar suspension sessions from failing execution coverage gates.
- Fix derived Parquet recertification by enforcing stable numeric schemas during exports and certifying independently consistent production scopes when another scope fails validation.

- Fix one-click TuShare increments to refresh the trading calendar before choosing the market cutoff, advance sparse `stk_limit`/`suspend_d` coverage for newly listed securities, requeue dated catalogs when resuming incremental checkpoints, index basic-contract listing dates for visible catalog ranges, and accept provider-native futures/option catalog nulls without discarding the full update.
- Give Research Runs names a stable two-line column and preserve sensible row heights with horizontal table overflow on narrower layouts.
- Unify Research around reproducible template Runs and a shared nested DataScope/Data Gateway contract; separate network-isolated, frozen-snapshot Notebook Workspaces from run history; add explicit Backtest handoff with renewed strategy/preflight requirements; retire Research experiment batches and direct factor, convertible-bond and futures analysis routes; and redesign the responsive Research UI as a dense brokerage-style workstation.
- Convert A-share index technical/fundamental selection into a research-only final-date screen with complete qualified and Top-N result layers, dedicated screening UI/API/report output, security names and preserved six-digit A-share codes; add symbol-selectable multi-asset price charts with matching order markers and correct per-symbol holding valuation.
- Route Research Jupyter container start, readiness, logs, stop and removal
  through the authenticated restricted runner so API and Celery containers no
  longer attempt to reach an unavailable Docker socket, while keeping the raw
  socket confined to `lean-runner`.
- Fix direct A-share index-screening runs by persisting preflight failures,
  injecting the required PIT universe and fundamental schedules server-side,
  and allowing targeted CSI300 research-data refreshes without rewriting daily
  bars or revoking an unrelated production certification; non-finite provider
  financial values are now discarded before MySQL persistence, and LEAN warm-up
  slices with a present-but-null bar no longer crash dynamic-universe strategies.
  Preserve validated dynamic-universe symbol lists so execution-status artifacts
  and Source Gate checks cover every constituent instead of only the benchmark,
  while treating an explicitly persisted full-day suspension as valid execution
  coverage instead of incorrectly requiring an OHLC bar for that session.
  Production daily batches now persist their inferred suspension statuses,
  terminalize unexpected import failures, and ignore non-terminal orphan batches
  when resolving the latest completed per-symbol QA evidence. Index-screening
  rotations now wait for exit orders to settle before submitting replacement
  buys, preventing cash-account buying-power errors during constituent changes.
- Fix A-share backtest symbol repair after a governed MySQL library grows beyond 50 GiB: the on-demand guard now limits the individual write estimate instead of misclassifying the whole shared database as on-demand cache usage, while retaining the physical disk reserve.
- Keep Celery beat and Source Gate recovery active with a writable scheduler file and complete documented startup, make Parquet maintenance rewrite the earliest historically changed or count-mismatched year, let complete governed full-rebuild evidence supersede stale batch state without admitting synthetic data, tightly bound DuckDB consistency memory, fetch and parse large batch lineage metadata once per batch instead of duplicating it per symbol, remove the full grouping filesort, return exact execution and operational blockers from dependency health, and make Dashboard distinguish production-data recertification from infrastructure failure.
- Add an A-share index screening project case for CSI300, CSI500, CSI1000 and STAR50 with PIT membership/fundamental streams, per-stock trend and buy-suitability scoring, guarded Top-N LEAN execution, structured screening artifacts, and full screening tables in backtest HTML reports.
- Add separate research-only and executable A-share gap-buy strategy templates, guarded LEAN limit-buy support, first-minute/next-minute timing, PIT-universe audit output, and an admission hard block for the source-replica contract.
- Complete Level 5 Wave 6 with route-aware four-group Chinese navigation, persistent Backtest/Paper URL context, dedicated Paper deployment/risk/daily-run views and prominent automation failures, accessible focus/control/chart behavior, three responsive Playwright projects and four user journeys, plus modular ECharts chunks below 400 kB.
- Reclassify real external Webhook 2xx delivery as an optional unattended-operations acceptance rather than a Level 5 pass requirement, while retaining fail-closed operational readiness whenever scheduled automation is enabled without an external alert channel.
- Retire the legacy Paper session API, navigation and Insight handoff surface; move trusted backtest candidates under Paper Accounts; purge unlinked legacy session records; and require newly rebuilt accounts to pass Source Gate and projection-history recertification before performance is trusted.
- Distinguish interactive platform executability from unattended-operation readiness in dependency health, and prevent Dashboard loading state or a missing external alert webhook from falsely reporting that platform execution is blocked.
- Complete the actionable Level 5 Wave 1–5 controls: make historical Paper replay ledger- and quote-point-in-time with guarded recertification; strengthen the 21-day multi-account/fault acceptance runner; enforce A-share calendar, status, ST and timezone fail-closed rules with 13-rule/7-failure matrices; consolidate API routes and fingerprint keys; authenticate Prometheus metrics; constrain report files to runtime roots; and retain `object_store_items` as the active `stored_objects` index. Historical recertification now refuses to rewrite legacy checkpoint digest divergence, and the XL Paper/data-sync repository split remains in progress.
- Close 11 Level 5 P1 findings: extract the shared trading calendar; standardize bounded list envelopes with a legacy compatibility mode; persist and replay API idempotency keys; add cursor-based task/backtest logs and field-aware errors; propagate trace/workflow IDs through Celery, LEAN config and artifacts; permanently prohibit same-close Paper execution; declare rollback policy for all migrations; hide runtime secrets from read-only worker workspaces; verify restore row counts/checksums; and add configurable industry concentration, volume-capacity and drawdown circuit-breaker controls. Keep the XL Paper repository-layer extraction explicitly in progress.
- Close the nine Level 5 P0 remediation gaps: schedule hash-verified MySQL backups and evidence-producing isolated restore drills; make alert/Paper outbox delivery depend on external 2xx acknowledgements with fail-closed readiness and backfill; default to Paper v2 and enforce 21-day differentiated-capital acceptance; replace runner free-form Docker commands with a structure-only API; add exact/hash-locked Python dependencies, locally scanned signed SBOM evidence and expiring CVE exceptions; and automatically re-certify stale production datasets while exposing platform executability in health and the dashboard.
- Complete the Paper valuation remediation by certifying equity and index closes against their matching Source Gate scopes, requiring exact benchmark dates, failing daily snapshots closed when benchmark/checkpoint evidence is absent, and extending regression coverage for checkpoint and ledger sequence integrity.
- Make Paper valuation point-in-time and source-bounded, compute benchmark and excess return in the canonical projection writer with missing data failing closed, and write account ledger context and Decimal amounts once at append time under a unique generation sequence.
- Pause runnable Paper accounts while Level 5 remediation addresses untrusted look-ahead valuation, surface a non-dismissible valuation-trust warning and machine-readable `dataTrust` flag across Paper account performance APIs, and mark notification outbox records as failed when no external channel is configured instead of falsely reporting delivery.
- Mark Level 5 evidence reuse as `revalidated_from_prior_evidence` rather than a passing certification, and withdraw the obsolete Level 5 Paper-interruption PASS claim from the roadmap.

- Add PDF, CSV and versioned JSON report exports; enforce ETF, convertible-bond, futures and options dataset quality gates; add launch-aware PIT coverage ledgers and licensed history import for every offered A-share universe; schedule independent incremental Parquet/ClickHouse maintenance with visible per-layer watermarks and bounded date-count drift repair; and add real-stack Level 4 train/validation/OOS plus failed-child retry and cancel/restart recovery evidence.
- Make the Backtests cumulative-return chart derive its vertical range from valid strategy and benchmark values, ignore zero-valued benchmark placeholders that falsely appeared as a 100% loss, and rebuild historical reports with the same placeholder filtering so small fluctuations remain visible.
- Redesign backtest results around performance, trades, research quality, and run details; compare strategy and benchmark on rebased cumulative returns and treat admission as an optional promotion workflow.
- Fix the backtest-detail white screen caused by invalid cumulative-return label precision crashing ECharts during tab changes; normalize malformed historical chart and ledger collections, isolate all four detail panels, and rebuild local parsed results and HTML reports with canonical `report-layout-v2`.

- 2026-07-26 — align Paper account name and description length checks with the API before submission, reject whitespace-only names in the setup wizard, and surface structured request-validation field details instead of only a generic Trace ID.
- 2026-07-26 — add a production-ready Pipedream/Make-to-Feishu alert relay recipe with an end-to-end Pipedream transformer and optional Feishu signing; add protected cascading deletion for stopped Paper accounts; make Paper account details render from the overview before lazily loading tab data; make Project Open scroll the selected project into view; and display legitimate empty TuShare entitlement probes such as `suspend_d` as endpoint availability instead of a failure-like `EMPTY` tag after successful synchronization.
- 2026-07-26 — make Level 3 smoke audits project-aware for dynamic-universe strategies by materializing and recording the required PIT `universeSchedule`, with optional aggregate evidence output; allow Level 5 clean and combined six-phase evidence reuse to verify scope, durable daily-job/checkpoint coverage, worker-loss actions, and canonical equivalence after historical sessions are retired; and add a fail-closed external webhook acceptance probe that only certifies a persisted 2xx delivery to a public endpoint.
- 2026-07-25 — add the additive `0029_paper_accounts` domain and brokerage-style Paper workspace: isolated multi-account opening ledgers and rebuildable Decimal projections, frozen/versioned strategy deployments, idempotent daily execution cycles, due scheduling and orphan recovery, paginated account/position/order/trade/signal/performance/audit APIs, notification outbox delivery, account comparison, five-step React account setup, responsive account detail tabs, MySQL/unit/Playwright coverage, and a machine-readable real-stack acceptance runner; preserve legacy Paper sessions under a separate read-only-compatible route and keep index benchmarks on their dedicated fail-closed gate instead of misclassifying them as equity multi-source QA subjects.
- 2026-07-25 — 修复 LEAN ResultsAnalyzer 在周末或美股休市日错误要求 SPY 覆盖到自然日的问题，明确区分 SPY 技术参考、美股、A 股和港股交易日历；将 New Backtest 与批量回测合并为按运行范围配置切换的统一入口，并让批次子任务继承市场、基准、来源、费用、滑点与研究数据覆盖配置；补齐全部回测案例模板检查和 Web 使用/排障文档。
- 2026-07-25 — preserve Web data across route changes with shared stale-while-revalidate caching and in-flight request deduplication; lazy-load and intent-prefetch page bundles; stop terminal Research sessions from polling forever; parallelize and coalesce Backtest detail refreshes; and ignore stale page, search, file and preview responses after navigation.
- 2026-07-25 — add cross-batch experiment ranking and side-by-side comparison, parameter-sensitivity heatmaps and Train/Validation/OOS charts; add executable factor normalization, neutralization, portfolio-construction and robustness templates; and add persisted futures continuous-contract series with versioned fees, strict margin metadata, LEAN mapping/adjustment controls and roll-level PnL/cost attribution.
- 2026-07-25 — complete local P1 stability and Paper operations acceptance: prove five accepted LEAN jobs under a two-active/three-queued budget, queued/running phase cancellation, Redis/MySQL/worker recovery, a real 21-day LEAN Paper v2 baseline and six-checkpoint interruption/idempotency chain; add durable finalization recovery, independent notification escalation, automatic resolved notices, disk/memory/CPU/queue pressure alerts, evidence-producing acceptance scripts, and the Level 5 operational runbook.
- 2026-07-25 — close P0 trust and data-coverage acceptance: independently re-run certified production Source/QA/reference fail-closed gates; reconstruct official CSI300 PIT from 2005-04-08 without current-member substitution and retain a hash-verified fetchable bundle; prove input/canonical-result repeatability with two real LEAN release goldens; and reconcile all 37 historical archive issues against passing ten-dataset manifest/watermark/archive evidence.
- 2026-07-25 — consolidate backtest navigation into one canonical Backtest History workspace: remove duplicate run tables from Dashboard and Projects, split run/history tasks into URL-addressable Backtests tabs, and preserve project-scoped filters when entering history.
- 2026-07-24 — 将通用结构化 Insight 升级为统一 technical 指标/诊断视图和可审计 Agent 工作流，增加行情新鲜度、不确定性、证据覆盖与执行边界检查；同时兼容模型 JSON、signal 枚举/百分数/评分差异，禁止观望信号进入 Paper，为 View 增加加载态、选中高亮和详情自动定位，开放 A 股科技日报观察池规则分组编辑，并支持取消活动任务或清理孤儿状态后删除卡死历史报告。
- 2026-07-24 — rebuild the Backtest run detail workspace with brokerage-style hierarchy, bounded financial precision, structured overview and analysis ledgers, searchable metrics, tabular order/trade/holding records, improved charts, artifact controls, and responsive terminal layouts.
- 2026-07-24 — add fail-closed Level 4 validation-only selection and leakage evidence, immutable Paper constraint/matching/reconciliation records, durable daily Paper jobs, and a dedicated allowlisted LEAN runner; remove the raw Docker socket from the general backtest worker and retain Level 4/5 hard-gate failures until production-like replay, recovery, DR, credential and fault-matrix evidence exists.
- Derive Paper v2 cash and position read models from immutable opening and fill
  ledger entries, and separate principal from commission so a replay cannot
  double-count fees.
- 2026-07-24 — continue Level 4/5 remediation: split walk-forward evaluation into fingerprinted train/validation/OOS phases with validation-only parameter selection and UI controls; add failed-only retry and cancelled-batch restart while preserving successful children; introduce a feature-gated LEAN Paper v2 immutable intent/13-state transition/constraint/matching/fill/ledger pipeline with six idempotent recovery checkpoints, migration, audit APIs and deletion support; repair the Level 5 wrapper's CLI, evidence parsing and reject-reason handling; keep legacy sessions and historical evidence unchanged pending a new production-like Level 4 and 21-day Level 5 revalidation.
- 2026-07-24 — harden re-audit truthfulness: add a disposable real-MySQL migration/locking/uniqueness lane and an explicitly uncertified Level 5 SLO/RPO/RTO/runbook contract; authenticate Level 4 and production-like Playwright evidence clients; fail invariant violations and legacy train/test-only walk-forward; add the missing real 3×3 grid and three-window probes; align Level 3/5 audit defaults with Compose port 8000; and correct stale API/authentication, migration and maturity documentation.
- 2026-07-24 — add reproducible Level 4/5 re-audit runners for rolling, walk-forward, dynamic PIT and 21-day LEAN Paper evidence; make the Level 5 fault matrix opt-in and document the evidence-producing verification paths.
- 2026-07-24 — document independent re-audit 2026-07-24 and update roadmap/history index wiring; extend level-3 shadow runner python/bootstrap fallback for constrained environments.
- 2026-07-23 — fix independent audit scripts: `run_level3_shadow_audit.py` 现在兼容 docker compose 插件差异（`docker compose` / `docker-compose`），`run_paper_constraints_acceptance.py` 修复单符号输入导致的拒单场景误判，确保 `max_positions` 与 `not_in_watchlist` 能稳定得到对应拒单原因。
- 2026-07-23 — add evidence-driven operational acceptances：增加可恢复的真实 21 交易日 LEAN Paper 验收、活动任务安全门禁下的 Redis/MySQL/worker 重启矩阵、带 SHA-256 校验且禁止覆盖正式库的隔离恢复入口、镜像 CycloneDX SBOM 生成与供应链固定检查；实际导入 2005–2026 TuShare CSI300 影子 PIT，并继续禁止其冒充官方 CSI300。
- 2026-07-23 — close governed rebuild and reproducibility gaps：完成十数据集 full rebuild、raw archive、Parquet/DuckDB/ClickHouse 对账与 TuShare production recertification；将 CSI300 index daily 规范化为 index canonical，并修复 fingerprint 慢查询、终态 scheduler lease、Paper replay 重复 reference scan 和 run-local snapshot 路径导致的 canonical result digest 漂移。
- 2026-07-23 — revalidate Level 3 production path：重新执行受治理双标的 A 股 shadow、真实 LEAN integration、两次 deterministic golden backtest、Paper 约束、十数据集 Preview、后端全量测试、前端 build/E2E、migration、文档与仓库卫生检查；保留真实 21 日 LEAN Paper、故障矩阵、DR 和安全边界为未关闭项。
- 2026-07-23 — bound governed materialization resources：将 Parquet 年度切分改为单次线性 partition，并增大年度 part 以减少 Docker Desktop 文件共享事件；限制 Polars 并行线程和 data-demand worker CPU，避免全量派生期间挤占 MySQL、API 与 Docker 控制面。
- 2026-07-23 — authenticate audit entrypoints：Level 3 shadow 与 daily shadow 脚本自动从环境或受限 runtime secret 读取 API Token，避免认证加固后把 401 误判为平台故障，且不会将凭据写入证据。
- 2026-07-23 — preserve governed lineage across resume：`resume_checkpoint` 保留其 `full_rebuild` 基础语义，使 Parquet 认证直接使用完整 manifest/archive 证据，避免恢复任务回退到数千万行历史 batch 聚合。
- 2026-07-23 — bind shadow audits to project snapshots：Level 3/daily shadow 验收现在强制接收正式 `projectId`，真实 LEAN smoke 不再尝试创建无项目快照的回测。
- 2026-07-23 — make shadow Parquet checks read-only：daily shadow 只校验已治理 Parquet，不再每次重建 1,700 万行；显式请求的数据集缺失时 consistency report 现在 fail closed。
- 2026-07-23 — canonicalize dataset versions：Source Gate 与 Parquet writer 使用按路径排序的相同文件 manifest 结构；认证时原子刷新 `dataset_version`，持久化版本与实际文件清单不一致时认证立即失效。
- 2026-07-23 — recover API auth without leaking secrets：API 可从 0600 runtime token 文件恢复认证；Level 3 审计仅执行 quiet Compose 校验并对兜底文本脱敏，不再把容器环境写入证据输出。
- 2026-07-23 — reconcile governed full snapshots and stabilize derivatives：full rebuild 现在按 TuShare raw archive 的完整 symbol/date key 集合删除 canonical stale 行及孤儿标的；增加可 dry-run/apply 的受控对账工具、ClickHouse 定向替换、批量年度分区镜像、无 filesort 的主键流式 Parquet 导出，以及派生任务 advisory lock、心跳、长任务可见性和孤儿恢复保护。
- 2026-07-23 — pin platform container inputs：将 Python、MySQL、Redis、ClickHouse、Prometheus 和 Grafana 固定到已核验 RepoDigest，并固定 Grafana ClickHouse 插件版本，避免 tag 或插件 latest 在重建时静默漂移。
- 2026-07-23 — persist and dispatch operational alerts：增加 Webhook 告警投递、投递结果与尝试次数持久化、敏感查询参数脱敏、冷却去重和重复 Paper 调度失败自动升级；真实 LEAN Paper、受治理数据同步和自动报告失败现在会产生 Critical 运维告警。
- 2026-07-22 — accelerate governed TuShare rebuilds：将 daily、adj_factor、suspend_d、stk_limit 全量历史改为受限并发、多股票批量提交和仅差异 canonical 写入，daily 扩大安全请求窗口并将 raw archive 改为低 CPU 规范化压缩；补齐 index_daily 分窗以及指数、期货、期权全市场/交易所抓取，并增加 TuShare CSI300 历史权重影子 universe 校验工具。
- 2026-07-22 — fail closed after the independent maturity audit：收紧 Data API、回测和 Paper 的生产数据源与 A 股 QA/PIT/reference 双阶段门禁，以 sync manifest + raw archive 建立不可由导入接口伪造的 TuShare provenance，撤销旧认证并阻止 synthetic 批次晋级；增加覆盖资金及实际行情内容的稳定 input/result digest，将历史孤儿 raw archive 可追溯隔离并增加对象完整性检查和安全预览降级；增加本地 API Token/HttpOnly Web session，限制 LEAN/Research 镜像并隔离网络、挂载与资源，将服务端口默认绑定回环地址，修复迁移/备份入口及浏览器报告、重复提交和移动端导航回归。
- 2026-07-22 — compact and group Web forms：新增统一响应式表单栅格、分组、高级设置和操作区；桌面最多四列、平板两列、手机单列，并将运行镜像、API Key 与原始 JSON 等低频字段折叠，保持请求字段和默认值不变。
- 2026-07-21 — make Web tables and history cleanup safer：统一全站表格多行展示、表头/行态和响应式布局，重组超宽科技日报列；取消 Dashboard 一键强制清空，新增 Backtest、Optimization、Research、Report、Paper、Task、Project 和实验批次的受保护删除入口。
- 2026-07-21 — pin the primary Web navigation：将 Dashboard 至 Settings 主导航固定为独立全高侧栏，右侧长页面滚动时保持可见，低高度视口仅在导航内部滚动。
- 2026-07-21 — rebuild the in-app documentation center：使用 GFM Markdown 渲染、可复制深链、合并式目录和响应式表格重构 Web Docs；扩充数据、策略、回测、优化、Research、Paper、报告和排障教程，纳入仓库参考/历史文档、OpenAPI 全端点索引、链接校验和隔离 E2E 截图。
- 2026-07-21 — reorganize repository boundaries：将独立 Docker/CLI demo 移入 `examples/`，正式报告生成器移入后端 reporting 包，回测强制使用项目快照，统一源码、运行产物和 portable data manifest 边界。
- 2026-07-21 — align reports and documentation：统一所有 HTML/Markdown 报告表头与缓存策略，更新 README、架构、数据源、部署、帮助和历史问题文档。

## 2026-07-08 至 2026-07-21 — 历史里程碑回填（63 commits）

### 2026-07-21 — 稳定性、预览和实验工作台

- 修复 MySQL 临时断连的 API、Celery 周期任务重试和结构化错误响应。
- 修复指数、期货和期权数据集预览的不可序列化字段与前端空白页。
- 增加 Backtests、Optimization、Research 案例模板、批量实验、取消、失败重试和导出工作流。

### 2026-07-19 至 2026-07-20 — TuShare 全库同步与数据页面

- 完成十数据集首次全量、后续增量同步，增加 checkpoint、heartbeat、watermark、孤儿任务恢复和真实 API 调用指标。
- 批量化 MySQL 写入、交易状态来源判优和 loader 连接，删除逐行完整 JSON 重复写放大，改用轻量 raw 索引与压缩批次归档。
- 增加股票、交易日历、指数、期货和期权预览，按需数据集可选择存储目标，CSV 导入提供模板。
- 统一磁盘/MySQL 容量统计和安全线，改进单实例启动、退出清理与 worker 恢复。

### 2026-07-17 至 2026-07-18 — Paper、Insights 与跨市场链路

- 增加基于验证通过项目快照的 LEAN Paper walk-forward、约束验收和日终报告。
- 修复 A 股及港股回测验证、图表、结果展示和跨市场数据同步。
- 增加多模型技术洞察、报告刷新、行业展示和可编辑分析工作流。

### 2026-07-14 至 2026-07-16 — 项目回测与执行可信度

- 改进项目创建、克隆、参数模板、数据预览和回测配置流程。
- 强制 A 股 next-open、涨跌停、停牌、T+1、费用和滑点执行验证。
- 将正式研究、优化和回测统一到 LEAN 项目与可复现运行指纹。

### 2026-07-09 — Web 启动、任务与项目工作区

- 增加单实例 Web 启动、自动端口回退、完整 Compose profile、可选 `--build` 和健康检查。
- 修复队列无 worker、陈旧 queued 任务、任务删除、页面轮询和端口日志污染。
- 重构项目工作流并增加更新/克隆 API，简化数据表单和历史结果展示。
- 修复 LEAN orders、fills、holdings 推断和图表记录渲染。

### 2026-07-08 — MySQL 与多数据源统一

- 移除 SQLite 运行默认值和旧迁移回退，统一 MySQL 运行事实库与后端目标。
- 将 TuShare 设为默认 A 股生产源，增加 JQData CSI1000、Binance crypto 和多源 fallback。
- 重构 Data 页面、CSV 导入和本地历史维护，增加 Web E2E 回测覆盖。
- 修复数据库健康检查、前后端端口绑定、启动等待和行情 source resolution。

## 2026-07-07 - 本次提交 - Add Level 3 shadow pass pipeline

- 新增生产数据源门禁：A 股日线 backtest、Paper、Data API、Parquet/DuckDB 查询默认只允许 certified production source，`source=test/baostock/adata` 需显式 `allowResearchSource=true` 才可进入研究查询。
- 新增 dataset/source certification 元数据迁移，`parquet_datasets`、`dataset_versions` 和 run fingerprint 记录 source、dataset version、certification 与 QA report。
- 新增 `instrument_identifiers` 回填服务和 `scripts/import_instrument_identifiers.py`，从 canonical securities/instruments/market bars 生成 raw、exchange、ts_code、LEAN ticker、provider symbol 映射。
- 新增数据覆盖 API：`/api/data/coverage/ashare`、`/api/data/coverage/symbol/{symbol}`、`/api/data/coverage/benchmark/{symbol}`，并把 coverage summary 写入 Paper daily report。
- 新增 `scripts/run_daily_shadow_pipeline.py`，串联环境检查、source gate、coverage、QA、Parquet consistency、LEAN cache restore、backtest smoke、Paper replay 和 Reports API。
- 新增 `scripts/run_paper_constraints_acceptance.py`，覆盖 blacklisted、observe_only、st_blocked、max_positions、cash_floor、not_in_watchlist、qa_failed、benchmark missing 和 same_close 默认禁止。
- 新增 `scripts/run_level3_shadow_audit.py`，固化 Level 3 shadow 本地审计，输出 `LEVEL3_PASS`、`LEVEL3_CANDIDATE` 或 `LEVEL3_FAIL`。
- Reports API 默认返回轻量列表，detail/object 通过独立 API 读取；新增 `scripts/cleanup_report_artifacts.py` 支持 dry-run artifact retention 检查。
- 自研 migration runner 增加 checksum、execution time、status/verify 命令，新增 `scripts/db_migrate.py`。
- 后端全量测试通过：`107 passed, 1 skipped`。

## 2026-07-06 - 本次提交 - Close Level 3 P1 audit gaps

- 补充 `baostock` 后端依赖，确保 AData/Baostock 多源导入路径可安装并有 canonical 落库回归覆盖。
- 公开参考数据公司行动默认样本扩展到 `600519,000001,300750`。
- PIT API 对 CSI300 官方覆盖起点前日期返回 `coverage_gap` 和 0 成员，避免用局部/手工数据伪造 2005-2017 历史。
- 增加 Paper API 级 ST/停牌 fixture，验证生产接口能在存在日线 bars 时拒单并返回 `st_blocked`/`suspended`。
- 真实 MySQL 验证 AData/Baostock 600519 小窗口落库：两源各 4 行，multi-source QA severity=ok，reportId=`1a99bd5f-1520-5929-8c4c-5013e2e2abc1`。
- 真实 MySQL 验证 300750 公司行动导入：AKShare 写入 2 条 `corporate_actions`，reportId=`b4caf512-93f0-40f5-b7f4-a13a63db5a7d`。
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
