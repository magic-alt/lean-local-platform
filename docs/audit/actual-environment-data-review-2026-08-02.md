# Actual-environment data review — 2026-08-02（第四次复审）

## 1. 结论

数据维度保持 **13/15**，但第三次复审遗留的实际大规模 lineage OOM 已被本轮发现并修复。`0043_p1_lineage_query_index` 已应用，原 maintenance run 从 checkpoint attempt 3 成功恢复；equity 17,703,084 rows/194 files、index 44,741 rows/37 files均与 DuckDB derived output 对账。剩余 2 分来自连续 7 日稳定观察和有限公司行动/全量规则覆盖，不是当前 recertification失败。

## 2. 当前认证资产

| Scope | Canonical/Release事实 | Derived事实 | 状态 |
| --- | --- | --- | --- |
| equity/china/daily/trade/raw/tushare | active production certified；17,703,084 rows | 194 files；21,273 batch groups；DuckDB match | PASS |
| index/china/daily/trade/raw/tushare | active production certified；44,741 rows | 37 files；DuckDB match | PASS |

Dataset Release仍是 production authority；run、certificate、Paper deployment和WF均引用有效 frozen release。unsupported scopes继续以 `metadata_only` 或 `unavailable` fail-closed，不因 catalog metadata存在而宣称 executable。

## 3. Lineage OOM 根因与修复

maintenance run `7f9b66f5-cdca-47f5-9c97-226ae5ed0e3e` 在对 17.7M equity rows 执行 `batch_id,symbol` grouping 时出现 MySQL OOM。该查询缺少与 scope过滤和group顺序匹配的索引，optimizer使用高内存 grouping/filesort；这也是旧 attempt不能完成而非数据缺失的根因。

本轮修复：

1. additive migration `0043_p1_lineage_query_index` 增加 production-lineage复合索引；
2. MySQL lineage query使用明确 `FORCE INDEX`，SQLite测试路径保持兼容；
3. rollback policy声明该索引只通过 reviewed forward migration移除；
4. checkpoint保留并从 attempt 3恢复，没有删除旧失败或从头重导；
5. query结果与 DuckDB rows/files重新对账。

修复关闭当前 OOM 和不可恢复事实；`ACT-P1-002` 仍要求连续 7 日无 MySQL 2013/OOM/orphan chain，所以状态为 `OPEN_OBSERVATION_PENDING`。

## 4. Capability 与 fail-closed

| Asset/resolution | Canonical rows | State | 结论 |
| --- | ---: | --- | --- |
| equity daily | production release覆盖 | executable | PASS |
| index daily | 44,741 | executable | PASS |
| equity minute/tick | 0 | metadata_only | fail-closed |
| ETF/option daily | 0 canonical | metadata_only | fail-closed |
| future/cbond daily | 0 | unavailable | fail-closed |

四态契约 `unavailable/metadata_only/data_ready/executable` 保持。Paper 本轮新增 admission guard：即使 backtest trusted，若其参数显式标记 research-only、screening或不可交易，也不能成为执行 seed。

## 5. WF、Backtest 与 Paper 数据链

### Walk-Forward

batch `8ee62a11-d82a-47eb-ab6a-df64bdc4cda9`：

- Train run `600519-20230101-20231231-20260803151007`；
- Validation run `600519-20240101-20240630-20260803151040`；
- OOS run `600519-20240701-20241231-20260803151330`；
- certificate valid，decision=`ALLOW`，leakage violations=0；
- result digest=`c0a561…`，config digest=`baa51e…`。

三个区间、selection和OOS lineage不可变，关闭 `ACT-P0-002`。

### Paper executable source

source backtest `600519-20230101-20231130-20260804065922` 为 trusted、`strategyMode=STANDARD`、`researchOnly=false`、tradable/admission eligible，47 orders、net 7.802%，引用 certified production data。它替代了会生成零可执行订单的 screening source。

两个差异资金账户最终各完成 23 个成功日并形成 certified cohort。首个 cumulative child允许基于账户初始资本建立数量不同但代码/数据/时间一致的 immutable baseline；此后每个 child均与上一成功 child的历史 orders fingerprint对账，真实 drift regression仍会失败。ledger replay与projection cash/positions一致。

## 6. QA、PIT 和交易规则

| Gate | 第四次复审结果 | 状态 |
| --- | --- | --- |
| source certification/release | active production certified | PASS |
| MySQL↔DuckDB counts | equity/index match | PASS |
| maintenance checkpoint resume | attempt3 success | PASS |
| WF leakage | valid cert、0 violations | PASS |
| Paper executable admission | research/screening fail-closed | PASS |
| Paper non-zero fill/reject | actual evidence | PASS |
| unsupported assets | metadata_only/unavailable | PASS |
| 7-day maintenance stability | 时间窗口未满 | OPEN |
| company actions | 当前声明scope有限 | PARTIAL |
| full MySQL↔Parquet rehash | 未执行、无必要重建 | NOT_VERIFIED |

本轮未下载新的全市场 provider数据、未全量 reimport、未重建全部 Parquet/ClickHouse。有限 scope 不被推广为全资产/全市场覆盖。

## 7. 剩余数据任务

1. 保持当前 0043 和 bounded-memory query，连续 7 日采集 single-active、checkpoint、attempt、MySQL连接错误和orphan evidence；
2. 若窗口内再次失败，只从现有 checkpoint恢复，不删除历史 run；
3. 明确公司行动实际覆盖范围，并在 preflight/UI维持 fail-closed声明；
4. 全量 rehash仅在 manifest/count drift触发时执行，不为审计分数做无必要重建；
5. 后续 Golden/WF/Paper regression继续引用同一类 frozen certified release并包含非零fill样本。

## 8. 数据问题状态

| Issue | 状态 | 说明 |
| --- | --- | --- |
| ACT-P1-002 | OPEN_OBSERVATION_PENDING | 当前 OOM已修复并恢复成功；7日门禁未满 |
| ACT-P1-004 | RESOLVED | capability/canonical truth一致 |
| ACT-P1-005 | RESOLVED | Dataset Release为唯一production authority |
| ACT-P1-006 | RESOLVED | Golden Pair/certificates可取 |
| ACT-P0-002 | RESOLVED | current valid WF certificate |
| ACT-P0-001 | RESOLVED | Paper 2×23与ledger replay |

因此，数据链本身不再是 P0；只有真实 7 日观察、范围声明和非必要全量 rehash仍未完成。
