# Idempotency evidence

现有 21 日 session 的重复末日触发返回 HTTP 400，订单/成交/报告/snapshot 计数
保持稳定。该证据只证明 session/date 粗粒度保护，不能代替六阶段 intent/fill/
ledger 恢复矩阵，因此硬门禁未通过。
