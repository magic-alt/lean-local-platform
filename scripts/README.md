# Script Index

Scripts remain in one stable directory to avoid unnecessary operational path
churn. Their filename prefixes define the supported categories:

- `start_*`: local stack launchers.
- `import_*`: provider or reference-data imports.
- `cleanup_*`: derived-cache, registry or storage maintenance.
- `run_*`: acceptance, replay and scheduled workflow entrypoints.
- `check_*`, `compare_*`: read-only diagnostics and validation.
- `db_migrate.py`: schema migration control.
- `platformctl.py`: Docker/native bootstrap, lifecycle, doctor, logs, migration,
  backup/restore and pinned runtime control.
- `install_lean_runtime.py`: HTTPS download plus SHA-256, signature and SBOM
  verification for native LEAN.
- `check_lean_backend_parity.py`: compare certified Docker/native result artifacts.
- `install_git_hooks.sh`: enable repository commit policy.

Keep a script only when it is a supported operator entrypoint, is called by
automation, or provides a repeatable diagnostic, migration, recovery or
acceptance workflow that is not already covered by a newer entrypoint. Put
one-off investigation and release-specific verification in tests or an
operator-selected runtime workspace instead of committing another script.

The canonical deployment entrypoint is `platformctl.py`. DataRelease
publication uses `publish_data_release.py`; current cross-repository acceptance
uses `run_cross_repo_golden_platform_stage.py`; current staged platform audits
use the maintained `run_level*_audit.py` and focused acceptance scripts. Do not
add date-bound release scripts, hard-coded project IDs, partial-coverage PIT
replacement tools, or launchers with embedded database credentials.

Runtime output must go to `web/runtime/`, `LEAN_DATA_DIR`, database volumes or an
explicit operator-selected export target. Scripts must not create root-level
`results/`, `runs/`, `Data/` or `parquet/` directories.

Stock downloads write the existing `data/bronze` and `data/silver` hierarchy
through the backend market-lake service. Scripts may read `data/qlib` or
`gold/qlib_staging`, but must never modify the Qlib repository or Qlib-owned
materializations.
