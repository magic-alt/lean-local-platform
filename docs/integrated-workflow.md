# Integrated Research-to-Paper Workflow

The integrated workflow is a **read model and command contract**, not a second scheduler or state machine.

Canonical ownership remains unchanged:

- qlib-platform owns research computation and research-side promotion;
- Artifact Contract v2 import verifies bytes, hashes, DataRelease/UniverseRelease bindings and parent lineage before registration;
- the platform artifact registry owns execution-stage promotion;
- LEAN validation is recorded by the existing Qlib promotion service;
- Paper deployment and the append-only Paper ledger keep their existing canonical writers;
- RabbitMQ transports work but never grants promotion by itself.

## API operations

All clients use the same server-derived contract:

```text
GET  /api/integrated-workflows/{import_id}/status
GET  /api/integrated-workflows/{import_id}/plan
GET  /api/integrated-workflows/{import_id}/explain
POST /api/integrated-workflows/{import_id}/resume
GET  /api/integrated-workflows/compare?left=...&right=...
```

`resume` requires `Idempotency-Key`. It does not create a shadow task. The response identifies the existing domain owner and the safe next action. Any actual transition still goes through that owner's existing API/service.

The response carries a stable `correlationId`, `researchRunId`, `dataReleaseId`, target `artifactId`, validation/backtest identities, Paper deployment identity when present, and a deterministic input hash. `cycleId` remains null until a canonical Paper cycle exists; the workflow view never invents one.

## Stages

The stage is derived from canonical facts:

1. `ARTIFACT_RECEIVED`
2. `RESEARCH_REVIEW`
3. `LEAN_VALIDATION_REQUIRED`
4. `PAPER_APPROVAL_REQUIRED`
5. `PAPER_ACTIVE`
6. `REQUIRES_REVIEW` or `REJECTED` for fail-closed states

A Qlib promotion alone cannot authorize Paper. `LEAN_VALIDATED` requires recorded, target-bound LEAN evidence. `PAPER` requires the existing explicit platform-owned deployment path.

Readiness, certification and authorization are reported separately. A green CI run or successful workflow stage does not replace the post-migration runtime certification tracked by Issue #61, and Live/P9 remain disabled.

## Recovery semantics

The shared recovery classifier preserves one logical task identity across at-least-once delivery windows:

- DB not committed → retry the transaction;
- DB committed but outbox not published → resume outbox publication;
- published but unacknowledged → redeliver the same logical task identity;
- acknowledged and current lease active → wait for existing work;
- completed → terminal success;
- stale/unknown ownership → `REQUIRES_REVIEW` rather than creating a second task.

These rules are software-level recovery contracts. Production-like PostgreSQL/RabbitMQ failure injection, restore evidence and Paper soak certification remain owned by Issue #61.

## Clients

TypeScript callers import the workflow helpers from `web/frontend/src/api.ts`.

A dependency-free Python client is available under `sdk/python/lean_local_platform`, and `scripts/workflowctl.py` exposes the same `status`, `plan`, `explain`, `resume` and `compare` operations. Neither client writes platform databases directly.
