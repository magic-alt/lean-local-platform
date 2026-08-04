# Actual-environment feature matrix — 2026-08-02（第四次复审）

`PASS` 需要第四次复审 current actual evidence；`PARTIAL` 表示能力可用但长期或扩展场景仍缺；`NOT_VERIFIED` 不由源码、单测或 mock 代替。

| Domain | Capability | 第四次复审 actual 证据 | 状态 | Issue/说明 |
| --- | --- | --- | --- | --- |
| Platform | Release identity | 8 services同 `2ebbd09…-acc872…` | PASS | ACT-P0-004 closed |
| Platform | Schema/OpenAPI | source=actual 0043；233=233；hash aligned | PASS | ACT-P0-004 closed |
| Platform | Workers/Beat | 5 Celery workers pong；Beat在线 | PASS | 同代次 |
| Projects | list/detail/files | routes与现有项目可用 | PASS/PARTIAL | Browser写journey NV |
| Strategies | templates/edit | 可执行 template/source snapshot实际创建 | PASS/PARTIAL | Browser save/clone NV |
| Data | Capability truth | 8 scopes；equity/index executable；其他 fail-closed | PASS | ACT-P1-004 closed |
| Data | Dataset Release | equity/index active production certified | PASS | ACT-P1-005 closed |
| Data | Maintenance lineage | 0043；17,703,084 equity + 44,741 index对账成功 | PASS/PARTIAL | ACT-P1-002需7日 |
| Data | Checkpoint recovery | maintenance attempt3从checkpoint恢复成功 | PASS/PARTIAL | 长期观察待补 |
| Data | Parquet/QA | MySQL↔DuckDB row count match；bounded list | PASS | 全量rehash NV |
| Data | Corporate actions | 当前声明范围 fail-closed | PARTIAL | 覆盖范围仍有限 |
| Backtest | Trusted execution | source run trusted、47 orders、7.802% net | PASS | 非零fill source |
| Backtest | Terminal trust | historical critical-success additive invalid | PASS | ACT-CRIT-001 closed |
| Backtest | Golden Pair | current pair/certificates一致 | PASS | ACT-P1-006 closed |
| Backtest | Restricted runner | tmpfs staging/allowlist；实际约5–13秒 | PASS | 无递归results copy |
| Backtest | Cursor logs | backend cursor存在 | PARTIAL | actual Browser NV，ACT-P2-002 |
| Experiment | Walk-Forward | batch `8ee62a11-…` 3/3 success、valid cert、0 leakage | PASS | ACT-P0-002 closed |
| Experiment | Grid/rolling | 未生成新的 bounded actual matrix | NOT_VERIFIED | 独立扩展验收 |
| Paper | Executable admission | research-only/screening显式 fail-closed | PASS | regression covered |
| Paper | Accounts/cohort | 原两账户最终各23 success；cohort certified；deployments paused | PASS | ACT-P0-001 closed |
| Paper | Orders/fills/rejects | duplicate同cycle；非零fill；risk rejection；no-signal | PASS | actual evidence |
| Paper | Ledger/projection | opening隔离；digest replay；cash/positions match | PASS | actual evidence |
| Paper | Restart recovery | successful runner可接续post-processing | PASS | actual deployment-window evidence |
| API | Path/schema convergence | 233/233；0043/0043 | PASS | release verifier |
| API | Primary envelopes | 既定5 endpoints + alert-events PageEnvelope | PASS | ACT-P2-001/P1-003 closed |
| API | Alert payload | 默认20条32,569 B；delivery cap3 + count | PASS | 旧约584,697 B |
| API | Idempotency timeout | timeout→same resource replay；payload drift409 | PASS | ACT-P2-003 closed |
| API | Dependency errors | worker timed detail返回200/degraded | PASS | 不再health 500 |
| Architecture | Unique writer | actual container characterization tests 3 pass | PASS | ACT-P2-004 closed |
| System | Notification delivery | health endpoint实际可用；placeholder/dead letters，无真实2xx/24h | PARTIAL | ACT-P1-007 |
| System | Capacity | limits与serial default生效；当前worker约4.6%/3GiB | PARTIAL | ACT-P1-008需24h |
| System | Frontend build | 5727 modules；无 ECharts circular warning | PASS | ACT-P3-002 closed |
| System | Architecture docs | 无硬编码latest migration | PASS | ACT-P3-001 closed |
| System | Browser/responsive | 当前无可用 Browser session | NOT_VERIFIED | ACT-P2-002 |

## 结论

Iteration 4 已将 P0 从 3 降到 0：发布收敛、真实 WF certificate 和 Paper 2×23 全部通过。剩余缺口均明确分为真实时间跨度/外部通道（3 P1）和 actual Browser（1 P2）；它们不能靠继续改代码或 synthetic evidence 合理关闭，因此当前矩阵支撑 89/100 `LEVEL5_FAIL`，不支撑提前签发 Level 5 PASS。
