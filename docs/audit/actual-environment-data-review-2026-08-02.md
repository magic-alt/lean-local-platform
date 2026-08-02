# Actual-environment data review — 2026-08-02

## 1. 结论

当前 equity/index 主数据在审计期间完成重新认证，健康状态最终为 `ok`；TuShare equity Parquet 17,703,084 行、index Parquet 44,741 行均为 production/certified/QA ok，Parquet watermarks 与自身 row_count/date range 一致。数据治理能力真实存在，但尚未形成单一 Dataset Release 权威：`parquet_datasets` 有两份 production certification，`dataset_versions` 158 条却全部为 research/uncertified。跨资产 canonical 数据仅有 equity/index；期货、期权、可转债、分钟/tick 不能因 raw metadata archive 或页面入口而判定支持。

本轮没有下载、导入、同步、重建或认证写入；观察到的 `source_recertification` 是平台审计前已由 Beat/worker 自动调度的现有任务，不由本轮触发。

## 2. 当前数据资产

计数优先采用 `/api/health/dependencies` 的精确 `COUNT`；未在 health 返回的超大表使用 DB 元数据/已有 QA，标记为约数。

| 资产/表 | 数量 | 时间范围/覆盖 | Source/Version | Certification/QA | 最近事实 |
| --- | ---: | --- | --- | --- | --- |
| `instruments` | 8,103 | 8,095 equity；8 index | 多 source | canonical | 2026-08-02 health |
| `securities` | 约 5,551 | listed/delisted lifecycle | TuShare/AKShare | reference gate | ST 557；delisted 366 |
| `trade_calendar` | 8,610+ | 1990-12-19..2026-07-30 | TuShare | gate pass | 当前截止日 |
| `market_daily_bars` | 19,220,229 | 多资产统一表 | TuShare 等 | canonical | health exact |
| `ashare_daily_bars` | 19,163,456 | 1990-12-19..2026-07-30 | TuShare | canonical | health exact |
| adjustment factors | 约 19.2M | A 股日频 | TuShare | preflight gate | 未全量扫描 |
| `market_trade_status` | 约 44M | 1990-12-19..2026-07-30 | TuShare/inference evidence | gate pass | suspended 样本存在 |
| `corporate_actions` | 59 | 1992-03-23..2026-06-26，3 symbols | AKShare cninfo | gate pass，但窄 | dividend 样本 |
| factor values | 约 8M | 财务/因子 | 多源 | research | 未专项复算 |
| financial facts | 约 1.1M | 基本面 | 多源 | research | 未专项复算 |
| PIT membership | 299,610 | 多 universe | official/secondary | watermark | health exact |
| CSI300 official PIT | 1,225 membership rows | 2005-04-08..2026-07-26；69 snapshots；1,225 symbols/rows scope | CSIndex | complete | hash `608de…` |
| `parquet_datasets` | 7 | 5 research/stale + 2 production | 见下表 | 2 certified | 05:28 UTC recertified |
| `dataset_versions` | 158 | run/scope snapshots | 多 | 全 research/uncertified | lineage split |
| `stored_objects` | 25,011 | 多 namespace | SHA-256 | health orphan raw=0 | 约 2.2 GB 已列命名空间 |
| provider raw archive | 937 objects | daily/index/contracts/suspend/calendar | provider responses | 37 quarantine issues | 约 1.14 GB |
| futures contracts/bars | 0 canonical | 无 | raw `fut_basic` archive only | unavailable | FAIL |
| options contracts/bars | 0 canonical | 无 | raw `opt_basic` archive only | unavailable | FAIL |
| convertible bonds | 0 canonical | 无 | 无 executable release | unavailable | FAIL |
| minute/tick | 0 canonical | 无 | 无 | unavailable | FAIL |

## 3. Parquet、派生层与版本

### 3.1 当前 production Parquet

| Dataset ID | Asset | Rows | Files | Range | Dataset version | Environment | Certified | QA |
| --- | --- | ---: | ---: | --- | --- | --- | --- | --- |
| `a75936aa-7e7f-5627-8583-0cef7c6542fc` | equity | 17,703,084 | 194 | 1990-12-19..2026-07-30 | `tushare-a75936aa-7e7-a1cf7654b7c7` | production | yes | ok |
| `0338bdfe-27b0-54e2-bb3b-c95f0ca9aaad` | index | 44,741 | 37 | 1990-12-19..2026-07-30 | `tushare-0338bdfe-27b-01a1017c9e40` | production | yes | ok |

另有 AKShare equity 1,220,774 行/36 files（1991-01-29..2026-07-03）和三个极小 research/stale dataset；均不可作为 production fallback。

### 3.2 Derived watermarks

| Layer | Scope | Rows | Canonical/materialized range | Status | Content hash |
| --- | --- | ---: | --- | --- | --- |
| Parquet | equity | 17,703,084 | 1990-12-19..2026-07-30 / same | ready | `e66b453b9fdf44ce…` |
| Parquet | index | 44,741 | 1990-12-19..2026-07-30 / same | ready | `fcb14a74fbc971e2…` |
| ClickHouse | equity | 17,703,084 | same | ready | `0bacc02a94f7829e…` |
| ClickHouse | index | 5,960 | 2002-01-04..2026-07-30 / same | ready | `302fc49ada8b287c…` |

ClickHouse index 5,960 是较窄 scope，不应与全 index Parquet 44,741 直接比较为 drift；API/UI 必须显示 scope。

### 3.3 认证时间线

| Run | 时间 UTC | 结果 | 错误 |
| --- | --- | --- | --- |
| `12c81958-...` | 02:20 | failed | MySQL 2013 lost connection |
| `ef584d1c-...` | 03:35 | failed | MySQL 2013 |
| `72c61058-...` | 04:10 | failed | MySQL 2013 |
| `8d69a7cc-...` | 04:22 | failed | MySQL 2013 |
| `ce3ed091-...` | 04:47 | failed | orphaned after worker restart |
| `13ab5a87-...` | 04:55 | failed | orphaned after worker restart |
| `ee324b2b-...` | 05:01 | failed | orphaned after worker restart |
| `5f59c8c1-...` | 05:20–05:28 | success | none |

健康端点在恢复前正确输出 `degraded` 和 `source_certification` blocker，恢复后输出 `status=ok`,`executionStatus=ok`。这是 fail-closed PASS 与运行稳定性 P1 同时成立的证据。

## 4. Provider raw archives

| Dataset | Archives | Archived response rows | Latest/说明 |
| --- | ---: | ---: | --- |
| daily | 770 | 28,119,237 | latest 2026-07-30 |
| fut_basic | 4 | 44,500 | metadata only |
| index_basic | 5 | 48,215 | metadata |
| index_daily | 5 | 95,442 | latest 2026-08-02 |
| index_weight | 1 | 76,498 | PIT source input |
| opt_basic | 4 | 264,062 | metadata only |
| suspend_d | 176 | 595,200 | suspension evidence |
| trade_cal | 8 | 65,008 | calendar evidence |

Raw archive 有 source/batch/object hash，但“有 archive”不等于 canonical、certified 或 LEAN executable。

## 5. Stored objects

| Namespace | Objects | Bytes | 用途 |
| --- | ---: | ---: | --- |
| `backtest-results` | 68 | 354,443,962 | raw/summary/report artifacts |
| `lean-data-files` | 23,985 | 702,244,348 | LEAN cache files |
| `pipeline-artifacts` | 17 | 4,765,719 | pipeline evidence |
| `provider-raw` | 937 | 1,138,947,175 | provider immutable responses |
| `universe-pit` | 4 | 1,328,735 | PIT bundles |

Health 显示 orphan provider raw archives=0、quarantined issues=37。run1 本地 raw result SHA 与 stored-object SHA 匹配，证明至少该 artifact 的归档链成立。

## 6. 数据正确性抽样

| 类型 | 样本 | 结果 | 状态 |
| --- | --- | --- | --- |
| 普通 A 股 | 600519 | 2026-07-30 O/H/L/C 1323/1362/1322/1361.76，volume 7,187,261 | PASS |
| ST | 000010 `*ST美丽` | `is_st=1`，UTF-8 正常 | PASS |
| 停牌 | 002348, 2010-03-30 | suspended=1, tradeable/buy/sell=0 | PASS |
| 公司行动 | 000001 | 多次 dividend，source AKShare cninfo | PASS（样本） |
| 退市 | 000004 `国华退` | delisted 2026-07-14 | PASS |
| CSI300 | 000300 | index instrument + PIT membership | PASS |
| 指数 | 8 instruments | 000001/16/300/688/852/905/399001/399006 | PASS |
| ETF | 无独立 instrument | 0 executable sample | FAIL |
| 可转债 | 无 | 0 | NOT_SUPPORTED |
| 期货 | raw metadata only | canonical 0 | NOT_SUPPORTED |
| 期权 | raw metadata only | canonical 0 | NOT_SUPPORTED |

证券名称最初在非 utf8 CLI 下显示 `?`，以 `--default-character-set=utf8mb4` 和 `HEX(name)` 复核后确认数据库内容正常，不记录为缺陷。

## 7. Point-in-Time、benchmark 与交易规则数据

- CSI300 official PIT 以 2005-04-08 为 launch-aware 起点，没有使用当前成分替换早期历史；当前 watermark complete。
- CSI1000/CSI500/SSE50/STAR50 记录为 partial，不能在缺失窗口宣称完整。
- A_SHARE_L3P_50 的 Paper universe certification 于 2026-07-31 到期，且 50/50 有 `provider_secondary_missing` warning；当前没有账户运行，但后续 Paper deployment 必须 fail closed。
- benchmark 000300 对 run1 请求范围有 1,211 行且结果中实际收益 6.2461%，不是常量 placeholder。
- trade status gate 记录 start/end、suspended days、ST days；公司行动只有 3 symbols，是当前 reference 数据最明显覆盖风险。

## 8. MySQL/Parquet 一致性

本轮禁止触发全量 rebuild。只读证据如下：

1. 最新 derived watermark 的 Parquet equity/index row_count、范围与 `parquet_datasets` 完全相同；
2. 两个 scope 的 content SHA 已记录；
3. 51 份历史 Parquet consistency report 为 ok，最后日期 2026-07-31；同时存在 2 份历史 critical report；
4. 2026-08-02 的新 certification 已对当前 manifest 做 QA 并标 ok，但本轮没有独立逐文件重算全量 hash。

因此当前一致性为 `PASS`（平台认证和水位）/`NOT_VERIFIED`（本轮独立全量文件重算），不能把历史 51 个 ok 当作本轮全量重算。

## 9. LEAN cache

`lean-data-files` 有 23,985 objects/约 702 MB，实际回测能产生 LEAN raw result，说明 cache 使用成立。问题：run fingerprint 的 `leanZipSha256`、`factorFileSha256` 为空，无法从某个 run 独立证明其逐文件 cache 内容。要求 Dataset Release/Run Certificate 引用具体 cache manifest hash，而不是只记录 dataSource/version string。

## 10. Fail-closed

| Gate | 当前证据 | 状态 |
| --- | --- | --- |
| source certification | 恢复前 preflight HTTP 400；恢复后 health ok | PASS |
| benchmark missing/range | run validation 有 dedicated gates；未构造缺失 | PARTIAL |
| PIT missing/current substitution | official launch-aware watermark；未篡改数据 | PASS/PARTIAL |
| QA critical | 历史 critical report；当前 production QA ok | PARTIAL |
| suspension/ST/delisted/corporate action | final validation gates 与样本存在 | PARTIAL |
| synthetic/research source | production gate distinguishes | PASS（代码+实际拒绝） |
| manifest mismatch/stale derived | recertification blocker/maintenance history | PASS（门禁） |
| final run gate | success run 最终 source gate critical | FAIL（ACT-CRIT-001） |

## 11. 数据问题

1. `ACT-CRIT-001`：回测 finalization 未原子绑定数据认证。
2. `ACT-P1-005`：production certification 与 `dataset_versions` 权威分裂。
3. `ACT-P1-002`：recertification 多次 MySQL 2013/worker orphan。
4. `ACT-P1-004`：跨资产 metadata/catalog 与 executable readiness 不一致。
5. 公司行动只有 59 行/3 symbols，不能支撑全 A 股 Level 5 交易规则声称。
6. 当前 full independent MySQL↔Parquet rehash 未执行，按约束保留 NOT_VERIFIED。

## 12. 不得重复创建的数据说明

本轮复用了 canonical MySQL、当前 Parquet、watermarks、raw archives、LEAN cache、stored objects、3 个已有回测、2 个 batch 与 PIT bundle。没有重新下载 TuShare、导入 CSI300、生成全量 Parquet/ClickHouse、创建证券/日历/公司行动或修改 certification。后续整改应继续使用增量、幂等、checkpoint 和 release；任何全量操作需要独立授权，不能作为本审计默认验收步骤。

## 13. P1 数据整改附录

审计后 migration `0040_p1_trust_and_reproducibility` 和对应服务已实现，原 §1–12 仍是部署前历史事实：

- `dataset_releases` 成为 production certification 的单一 immutable authority。Parquet recertification 原子生成 release，并把 `parquet_datasets`、run-scoped `dataset_versions` 和 `backtest_runs` 绑定到 release；实际 MySQL 若仍无 release，Source Gate fail-closed。
- derived maintenance 只允许一个 active run，按 scope/layer 保存 checkpoint、attempt、heartbeat、lease owner 和 next retry；worker 丢失后续跑原 run，不再制造 orphan chain。
- `asset_capabilities` 从 canonical 表实时生成 metadata/rows 证据，区分 `unavailable/metadata_only/data_ready/executable`；未认证 scope 无法通过 preflight。
- reproducibility certificate 记录 release、Docker image、project/config、LEAN zip/factor、canonical result、orders/fills/equity 和逐文件 artifact manifest digest，并存入 object store。

代码测试覆盖 release 唯一性、maintenance resume、capability 三态和 golden pair；实际环境仍需增量 recertify 当前 equity/index，随后执行最小真实 LEAN 双跑。无需全量数据重导或全量 Parquet rebuild。

## 14. P2 数据状态 ownership 附录

Data Release、Data Sync recovery 与 Paper ledger/projection 的写入边界已显式化。`data_sync_commands` 只编排 command/task，`data_sync` 持有 sync-run 状态写入；`dataset_releases` 是 release 唯一 writer；`paper_order_pipeline` 是 ledger 唯一 writer；`paper_accounts` 是 account/position/daily projection 唯一 writer。`app/architecture/state_ownership.py` 是机器可读清单，测试扫描 SQL mutation 并拒绝第二 writer，同时禁止 API/Celery entrypoint 直接改 backtest/task/data-sync orchestration state。此项无 migration、无历史数据改写，实际环境仍需 characterization journey。
