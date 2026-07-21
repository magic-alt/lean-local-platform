# Script Index

Scripts remain in one stable directory to avoid unnecessary operational path
churn. Their filename prefixes define the supported categories:

- `start_*`: local stack launchers.
- `import_*`: provider or reference-data imports.
- `rebuild_*`, `export_*`, `cleanup_*`: storage maintenance.
- `run_*`: acceptance, replay and scheduled workflow entrypoints.
- `check_*`, `compare_*`: read-only diagnostics and validation.
- `db_migrate.py`: schema migration control.
- `install_git_hooks.sh`: enable repository commit policy.

Runtime output must go to `web/runtime/`, `LEAN_DATA_DIR`, database volumes or an
explicit operator-selected export target. Scripts must not create root-level
`results/`, `runs/`, `Data/` or `parquet/` directories.
