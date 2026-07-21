# Contributing

Follow [AGENTS.md](AGENTS.md) for code style and test commands, and
[Repository Layout](docs/repository_layout.md) for source/runtime boundaries.

## Commit policy

Enable the versioned local hooks once per clone:

```bash
./scripts/install_git_hooks.sh
```

Every commit must stage a concise entry in the `Unreleased` section of
`CHANGELOG.md`. The entry records the date, commit subject and observable change.
Do not include the commit's own hash because that hash does not exist until the
commit has been created; Git history remains the authoritative hash ledger.

Use concise imperative commit subjects, keep generated artifacts out of the
change, and run:

```bash
python3 scripts/check_repository_hygiene.py
cd web/backend && .venv/bin/python -m pytest -q
cd ../frontend && npm run build
```

Docker/LEAN integration remains opt-in as documented in AGENTS.md.
