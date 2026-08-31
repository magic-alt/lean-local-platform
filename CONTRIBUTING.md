# Contributing to LEAN Local Platform

Thank you for helping improve LEAN Local Platform. This repository is an execution and data-control plane, so changes are reviewed not only for code quality but also for reproducibility, data integrity, side effects, and operational safety.

Please read [AGENTS.md](AGENTS.md) for repository-specific engineering rules, [Current State](docs/current-state.md) for current architecture facts, and [Repository Layout](docs/repository_layout.md) for source/runtime boundaries before making structural changes.

By submitting a contribution, you represent that you have the right to submit it and agree that the contribution may be distributed under this repository's [Apache-2.0 license](LICENSE).

## Ways to contribute

Good contribution areas include:

- bug fixes and reliability improvements;
- data-quality and lineage checks;
- LEAN integration and reproducibility;
- Paper execution correctness;
- API and frontend usability;
- observability and operational tooling;
- tests, documentation, and developer experience;
- security hardening that preserves the documented execution boundary.

For security vulnerabilities, follow [SECURITY.md](SECURITY.md) and do not open a public issue.

## Before opening an issue

1. Search existing issues and pull requests for the same problem or proposal.
2. Confirm that the behavior belongs to this repository rather than external `qlib-platform` research.
3. For bugs, capture the smallest safe reproduction, relevant logs with secrets removed, and the affected commit / environment.
4. For architecture proposals, explain which source-of-truth or side-effect boundary changes.

Use the provided GitHub issue forms so reports have enough context to be actionable.

## Architecture invariants

Contributions must preserve the current architecture unless the pull request explicitly proposes and justifies an architecture change.

### Storage and authority

- Parquet under `$LEAN_DATA_DIR` is the authoritative market-time-series layer.
- PostgreSQL is the control-plane fact store.
- RabbitMQ transports work and is never a business source of truth.
- DuckDB queries Parquet directly and is not an independent fact store.
- SQLite is test-only and must not be reintroduced as a runtime fallback.

### Research / execution split

`platform` owns immutable DataRelease publication, authoritative LEAN validation, portfolio/execution validation, Paper, OMS/ledger boundaries, and lifecycle states after `RESEARCH_PROMOTED`.

External `qlib-platform` owns Qlib materialization, feature/factor research, model training and selection, walk-forward research, and research-only screening.

The handoff is:

```text
DataRelease
+ Artifact Contract v2
+ content-addressed TARGET_PORTFOLIO
```

Preserve `artifactId`, `DataReleaseId`, target-weight SHA-256, lineage, and lifecycle state. Never silently repair or reinterpret an invalid imported artifact.

### Live-execution boundary

P9 is not enabled. Ordinary contributions must not introduce:

- `PAPER -> PRODUCTION` transitions;
- live broker order endpoints;
- broker cancel/replace endpoints;
- OMS live-write endpoints;
- QMT write methods;
- automatic live activation.

A deliberate change to that boundary requires an explicit architecture and security review.

## Side-effect classification

Before changing code, classify the affected path as one of:

- `READ_ONLY`
- `LOCAL_TEST_WRITE`
- `DATA_CONTROL_PLANE_WRITE`
- `PAPER_STATE_WRITE`
- `BROKER_OBSERVATION`
- `BROKER_WRITE`
- `LIVE_ACTIVATION`

State the highest classification in your pull request. `BROKER_WRITE` and `LIVE_ACTIVATION` are not normal feature-validation surfaces and must never be exercised casually in tests or review environments.

## Development setup

### Full local stack

```bash
cp .env.example .env
python scripts/platformctl.py --mode docker --profile full doctor
python scripts/platformctl.py --mode docker --profile full start
```

See [Deployment](docs/deployment.md) for required infrastructure secrets and supported deployment modes.

### Backend

```bash
cd web/backend
.venv/bin/python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

### Frontend

```bash
cd web/frontend
npm ci
npm run dev
```

## Coding conventions

### Python

- Use Python 3.12-compatible code.
- Use 4-space indentation.
- Prefer type hints where practical.
- Use `snake_case` for modules, functions, and variables.
- Keep FastAPI schemas and service payloads JSON-friendly and machine-readable.
- Reuse established service and repository boundaries rather than issuing ad-hoc SQL from routes or tasks.

### TypeScript / React

- Use `PascalCase` for React components.
- Use `camelCase` for props, state, and local variables.
- Keep API types explicit and avoid duplicating server-owned semantics in the UI.
- Preserve responsive behavior for workstation, tablet, and mobile layouts when changing shared UI surfaces.

### Data and execution code

- Prefer deterministic, idempotent operations.
- Preserve raw evidence before parsing or normalization when the existing pipeline requires it.
- Do not add synthetic fallback data to a production validation path.
- Do not bypass PIT, benchmark, source-certification, QA, hash, or lineage gates merely to make a test pass.

## Branches and commits

Use a focused branch name such as:

```text
fix/backtest-cancellation
feat/data-lineage-audit
docs/research-handoff
chore/open-source-governance
```

Commit subjects should be concise and imperative, for example:

```text
harden artifact lineage validation
fix paper checkpoint replay
clarify native deployment boundary
```

Avoid mixing unrelated refactors, generated artifacts, runtime files, or downloaded data into the same commit.

### Changelog policy

Every commit must add a concise entry to the `Unreleased` section of `CHANGELOG.md` describing the observable change. Do not put the commit's own hash in that same entry.

Enable the tracked local hook once per clone:

```bash
./scripts/install_git_hooks.sh
```

## Validation

Run the narrowest relevant tests while developing, then run the required baseline before requesting review.

### Repository baseline

```bash
python scripts/check_repository_hygiene.py
python scripts/check_oss_governance.py
```

### Backend

```bash
cd web/backend
.venv/bin/python -m pytest -q
```

### Frontend

```bash
cd web/frontend
npm ci
npm run build
```

### Optional integration lanes

Run integration suites only when their runtime dependencies are available and the change warrants them.

```bash
cd web/backend
RUN_POSTGRES_INTEGRATION=1 .venv/bin/python -m pytest -q \
  -m integration_postgres tests/test_postgres_integration_lane.py
```

```bash
cd web/backend
RUN_LEAN_DOCKER_INTEGRATION=1 .venv/bin/python -m pytest -q \
  tests/test_ashare_lean_integration.py
```

See [Testing](docs/testing.md) and `AGENTS.md` for additional native, Windows, parity, browser, and acceptance lanes.

## Pull requests

A reviewable pull request should:

- explain the problem / motivation;
- describe the behavioral change rather than only listing files;
- state the highest side-effect classification;
- identify data, schema, migration, API, runtime, or security impacts;
- list exact validation commands and their results;
- include screenshots for visible UI changes;
- call out intentionally skipped integration lanes;
- update documentation when contracts, workflows, or operator behavior change;
- update `CHANGELOG.md`;
- remain focused enough to review and revert safely.

Use `.github/PULL_REQUEST_TEMPLATE.md` as the default structure.

## Database migrations

Treat migrations as durable compatibility contracts.

- Never rewrite an already-applied production migration.
- Keep legacy migration lineage immutable when current architecture documentation says it is historical evidence.
- Explain upgrade, rollback, and recovery implications in the PR.
- Add targeted migration tests when schema behavior changes.

## Documentation changes

Current operating documentation must agree with [Current State](docs/current-state.md) and [Release Status](docs/release-status.md). Historical files under `docs/history/` should remain historical evidence and must not be silently rewritten to look current.

When changing APIs or in-app help, run the existing documentation/reference checks documented in the repository.

## Dependency changes

- Prefer pinned, reproducible dependencies and existing lockfile workflows.
- Explain new runtime dependencies and why existing packages are insufficient.
- Do not weaken image digest / allowlist controls or introduce unreviewed `latest` tags into production paths.
- Consider license compatibility before adding a dependency.

## Review and ownership

`CODEOWNERS` defines default review ownership. Approval is not a substitute for passing the relevant validation and architecture gates.

For changes that affect authentication, runner isolation, data certification, immutable ledgers, broker observation, or any live-execution boundary, expect additional security and architecture scrutiny.

## Code of Conduct

Participation in this project is governed by [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).
