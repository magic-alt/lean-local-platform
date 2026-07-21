# Repository Guidelines

## Project Structure & Module Organization

This repository contains a local QuantConnect LEAN platform with a FastAPI backend and React frontend. Core backend code lives in `web/backend/app/`: API routers in `api/`, domain services in `services/`, Celery tasks in `tasks/`, LEAN/Docker helpers in `lean_engine/`, and migrations in `migrations/`. Backend tests are in `web/backend/tests/`. Frontend source is in `web/frontend/src/`. Operational scripts are in `scripts/`, standalone examples in `examples/`, portable configuration in `config/`, strategy templates in `strategies/templates/`, documentation in `docs/`, and runtime artifacts under `web/runtime/` or external `Data/` paths. Root-level `results/`, `runs/`, `Data/`, and `parquet/` directories are not supported.

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

Start the full local app stack:

```bash
docker compose --profile app up -d --build mysql redis api worker
```

Run backend tests with `cd web/backend && .venv/bin/python -m pytest -q`. Run the LEAN Docker integration test only when Docker is available: `RUN_LEAN_DOCKER_INTEGRATION=1 .venv/bin/python -m pytest -q tests/test_ashare_lean_integration.py`. Build the frontend with `cd web/frontend && npm run build`.

## Coding Style & Naming Conventions

Use Python 3 style with 4-space indentation, type hints where practical, and snake_case for modules, functions, and variables. Keep FastAPI schemas and service payloads JSON-friendly and machine-readable. Use TypeScript/React components with PascalCase component names and camelCase props/state. Prefer existing service helpers and repository patterns over new abstractions.

## Testing Guidelines

Use pytest for backend coverage; name tests `test_*.py` and keep fixtures local unless shared setup belongs in `conftest.py`. Mark Docker/LEAN tests with the existing `integration` marker and keep them opt-in. Frontend validation is currently `npm run build`; add focused component tests only if a test framework is introduced.

## Commit & Pull Request Guidelines

Recent commits use concise imperative messages, usually lowercase, such as `remove sqlite runtime defaults` or `align data providers with multi-source fallback`. Keep commits scoped and avoid mixing generated artifacts with code changes. Pull requests should describe the behavioral change, list verification commands, note data or migration impacts, and include screenshots for visible UI changes.

Every commit must update the `Unreleased` section of `CHANGELOG.md`. Enable the tracked hook with `./scripts/install_git_hooks.sh`; the hook rejects commits that do not stage the changelog.

## Security & Configuration Tips

Do not commit `.env`, provider tokens, MySQL credentials, or downloaded market data. Runtime metadata uses MySQL; DuckDB is only for querying derived Parquet exports. Do not reintroduce SQLite as a runtime default.
