---
name: paper-execution-change
description: Implement or review Paper accounts, commands, orders, fills, scheduling, certification, ledger, or reconciliation behavior.
---

# Paper Execution Change

Trace:

```text
command -> admission/validation -> idempotency -> account state
-> order state -> fill -> position/cash -> ledger/reconciliation
```

Check duplicate submission, retry semantics, partial fills, out-of-order events, scheduler replay, crash recovery, transaction atomicity, idempotency keys, account isolation, races, stale state, and reconciliation divergence.

`PAPER` promotion is a lifecycle event. It must not implicitly start an account, schedule execution, or submit an order unless that behavior is separately and explicitly invoked.

Use mocks/fakes for external behavior. Never cross into broker writes or live activation, and never exercise those paths during verification.
