---
name: repo-audit
description: Audit platform changes across API, services, persistence, tasks, LEAN, providers, and broker boundaries. Use for architecture reviews, PR reviews, or unfamiliar cross-layer behavior.
---

# Repository Audit

Trace the smallest relevant path from entry point through API/router, service, repository/database, task or external integration, persisted/external side effect, and tests.

Classify each path as `READ_ONLY`, `LOCAL_TEST_WRITE`, `DATA_CONTROL_PLANE_WRITE`, `PAPER_STATE_WRITE`, `BROKER_OBSERVATION`, `BROKER_WRITE`, or `LIVE_ACTIVATION`.

Report concrete files and symbols, call/data flow, lifecycle transitions, contract and persistence effects, existing tests, and unresolved risks. Treat `BROKER_WRITE` and `LIVE_ACTIVATION` as architecture/security changes. Stay read-only when the request is an audit or review.
