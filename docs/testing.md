# Testing and Certification

Last reviewed: 2026-09-05. Tests use the narrowest meaningful lane and expand
with risk. Provider credentials and persistent production writes are excluded
from normal PR verification.

## Validation ladder

```text
Unit / isolated SQLite
  -> PostgreSQL integration
  -> RabbitMQ / Celery integration
  -> Web E2E on PostgreSQL/RabbitMQ
  -> LEAN Docker integration
  -> Windows Native contract
  -> Dockerless Golden
  -> real local-data certification
  -> Paper / fault / recovery
  -> release certification
```

SQLite is test-only. It proves fast domain behavior but never substitutes for
PostgreSQL migration, locking, constraint or recovery evidence.

## Mandatory pull-request gates

The default `CI` workflow no longer hides the deterministic application lanes
behind a repository variable. Every PR runs:

- `Governance`
- `Backend`
- `Frontend`
- `Web E2E smoke`
- `Native contract`
- `Windows native contract`

`Required CI` is a stable aggregate gate and succeeds only when all six lanes
succeed. `Dependency Review` remains a separate required security gate in the
repository desired-state policy. Actual LEAN Docker/native parity jobs remain
opt-in because they download/run a large pinned engine runtime; they are
covered by full/local certification on a capable host.

A skipped required lane is not a pass.

## One-command system verification

Use the same fail-closed orchestration locally:

```bash
python scripts/system_verify.py --profile pr
python scripts/system_verify.py --profile full
python scripts/system_verify.py --profile local-data --data-dir ./data
```

The verifier records every command, exit status, duration and output tail in:

```text
web/runtime/audit/system-verification.json
```

`pr` covers governance, backend pytest, frontend build, responsive UI audit and
fixture-backed PostgreSQL/RabbitMQ smoke E2E. `full` runs the complete Chromium
E2E suite including real LEAN-backed journeys. `local-data` adds read-only
certification of the operator's canonical `data/` lake plus the real-data Web
preview case.

When an already deployed stack must be bound to the evidence bundle, add:

```bash
python scripts/system_verify.py --profile full \
  --base-url http://127.0.0.1:8000
```

This appends `verify_release_convergence.py` so source/deployed OpenAPI,
migration state, service release IDs/Git SHAs and worker reachability are part
of the same result.

## Real local-data certification

The data certificate can also be run independently:

```bash
python scripts/local_data_certification.py --data-dir ./data
```

It is deliberately read-only with respect to the supplied source data. It
checks the canonical equity, `daily_basic`, and CSI300 Parquet layouts; scans
all Parquet metadata; verifies minimum coverage, unique primary keys, non-null
keys and OHLC invariants; then selects a well-covered real A-share symbol,
materializes only that bounded history into an isolated temporary LEAN Data
directory and runs the digest-pinned LEAN Docker engine.

The resulting evidence is written to:

```text
web/runtime/audit/local-data-certification.json
```

A successful certificate therefore proves a concrete path:

```text
operator data/
  -> canonical Parquet
  -> DuckDB read
  -> isolated LEAN cache
  -> pinned LEAN engine
  -> result JSON/statistics
```

It does **not** claim that every possible strategy is profitable or that a
release is production-certified. Release certification still requires the
broader topology/fault/restore evidence below.

## Backend unit tests

```bash
cd web/backend
.venv/bin/python -m pytest -q
```

For a focused change, run the directly related test module first, then the full
backend suite when the change crosses API/service/persistence/task boundaries.

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

The lane uses a dedicated tmpfs-backed `lean_integration` database and must not
access the production PostgreSQL volume, repository data lake or Docker socket.

## RabbitMQ and Celery

Broker integration verifies AMQP authentication/vhost, durable dispatch,
publisher confirm, late acknowledgement, queue routing, heartbeat, retry and
reconciliation from authoritative PostgreSQL task rows. Queue recovery evidence
must not treat RabbitMQ as a business source of truth.

The Playwright harness now follows this topology as well: it creates isolated
PostgreSQL/RabbitMQ services and never configures legacy MySQL/Redis variables.

Fault tests restart RabbitMQ, individual worker roles and PostgreSQL as separate
failure domains. They must prove idempotency/lease invariants and preserve
terminal business facts.

## LEAN Docker integration

Run only when Docker is available:

```bash
cd web/backend
RUN_LEAN_DOCKER_INTEGRATION=1 .venv/bin/python -m pytest -q \
  tests/test_ashare_lean_integration.py
```

The runner must use a digest-pinned allowlisted image, restricted network/mounts
and isolated runtime paths. Never substitute a `:latest` image to make a test
pass.

## Windows Native

Treat these as distinct contracts:

| Lane | Manager | Evidence |
| --- | --- | --- |
| Windows Native Local | user processes | startup/status/stop, process-tree cleanup, current env load |
| Windows Native SCM | Windows services | service identity, ACLs, restart/fault matrix, host-bound certification |

`scripts/start_windows_native.ps1` exercises local mode by default. SCM must be
selected explicitly.

## Frontend and documentation

```bash
cd web/frontend
npm run build

cd ../..
web/backend/.venv/bin/python scripts/check_help_docs.py
web/backend/.venv/bin/python scripts/generate_help_api_reference.py --check
```

The generated API reference owns the endpoint list. Documentation checks reject
broken catalog links and stale current-runtime terms outside historical
snapshots.

## Paper, fault and recovery

Current acceptance must cover PostgreSQL failure/recovery, RabbitMQ/worker
recovery, LEAN runner loss, Parquet/object-store validation, migration mismatch
and Paper checkpoint reconciliation. Paper tests verify append-only ledger facts,
six checkpoint digests, idempotent resume and projection rebuild; they never
exercise broker writes or live activation.

Backup drills restore only to a new `lean_restore_*` namespace and compare
critical row counts/digests. A database backup without the Parquet/object store,
or a data-lake backup without the control plane, is incomplete.

## Release certification

Certification binds Git SHA, PostgreSQL migration revision/checksum, OpenAPI
hash, frontend digest, runtime/image identities, database/broker identities,
DataRelease contract version and topology-specific fault/restore/soak evidence.
Architecture changes invalidate earlier evidence automatically. Passing
`Required CI` or local-data certification is necessary evidence, not by itself a
production release seal. See [Release Status](release-status.md).
