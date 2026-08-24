# Docker and Native deployment

The application and task model are runtime-neutral. Deployment orchestration
and LEAN execution are selected independently:

```text
LEAN_DEPLOYMENT_MODE=docker|native
LEAN_EXECUTION_BACKEND=docker|native
LEAN_DEPLOYMENT_PROFILE=core|ml|observability|full|dev
```

Precedence is command line, environment configuration, then persisted
`web/runtime/deployment/state.json`. `--mode auto` fails when these sources
are absent or disagree; it never silently changes execution semantics.

## Profiles

Native defaults to `core`: external localhost MySQL and Redis, API, separate
Celery workers for `default`, `data-bulk`, `data-lineage`,
`data-demand`, and `backtest`, Beat, and the restricted Runner. `ml` adds
the isolated ML venv, worker and MLflow; `observability` adds Prometheus and
Grafana; `full` enables all optional services including ClickHouse. `dev`
uses local processes, Vite, and workstation-only native Jupyter.

Docker defaults to the legacy-compatible `full` topology. Compose images,
Dockerfiles, the Docker Runner security policy, and the Docker CI lane remain
first-class.

## Native bootstrap

```bash
cp config/deployment/native.env.example .env
python scripts/platformctl.py --mode native --profile core doctor
python scripts/platformctl.py --mode native --profile core bootstrap --install-deps
python scripts/platformctl.py --mode native runtime install
python scripts/platformctl.py --mode native db init
```

Bootstrap only changes user-space repository/runtime directories. It never
invokes a system package manager. MySQL, Redis, dotnet, Node/npm and, for
Linux production, bubblewrap must be installed by the operator.

The checked-in native runtime lock intentionally has `supported=false` until
release engineering publishes an exact LEAN commit build for each supported
RID with immutable HTTPS URLs, SHA-256, detached signature, and CycloneDX
SBOM. Native execution fails closed before that release is configured.

## Linux production

Review `deploy/native/systemd`, create the `lean-platform` and
`lean-runner` users and private `/etc/lean-platform/platform.env`, then:

```bash
python scripts/platformctl.py --mode native install --system
systemctl enable --now lean-platform.target
```

The runner is an independent service. API and workers never receive arbitrary
process execution permission. Each job is reconstructed from a structured v2
request, checked against runtime and path allowlists, and executed through
bubblewrap with no network, read-only runtime/data/project/support inputs and
only results/object-store writable. Missing sandbox capability blocks the
runner.

macOS native is a workstation target using the local process manager. Windows
is experimental. Native Research is available only in the `dev` profile and
uses `.venv-research`; its token is stored in a 0600 credential file while
`session.json` contains only the hash.

## Operations

```bash
python scripts/platformctl.py --mode native status
python scripts/platformctl.py --mode native logs runner
python scripts/platformctl.py --mode native backup
python scripts/platformctl.py --mode native restore \
  --backup web/runtime/backups/lean_market-....sql \
  --target-database lean_restore_drill \
  --confirm RESTORE_ISOLATED_DATABASE
```

Backup and restore use MySQL TCP clients for both deployment modes. Restore
refuses the primary database and an existing target.

## Certification gate

Native remains experimental until a clean Linux host with no `docker` in
`PATH` passes bootstrap, migrations, data task, fixed Python LEAN backtest,
report, cancellation/restart recovery, Paper isolation, backup/restore, and
Docker/native parity. Parity requires exact result schema, order sequence,
fills/trade count and Artifact Contract bindings; ending equity, Sharpe and
drawdown use absolute tolerance `1e-8`.
