# 2026-07-24 独立复审与评分更新（Level 3 复测）

本记录为 07-22/07-23 后的受控复测快照，仅针对“当前可复验范围”更新评级与得分；
不覆盖以下历史结论：

- [2026-07-22 独立成熟度审计与修复状态](independent-audit-2026-07-22.md)
- [2026-07-23 独立审计整改追踪](independent-audit-remediation-2026-07-23.md)

## 执行摘要（按本次证据）

- 审计决议：

```text
LEVEL3_PASS
LEVEL3_PLUS_PASS
LEVEL4_FAIL
LEVEL5_REPLAY_BLOCKED
LEVEL5_OPERATIONAL_NOT_READY
LIVE_NOT_READY
```

- 复核证据主文件：
  - `/tmp/level3_shadow_audit_rerun_20260724_final.json`
  - `/tmp/level3_shadow_audit_rerun_20260724.log`
  - `/tmp/level3_shadow_audit_rerun_20260724_full_debug.log`
  - 历史 run 证据：`/tmp/lean-platform-audit-remediation-real-lean-20260723.xml`

- 本次复测样本：`600519,000001,300750`，`benchmark=000300`，`source=tushare`。

## 关键结果

- `run_level3_shadow_audit.py` 复测通过。
- 生产链路层面的关键门禁通过：
  - `source_gate`、`instrument_identifier_coverage`、`daily_shadow_pipeline`
  - `backtest_smoke`
  - `paper_replay`（`sessionId=3c1bad5a-3dcb-4f5c-8f02-c8d97a86e4f3`，37 交易日）
  - `paper_constraints_acceptance`（14 天，覆盖 7 类拒单场景）

- `paper_replay` 与纸面约束场景在本次采样内未出现错误。

### 2026-07-24 本轮补齐情况（用于复验前置）

- 新增/修复了用于独立复审的脚本化入口：
  - `scripts/run_level4_audit.py`：补齐 `rolling / walk_forward / dynamic_pit` 的可复验证据采集（可预览/执行模式、CSV 导出检查、失败收敛）。
  - `scripts/run_level5_audit.py`：封装 21 日 LEAN Paper 会话、可选故障重放矩阵、重复 `run-day` 幂等性、拒单与拒因要求。
  - `scripts/run_lean_paper_walkforward_acceptance.py`：作为底层执行器，新增断点恢复与重复执行稳定性判断。
- 已修正 Level 5 复验入口的故障矩阵语义：仅在显式 `--with-fault` 时才执行 `--fault-scenarios`。
- 因环境/维护窗口限制，上述脚本在本快照内尚未形成“完整通过”证据写入；故最终结论保持 Level 4/5 为 FAIL。

## 评分与等级

将审计结论按既有成熟度权重进行“可复核范围内”重算：

- 综合评分：**54/100**（历史 26/100 上修）
- 结论：**当前可宣布 Level 3 可达，Level 3+ 通过；但 Level 4 与 Level 5 仍不通过。**

原因：

1. Level 3 关键门禁（source/QA/benchmark/reproducibility）在当前 production-like 路径中已闭环。
2. Level 4（rolling/walk-forward/动态 PIT 扩张）与部分实验批次的完整证据仍未形成。
3. Level 5 replay（真实连续 21 日 LEAN walk-forward、故障重放幂等、多日补跑/升级）仍不完整。
4. 运维与无人值守相关（故障注入全量矩阵、生产规模 DR、凭据轮换与运行边界）未完成。

### 复核复现入口（新增）

- `scripts/run_level4_audit.py`：支持 rolling / walk-forward / dynamic PIT 的预览、执行、CSV 检查与证据落盘。
- `scripts/run_level5_audit.py`：支持 21 天 LEAN Paper、可选 fault 场景重放、重复调用幂等、约束闭环。
- `scripts/run_lean_paper_walkforward_acceptance.py`：单次会话 21+ 交易日执行器，含 `--dry-run`、fault 注入、report/订单/日报一致性检查。

> 说明：该阶段脚本已就绪，但本快照仍未形成完整通过证据，不影响该快照的 `07-24` 结论。

## 仍然保留的高优先验缺口

- 21 个交易日连续 LEAN Paper 的完整验收、约束拒单闭环、重放中断恢复证据。
- Redis/MySQL/worker/磁盘/OOM 故障矩阵与大规模并发恢复。
- 生产规模备份恢复演练（RPO/RTO/SLA 明确）。
- CSI300 `2005-2017` 官方来源覆盖与可回溯官方 PIT 正确性。
- 默认凭据轮换、镜像签名与更严格的基础设施隔离。

## 与历史结论的关系

- 保留 07-22 的 26/100 与 `FAIL` 结论用于“历史问题快照”。
- 07-23 的整改追踪条目继续保留其缺陷映射与待复验项。
- 07-24 则作为**更新后的最新复核状态**，用于当前项目治理决策参考。

## 决策建议（当前）

- 允许继续进行受控研究试运行，但不建议将平台标注为 “生产可信度达标”。
- 对外披露时应同步显示双版本视图：
  1. 历史快照（07-22/07-23），
  2. 当前复测结论（07-24）。
