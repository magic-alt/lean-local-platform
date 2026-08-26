# Native deployment

Last reviewed: 2026-08-25.

Native mode uses the same PostgreSQL/RabbitMQ/control-plane architecture as
Docker Compose. Only the service manager and LEAN/Research execution adapter
change. Node is a build-time dependency; FastAPI serves `web/frontend/dist`.

## Common prerequisites

- Python 3.12 and the locked backend environments
- PostgreSQL 17 with `lean_platform`, `lean_celery` and `lean_mlflow`
- RabbitMQ 4.3.5 with the `lean` vhost and a dedicated worker user
- .NET and the pinned, signed native LEAN artifact
- Node/npm to build the frontend
- `pg_dump` and `pg_restore` on `PATH` or under `LEAN_POSTGRES_BIN`

Copy `config/deployment/native.env.example` into a private environment file
(`config/deployment/windows-native.env.example` for Windows), replace every
placeholder and keep credentials out of Git.

```bash
python scripts/platformctl.py --mode native --profile core doctor
python scripts/platformctl.py --mode native --profile core bootstrap --install-deps
python scripts/platformctl.py --mode native db init
python scripts/platformctl.py --mode native runtime install
python scripts/platformctl.py --mode native --profile core start
```

`platformctl db migrate` is the only platform migration executor. API, beat and
workers verify the current PostgreSQL baseline but never apply migrations.

## Linux

Production LEAN uses the native backend with the repository's fail-closed
sandbox requirements. Systemd unit templates are under
`deploy/native/systemd/` and depend on `postgresql.service` and
`rabbitmq-server.service`. Docker remains available as a separate deployment
mode; native mode does not silently fall back to it.

## Windows

Windows is a project-certified deployment lane because Celery upstream does not
provide official Windows support. Install PostgreSQL and RabbitMQ as Windows
services, then follow [the Windows runbook](../deploy/windows/README.md).
SCM deployments require absolute data/runtime paths; the Windows template and
sandbox configurator share the same policy/work defaults.

On a Dockerless development workstation, restart the complete Core process set
with the PowerShell entry point below. It forces the local process manager and
therefore does not require pre-installed `LeanPlatformSupervisor` or
`LeanRestrictedRunner` services. Restarting also reloads repository `.env`
configuration, which is read once when each Python process imports the backend.

```powershell
.\scripts\start_windows_native.ps1
```

Use `-Profile dev` when the Vite development server is also required. Formal
SCM deployments must set `LEAN_NATIVE_MANAGER=windows-scm`; production mode
selects SCM automatically and retains the certification gate.

The service topology is:

```text
PostgreSQL service
RabbitMQ service
LeanPlatformSupervisor
  FastAPI
  Celery beat
  worker-default-1       --pool=solo
  worker-data-bulk-1     --pool=solo
  worker-data-lineage-1  --pool=solo
  worker-data-demand-N   --pool=solo
  worker-backtest-1      --pool=solo
  optional worker-ml-1 and MLflow
LeanRestrictedRunner
  native LEAN process tree
  native Jupyter/Research process tree
```

The runner binds only to `127.0.0.1`, validates the signed runtime, account,
policy, firewall and ACL configuration, and assigns each execution to a bounded
kill-on-close Job Object. Any failed check returns `LEAN_RUNNER_UNSAFE`; the
request is rejected rather than downgraded to an ordinary subprocess.

For formal production startup, collect the real broker/database fault matrix
and at least 12 hours of soak evidence, then issue a host-bound certificate:

```powershell
python scripts/windows_certification.py issue --evidence C:\evidence\windows-celery.json
python scripts/windows_certification.py verify
$env:LEAN_WINDOWS_PRODUCTION_MODE = "1"
python scripts/platformctl.py --mode native --profile core start
```

Changing the Python lock, native runtime lock, certification policy, certified
host or version family invalidates the certificate.

## Research

Docker mode uses `DockerResearchBackend`; native mode uses
`WindowsNativeResearchBackend` or the native workstation backend. Native
Research binds Jupyter to loopback with a random token, an allowlisted
environment, bounded process tree and read-only market data. Platform remains
the execution-validation boundary and does not grow into a second model
training platform.

## Operations

```bash
python scripts/platformctl.py --mode native status
python scripts/platformctl.py --mode native logs
python scripts/platformctl.py --mode native backup
python scripts/platformctl.py --mode native stop
```

Use [deployment.md](deployment.md) for backup, isolated restore and real
PostgreSQL integration validation.
