# Actual-environment data review — 2026-08-02（第二次审计）

## 1. 结论

当前 equity/index 主链可执行：TuShare equity Parquet 17,703,084 行、index Parquet 44,741 行均为 production/certified/QA ok，4 个 derived watermark ready，当前 source recertification 成功，最小回测 preflight `ready=true`。但 `0040` 未部署，实际没有 immutable Dataset Release；`parquet_datasets` 的两份 production certification 与 158 条全 research/uncertified 的 `dataset_versions` 构成双重版本权威。期货、期权、可转债、分钟/tick 没有 canonical executable data；公司行动仅 59 行/3 symbols。数据成熟度为 PARTIAL，不足以支撑“全部资产 Level 5”。

本轮没有下载、导入、同步、重建、重新认证或修改 certification。所有检查使用当前 canonical MySQL、已有 raw archives、Parquet、watermarks、LEAN cache、stored objects、QA/certification 和只读 SQL/API。

## 2. 当前数据资产

| 资产/表 | 当前数量 | 时间/覆盖 | Source/Version | Certification/QA | 状态 |
| --- | ---: | --- | --- | --- | --- |
| `instruments` | 8,103 | 8,095 equity；8 index | canonical multi-source | current health | PASS |
| `securities` | 5,902 | listed/ST/delisted lifecycle | reference sources | reference gate | PASS |
| trade calendar | 8,693 | 1990-12-19..2026-07-30 | TuShare | gate pass | PASS |
| `market_daily_bars` | 19,220,229 | current daily scope | TuShare/derived | canonical | PASS |
| `ashare_daily_bars` | 19,163,456 | A-share daily | TuShare | canonical | PASS |
| market trade status | 18,302,220 | 8,053 symbols | TuShare/reference | gate | PASS/PARTIAL |
| suspended days | 141,551 | historical | trade status | gate | PASS |
| ST securities | 557 | lifecycle | reference | gate | PASS |
| delisted securities | 366 | lifecycle | reference | gate | PASS |
| corporate actions | 59 | 3 symbols | AKShare cninfo | gate pass for covered scope | PARTIAL |
| PIT memberships | 299,610 | multiple universes | PIT sources | watermark | PASS/PARTIAL |
| CSI300 membership | 1,225 | 2005 launch-aware onward | official PIT input | current | PASS |
| `parquet_datasets` | 7 | 2 production + research/stale | multiple | 2 certified | PASS/PARTIAL |
| `dataset_versions` | 158 | run/scope snapshots | multiple | certified=0,production=0 | FAIL |
| `stored_objects` | 25,011 | raw/cache/result/PIT | SHA-256 | provider raw orphan=0 | PASS |
| provider raw quarantine | 37 issues | existing history | provider raw | quarantined | PASS/PARTIAL |
| futures | canonical 0 | none | fut_basic metadata only | cross-asset QA fail | NOT_SUPPORTED |
| options | canonical 0 | none | opt_basic metadata only | cross-asset QA fail | NOT_SUPPORTED |
| convertible bonds | canonical 0 | none | required datasets missing | cross-asset QA fail | NOT_SUPPORTED |
| minute/tick | canonical 0 | none | none | unavailable | NOT_SUPPORTED |

## 3. Production Parquet 和 derived stores

| Dataset ID | Asset | Rows | Files | Range | Dataset version | Environment | Certified/QA |
| --- | --- | ---: | ---: | --- | --- | --- | --- |
| `a75936aa-7e7f-5627-8583-0cef7c6542fc` | equity | 17,703,084 | 194 | 1990-12-19..2026-07-30 | `tushare-a75936aa-7e7-a1cf7654b7c7` | production | yes/ok |
| `0338bdfe-27b0-54e2-bb3b-c95f0ca9aaad` | index | 44,741 | 37 | 1990-12-19..2026-07-30 | `tushare-0338bdfe-27b-01a1017c9e40` | production | yes/ok |

| Layer | Scope | Rows | Range | Status | Content hash |
| --- | --- | ---: | --- | --- | --- |
| Parquet | equity | 17,703,084 | 1990-12-19..2026-07-30 | ready | `e66b453b9fdf44ce…` |
| Parquet | index | 44,741 | 1990-12-19..2026-07-30 | ready | `fcb14a74fbc971e2…` |
| ClickHouse | equity | 17,703,084 | same | ready | `0bacc02a94f7829e…` |
| ClickHouse | index narrow scope | 5,960 | 2002-01-04..2026-07-30 | ready | `302fc49ada8b287c…` |

ClickHouse index 的 scope 明显比全 index Parquet 窄，不能直接以 5,960 vs 44,741 判 drift；API/UI 应显示 scope 和过滤条件。DuckDB 仅查询 derived Parquet，不是 canonical write store。

## 4. 数据同步、checkpoint 和认证时间线

最新 20 个 sync run 可查，当前 `ee0522…` 为 `all_entitled_low_frequency` success；此前有 partial/failed 和 MySQL 2013。最近 recertification `5f59c8c1-3a3e-4b6d-aafd-be59b20a9ef0` 成功，在它之前至少 8 次失败：多次 MySQL lost connection 和 worker restart orphan。当前水位已恢复 ready，说明 fail-closed 和最终恢复真实存在；也证明恢复过程尚不稳定。

P1 源码已增加 single-active、attempt、heartbeat、checkpoint、resume 和指数退避，但实际 `0040`/进程未部署，不能将代码测试升级为 actual PASS。验收需要部署后观察 7 日，无需全量重建。

## 5. Source、batch、version、QA、certification 追踪

```text
Provider response
  -> provider raw stored object (source/batch/hash)
  -> normalization / identifier mapping
  -> canonical MySQL
  -> QA report / quarantine
  -> current source certification
  -> Parquet + LEAN cache watermarks
  -> backtest/Paper request
  -> raw result artifact / parsed result
```

各层均能找到部分 ID/hash，但无法用一个 actual `dataset_release_id` 贯穿：0040 的 `dataset_releases` 表不存在，`/api/data/releases` 404。现有 production Parquet version 与 run-scoped `dataset_versions` 不是同一权威；部分 backtest 指纹的 LEAN zip/factor SHA 为空。这是 `ACT-P1-005/P1-006`，直接影响复现。

## 6. 数据正确性抽样

第二次审计复用同日首次审计样本，并以当前 health/reference range 重新确认数据仍在：

| 类型 | 样本/事实 | 检查 | 状态 |
| --- | --- | --- | --- |
| 普通A股 | 600519，2026-07-30 | O/H/L/C 1323/1362/1322/1361.76，volume 7,187,261 | PASS |
| ST | 000010 `*ST美丽` | `is_st=1`、UTF-8正常 | PASS |
| 停牌 | 002348，2010-03-30 | suspended=1，tradeable/buy/sell=0 | PASS |
| 公司行动 | 000001 | dividend action可关联source | PASS（样本） |
| 退市 | 000004 `国华退` | delisted 2026-07-14 | PASS |
| CSI300 | 000300 | index instrument + PIT membership | PASS |
| 指数 | 8 instruments | 000001/16/300/688/852/905/399001/399006 | PASS |
| ETF | 独立instrument/executable sample | 0 | FAIL |
| 可转债 | canonical | 0 | NOT_SUPPORTED |
| 期货 | raw metadata only | canonical 0 | NOT_SUPPORTED |
| 期权 | raw metadata only | canonical 0 | NOT_SUPPORTED |

`ST days=1` 与 ST securities 557 的统计口径差异需要专项说明或检查，但没有证据证明行值错误；本轮不以“可能”立 issue。公司行动的 3-symbol 覆盖是明确缺口，不能用少量样本推断全A股规则完整。

## 7. PIT、benchmark 与交易规则数据

- CSI300 official PIT 从 launch-aware 历史开始，未发现 current constituent substitution；当前 membership/watermark 可关联。
- 其他部分 universe 的覆盖为 partial，缺失窗口应 fail closed。
- benchmark 000300 在 run1 原始结果中收益 6.2461%，不是常量 placeholder。
- trade calendar、status、ST、suspension、delisting、adjustment/corporate-action gate 都存在；“gate存在”不等于每项 matching 已在本轮逐条成交验证。
- Paper deployment 的 source/PIT/QA/release 必须绑定当前 release；actual trust仍引用旧账户，不能作为当前数据可信证明。

## 8. MySQL、Parquet、ClickHouse 与 LEAN cache 一致性

本轮没有调用会持久化新 report 或触发重比较的 consistency POST，也没有全量逐文件 rehash。当前只读证据：

1. production Parquet row count/date range 与其 derived watermark一致；
2. 两个 production scope 有 content hash、certified/QA ok；
3. ClickHouse equity row count与Parquet一致，index明确为窄scope；
4. 现有 consistency reports/QA 可查，但不是本轮新建；
5. `lean-data-files` 约23,985 objects/702MB，现有真实LEAN run可读取并产出raw result；
6. run1 raw result SHA与stored object SHA一致。

结论：当前平台水位一致性 PASS；本轮独立全量 MySQL↔Parquet rehash NOT_VERIFIED。该 NOT_VERIFIED 来自明确的“不进行无必要全量构建”约束，不单独构成 Level5 Fail；版本权威分裂和run级cache hash缺失则是实质问题。

## 9. Fail-closed

| Gate | 当前实际证据 | 状态 |
| --- | --- | --- |
| source certification | 当前health ok；历史未认证preflight被拒 | PASS |
| preflight current source | 实际200、ready=true | PASS |
| benchmark coverage | run1真实benchmark；缺失场景未构造 | PARTIAL |
| PIT/current substitution | official launch-aware CSI300 | PASS/PARTIAL |
| QA critical | 当前production ok；20 latest含2 critical历史报告 | PARTIAL |
| synthetic/research source | production gate区分 | PASS/PARTIAL |
| cross asset missing | cross-asset QA `passed=false` | PASS（fail-closed） |
| manifest/stale derived | watermarks/certification blocker存在 | PASS |
| final backtest gate | canonical success + final critical | **FAIL** |
| Dataset Release | actual table/endpoint不存在 | **FAIL** |

不得通过修改正式 certification 来制造失败案例；本轮只使用历史拒绝和当前 preflight/health。

## 10. LEAN 原始 artifact 与数据版本

run `000001-20260401-20260722-20260728142527` 的 raw result SHA-256 为 `9d06b8eafe346594673c593f149030077df131958d487074afa61a61fd37e18c`，stored object、本地artifact、parsed metrics和HTML report相符。其 dataset version仍属于research/uncertified记录体系，LEAN zip/factor SHA为空，实际 reproducibility certificate endpoint 404。因此可以证明“真实LEAN和raw先保存”，不能证明“冻结release下相同输入完全可复现”。

## 11. 当前数据问题

| Issue | 明确事实 | 严重度 |
| --- | --- | --- |
| ACT-CRIT-001 | final critical validation仍对应canonical success | Critical |
| ACT-P1-005 | 2 production Parquet vs 158全research dataset versions；无release | P1 |
| ACT-P1-002 | recertification多次MySQL2013/orphan；新恢复代码未部署 | P1 |
| ACT-P1-004 | catalog泛资产入口与canonical executable 0不一致 | P1 |
| DATA-GAP-CA | corporate actions仅59 rows/3 symbols | 纳入P1-004数据覆盖 |
| ACT-P1-006 | no Golden pair，run cache/certificate digest不完整 | P1 |

## 12. 不重复创建数据说明

本轮复用：19.2M canonical bars、当前 certification、7 Parquet datasets、4 watermarks、25,011 stored objects、provider raw archives、PIT bundle、LEAN cache、3 backtests和现有QA/sync records。未下载TuShare、重复导入行情、生成全量Parquet/ClickHouse、导入CSI300、创建证券/日历/公司行动、修改source certification或运行全量consistency。后续只需应用0040并做增量release认证，不需要全量重导。

## 13. 验收条件

1. actual `0040` applied，equity/index各有一个active immutable release。
2. Parquet、QA/certification、LEAN cache manifest、run和certificate均引用同release。
3. success run不存在 final critical trusted记录。
4. capability API与canonical行数/认证一致，unsupported资产fail closed。
5. recertification连续7日无lost/orphan chain。
6. 当前Golden Pair的canonical/orders/fills/equity digest一致。
7. 公司行动覆盖达到声明scope，或UI/preflight明确限制可执行scope。
