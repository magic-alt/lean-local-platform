# 整改 Wave 状态与最小后续步骤

## Wave 1：Level 4 证据

状态：`PARTIAL`

已完成隔离 MySQL integration lane、审计客户端鉴权、失败判定防伪回归、3×3 参数
网格、三个 rolling window、现有 walk-forward/dynamic PIT 实跑和 production-like
Chromium smoke。尚需新增 validation/OOS 数据模型及 fingerprint、失败子任务重试、
cancel/restart 恢复和完整 Level 4 browser 场景。

## Wave 2：统一 Paper 状态机

状态：`OPEN`

最小正确改造不是给日报人工添加拒单，而是新增不可变 intent/transition/fill/ledger
模型，将 LEAN 输出解释为 intent，并让 accepted/rejected 通过同一约束引擎。旧
session 应保持只读，使用 feature gate 创建 v2 session；需新增 migration、回填
策略和 rollback/export。

## Wave 3：幂等与无人值守

状态：`OPEN`

状态机完成后才能正确实现六阶段 failpoint、恢复游标、completion marker、session
lease、漏跑阻断和补偿。每个 failpoint 必须与无故障基准比较 order/fill/fee/cash/
position/snapshot/report/alert/reconciliation digest。

## Wave 4：运维和 DR

状态：`PARTIAL`

已新增明确标为未认证的 SLO/RPO/RTO 和 runbook。下一步是在隔离 Compose 和独立
卷执行生产代表规模的加密 MySQL/stored-object restore，并完成用户指定的服务、
资源和并发故障矩阵。

## Wave 5：安全和供应链

状态：`OPEN`

首先实现只接受固定 digest、entrypoint、mount schema、资源和网络策略的 restricted
runner，再移除通用 worker 的 Docker socket。凭据轮换必须在维护窗口内原子执行，
不得在本轮无授权地破坏现有卷。随后补齐 Python transitive hash lock、漏洞例外
账本、签名主体/验证和 provenance release gate。
