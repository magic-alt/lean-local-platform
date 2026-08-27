# Roadmap

Last reviewed: 2026-08-27. Current architecture: [Current State](current-state.md). Current evidence binding: [Release Status](release-status.md).

The pre-migration roadmap is frozen at [roadmap-2026-08-04.md](history/roadmap-2026-08-04.md). Historical completion claims do not certify the PostgreSQL/RabbitMQ or current Windows runtime architecture.

## Current baseline

- Parquet is the authoritative market-fact layer.
- PostgreSQL 17 owns the control plane; RabbitMQ 4.3.5 transports Celery tasks.
- External `qlib-platform` owns feature/factor research, training, selection and walk-forward research.
- Platform owns DataRelease publication, Artifact Contract v2 import, authoritative LEAN validation, Backtest, Paper, OMS and hard risk.
- Windows Dockerless development uses local processes by default; SCM is explicit and certification-bound.
- P9/live activation is disabled.

## Priority 0: post-migration certification

1. Produce a current release bundle binding Git SHA, PostgreSQL migration revision/checksum, OpenAPI hash, frontend digest, runtime locks, DataRelease contract and broker/database identities.
2. Execute PostgreSQL backup/isolated restore and RabbitMQ/worker fault recovery without relying on pre-migration evidence.
3. Re-run Paper checkpoint/reconciliation and unattended alert delivery evidence on the current runtime.
4. Certify Windows Native Local and SCM as separate topologies; do not infer one from the other.

## Priority 1: cross-repository and execution hardening

1. Keep the `qlib-platform -> platform` handoff fail-closed and content-addressed.
2. Extend cross-repository golden acceptance for DataRelease, Artifact Contract v2, `TARGET_PORTFOLIO` hash and LEAN validation lifecycle.
3. Harden Paper ledger/projection reconciliation, restore drills and execution certification.
4. Preserve the broker observation/write boundary; no live write or activation endpoint is ordinary feature work.

## Priority 2: documentation governance

1. Generate endpoint indexes from OpenAPI and bulk dataset tables from `BULK_DATASET_KEYS`.
2. Enforce semantic lint for forbidden current-runtime terms while exempting explicit historical snapshots.
3. Validate script, Compose service and environment-variable references against code/config.
4. Invalidate current certificates automatically when database, broker, migration, runtime manager, OpenAPI or Research contract identity changes.

## Definition of done

A capability requires persisted lifecycle/restart semantics, explicit PIT/data scope, structured failures, proportional tests, current user/operation documentation, migration/compatibility notes, and release evidence tied to the current architecture. An endpoint or historical pass alone is insufficient.
