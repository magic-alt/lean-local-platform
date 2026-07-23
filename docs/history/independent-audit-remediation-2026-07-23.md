# 2026-07-23 独立审计整改追踪

本文件追踪 2026-07-22 独立审计 `AUD-001` 至 `AUD-019` 的后续状态。
原始 26/100 结论和缺陷内容保留在
[独立成熟度审计与修复状态](independent-audit-2026-07-22.md)，不得用本表覆盖。

状态语义：

- `FIXED_PENDING_REAUDIT`：实现和自动回归已修复，但尚未通过新的 production-like 独立复验。
- `IN_PROGRESS`：当前受治理流程正在生成所需证据。
- `PARTIAL`：已关闭部分根因，仍有明确安全或验收缺口。
- `OPEN`：关键能力或可复现证据尚未完成。

## 缺陷映射

| ID | 当前状态 | 当前证据 | 仍需完成 |
| --- | --- | --- | --- |
| AUD-001 Source Gate | FIXED_PENDING_REAUDIT | 受治理 full rebuild、raw archive、Parquet 一致性和 production certification 已完成；实库矩阵仅允许 `tushare`，默认拒绝 `baostock`、`adata`、`test`；canonical 变化会立即撤销认证。 | 由独立审计环境重跑伪造 provider label、post-certification mutation 与 API/worker 双阶段拒绝矩阵。 |
| AUD-002 容器/API 隔离 | PARTIAL | API 默认认证且端口仅绑定 loopback；LEAN 镜像 digest allowlist、无网络、只读根、资源/PID限制、最小挂载。运行容器复核仍为 `raw_docker_socket=true`。 | `backtest-worker` 仍是持有 Docker socket 的可信基础设施，不构成多租户边界；需窄权限独立 runner/专用 daemon，允许任意 bind mount 的通用 socket proxy 不足以关闭风险。 |
| AUD-003 QA Critical 绕过 | FIXED_PENDING_REAUDIT | 创建和 worker 执行阶段复用 fail-closed Source/QA/benchmark/PIT/reference gate；重新认证数据上的真实 A 股 shadow 为全部 gate `ok`。 | 在隔离 production-like MySQL 注入 Critical，并证明创建阶段和 worker 阶段均未启动 LEAN 容器。 |
| AUD-004 指纹不稳定 | FIXED_PENDING_REAUDIT | 两次 pinned real-LEAN golden run 的 `inputFingerprint`、schema v2 `canonicalResultSha256`、ending equity、fill count 和完成日期完全一致；raw SHA 因运行元数据不同而允许不同。 | 独立审计重跑同一双跑，并验证只改变一个策略参数时 input/canonical 关系符合规范。 |
| AUD-005 Preview 孤儿对象 | FIXED_PENDING_REAUDIT | Preview 只选完整 stored object，读取校验 chunk、长度和 SHA；历史孤儿已隔离；受治理重建后的股票、日历、指数、期货和期权十类 Preview 均已读取真实数据。 | 在独立浏览器复验中注入缺失对象并保存结构化错误与无白屏截图。 |
| AUD-006 Daily Preview 慢查询 | FIXED_PENDING_REAUDIT | Preview 使用规范化 exact symbol；生产 MySQL `EXPLAIN ANALYZE` 为 PK lookup，daily/adj/suspend/stk_limit 分别约 11.3/6.4/4.8/0.9 ms，实际服务调用均降至毫秒级。 | 保存独立浏览器 P95 和并发预览证据。 |
| AUD-007 LEAN 集成测试契约 | FIXED_PENDING_REAUDIT | opt-in 真实 Docker/LEAN 测试在重建完成后重新执行，`1 passed`，JUnit 保存在 `/private/tmp/lean-platform-audit-remediation-real-lean-20260723.xml`。 | 独立审计保存镜像 inspect、JUnit 和运行 artifact checksum。 |
| AUD-008 SQLite 默认测试 | OPEN | 单元套件明确为 SQLite，迁移翻译与生产 MySQL 检查分离。 | 建立强制 MySQL repository/migration lane 与 nightly real-LEAN/browser lane，并在报告中标注 engine/source/image。 |
| AUD-009 CSI300 portable PIT | PARTIAL | TuShare 全期实取 76,498 行，254 个完整月度快照生成 76,200 条 `CSI300_TUSHARE` 区间，覆盖 2005-04-29..2026-06-30；2009-12-31 不完整快照已隔离，仍不覆盖官方 `CSI300`。 | 保留或获取中证官方不可变附件；补齐官方 2005–2017 覆盖并验证 correction ledger。 |
| AUD-010 十数据集证据 | FIXED_PENDING_REAUDIT | run `b15c8791-1e35-499d-9730-6b4d4e42164b` 十项全部 success、0 failed，completion/raw integrity 通过；MySQL、Parquet/DuckDB、ClickHouse 的 TuShare equity canonical 均为 17,668,931 行。 | 独立审计按 manifest、watermark、archive/object checksum 再抽样，并保存数据版本快照。 |
| AUD-011 备份命令 | FIXED_PENDING_REAUDIT | `scripts/backup_mysql.sh` 使用 `--no-tablespaces`、partial 文件、SHA-256 和 0600 权限。 | 定义 RPO/RTO、加密/保留策略，并执行生产规模异机恢复。 |
| AUD-012 真实 21 日 Paper | PARTIAL | session `b05836d8-8bb8-4df4-9896-a7e2919ec0a7` 已完成 2023-07-03..2023-07-31 共 21 个交易日的真实累计 LEAN 子回测：21 success、21 reports、21 snapshots、2 filled、0 reconciliation failure，重复末日被 HTTP 400 阻断且计数稳定。 | 同 session 没有约束拒单，严格验收为 `partial`；需实现 LEAN intent 执行前约束拒单，再做六阶段中断、费用和恢复对账。 |
| AUD-013 Browser E2E 回归 | FIXED_PENDING_REAUDIT | 当前构建和重新认证数据上 Chromium 为 15 passed、1 个显式截图用例 skipped；真实 SPY/A 股 Web 回测、Docs、响应式与错误恢复通过。 | 补足审计规范中尚未自动化的 Data 全操作、实验批次、Paper 与缺失对象浏览器截图矩阵。 |
| AUD-014 网络与默认凭据 | PARTIAL | API Bearer Token 自动生成；所有服务端口默认 loopback。本轮只读运行态复核明确检出 MySQL user/root 与 Grafana admin 仍为仓库已知默认值。 | 在维护窗口原子轮换 MySQL、ClickHouse、Redis 与 Grafana 凭据并验证已有数据卷、健康检查和所有客户端升级；本轮未在刚完成重建的正式卷上冒险执行。 |
| AUD-015 对象引用完整性 | FIXED_PENDING_REAUDIT | 删除保护、定期不变量报告、依赖健康孤儿计数和同步完成谓词已实现；历史不可恢复引用保留在 issue 表。 | 在隔离 MySQL 注入孤儿并验证清理阻断、success 阻断和重建路径。 |
| AUD-016 Migration CLI 文档 | FIXED_PENDING_REAUDIT | 文档统一使用 `db_migrate.py --status/--verify`，CLI 保留兼容入口。 | 文档命令 smoke 进入 CI。 |
| AUD-017 Grafana 地址 | FIXED_PENDING_REAUDIT | host 端口由 `LEAN_GRAFANA_PORT` 统一传入 API 返回 URL，Compose 端口回环绑定。 | 使用非默认端口执行浏览器链接与依赖页验收。 |
| AUD-018 供应链 | PARTIAL | Python、MySQL、Redis、ClickHouse、Prometheus、Grafana 和 Grafana 插件已固定；当前 11 个本地运行镜像已生成 CycloneDX SBOM 与 SHA-256 manifest，新增机器可读固定检查。 | Python transitive hash lock、漏洞策略/例外账本和可信主体镜像签名验证仍未完成。 |
| AUD-019 故障矩阵 | PARTIAL | 活动任务门禁先在 1 backtest/1 Paper 时拒绝注入；任务结束后 worker、Redis、MySQL 依次真实重启并分别在 0.05/10.40/6.26 秒恢复，Celery pong、API 200，五类关键表行数前后完全一致。 | 在独立 Compose 完成磁盘/OOM、网络分区、in-flight 订单/成交边界和五任务并发验收。 |

## 2026-07-23 新增实现证据

- 运维告警支持 Webhook 外发、最低等级、持久化投递记录、失败信息、敏感查询参数脱敏、成功冷却和重复 Paper 调度警告升级。
- Paper walk-forward、受治理全量同步和自动报告失败会产生 Critical 告警；外发失败不会把原任务误标成功或覆盖原始错误。
- `alert_deliveries` 由 migration `0021` 管理，`GET /api/alert-events` 返回对应投递审计记录。
- 后端完整回归：`354 passed, 1 skipped`；Compose、仓库卫生、帮助文档、OpenAPI 帮助索引和 diff 检查通过。
- full rebuild 的 `daily` 已完成 5867/5867、0 failed；本轮完整 daily 阶段约 23 分钟。十数据集 canonical、派生一致性与重新认证均已完成，production Source Gate 已按新数据版本重新开放。

## 2026-07-23 受治理重建复验

- canonical run `b15c8791-1e35-499d-9730-6b4d4e42164b` 的 10 个数据集全部 `success`、零失败，completion evidence `passed=true`，raw object integrity `passed=true`。
- 首次一致性门禁正确阻断认证：daily manifest/raw archive 为 17,668,931 行，但旧 upsert-only 语义在 canonical 中遗留 14,356 条历史 code-reuse 行，另有错误归类为 equity 的 `000300` 614 条。
- `scripts/reconcile_tushare_daily_full_snapshot.py` 先 dry-run，再从 87 个 raw archive 重建权威 key 集合；应用后 `ashare_daily_bars` 与 `market_daily_bars` 均精确为 17,668,931 行，12 个 mismatch 和 orphan symbol 均为 0。
- ClickHouse 对 13 个受影响 symbol 做同步 mutation 与 canonical reload；`FINAL` 行数为 17,668,931，154 个 active parts，约 346 MiB。
- 修复 full rebuild 语义，使未来全量任务在每批 QA 通过后删除权威 snapshot 中不存在的日期，并在完成时清理 run scope 外的 orphan symbol；增量更新不执行删除。
- 派生层根因修复包括：每 run advisory lock、长 visibility timeout、派生 heartbeat/checkpoint、live lease 恢复判定、ClickHouse 五年插入块与年度分区、MySQL `FORCE INDEX(PRIMARY)` 流式读取，以及按年 50,000 行缓冲写 Parquet。
- 后端完整回归更新为 `345 passed, 1 skipped`；migration 21/21 applied、0 pending、0 checksum mismatch；仓库卫生和 diff 检查通过。
- Parquet dataset `a75936aa-7e7f-5627-8583-0cef7c6542fc` 已生成 193 个文件、17,668,931 行；MySQL/DuckDB 行数一致，认证版本为 `tushare-a75936aa-7e7-540b18f28ffe`。
- ClickHouse `lean_market.market_bars FINAL` 的 TuShare A 股日线为 17,668,931 行、5,537 个 symbol、覆盖 `1990-12-19..2026-07-22`，与 canonical 一致。
- `index_daily` raw archive 已规范化为独立 `asset_class=index` canonical；CSI300 `000300` 共 5,954 行，2023-01-03 至 2023-06-30 基准窗口 118/118，LEAN cache 校验通过。

## 2026-07-23 重建后 Level 3 复验

- 受治理 shadow audit 返回 `LEVEL3_PASS`：symbols `600519,000001`、benchmark `000300`、source `tushare`；daily pipeline、真实 LEAN backtest、Paper signal-simulation helper 和七类拒单约束均通过。
- shadow pipeline `l3p-20260723131320-edee9f78` 覆盖 118 个交易日；回测 `600519-20230103-20230630-20260723131515` 成功；Paper helper 生成 118 份日报和 44 笔成交。该 helper 不是 21 日真实 LEAN walk-forward，不能用于关闭 AUD-012。
- 两次新 golden run `600519-20230103-20230630-20260723133141` 与 `600519-20230103-20230630-20260723133253` 的 input fingerprint 均为 `55b5e219…c84c355`，canonical result digest 均为 `94058dd2…d7dbc35`，ending equity 均为 `964864.92`，fill count 均为 5；raw digest 不同且按 schema v2 明确排除运行元数据。
- 找到并修复 fingerprint 性能瓶颈：trade-status 查询补全 `(asset_class, market, symbol, trade_date)` 索引前缀，生产窗口构建由约 206.55 秒降至约 0.16 秒。
- 修复终态 backtest 遗留 scheduler lease；新任务可回收 failed/cancelled/success holder，不再等待两小时 TTL。
- 十个 Preview API 均返回 HTTP 200；无 keyword 时 trade calendar 8,687、index basic 9,643、CSI300 index daily 5,954、future basic 11,119、option basic 65,948 条。
- 真实 Docker/LEAN integration `1 passed`；后端 `354 passed, 1 skipped`；前端 production build 通过；Chromium E2E `15 passed, 1 skipped`；migration 21/21 applied 且 checksum 正常。

本节是整改方的受控复验，不替代独立审计。完整 Level 5 同 session
成交/拒单门禁、完整故障注入、生产规模 DR、默认凭据轮换、供应链签名
和 Docker runner 权限边界完成前，不提升最终成熟度结论。

## 2026-07-23 专项运行证据

- 真实 LEAN Paper 证据：
  `/private/tmp/lean-paper-21day-20260723.json`。连续 21 日链路本身通过，
  但同 session 为 2 笔成交、0 笔拒单，因此
  `level5ReplayRequirementsPassed=false`，不得关闭 Level 5。
- 服务恢复证据：
  `/private/tmp/lean-service-fault-20260723.json`。worker、Redis、MySQL
  均恢复且不变量稳定；磁盘、OOM、网络分区和 in-flight 边界显式未覆盖。
- CSI300 TuShare 影子证据：
  `/private/tmp/csi300-tushare-shadow-import-20260723.json`。影子数据不改变
  官方 `CSI300` 2017-12-08 以前的 `coverage_gap`。
- 供应链证据：
  `/private/tmp/lean-platform-sbom-20260723/` 包含 11 个运行镜像的
  CycloneDX SBOM 和 SHA-256 manifest；
  `/private/tmp/lean-supply-chain-check-20260723.json` 因 Python 仍为版本区间
  正确返回 failed。签名验证未因缺少可信签名主体而伪造通过。
- 新增 `scripts/restore_mysql.sh`，校验 dump SHA-256 并拒绝覆盖正式
  `lean_market`；本轮没有在正式 60+ GiB 数据卷旁创建第二份数据库，
  所以生产规模 DR 仍未执行。

当前结论仍保持：

```text
LEVEL3_FAIL
LEVEL4_FAIL
LEVEL5_REPLAY_BLOCKED
LEVEL5_OPERATIONAL_NOT_READY
LIVE_NOT_READY
```
