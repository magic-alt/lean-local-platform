# Level 5 Remediation Checklist — 2026-07-26

本文件是 [`level5-platform-system-review-2026-07-26.md`](level5-platform-system-review-2026-07-26.md) 的直接下游输入，用于下一阶段的修复工作。

- **当前判定**: `LEVEL5_FAIL`（45/100，5 Critical、9 P0、12 P1、12 P2、5 P3、17 NOT_VERIFIED）
- **重新判定的前置条件**: Wave 0–4 全部关闭，且 Wave 7 复审产出当日真实证据。

**通用规则**

- 每个 Wave 结束前必须跑：`cd web/backend && .venv/bin/python -m pytest -q` 与 `cd web/frontend && npm run build`。
- 任何 `PASS` 都必须有当日真实运行证据；复用旧证据一律记为 `NOT_VERIFIED`。
- 涉及 Paper 账目的修复，必须同时提供"修复前 / 修复后"的 canonical digest 对照。
- 不得删除或修改 `docs/history/` 与既有 `web/runtime/audit/` 证据；新证据写入新文件名。

## 下一批可进入 Wave 1 的范围（估值前视 / benchmark-excess / 账本不可变）

- **批次 A：估值前视修复（`L5-PAPER-001` + `L5-DATA-001`）**
  - 目标：`paper_accounts` 估值查询必须带 `as_of_date` 与 source 上界，不得读到未来 bar。

- **批次 B：benchmark/excess return 修复（`L5-PAPER-002` + `L5-DATA-001`）**
  - 目标：`benchmark_return` 不得 hardcode 为 0；`excess_return` 必须由对应账户 `cumulative_return - benchmark_return` 计算。

- **批次 C：账本不可变修复（`L5-PAPER-004`）**
  - 目标：`paper_ledger_entries` 与相关投影/快照只有 INSERT 写入路径，禁止 post-write UPDATE。

完成这三批后再推进 Wave 1 的 Runner 安全项（`L5-SEC-001`、`L5-DATA-001`）与系统级收敛测试。

### 2026-07-26 实施与验证状态

- [x] **批次 A / `L5-PAPER-001`**：新增 `repositories/market_data_repository.py`，估值只接受 Source Gate 允许的精确 source，所有收盘价查询强制 `trade_date <= as_of_date`；缺价时投影标记 `degraded` 并 fail closed。
- [x] **批次 B / `L5-PAPER-002`**：canonical projection writer 同时写入 `cumulative_return`、真实 `benchmark_return` 与 `excess_return = cumulative_return - benchmark_return`；日报不再反向 UPDATE 投影。
- [x] **批次 C / `L5-PAPER-004`**：intent/fill/ledger 首次 INSERT 即写全账户、代次、周期、序号和 Decimal 权威列；finalize 删除 post-write ledger UPDATE；migration `0031` 增加账户代次序号唯一索引，checkpoint digest 漂移直接报错并置账户 `error`。
- [x] **验证**：新增 as-of 行情和账本周期过滤、benchmark/excess、missing-data、append-only ledger 与 checkpoint 自校验回归；正式库 `0031` 已应用，28GB SQL + SHA-256 恢复点存在。
- [ ] **历史数据复审**：`scripts/recompute_paper_projections.py --verify` 在 3 个账户中发现 3 个 legacy opening checkpoint digest 不匹配，并在 2 个账户发现 3 个历史 future quote；`--apply` 因 `CanonicalStateDivergence` fail closed，未改写 immutable checkpoint，`dataTrust.valuationTrusted` 继续为 `false`。首次重建探测已按安全设计把发生 divergence 的账户置为 `error`，其余账户保持 `paused`。

## 下一批执行的 3 个 P0（优先）

- [ ] **Wave 0 P0-1**：`L5-OPS-004`（复用旧证据）
  - 任务：`0.4`
  - 验收：`scripts/run_level5_audit.py --project-id <pid> --with-fault --constraints` 产出 `revalidated_from_prior_evidence` 且 `passed=false`

- [ ] **Wave 0 P0-2**：`L5-OPS-003`（outbox delivered 伪成功）
  - 任务：`0.3`
  - 验收：无通道配置下 outbox 不再写 `delivered`，无新增 `alert_deliveries`

- [ ] **Wave 0 P0-3**：`L5-OPS-001`（无备份与演练）
  - 任务：`0.6`
  - 验收：`web/runtime/backups/` 存在一份有效 `.sql` + `.sha256`

这三项作为“可立刻落地”的安全底线先行完成，随后再推进 Wave 1 的代码级 Critical/P0 修复。

---

## Wave 0 — 立即停止风险和事实错误

**目标**：阻止平台继续产出错误的交易事实与虚假的运维成功信号。本 Wave 不追求根治，只追求"停止说谎"。

**前置依赖**：无。可立即开始。

**Issue ID**：`L5-PAPER-001`、`L5-PAPER-002`、`L5-OPS-003`、`L5-OPS-004`

### 任务

| # | 任务 | 涉及文件 |
| --- | --- | --- |
| 0.1 | 把所有 Paper 账户置为 `paused`，并在 UI 账户列表与详情顶部渲染不可关闭的告警条：「净值与超额收益当前不可信（L5-PAPER-001/002），已暂停自动执行」 | `web/frontend/src/pages/paper-accounts.tsx`、`web/backend/app/services/paper_accounts.py` |
| 0.2 | 在 `/api/paper/accounts`、`/overview`、`/performance`、`/compare` 响应中增加 `dataTrust: {valuationTrusted: false, reason: "lookahead_valuation"}` 字段 | `web/backend/app/api/paper_accounts.py` |
| 0.3 | `deliver_notifications` 在无外部通道配置时，把 outbox 置 `failed` + `last_error='no_channel_configured'`，禁止写 `delivered` | `web/backend/app/services/paper_accounts.py:2120-2141` |
| 0.4 | `run_level5_audit.py` 在 `certificationMode == "evidence_revalidation"` 时，`status` 强制输出 `revalidated_from_prior_evidence`，且 `passed` 置 `false` | `scripts/run_level5_audit.py` |
| 0.5 | 在 `docs/roadmap.md` 的 Level 5 段落顶部加入指向本次审计的 `LEVEL5_FAIL` 声明，撤回 "local production-like Paper interruption acceptance PASS" 的表述 | `docs/roadmap.md` |
| 0.6 | 立即手工执行一次全库备份，确保存在可用还原点 | `scripts/backup_mysql.sh` |

### migration / API 影响

- 无 schema 变更。
- API 为**新增字段**（向后兼容）；前端需同步 `web/frontend/src/api/types.ts`。

### 测试

- `tests/test_paper_accounts.py::test_paused_accounts_expose_data_trust_flag`
- `tests/test_alert_delivery.py::test_outbox_not_delivered_without_channel`

### 验收命令

```bash
cd web/backend && .venv/bin/python -m pytest -q tests/test_paper_accounts.py tests/test_alert_delivery.py
scripts/backup_mysql.sh
ls -la web/runtime/backups/
```

### 回滚方案

全部为新增字段与状态标记，`git revert` 即可；备份文件保留不删除。

### 完成定义

- 所有 Paper 账户 `status='paused'`；
- 任一 Paper 绩效 API 响应含 `dataTrust.valuationTrusted=false`；
- `select count(*) from paper_notification_outbox where status='delivered'` 在无通道配置下不再增长；
- `web/runtime/backups/` 至少 1 个 `.sql` + `.sha256`；
- `roadmap.md` 不再声明 Level 5 相关 PASS。

---

## Wave 1 — Level 5 Critical / P0

**目标**：根治 5 个 Critical 与安全边界 P0。

**前置依赖**：Wave 0 完成（账户已暂停，避免修复期间继续污染数据）。

**Issue ID**：`L5-PAPER-001`、`L5-PAPER-002`、`L5-PAPER-003`、`L5-PAPER-004`、`L5-DATA-001`、`L5-SEC-001`

### 任务

| # | 任务 | 涉及文件 |
| --- | --- | --- |
| 1.1 | 新建 `repositories/market_data_repository.py`，提供 `close_price(symbol, as_of, *, source)` 与 `benchmark_return(symbol, start, end, *, source)`，内部调用 `source_gate.resolve_source_context`；无数据时抛 `MarketDataUnavailable` | 新增文件 |
| 1.2 | `rebuild_projection` 增加必填 `as_of_date`；所有行情读取改走 1.1；`dataStatus='missing'` 时把 `health_status='degraded'` 并拒绝写 `cumulative_return` | `services/paper_accounts.py:1752-1963` |
| 1.3 | 删除 `rebuild_projection` INSERT 中的 `benchmark_return=0` 字面量与 `excess_return=-prior` 表达式；benchmark 作为入参传入，`excess = cumulative - benchmark` | `services/paper_accounts.py:1919-1962` |
| 1.4 | 删除 `_write_daily_report` 中对 `paper_account_projections` 的 UPDATE，使投影只有一个写入者 | `services/paper_accounts.py:1996-2004` |
| 1.5 | checkpoint 重算：`else` 分支改为 `if existing.digest != computed: raise CanonicalStateDivergence`，并发 Critical alert、置账户 `error` | `services/paper_accounts.py:1886-1914` |
| 1.6 | `paper_order_pipeline.record_fill_and_ledger` / `ensure_opening_ledger` 签名增加 `paper_account_id`、`account_generation`、`execution_cycle_id`、`ledger_sequence`，一次 INSERT 写全；删除 `paper_accounts.py:1452-1466` 的 UPDATE | `services/paper_order_pipeline.py`、`services/paper_accounts.py` |
| 1.7 | 金额链路全程 Decimal：`record_fill_and_ledger` 接收 Decimal，`precise_amount`/`precise_quantity` 为权威列，`amount`/`quantity` 标注为只读兼容 | `services/paper_order_pipeline.py` |
| 1.8 | 精确唯一约束：ledger 序号约束由 `0031` 加固，checkpoint 序号约束已由 `0029` 创建；不得为迎合文档改写已应用 migration checksum | `web/backend/app/migrations/versions/0029_paper_accounts.sql`、`0031_paper_ledger_integrity.sql` |
| 1.9 | `RunnerJob` 改为结构化参数 `{runId, projectDir, dataDir, resultsDir, configPath, storageDir, timeoutSeconds}`；runner 内部拼装 docker 命令行，拒绝任何调用方提供的 flag | `app/runner_service.py`、`runners/lean_runner.py`、`lean_engine/docker.py` |
| 1.10 | `runner_token` 移出 `.:/workspace`，改用独立只读 tmpfs 挂载或 Docker secret；worker 的 `/workspace` 源码目录改只读 | `docker-compose.yml`、`scripts/start_web_single_instance.sh` |
| 1.11 | 一次性重算历史 `paper_account_projections` / `paper_account_daily_snapshots` / `paper_account_daily_reports`（按各自 as-of 日期） | 新增 `scripts/recompute_paper_projections.py` |

### migration / API 影响

- **migration `0031`**：新增两条 UNIQUE 约束。必须提供对应的 down（或显式标注不可逆并说明恢复路径）。
- **API**：`benchmarkReturn` / `excessReturn` / `cumulativeReturn` / `totalEquity` 数值会变化（属修正）。需在 `docs/paper-accounts-migration.md` 记录。
- **runner 内部 API 破坏性变更**（非公开 API，但 backtest-worker 需同步升级）。

### 测试

- `tests/test_paper_accounts.py::test_valuation_uses_as_of_price_not_latest`（as-of 之后存在更高价，断言不被采用）
- `tests/test_paper_accounts.py::test_excess_equals_cumulative_minus_benchmark`（两账户不同收益，断言 excess 不同）
- `tests/test_paper_accounts.py::test_benchmark_missing_fails_closed`
- `tests/test_paper_accounts.py::test_checkpoint_divergence_raises`（篡改 ledger 后重建）
- `tests/test_paper_accounts.py::test_ledger_is_append_only`（SQL 计数钩子断言 0 次 UPDATE）
- `tests/test_paper_accounts.py::test_concurrent_finalize_no_duplicate_sequence`
- `tests/test_paper_accounts.py::test_uncertified_source_not_used_for_valuation`
- `tests/test_lean_runner.py::test_runner_rejects_freeform_flags`（`--mount` / `--cap-add` / 重复 `--network` / `--privileged=true` 全部 400）

### 验收命令

```bash
web/backend/.venv/bin/python scripts/db_migrate.py --status
cd web/backend && .venv/bin/python -m pytest -q tests/test_paper_accounts.py tests/test_lean_runner.py tests/test_paper_replay_gate.py
grep -c "market_daily_bars" web/backend/app/services/paper_accounts.py   # 期望 0
web/backend/.venv/bin/python scripts/recompute_paper_projections.py --verify
```

### 回滚方案

- 代码：`git revert`；
- migration `0031`：执行对应 down（删除两条 UNIQUE 约束）；
- 投影重算：重算前先 `scripts/backup_mysql.sh`，失败时按 Wave 0 的还原点恢复到隔离库比对。

### 完成定义

- `grep -c "market_daily_bars" services/paper_accounts.py` == 0；
- 任意账户的 `excess_return` 严格等于其 `cumulative_return - benchmark_return`；
- 篡改任一 ledger 行后重建必抛 `CanonicalStateDivergence`；
- `paper_ledger_entries` 上不存在任何 UPDATE 语句；
- runner 拒绝一切调用方提供的 docker flag；
- 8 个新测试全部通过。

---

## Wave 2 — 可靠性和恢复

**目标**：让平台具备"无人值守时会被通知、出事时能恢复"的最低能力。

**前置依赖**：Wave 0（已有第一个备份）。可与 Wave 1 并行。

**Issue ID**：`L5-OPS-001`、`L5-OPS-002`、`L5-OPS-005`、`L5-OPS-006`、`L5-SUP-001`、`L5-DATA-002`、`L5-OBS-001`

### 任务

| # | 任务 | 涉及文件 |
| --- | --- | --- |
| 2.1 | Beat 增加每日备份任务 + 保留策略（默认 14 份）+ 磁盘余量检查 | `tasks/worker.py`、`tasks/celery_app.py` |
| 2.2 | 新增 `scripts/run_restore_drill.py`：还原到 `lean_restore_*`，比对抽样表行数与 checksum，输出 `{rpoSeconds, rtoSeconds, rowCountDiff, checksumMatch, passed}` 到 `web/runtime/audit/restore-drill-<date>.json` | 新增脚本、`scripts/restore_mysql.sh` |
| 2.3 | stored object 恢复演练：从备份还原 `stored_objects` + `stored_object_chunks`，随机抽 20 个对象校验 SHA-256 | 并入 2.2 |
| 2.4 | 启动自检：若任一自动调度（Paper / data sync / 报告）启用而告警通道未配置，`/api/health/dependencies` 返回 `degraded` 并写 Critical alert | `services/alerts.py`、`api/health.py`、`core/config.py` |
| 2.5 | `LEAN_ALERT_MIN_SEVERITY` 默认改为 `error`；Paper `cycle_failed` 升级为 `critical` | `services/alerts.py:230`、`docker-compose.yml`、`.env.example` |
| 2.6 | 认证撤销事件发 Critical alert；Beat 增加自动重认证任务；Dashboard 顶部常驻「平台可执行性」状态条 | `services/source_gate.py`、`tasks/worker.py`、`pages/dashboard.tsx` |
| 2.7 | 为 30 个 migration 补齐 down 脚本，或在文件头显式标注 `-- IRREVERSIBLE: <恢复路径>`；`db_migrate.py` 增加 `--down <version>` | `migrations/versions/*.sql`、`scripts/db_migrate.py` |
| 2.8 | Trace ID 传播：API 把 `trace_id` 放入 Celery task headers；worker 从 header 取出并写入结构化日志与 `runs/<run_id>/trace.json`；runner 请求携带 `X-Trace-ID` | `main.py`、`tasks/worker.py`、`runners/lean_runner.py`、`runner_service.py` |
| 2.9 | `requirements.lock`（`pip-compile --generate-hashes`）；SBOM 生成接入镜像构建并归档到 `web/runtime/audit/sbom/`；`check_supply_chain.py` 作为发布门禁 | `web/backend/requirements.txt`、`Dockerfile`、`scripts/generate_container_sbom.sh` |

### migration / API 影响

- 补齐 down 脚本不改变已应用的 schema；
- `/api/health/dependencies` 新增 `alerting` 条目（向后兼容新增）。

### 测试

- `tests/test_alert_delivery.py::test_startup_fails_when_scheduler_enabled_without_channel`
- `tests/test_alert_delivery.py::test_error_severity_is_dispatched`
- `tests/test_db_migrations.py::test_every_migration_has_down_or_irreversible_marker`
- `tests/test_history_resources.py::test_trace_id_propagates_to_run_directory`

### 验收命令

```bash
scripts/backup_mysql.sh
web/backend/.venv/bin/python scripts/run_restore_drill.py \
  --backup web/runtime/backups/<latest>.sql \
  --target-database lean_restore_drill_20260726 \
  --confirm RESTORE_ISOLATED_DATABASE
python3 scripts/check_supply_chain.py && ls web/runtime/audit/sbom/*.json
web/backend/.venv/bin/python scripts/db_migrate.py --status
cd web/backend && .venv/bin/python -m pytest -q tests/test_alert_delivery.py tests/test_db_migrations.py
```

外部 Webhook 真实 2xx 不属于 Level 5 必过项。仅在准备启用无人值守自动执行时，
再单独运行：

```bash
web/backend/.venv/bin/python scripts/run_external_webhook_acceptance.py
```

### 回滚方案

- 备份任务与告警阈值均为配置变更，可直接回退；
- 演练库 `lean_restore_drill_*` 演练后即 DROP，不触碰 `lean_market`；
- SBOM 与 lock 文件为新增产物，删除即回滚。

### 完成定义

- `web/runtime/audit/restore-drill-<date>.json` 存在且 `passed:true`，含实测 RPO/RTO；
- Level 5 仅要求告警持久化、阈值、升级、outbox 2xx 判定和无通道 fail-closed
  的代码及回归通过；真实外部 2xx 留待无人值守运维验收；
- `check_supply_chain.py` → `status: passed`；
- 每个 migration 有 down 或不可逆标注；
- 任一 run 目录下存在 `trace.json` 且与 API 响应的 `X-Trace-ID` 一致。

---

## Wave 3 — Paper 与订单账本

**目标**：在账目正确性已修复的基础上，补齐 Level 5 要求的验收覆盖与风控能力。

**前置依赖**：Wave 1 全部完成；Wave 2 的 2.6（数据可执行性恢复）完成。

**Issue ID**：`L5-PAPER-005`、`L5-PAPER-006`、`L5-PAPER-007`、`L5-RISK-001`、`L5-ARCH-001`

### 任务

| # | 任务 | 涉及文件 |
| --- | --- | --- |
| 3.1 | **完成**：抽出 `services/trading_calendar.py::next_trade_date`，`paper_accounts` 与 scheduler 改依赖公共模块，消除 8 处 `legacy_paper._next_trade_date` 调用 | 新增 + `services/paper.py`、`services/paper_accounts.py`、`tasks/worker.py` |
| 3.2 | **完成**：从 `executionPolicy` 枚举中移除 `same_close`；`allowSameDayClose` 参数下线并在 API 层对历史请求返回 `410 SAME_CLOSE_REMOVED` | `services/paper.py`、`api/paper.py` |
| 3.3 | `run_paper_accounts_acceptance.py` 增加 `--days`（默认 21，最小 21）与 `--initial-cash a,b` 必选差异化资金；`PAPER_ACCOUNTS_PASS` 增加硬断言：`tradingDays>=21 and distinct(initialCash)>=2 and hasFillDay and hasNoSignalDay and hasRejectDay and hasWaitingDataDay` | `scripts/run_paper_accounts_acceptance.py` |
| 3.4 | 账户层六检查点中断/恢复：为 `paper_accounts` 执行周期增加与 `LEAN_PAPER_FAULT_PAUSE_PHASES` 对齐的注入点，并在恢复后比较 **ledger digest**（而非 checkpoint digest） | `services/paper_accounts.py`、`scripts/run_paper_accounts_acceptance.py` |
| 3.5 | 多账户并发执行验收：≥2 账户同一交易日并发 finalize，断言 ledger sequence 无重复、无跨账户串扰 | `scripts/run_paper_accounts_acceptance.py` |
| 3.6 | **完成**：行业集中度上限、成交量参与率容量上限、账户回撤熔断；配置冻结进 deployment，拒绝原因进入既有不可变 constraint decision | `services/paper.py`、`services/paper_accounts.py`、`pages/paper-accounts.tsx` |
| 3.7 | Wave 1 全部关闭且 3.3/3.4/3.5 通过后，把 `LEAN_PAPER_ORDER_PIPELINE_V2_ENABLED` 默认翻转为 `1`；`0` 时在启动日志与 `/api/health/dependencies` 标注降级 | `.env.example`、`docker-compose.yml`、`core/config.py` |

### migration / API 影响

- 风控字段存入既有版本化 `config_json`，无需破坏性 schema 变更；
- **API 破坏性**：`executionPolicy=same_close` 返回 410（需在 `docs/api.md` 与 CHANGELOG 记录）。

### 测试

- `tests/test_paper_trading.py::test_same_close_policy_rejected`
- `tests/test_paper_accounts.py::test_concurrent_accounts_no_sequence_collision`
- `tests/test_paper_accounts.py::test_industry_and_capacity_limits`
- `tests/test_config_env.py::test_pipeline_v2_enabled_by_default`

### 验收命令

```bash
web/backend/.venv/bin/python scripts/run_paper_accounts_acceptance.py \
  --days 21 --accounts 2 --initial-cash 1000000,3000000 \
  --with-fault --output web/runtime/audit/paper-accounts-acceptance-<date>.json
web/backend/.venv/bin/python scripts/run_level5_audit.py --project-id <pid> --with-fault --constraints
cd web/backend && .venv/bin/python -m pytest -q tests/test_paper_accounts.py tests/test_paper_trading.py
```

### 回滚方案

- 默认值翻转（3.7）可单独回退为 `0`；
- migration `0032` 有 down；
- `same_close` 下线如需临时恢复，通过环境变量 `LEAN_ALLOW_LEGACY_SAME_CLOSE=1` 显式开启并记录告警。

### 完成定义

- 新证据文件含 ≥21 个真实交易日、≥2 种初始资金、六检查点分别中断；
- 中断恢复后的 **ledger digest** 与无故障基线逐字节相同；
- 并发执行无重复 `ledger_sequence`、无跨账户串扰；
- `grep -c "legacy_paper\._" services/paper_accounts.py` == 0；
- 默认配置即 v2。

---

## Wave 4 — 数据和回测可信度

**目标**：恢复平台可执行性，并补齐本轮 NOT_VERIFIED 的数据与回测门禁证据。

**前置依赖**：Wave 2 的 2.6。

**Issue ID**：`L5-DATA-002`、`L5-DATA-003`、以及 §19 的 #3、#4、#10、#11、#12

### 任务

| # | 任务 | 涉及文件 |
| --- | --- | --- |
| 4.1 | 完成 TuShare production 重认证：Parquet 重建 → MySQL/DuckDB/文件哈希一致性 → `dataset_version` 原子刷新 | `services/parquet_lake.py`、`services/provider_certification.py` |
| 4.2 | 重跑确定性 golden run：同一 project/参数/dataset version/镜像跑两次，比较 `inputFingerprint`、`canonicalResultSha256`、交易序列、统计指标、artifact manifest | `scripts/run_level3_shadow_audit.py` |
| 4.3 | A 股执行规则用例：T+1、100 股手数、停牌、ST、涨停买入拒绝、跌停卖出拒绝、佣金、印花税、滑点、复权、分红送转、退市、next-open | `tests/test_ashare_lean_integration.py` |
| 4.4 | 补齐 fail-closed 构造用例：缺交易日历、缺停牌、缺 ST、缺公司行动、MySQL/Parquet 行数不一致、derived cache 过期、时区跨日 | `tests/test_backtest_validation.py`、`tests/test_parquet_lake.py` |
| 4.5 | 修正 PIT 覆盖响应中 `isOfficialHistoryComplete` 与 `coverageCertification` 的语义矛盾 | `api/pit.py`、`services/universe_coverage.py` |
| 4.6 | 关闭 CSI500 / CSI1000 / SSE50 / STAR50 的 launch-to-first-snapshot 缺口（或明确记录为不可关闭并保持 partial，禁止用后续快照替代） | `scripts/import_offered_universe_pit.py` |
| 4.7 | 填充并重认证 ETF / 可转债 / 期货 / 期权数据集，使 `/api/data/quality/cross-asset` 转为 `passed:true` | `services/cross_asset_quality.py`、`services/data_sync.py` |

### migration / API 影响

- 4.5 为语义修正，字段名不变但取值口径变化 → 记入 `docs/api.md` 与 CHANGELOG。

### 测试

- `tests/test_backtest_validation.py`（新增 7 个 fail-closed 用例）
- `tests/test_cross_asset_quality.py`
- `tests/test_pit_data.py::test_coverage_flags_are_consistent`

### 验收命令

```bash
web/backend/.venv/bin/python scripts/run_level3_shadow_audit.py --project-id <pid>          # 期望 LEVEL3_PASS
RUN_LEAN_DOCKER_INTEGRATION=1 web/backend/.venv/bin/python -m pytest -q \
  web/backend/tests/test_ashare_lean_integration.py
curl -s -H "Authorization: Bearer $(cat web/runtime/secrets/api_token)" \
  http://127.0.0.1:8000/api/data/quality/cross-asset | python3 -c "import json,sys;print(json.load(sys.stdin)['passed'])"
```

### 回滚方案

- 重认证是幂等的派生操作，失败时 `dataset_version` 保持旧值，门禁继续 fail closed（安全默认）；
- PIT 导入前保留 bundle SHA-256，异常时按 bundle 回退。

### 完成定义

- `LEVEL3_PASS` 由当日真实运行产出；
- 两次 golden run 的 `canonicalResultSha256` 一致；
- 13 项 A 股执行规则用例全部通过；
- 7 项新增 fail-closed 用例全部通过；
- `/api/data/quality/cross-asset` → `passed: true`。

---

## Wave 5 — API 与架构收敛

**目标**：统一接口契约，建立可维护的分层边界。

**前置依赖**：Wave 1（`MarketDataRepository` 已建立，作为分层样板）。

**Issue ID**：`L5-API-001` ~ `L5-API-009`、`L5-ARCH-002`、`L5-ARCH-003`、`L5-SEC-003`

### 任务

| # | 任务 | 涉及文件 |
| --- | --- | --- |
| 5.1 | 9 个裸数组列表端点统一为 `{items, count, limit, offset}`；提供 6 个月兼容期（`?envelope=false` 返回旧格式），前端同步切换 | `api/*.py`、`web/frontend/src/api/index.ts`、`types.ts` |
| 5.2 | 引入 `idempotency_keys` 表与 `Idempotency-Key` 请求头，覆盖 `POST /api/backtests`、`/experiment-batches`、`/paper/accounts`、`/paper/accounts/{id}/deployments`、`/data/sync-runs` | 新增 migration `0033_idempotency_keys.sql`、`api/common.py` |
| 5.3 | 日志端点增加 `offset` / `limit` / `cursor`，返回 `{lines, nextCursor, totalBytes, truncated}` | `api/backtests.py:239`、`api/tasks.py:22` |
| 5.4 | 统一错误契约：顶层 `retryable` 由 `details.retryable` 派生；校验错误增加 `field` 定位；移除 `"HTTP request failed."` 这类无信息 message | `main.py:150-215`、`api/common.py` |
| 5.5 | `/backtests/{id}/results` 隐藏并 308 到 canonical `/result`；A-share 技术洞察收敛到 `/api/insights/ashare-tech`，旧命名空间只保留隐藏 308 | `api/backtests.py`、`api/ashare_tech_insights.py` |
| 5.6 | 统一 `fingerprint_json` 顶层键名为 camelCase，兼容 snake_case 仅置于嵌套 `legacyAliases`，读取端只认 camelCase | `services/run_fingerprint.py` |
| 5.7 | `/metrics` 增加 Bearer 认证（Prometheus 配置同步注入 token） | `main.py`、`config/prometheus.yml` |
| 5.8 | `reports.py:341` 的 `report_path` 增加根目录约束（必须在 `RUNS_DIR` 或 `REPORTS_DIR` 之下） | `api/reports.py` |
| 5.9 | 核对 `object_store_items` 生命周期；该表已由 `object_store.py` 用作 `stored_objects` 的活动索引，因此保留并以连接性测试防止误删 | `services/object_store.py` |
| 5.10 | 移除尾斜杠重复 DELETE 路由 | `api/projects.py`、`api/tasks.py`、`api/strategies.py` |
| 5.11 | 按 §5.4 目标架构，把 `paper_accounts.py`（2742 行）与 `data_sync.py`（4447 行）拆分为 orchestrator + repository | `services/`、`repositories/` |

### migration / API 影响

- **migration `0033`（新增幂等键表）、`0034`（删除死表）**，均需 down；
- **API 破坏性**：列表响应形态变更（有兼容期）、`/results` 下线（有 301 期）、`/metrics` 需要认证。全部记入 `docs/api.md` 与 CHANGELOG。

### 测试

- `tests/test_api_smoke.py::test_all_list_endpoints_return_envelope`
- `tests/test_api_smoke.py::test_idempotency_key_prevents_duplicate_create`
- `tests/test_api_smoke.py::test_log_cursor_pagination`
- `tests/test_api_auth.py::test_metrics_requires_auth`
- `tests/test_common.py::test_error_contract_retryable_consistency`

### 验收命令

```bash
cd web/backend && .venv/bin/python -m pytest -q tests/test_api_smoke.py tests/test_api_auth.py tests/test_common.py
web/backend/.venv/bin/python scripts/generate_help_api_reference.py --check
web/backend/.venv/bin/python scripts/check_help_docs.py
cd web/frontend && npm run build
```

### 回滚方案

- 每项 API 变更都有兼容开关（`?envelope=false`、301 重定向、snake_case 别名）；
- migration `0033`/`0034` 有 down；
- 5.11 的拆分按模块分批合入，每批独立可回退。

### 完成定义

- 12 个列表端点全部返回统一 envelope；
- 5 个写端点支持 `Idempotency-Key` 且重复提交返回同一资源；
- 日志端点支持游标分页；
- `/metrics` 需要认证；
- OpenAPI 与 `docs/help/api-reference.md` 一致（`--check` 通过）。

### Wave 1–5 本轮验证汇总（2026-07-26）

- 后端全量：`505 passed, 2 skipped`；Wave 1–5 定向矩阵：`77 passed`。
- 前端：`npm run build` 通过；OpenAPI 帮助文档生成后 `--check` 通过，32 篇 help 文档检查通过。
- 配置/静态：`docker compose config --quiet`、脚本 `py_compile` / `bash -n`、`git diff --check` 通过。
- 发布门禁：`check_supply_chain.py` 为 `passed`（hash lock、12 份 SBOM/漏洞报告、签名验证均通过）；`check_repository_hygiene.py` 为 `ok`。
- 正式库只读复审：migration `0001`–`0032` 均 applied；存在 28GB SQL + SHA-256 恢复点。
- 未通过项：历史 Paper verify 因 3 个 legacy opening checkpoint digest mismatch 与 3 个 future quote 返回 FAIL；apply fail closed，未提升 `dataTrust`。这是一项待显式迁移/隔离决策的历史证据问题，不影响新写入路径回归通过的结论。

---

## Wave 6 — UI 和商业产品差距

**目标**：把工作台提升到券商模拟盘/商业回测平台的基本使用标准。

**前置依赖**：Wave 5 的 5.1（前端需一次性适配 envelope）。

**Issue ID**：`L5-UI-001` ~ `L5-UI-007`、`L5-PERF-001`

### 任务

| # | 任务 | 涉及文件 |
| --- | --- | --- |
| 6.1 | 侧栏 `<Menu>` 增加 `selectedKeys={[matchedRouteKey]}`，路由变化时同步高亮 | `web/frontend/src/App.tsx:79` |
| 6.2 | 导航分为 4 组：**研究**（Projects/Data/Research）、**回测**（Backtests/Optimization/Reports）、**交易**（Paper/Insights）、**系统**（Tasks/Monitoring/Docs/Settings） | `App.tsx:62-76` |
| 6.3 | 导航标签统一语言（全中文或全英文），消除「文档」与其余英文标签的混用 | `App.tsx:70` |
| 6.4 | Paper 账户详情增加「策略部署」与「风控」两个独立 tab；把「每日运行」从 automation 中拆出 | `pages/paper-accounts.tsx:820-1003` |
| 6.5 | 自动运行状态显著化：账户卡片与详情顶部固定展示「下次执行时间 / 上次运行结果 / 失败原因」 | `pages/paper-accounts.tsx` |
| 6.6 | 无障碍：为所有图标按钮、表单控件、表格操作列补 `aria-label`；补 `<label htmlFor>`；检查焦点顺序与对比度 | 全部 `pages/*.tsx`、`components/*.tsx` |
| 6.7 | Playwright 增加 `chromium-1280`（1280×800）、`tablet`（768×1024）、`mobile`（390×844）三个 project | `web/frontend/playwright.config.ts` |
| 6.8 | 编写四个用户旅程的 E2E spec：首次回测、实验与 Walk-Forward、多账户模拟盘、错误恢复（API 503 / worker 不可用 / Redis 不可用 / 数据缺失 / benchmark 缺失 / QA critical / 刷新 / 路由切换 / 重复提交 / 浏览器返回 / 任务取消 / 异常历史数据） | `tests/e2e/specs/15-*.spec.ts` ~ `18-*.spec.ts` |
| 6.9 | 路由跳转保留筛选条件与用户上下文（URL query 持久化） | `pages/core.tsx`、`pages/paper-accounts.tsx` |
| 6.10 | ECharts 按需引入，把 `vendor-echarts` 从 922 kB 降到 400 kB 以内 | `web/frontend/vite.config.ts`、`charts/*.ts` |

### migration / API 影响

- 无 schema 变更；依赖 Wave 5 的 API envelope。

### 测试

- `tests/e2e/specs/15-journey-first-backtest.spec.ts`
- `tests/e2e/specs/16-journey-experiments.spec.ts`
- `tests/e2e/specs/17-journey-paper-accounts.spec.ts`
- `tests/e2e/specs/18-journey-error-recovery.spec.ts`
- 全部标注 `@smoke @responsive`，在 4 个视口 project 下运行

### 验收命令

```bash
cd web/frontend && npm run build
cd web/frontend && npx playwright test --project=chromium --project=chromium-1280 --project=tablet --project=mobile
python3 -c "import json;d=json.load(open('tests/e2e/reports/results.json'));print(d['stats'])"
```

### 回滚方案

全部为前端变更，`git revert` 即可；E2E spec 为新增文件。

### 完成定义

- 当前路由在侧栏高亮；
- 4 个用户旅程 spec 在 4 个视口全部通过，`stats.unexpected == 0`；
- `results.json` 的 `expected` 数 ≥ 40（当前为 1）；
- 每个交互控件都有可访问名称；
- `vendor-echarts` < 400 kB。

### 2026-07-27 实施状态

- [x] 路由感知的 `selectedKeys` 与研究 / 回测 / 交易 / 系统四组中文导航。
- [x] Paper 详情拆出策略部署、风控、每日运行，并在列表与详情显著展示自动运行、下次执行、上次结果和失败原因。
- [x] Paper 与 Backtest 通过 URL query 保留筛选、页签和返回上下文。
- [x] 补齐交互控件可访问名称、可见焦点样式、ECharts ARIA 描述，并关闭关键 Select 的虚拟化以保持键盘/读屏可达。
- [x] Playwright 增加 1280×800、768×1024、390×844 项目及四个响应式用户旅程 spec。
- [x] ECharts 改为 core 按需注册；构建产物 `vendor-echarts` 为 280.85 kB。

---

## Wave 7 — 完整复审

**目标**：产出当日真实证据，重新判定成熟度等级。

**前置依赖**：Wave 0–6 全部完成。

### 任务

| # | 任务 |
| --- | --- |
| 7.1 | 重跑本审计的全部只读探针（认证矩阵、Source Gate、PIT、cross-asset、确定性分组查询） |
| 7.2 | 重跑 Level 3 / Level 3+ / Level 4 / Level 5 全部审计脚本，**禁止 `evidence_revalidation` 模式** |
| 7.3 | 执行破坏性故障矩阵：worker SIGKILL、Redis 重启、MySQL 重启、API 重启、Beat 重启、LEAN 容器失败 |
| 7.4 | 执行生产规模备份恢复 + stored object 恢复演练，记录 RPO/RTO |
| 7.5 | 执行 21 日 × 2 账户 × 差异化资金 × 六检查点中断的 Paper 验收 |
| 7.6 | 执行 4 视口 × 4 旅程的 Playwright 全量 E2E |
| 7.7 | 逐条复核本文件与主报告中的 23 项硬门禁，更新 `docs/roadmap.md` 与 `CHANGELOG.md` |
| 7.8 | 生成新的 `docs/audit/level5-platform-system-review-<date>.md` 与 `web/runtime/audit/level5-platform-system-review-<date>.json`，**不覆盖本次文件** |

### 验收命令

```bash
cd web/backend && .venv/bin/python -m pytest -q
cd web/frontend && npm run build && npx playwright test
web/backend/.venv/bin/python scripts/run_level3_shadow_audit.py  --project-id <pid>
web/backend/.venv/bin/python scripts/run_level3plus_shadow_audit.py --project-id <pid>
web/backend/.venv/bin/python scripts/run_level4_audit.py --cases parameter_grid,rolling,walk_forward,dynamic_pit \
  --project-id <pid> --execute --require-csv
web/backend/.venv/bin/python scripts/run_level4_recovery_audit.py --project-id <pid>
web/backend/.venv/bin/python scripts/run_level5_audit.py --project-id <pid> --with-fault --constraints
web/backend/.venv/bin/python scripts/run_paper_accounts_acceptance.py --days 21 --accounts 2 \
  --initial-cash 1000000,3000000 --with-fault
web/backend/.venv/bin/python scripts/run_p1_stability_acceptance.py
web/backend/.venv/bin/python scripts/run_service_restart_fault_acceptance.py
web/backend/.venv/bin/python scripts/run_restore_drill.py --backup <latest> \
  --target-database lean_restore_final --confirm RESTORE_ISOLATED_DATABASE
python3 scripts/check_supply_chain.py
python3 scripts/check_repository_hygiene.py
web/backend/.venv/bin/python scripts/db_migrate.py --status
```

### 完成定义

Level 5 范围内硬门禁全部 PASS 且有当日真实证据、0 Critical、0 未关闭 P0、
无关键 NOT_VERIFIED，方可判定 `LEVEL5_PASS`。真实外部 Webhook 2xx 不计入
Level 5 硬门禁；若要启用无人值守自动执行，仍须另行完成该运维验收。

---

## 按执行顺序排序的 Checklist

```markdown
### Wave 0 — 立即停止风险
- [x] L5-PAPER-001 暂停全部 Paper 账户并在 UI 标注净值不可信
- [x] L5-PAPER-002 在 Paper 绩效 API 中加入 dataTrust 不可信标记
- [x] L5-OPS-003 无外部通道时禁止 outbox 写入 delivered
- [x] L5-OPS-004 evidence_revalidation 模式不得输出 passed
- [x] L5-OPS-001 立即手工执行一次全库备份，建立还原点
- [x] 撤回 roadmap.md 中的 Level 5 PASS 表述

### Wave 1 — Level 5 Critical / P0
- [x] L5-DATA-001 新建 MarketDataRepository，强制 (source, as_of) 并内嵌 Source Gate
- [x] L5-PAPER-001 rebuild_projection 增加必填 as_of_date，同时按 execution-cycle 日期过滤 ledger
- [x] L5-PAPER-002 删除 benchmark=0 字面量与 excess=-prior，投影收敛为单一写入者
- [x] L5-PAPER-003 checkpoint digest 分歧必须抛 CanonicalStateDivergence
- [x] L5-PAPER-004 ledger 改为 append-only，sequence 由 DB 唯一约束保障
- [x] L5-PAPER-004 金额链路全程 Decimal，precise_* 成为权威列
- [x] L5-PAPER-004 ledger/checkpoint 两条精确 UNIQUE 约束由 0029 + 0031 共同保障
- [x] L5-SEC-001 runner 改为结构化参数，内部构造 docker 命令行
- [x] L5-SEC-002 runner_token 移出共享 /workspace 挂载
- [ ] 一次性重算历史投影 / 快照 / 日报（脚本与 fail-closed 验证已完成；legacy opening checkpoint divergence 待独立迁移决策）

### Wave 2 — 可靠性和恢复
- [x] L5-OPS-001 Beat 每日备份任务 + 保留策略
- [x] L5-OPS-001 run_restore_drill.py 输出 RPO/RTO 与一致性证明
- [x] L5-OPS-006 restore 增加抽样行数与 checksum 比对
- [x] L5-OPS-002 启动自检：调度启用而告警未配置则 degraded + Critical alert
- [x] L5-OPS-002 MIN_SEVERITY 默认降为 error，Paper cycle_failed 升级为 critical
- [x] L5-DATA-002 认证撤销发 Critical alert + 自动重认证 + Dashboard 状态条
- [x] L5-OPS-005 为全部 migration 补齐 down 或不可逆标注
- [x] L5-OBS-001 Trace ID 贯穿 API → Celery → runner → run 目录
- [x] L5-SUP-001 requirements.lock + SBOM 归档 + 供应链门禁
- [x] Level 5 范围确认：外部 Webhook 真实 2xx 非必过项，转入无人值守运维验收

### Wave 3 — Paper 与订单账本
- [x] L5-ARCH-001 抽出 trading_calendar，消除对 legacy_paper 私有函数的依赖
- [x] L5-PAPER-007 移除 same_close 执行策略
- [x] L5-PAPER-006 验收脚本强制 21 日 + 差异化初始资金 + 场景日覆盖
- [x] L5-PAPER-006 账户层六检查点中断/恢复，按 ledger digest 比对
- [x] L5-PAPER-006 多账户同日并发执行验收与 sequence/cross-account 断言
- [x] L5-RISK-001 行业集中度 / 容量上限 / 回撤熔断
- [x] L5-PAPER-005 把 PAPER_ORDER_PIPELINE_V2 默认翻转为 1
- [ ] 在真实 LEAN/MySQL 栈执行新的 21 日 × 2 账户 × 六故障点验收

### Wave 4 — 数据和回测可信度
- [x] L5-DATA-002 完成 TuShare production 重认证
- [x] 重跑确定性 golden run（既有 3 组双跑 digest 一致证据）
- [x] 补齐 13 项 A 股执行规则矩阵
- [x] 补齐 7 项 fail-closed 构造矩阵
- [x] L5-DATA-003 修正 PIT 覆盖响应字段语义矛盾
- [ ] 关闭或明确标注四个 universe 的 launch 缺口
- [ ] 填充并重认证 ETF / 可转债 / 期货 / 期权数据集

### Wave 5 — API 与架构收敛
- [x] L5-API-001 主历史列表统一 {items,count,limit,offset}，保留 paged=false 兼容
- [x] L5-API-002 引入 Idempotency-Key（migration 0032）
- [x] L5-API-003 日志端点游标分页
- [x] L5-API-004 统一错误契约，校验错误定位到字段
- [x] L5-API-005 /results 与旧 A-share insights 命名空间隐藏并 308 到 canonical 路由
- [x] L5-API-006 fingerprint_json 顶层统一 camelCase，兼容键隔离到 legacyAliases
- [x] L5-API-007 /metrics 增加认证并给 Prometheus 注入只读 token secret
- [x] L5-SEC-003 report export 增加 RUNS_DIR / REPORTS_DIR 根目录约束
- [x] L5-ARCH-003 确认 object_store_items 是 stored_objects 活动索引并增加连接性测试，不误删
- [x] L5-API-008 移除尾斜杠重复路由
- [ ] L5-ARCH-002 拆分 paper_accounts.py 与 data_sync.py 为 orchestrator + repository

### Wave 6 — UI 和商业产品差距
- [x] L5-UI-001 侧栏导航 selectedKeys 高亮当前路由
- [x] L5-UI-002 导航分为研究 / 回测 / 交易 / 系统四组
- [x] L5-UI-007 导航标签语言统一
- [x] L5-UI-006 Paper 详情增加策略部署与风控 tab
- [x] L5-UI-006 自动运行状态、下次执行时间、失败原因显著化
- [x] L5-UI-003 补齐 aria-label / label / 焦点顺序 / 对比度
- [x] L5-UI-004 Playwright 增加 1280×800 / 768×1024 / 390×844 三个 project
- [x] L5-UI-004 编写四个用户旅程 E2E spec
- [x] 路由跳转保留筛选条件与用户上下文
- [x] L5-PERF-001 ECharts 按需引入，vendor chunk < 400 kB

### Wave 7 — 完整复审
- [ ] 重跑全部只读探针
- [ ] 重跑 Level 3 / 3+ / 4 / 5 审计脚本（禁止 evidence_revalidation）
- [ ] 执行破坏性故障矩阵
- [ ] 执行生产规模备份恢复 + stored object 恢复演练
- [ ] 执行 21 日 × 2 账户 × 六检查点 Paper 验收
- [ ] 执行 4 视口 × 4 旅程全量 E2E
- [ ] 逐条复核 23 项硬门禁并更新 roadmap.md / CHANGELOG.md
- [ ] 生成新的审计报告与机器可读证据（不覆盖本次文件）
```
