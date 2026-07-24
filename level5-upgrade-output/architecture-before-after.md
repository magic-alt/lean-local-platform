# 架构整改前后

## 修改前与当前关键链路

```text
Frozen project
  -> real LEAN cumulative run
  -> LEAN orders/fills treated as final
  -> positions replaced from LEAN holdings
  -> reconciliation/report (rejects = [])

Separate signal_simulation helper
  -> A-share constraints
  -> accepted/rejected simulation reports
```

这两条链不能证明同一 session、同一 trade date、同一 intent 源同时产生真实成交与
约束拒单，也不能证明六阶段恢复没有重复扣费或账本漂移。

## 本轮实际改变

```text
Release/audit clients
  -> runtime bearer token
  -> API
  -> MySQL/Celery/Docker LEAN
  -> invariant-aware evidence result

Isolated integration lane
  -> ephemeral MySQL 8.4 tmpfs
  -> all migrations
  -> repository/index/transaction/lock tests
  -> read-only constrained test container
```

本轮没有伪称 Paper 核心已重构。新增运维文件只定义目标控制，不改变现有运行边界。

## Level 5 所需目标架构

```text
Frozen validated project
  -> daily readiness gate
  -> real LEAN intent extraction
  -> immutable intent and transition log
  -> A-share/pre-trade constraints
  -> deterministic matching
  -> fill/cash/position/cost ledger
  -> reconciliation
  -> one final snapshot and report
  -> alert/audit/immutable archive

API/Scheduler
  -> database-backed fixed job specification
  -> restricted runner
  -> rootless/dedicated runtime
  -> hardened networkless LEAN container
```

只有目标架构经过 21 日、六阶段中断、重复调度、故障矩阵和 DR 独立复验后，才允许
Level 5 Replay/Operational PASS。
