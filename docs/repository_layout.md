# Repository Layout

Last reviewed: 2026-07-21.

The repository uses a gradual monorepo layout. Stable application paths remain
under `web/`; generated data is separated by policy and Git enforcement rather
than by a disruptive `apps/` migration.

```text
lean-platform/
├── web/
│   ├── backend/app/       FastAPI, Celery, LEAN runner and reporting code
│   ├── backend/tests/     pytest suite
│   ├── frontend/src/      React/TypeScript application
│   └── runtime/           generated local state; never committed
├── strategies/templates/  versioned strategy templates
├── scripts/               operational, import and verification commands
├── examples/              standalone examples, never production defaults
├── config/                versioned portable configuration and manifests
├── docs/                  living documentation and historical audits
├── docker/                monitoring and container configuration
└── tests/e2e/             browser acceptance suite
```

## Source-controlled files

Application code, tests, templates, Docker configuration, portable manifests,
documentation and migration files belong in Git. `config/data-sources/` may
store source identifiers, hashes and manual corrections but not downloaded data
or machine-specific paths.

## Generated and external files

`web/runtime/` is the local runtime boundary for run workspaces, project copies,
reports, uploads, source caches, secrets and stored-object files. Root-level
`results/` and `runs/` are obsolete and must not be recreated.

Market data defaults to the workspace-level `Data` directory through
`LEAN_DATA_DIR`, outside the repository. Parquet defaults to
`LEAN_DATA_DIR/parquet`. MySQL and ClickHouse files live in their configured
Docker volumes or explicit host directories.

Run `python3 scripts/check_repository_hygiene.py` before committing to detect
tracked runtime files and non-portable manifests.
