# 历史问题与修复记录

本目录保存已经发生过的问题、根因、修复措施、验证证据和剩余风险。记录采用追加式维护：问题修复后更新状态，但不删除原始症状和原因，避免相同故障在后续重构中被重复引入。

## 记录索引

- [2026-07 平台稳定性与数据同步修复](2026-07-platform-fixes.md)
- [2026-07 平台能力复审](platform-audit-2026-07.md) 保存 2026-07-04 起的 P0/P1/P2 问题、当时数据量和验收证据；其中旧路径与命令按历史原文保留。
- [2026-07-22 独立成熟度审计与修复状态](independent-audit-2026-07-22.md) 保留 26/100、Level 3/4 失败与 Level 5 阻塞结论，并记录后续修复和仍未关闭的验收缺口。
- [2026-07-23 独立审计整改追踪](independent-audit-remediation-2026-07-23.md) 将 AUD-001 至 AUD-019 映射到当前实现、回归证据和待复验项，不覆盖原始失败结论。
- [2026-07-24 独立复审更新](independent-audit-2026-07-24.md) 记录基于 production-like 重跑的最新等级与评分：
  - `LEVEL3_PASS` / `LEVEL3_PLUS_PASS`
  - `LEVEL4_FAIL`
  - `LEVEL5_REPLAY_BLOCKED`
  - `LEVEL5_OPERATIONAL_NOT_READY`
  - `LIVE_NOT_READY`

## 维护规则

1. 新问题记录症状、影响、根因、修复、验证和遗留风险。
2. 已解决的问题标记 `resolved`，不删除问题正文。
3. 指标、数据量和测试数量必须注明采集日期，不能当作永久现状。
4. 当前能力以 [架构](../architecture.md)、[数据管线](../data_pipeline.md)、[部署](../deployment.md) 和 [当前 Roadmap](../roadmap.md) 为准；本目录用于解释演进过程。
