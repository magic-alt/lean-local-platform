# Script Index

Scripts remain in one stable directory to avoid unnecessary operational path
churn. Their filename prefixes define the supported categories:

- `start_*`: local stack launchers.
- `import_*`: provider or reference-data imports.
- `rebuild_*`, `export_*`, `cleanup_*`: derived-cache, registry or storage maintenance; they must not export stock quotes from MySQL.
- `run_*`: acceptance, replay and scheduled workflow entrypoints.
- `check_*`, `compare_*`: read-only diagnostics and validation.
- `db_migrate.py`: schema migration control.
- `platformctl.py`: Docker/native bootstrap, lifecycle, doctor, logs, migration,
  backup/restore and pinned runtime control.
- `install_lean_runtime.py`: HTTPS download plus SHA-256, signature and SBOM
  verification for native LEAN.
- `check_lean_backend_parity.py`: compare certified Docker/native result artifacts.
- `install_git_hooks.sh`: enable repository commit policy.

Runtime output must go to `web/runtime/`, `LEAN_DATA_DIR`, database volumes or an
explicit operator-selected export target. Scripts must not create root-level
`results/`, `runs/`, `Data/` or `parquet/` directories.

Stock downloads write the existing `data/bronze` and `data/silver` hierarchy
through the backend market-lake service. Scripts may read `data/qlib` or
`gold/qlib_staging`, but must never modify the Qlib repository or Qlib-owned
materializations.
