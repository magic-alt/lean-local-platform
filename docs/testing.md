# Testing and Certification

Last reviewed: 2026-08-27. Tests use the narrowest meaningful lane and expand with risk. Provider, broker and persistent production access are excluded from normal verification.

## Validation ladder

```text
Unit / isolated SQLite
  -> PostgreSQL integration
  -> RabbitMQ / Celery integration
  -> LEAN Docker integration
  -> Windows Native contract
  -> Dockerless Golden
  -> Paper / fault / recovery
  -> release certification
```

SQLite is test-only. It proves fast domain behavior but never substitutes for PostgreSQL migration, locking, constraint or recovery evidence.

## Backend unit tests

```bash
cd web/backend
.venv/bin/python -m pytest -q
```

For a focused change, run the directly related test module first, then the full backend suite when the change crosses API/service/persistence/task boundaries.

## PostgreSQL integration

```bash
cd web/backend
RUN_POSTGRES_INTEGRATION=1 .venv/bin/python -m pytest -q \
  -m integration_postgres tests/test_postgres_integration_lane.py
```

Or run the disposable Compose lane:

```bash
docker compose --profile test run --build --rm postgres-integration-tests
```

The lane uses a dedicated tmpfs-backed `lean_integration` database and must not access the production PostgreSQL volume, repository data lake or Docker socket.

## RabbitMQ and Celery

Broker integration verifies AMQP authentication/vhost, durable dispatch, publisher confirm, late acknowledgement, queue routing, heartbeat, retry and reconciliation from authoritative PostgreSQL task rows. Queue recovery evidence must not treat RabbitMQ as a business source of truth.

Fault tests restart RabbitMQ, individual worker roles and PostgreSQL as separate failure domains. They must prove idempotency/lease invariants and preserve terminal business facts.

## LEAN Docker integration

Run only when Docker is available:

```bash
cd web/backend
RUN_LEAN_DOCKER_INTEGRATION=1 .venv/bin/python -m pytest -q \
  tests/test_ashare_lean_integration.py
```

The runner must use a digest-pinned allowlisted image, restricted network/mounts and isolated runtime paths. Never substitute a `:latest` image to make a test pass.

## Windows Native

Treat these as distinct contracts:

| Lane | Manager | Evidence |
| --- | --- | --- |
| Windows Native Local | user processes | startup/status/stop, process-tree cleanup, current env load |
| Windows Native SCM | Windows services | service identity, ACLs, restart/fault matrix, host-bound certification |

`scripts/start_windows_native.ps1` exercises local mode by default. SCM must be selected explicitly.

## Frontend and documentation

```bash
cd web/frontend
npm run build

cd ../..
web/backend/.venv/bin/python scripts/check_help_docs.py
web/backend/.venv/bin/python scripts/generate_help_api_reference.py --check
```

The generated API reference owns the endpoint list. Documentation checks reject broken catalog links and stale current-runtime terms outside historical snapshots.

## Paper, fault and recovery

Current acceptance must cover PostgreSQL failure/recovery, RabbitMQ/worker recovery, LEAN runner loss, Parquet/object-store validation, migration mismatch and Paper checkpoint reconciliation. Paper tests verify append-only ledger facts, six checkpoint digests, idempotent resume and projection rebuild; they never exercise broker writes or live activation.

Backup drills restore only to a new `lean_restore_*` namespace and compare critical row counts/digests. A database backup without the Parquet/object store, or a data-lake backup without the control plane, is incomplete.

## Release certification

Certification binds Git SHA, PostgreSQL migration revision/checksum, OpenAPI hash, frontend digest, runtime/image identities, database/broker identities, DataRelease contract version and topology-specific fault/restore/soak evidence. Architecture changes invalidate earlier evidence automatically. See [Release Status](release-status.md).
