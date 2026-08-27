# Level 5 Operations Runbook

Last reviewed: 2026-08-27. This runbook applies to the PostgreSQL/RabbitMQ runtime described in [Current State](../current-state.md). Pre-migration MySQL/Redis evidence is historical only.

## Release and incident principles

- Stop new scheduling before disruptive recovery, but preserve logs, task IDs, trace IDs, checkpoints and manifests.
- PostgreSQL is the authoritative control plane; Parquet/object storage is the authoritative market/object payload set; RabbitMQ is transport.
- Never mutate Paper ledger facts or bypass source/QA/PIT/benchmark gates to force progress.
- Never exercise broker write or live activation during normal verification. P9 is disabled.

## Failure domains

| Domain | Primary checks | Recovery authority |
| --- | --- | --- |
| PostgreSQL | `pg_isready`, SQLSTATE, connections, disk, migration checksum | verified PostgreSQL backup |
| RabbitMQ | AMQP auth/vhost, diagnostics, consumers, queue depth, confirms | PostgreSQL task reconciliation |
| Celery worker | process health, queue binding, heartbeat, leases, checkpoints | authoritative non-terminal task state |
| LEAN runner | health, pinned identity, allowlist, mounts, process tree | persisted run/task state and immutable inputs |
| Parquet/object store | manifest, SHA-256, DuckDB readability, free space | complete data/object backup |
| Migration | applied revision/checksum and sole migration executor | reviewed migration path; no manual DDL repair |
| Paper | ledger/checkpoint digests, orphan recovery, projection rebuild | append-only ledger and certified prices |

## Standard triage

```bash
python scripts/platformctl.py --mode docker --profile full status
python scripts/platformctl.py --mode docker --profile full logs
curl http://127.0.0.1:8000/api/health/dependencies
web/backend/.venv/bin/python scripts/db_migrate.py --status
```

Classify the incident before restarting anything. Record affected workflow IDs, first/last error, worker/queue, database SQLSTATE, current checkpoint and data manifest.

## PostgreSQL recovery

1. Pause new scheduling and confirm no migration is actively applying.
2. Check `pg_isready`, container/service restart state, connections, disk and PostgreSQL logs.
3. Restore only to a new `lean_restore_*` namespace with `platformctl restore` or `run_restore_drill.py`.
4. Verify migration checksums, critical table row counts/digests and business invariants.
5. Reconcile authoritative non-terminal tasks before workers resume.

`lean_celery` is not a disaster-recovery authority. Do not overwrite the live database during a drill.

## RabbitMQ and worker recovery

1. Verify `rabbitmq-diagnostics -q ping`, AMQP authentication, vhost `lean`, consumers and queue depth.
2. Restore RabbitMQ, then the exact workers for each queue.
3. Reconcile queued/running business rows from PostgreSQL and redispatch idempotently.
4. Confirm publisher confirms, manual late acknowledgements, heartbeat and prefetch 1.
5. Ensure no two workers acquired the same scheduler lease/idempotency key.

## Parquet/object-store recovery

Restore the complete `$LEAN_DATA_DIR` set, including Bronze current/revisions, Silver, Gold, registry/quality, object payloads and required LEAN cache inputs. Verify manifests, hashes, partition coverage and DuckDB readability before source certification or Paper scheduling resumes.

## Paper checkpoint recovery

For stale `running/finalizing` cycles, compare the six checkpoint digests, ledger sequence, execution-cycle date and persisted LEAN run. Orphan recovery may resume idempotently; it must not rewrite immutable ledger entries. Projection differences are repaired by rebuilding projections from ledger/fills and certified PIT prices.

## Release gates

A current Level 5 decision must bind Git SHA, PostgreSQL migration/checksum, OpenAPI hash, frontend/runtime digests, database/broker identities, DataRelease contract, backup/restore evidence, fault matrix, Paper reconciliation and external alert delivery. Architecture changes invalidate prior certification automatically. See [Release Status](../release-status.md).
