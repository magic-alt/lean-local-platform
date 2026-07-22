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
| AUD-001 Source Gate | FIXED_PENDING_REAUDIT | `source_gate.py` 使用持久化认证、manifest、QA 与环境门禁；旧认证已撤销；Source/QA 回归通过。 | full rebuild、Parquet 一致性和 production certification 完成后重跑 MySQL + LEAN 双阶段拒绝矩阵。 |
| AUD-002 容器/API 隔离 | PARTIAL | API 默认认证且端口仅绑定 loopback；LEAN 镜像 digest allowlist、无网络、只读根、资源/PID限制、最小挂载。 | `backtest-worker` 仍是持有 Docker socket 的可信基础设施，不构成多租户边界；需 socket proxy 或独立 runner。 |
| AUD-003 QA Critical 绕过 | FIXED_PENDING_REAUDIT | 创建和 worker 执行阶段复用 fail-closed Source/QA/benchmark/PIT/reference gate。 | 使用重新认证的 A 股数据证明 Critical 时没有启动 LEAN 容器。 |
| AUD-004 指纹不稳定 | FIXED_PENDING_REAUDIT | `run_fingerprint.py` 提供稳定 input fingerprint 与 canonical result digest，排除 run ID、时间和随机 trade UUID；单元回归覆盖参数与数据变更。 | 两次 pinned real-LEAN golden run 比较 input/result digest 和数值容差。 |
| AUD-005 Preview 孤儿对象 | FIXED_PENDING_REAUDIT | Preview 只选完整 stored object，读取校验 chunk、长度和 SHA；历史孤儿已隔离，维护删除受引用保护。 | full rebuild 后复验指数、期货、期权预览及缺失对象结构化错误。 |
| AUD-006 Daily Preview 慢查询 | PARTIAL | Preview 已使用规范化 symbol 和边界分页路径。 | 在重建后的约 19M+ 行 MySQL 上记录 `EXPLAIN ANALYZE` 与 P95 延迟，必要时增加覆盖索引/有界 count。 |
| AUD-007 LEAN 集成测试契约 | FIXED_PENDING_REAUDIT | opt-in 测试已补 `language` 参数；加固后曾运行通过。 | 数据构建期间不争抢 Docker；构建完成后重新保存 JUnit、镜像 digest 和 artifact checksum。 |
| AUD-008 SQLite 默认测试 | OPEN | 单元套件明确为 SQLite，迁移翻译与生产 MySQL 检查分离。 | 建立强制 MySQL repository/migration lane 与 nightly real-LEAN/browser lane，并在报告中标注 engine/source/image。 |
| AUD-009 CSI300 portable PIT | PARTIAL | 增加 TuShare `index_weight` 影子 universe，隔离为 `CSI300_TUSHARE`，不覆盖官方 `CSI300`。 | 保留或可获取官方不可变附件；补齐 2005–2017 覆盖并验证 correction ledger。 |
| AUD-010 十数据集证据 | IN_PROGRESS | 完成谓词要求 item、manifest、watermark、raw archive、对象引用和 derived 状态全部一致；当前正在执行受治理 full rebuild。 | 等待十数据集、Parquet materialization、一致性报告和重新认证全部成功。 |
| AUD-011 备份命令 | FIXED_PENDING_REAUDIT | `scripts/backup_mysql.sh` 使用 `--no-tablespaces`、partial 文件、SHA-256 和 0600 权限。 | 定义 RPO/RTO、加密/保留策略，并执行生产规模异机恢复。 |
| AUD-012 真实 21 日 Paper | OPEN | 已有逐日 LEAN walk-forward 数据模型和自动交易日调度。 | 执行真实 21 日链路、六阶段中断、成交/费用/报告幂等与对账。 |
| AUD-013 Browser E2E 回归 | FIXED_PENDING_REAUDIT | 修复报告、重复提交和移动端溢出后 Chromium 为 15 passed、1 skipped。 | 在当前构建和重新认证数据上重跑完整 Web-01 至 Web-07。 |
| AUD-014 网络与默认凭据 | PARTIAL | API Bearer Token 自动生成；所有服务端口默认 loopback。 | 轮换 MySQL、ClickHouse、Redis 与 Grafana 默认凭据并验证已有数据卷升级。 |
| AUD-015 对象引用完整性 | FIXED_PENDING_REAUDIT | 删除保护、定期不变量报告、依赖健康孤儿计数和同步完成谓词已实现；历史不可恢复引用保留在 issue 表。 | 在隔离 MySQL 注入孤儿并验证清理阻断、success 阻断和重建路径。 |
| AUD-016 Migration CLI 文档 | FIXED_PENDING_REAUDIT | 文档统一使用 `db_migrate.py --status/--verify`，CLI 保留兼容入口。 | 文档命令 smoke 进入 CI。 |
| AUD-017 Grafana 地址 | FIXED_PENDING_REAUDIT | host 端口由 `LEAN_GRAFANA_PORT` 统一传入 API 返回 URL，Compose 端口回环绑定。 | 使用非默认端口执行浏览器链接与依赖页验收。 |
| AUD-018 供应链 | PARTIAL | Python、MySQL、Redis、ClickHouse、Prometheus、Grafana 和 Grafana 插件均固定到已核验 digest/version。 | Python hash lock、SBOM、镜像签名验证和漏洞例外账本仍未完成。 |
| AUD-019 故障矩阵 | OPEN | 数据同步 heartbeat/checkpoint/recover 与任务 lease 有单元回归。 | 在隔离 Compose 执行五任务并发、阶段取消、Redis/MySQL/worker/磁盘/OOM 故障注入。 |

## 2026-07-23 新增实现证据

- 运维告警支持 Webhook 外发、最低等级、持久化投递记录、失败信息、敏感查询参数脱敏、成功冷却和重复 Paper 调度警告升级。
- Paper walk-forward、受治理全量同步和自动报告失败会产生 Critical 告警；外发失败不会把原任务误标成功或覆盖原始错误。
- `alert_deliveries` 由 migration `0021` 管理，`GET /api/alert-events` 返回对应投递审计记录。
- 后端完整回归：`332 passed, 1 skipped`；Compose、仓库卫生、帮助文档和 diff 检查通过。
- full rebuild 的 `daily` 已完成 5867/5867、0 failed；本轮完整 daily 阶段约 23 分钟。整个十数据集 run 尚未完成，因此不得恢复 production certification 或提高成熟度评级。

当前结论仍保持：

```text
LEVEL3_FAIL
LEVEL4_FAIL
LEVEL5_REPLAY_BLOCKED
LEVEL5_OPERATIONAL_NOT_READY
LIVE_NOT_READY
```
