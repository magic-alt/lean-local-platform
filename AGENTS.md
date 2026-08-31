# Repository Guidelines

This file defines repository-wide engineering constraints for humans and coding
agents. It is the first policy layer; task-specific workflows live under
`.agents/skills`, Codex session/reviewer controls under `.codex`, local
fast-fail checks under `.githooks`, and merge-time governance under `.github`.

## Project Structure & Module Organization

This repository contains a local QuantConnect LEAN platform with a FastAPI
backend and React frontend. Core backend code lives in `web/backend/app/`: API
routers in `api/`, domain services in `services/`, Celery tasks in `tasks/`,
LEAN/Docker helpers in `lean_engine/`, and migrations in `migrations/`. Backend
tests are in `web/backend/tests/`. Frontend source is in `web/frontend/src/`.
Operational scripts are in `scripts/`, standalone examples in `examples/`,
portable configuration in `config/`, strategy templates in
`strategies/templates/`, documentation in `docs/`, and runtime artifacts under
`web/runtime/` or the configured `LEAN_DATA_DIR`. Root-level `results/`,
`runs/`, `Data/`, and `parquet/` directories are not supported.

## Developer Automation Control Plane

Treat the following as security- and governance-sensitive repository surfaces:

```text
AGENTS.md                       repository-wide engineering invariants
.agents/skills/                 task-specific Agent Skills
.codex/config.toml              project Codex defaults
.codex/agents/                  specialized read-only reviewers/explorers
.codex/rules/                   command approval/forbid guardrails
.githooks/                      local fast-fail checks
.github/                        GitHub ownership, CI, security, release policy
```

Read [`.agents/skills/README.md`](.agents/skills/README.md),
[`.codex/README.md`](.codex/README.md), and
[`.github/README.md`](.github/README.md) before changing those surfaces.

For version-sensitive Codex configuration, rules, subagents, or skills, confirm
current upstream behavior before adding or changing syntax. Do not cargo-cult a
field from an old local configuration.

Custom reviewer agents are intentionally read-only. Keep them **behaviorally
read-only** even when a parent Codex turn applies broader live runtime
permissions. Use parallel agents for independent read-heavy investigation, not
for overlapping writes. The primary thread owns edits, integration, and final
validation.

## Build, Test, and Development Commands

Run the backend locally:

```bash
cd web/backend
.venv/bin/python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Run the frontend:

```bash
cd web/frontend
npm run dev
```

Start the full local app stack through the supported control entrypoint:

```bash
python scripts/platformctl.py --mode docker --profile full doctor
python scripts/platformctl.py --mode docker --profile full start
```

On a Windows Dockerless development host use
`./scripts/start_windows_native.ps1`. It uses the local process manager by
default; SCM is opt-in through `LEAN_NATIVE_MANAGER=windows-scm` or production
mode.

Run backend tests with
`cd web/backend && .venv/bin/python -m pytest -q`. Run the LEAN Docker
integration test only when Docker is available:
`RUN_LEAN_DOCKER_INTEGRATION=1 .venv/bin/python -m pytest -q tests/test_ashare_lean_integration.py`.
Build the frontend with `cd web/frontend && npm run build`.

## Repository Validation Baseline

For repository/governance/developer-automation changes run:

```bash
python scripts/check_repository_hygiene.py
python scripts/check_developer_governance.py
python scripts/check_oss_governance.py
```

Run targeted product tests before broader suites. GitHub `Governance`,
`Dependency Review`, and `CodeQL` are remote evidence; inspect whether the
substantive step actually executed rather than reporting a skipped/bootstrap
lane as a pass.

## Coding Style & Naming Conventions

Use Python 3 style with 4-space indentation, type hints where practical, and
snake_case for modules, functions, and variables. Keep FastAPI schemas and
service payloads JSON-friendly and machine-readable. Use TypeScript/React
components with PascalCase component names and camelCase props/state. Prefer
existing service helpers and repository patterns over new abstractions.

## Testing Guidelines

Use pytest for backend coverage; name tests `test_*.py` and keep fixtures local
unless shared setup belongs in `conftest.py`. Mark Docker/LEAN tests with the
existing `integration` marker and keep them opt-in. Frontend validation is
currently `npm run build`; add focused component tests only if a test framework
is introduced.

Tests and agent verification must not make real provider/broker writes or
cross the live-activation boundary. Use mocks/fakes unless an integration path
is explicitly authorized.

## Commit & Pull Request Guidelines

Use concise imperative commit subjects and keep commits scoped. Avoid mixing
generated artifacts with source or governance changes. Pull requests should
describe behavioral changes, validation commands, data/migration/security
impact, and screenshots for visible UI changes.

Every commit must update the `Unreleased` section of `CHANGELOG.md` under the
current repository policy. Enable the tracked hooks with:

```bash
./scripts/install_git_hooks.sh
```

Local hooks are fast feedback, not merge authority. Do not use `--no-verify` as
a routine workaround for a failing repository policy check.

## Security & Configuration Tips

Do not commit `.env`, provider tokens, PostgreSQL/RabbitMQ credentials, broker
credentials, API tokens, runner tokens, or downloaded market data.

Project Codex defaults intentionally disable sandbox network access, disable
login-shell semantics, and apply automatic secret-like environment variable
exclusions. Do not weaken those defaults merely to make an agent task easier.

Parquet under `LEAN_DATA_DIR` is the authoritative market-fact layer;
PostgreSQL is the control-plane store; RabbitMQ is the Celery transport; DuckDB
queries Parquet directly. SQLite is test-only. Do not write market time series
into PostgreSQL or reintroduce SQLite as a runtime default.

## Platform Invariants

This repository is the production data and execution control plane.

`platform` owns:

- canonical market-data ingestion and immutable DataRelease publication;
- authoritative LEAN validation;
- portfolio construction and execution validation;
- hard-risk enforcement;
- the Paper lifecycle;
- OMS, broker integration, fills, and ledgers;
- lifecycle states after `RESEARCH_PROMOTED`.

`qlib-platform` owns:

- Qlib materialization;
- feature and factor research;
- model training and selection;
- walk-forward research;
- research-only portfolio screening.

Do not grow `platform` into a second model-training or feature-research
platform.

## Cross-Repository Contract

The `qlib-platform` -> `platform` boundary is:

```text
DataRelease
+ Artifact Contract v2
+ content-addressed TARGET_PORTFOLIO
```

Preserve `artifactId`, `DataReleaseId`, target-weight SHA-256, lineage,
lifecycle state, and fail-closed validation. Never silently repair or
reinterpret an invalid imported artifact.

## Current Live-Execution Boundary

P9 is not enabled.

Do not introduce during ordinary feature work:

- `PAPER -> PRODUCTION` API transitions;
- live broker order endpoints;
- broker cancel/replace endpoints;
- OMS live-write endpoints;
- QMT write methods;
- automatic live activation.

Any deliberate change to this boundary is an architecture and security project,
not an incidental implementation detail.

## Side-Effect Discipline

Before changing code or automation that can execute code, classify the affected
path as one of:

- `READ_ONLY`
- `LOCAL_TEST_WRITE`
- `DATA_CONTROL_PLANE_WRITE`
- `PAPER_STATE_WRITE`
- `BROKER_OBSERVATION`
- `BROKER_WRITE`
- `LIVE_ACTIVATION`

Anything at `BROKER_WRITE` or `LIVE_ACTIVATION` requires an explicit
architecture change and must never be exercised by normal agent verification.

Repository governance changes are normally `READ_ONLY` with respect to platform
runtime, but workflows or hooks can still carry repository/security side
effects. Review their permissions and destructive-command surface separately.
