# Windows native deployment

Windows native uses PostgreSQL 17 and RabbitMQ 4.3.5 as Windows services, plus
two project-owned services:

- `LeanPlatformSupervisor` runs FastAPI, beat, MLflow, and one `--pool=solo`
  Celery process per worker slot.
- `LeanRestrictedRunner` exposes the loopback-only runner API and owns the
  native LEAN/Research process trees.

Current support status:

```text
Windows Native Architecture      COMPLETE
Windows Native Implementation    FEATURE COMPLETE
Windows Local Contract Gate      PASSED
Windows Dockerless Functional    NOT YET ACCEPTED
Windows Native Production        NOT CERTIFIED
```

Start from `config/deployment/windows-native.env.example`; Windows services
must not use the relative workstation paths in `native.env.example`. Run
`platformctl doctor --mode native`, apply database migrations explicitly,
configure the sandbox with `configure_windows_sandbox.ps1`, and only then
install the services. The policy defaults to
`C:\ProgramData\LeanPlatform\sandbox-policy.json`, exactly matching the Windows
environment template and verifier. The runner health endpoint returns `LEAN_RUNNER_UNSAFE`
when the policy file, service account, ACL, firewall rule, Job Object APIs, or
signed runtime identity cannot be verified.

Set LEAN_DOTNET_PATH to an absolute host executable when dotnet.exe is not on
PATH. Resolution is shared by platformctl doctor, the Native backend,
restricted runner health, sandbox configuration, and Golden Acceptance:
LEAN_DOTNET_PATH, then PATH, then C:\Program Files\dotnet\dotnet.exe.
Deployment hosts require the .NET 10 runtime only. Runtime build/release hosts
separately require the .NET 10 SDK, Python 3.11, and the private signing key;
the private key must not be present on deployment hosts.

## Local validation gate

GitHub Actions are not a required acceptance dependency. If Actions quota is
unavailable, run the equivalent local Windows contract gate and retain its JSON
evidence with the PR/release review:

```powershell
.\deploy\windows\run_local_native_validation.ps1
```

The default evidence path is:

```text
C:\ProgramData\LeanPlatform\evidence\windows-native-local-validation.json
```

A PR may be accepted when this local gate passes for its exact commit. GitHub
Actions remain optional secondary evidence. This does not replace Dockerless
Golden Acceptance or the separate production certification.

## Local Native LEAN runtime release

Windows runtime release can also be completed without GitHub Actions:

```powershell
.\deploy\windows\run_local_native_runtime_release.ps1 `
  -LeanCommit 81a62a1eb4d4e0a96bb7c3d183b4083c47d2b600 `
  -RuntimeId lean-81a62a1-windows-x64-r1 `
  -PythonRoot C:\path\to\Python311 `
  -DotnetPath "C:\Program Files\dotnet\dotnet.exe" `
  -SigningPrivateKeyPath C:\secure\lean-runtime-signing.pem `
  -PublishDraft
```

The local release script builds the exact LEAN commit, packages Python 3.11.11,
computes SHA-256, generates CycloneDX SBOM evidence, creates and locally verifies
the Ed25519 signature, and optionally uses authenticated `gh` CLI to publish a
draft release and render a reviewable runtime lock. The checked-in runtime lock
must remain fail-closed until the candidate passes the required acceptance
sequence.

## Dockerless Golden Acceptance

After a real signed `windows-x64` runtime has been published and locked, run the
acceptance script from an elevated PowerShell session on a clean host. Before
any ACL, firewall, or SCM mutation it emits a preflight summary and fails closed
unless the Docker CLI, service, Desktop executable, WSL distributions, install
directory, and uninstall registration are all absent. It also requires the
signed Windows runtime lock, .NET 10 runtime, service identity, frozen
acceptance spec, PostgreSQL, and AMQP readiness. It then bootstraps the
application, stages the four-bar deterministic fixture, installs and verifies
the runtime/sandbox, initializes PostgreSQL, starts the Windows services,
executes the Native LEAN smoke backtest, and performs a backup plus isolated
restore:

```powershell
.\deploy\windows\run_dockerless_golden_acceptance.ps1 `
  -RunnerAccount .\LeanRunner `
  -DotnetPath "C:\Program Files\dotnet\dotnet.exe"
```

Its evidence intentionally records `productionCertified=false`. Golden
functional acceptance cannot substitute for the separate 12-hour fault matrix
and host-bound production certificate.

RabbitMQ AMQP readiness is a Core Golden gate. Erlang-cookie-backed
rabbitmqctl/rabbitmq-diagnostics access is recorded as a
production-ops-warning and remains mandatory for the later fault
certification, but it does not block Core Golden.

## Production certification

Production mode additionally requires a host-bound Celery certification. Run
the real PostgreSQL/RabbitMQ failure and soak suite, capture its JSON evidence,
then issue and verify the certificate:

```powershell
python scripts/windows_certification.py issue --evidence C:\path\to\evidence.json
python scripts/windows_certification.py verify
$env:LEAN_WINDOWS_PRODUCTION_MODE = "1"
python scripts/platformctl.py --mode native --profile core start
```

The gate requires all scenarios in
`config/runtime/windows-celery-certification.json`, at least 12 hours of soak,
the certified version family, and unchanged requirements/runtime lock hashes.
It is intentionally not generated by unit tests.

Do not run either service as an interactive desktop user. The runner account
must have read access only to data, project snapshots, support inputs, and the
runtime; it receives write access only to run results, object storage, and its
research workspace.
