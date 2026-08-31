# Repository Git Hooks

These hooks provide fast local feedback. They are not authoritative security or
CI controls and can be bypassed by Git itself, so GitHub required checks remain
the merge-time source of enforcement.

## Enable

From the repository root:

```bash
./scripts/install_git_hooks.sh
```

This sets `core.hooksPath=.githooks`. Verify with:

```bash
git config --get core.hooksPath
```

## Hooks

### `pre-commit`

Runs lightweight repository/developer-governance checks before Git creates a
commit:

```text
check_repository_hygiene.py
check_developer_governance.py
```

It intentionally does not run backend/frontend/integration suites.

### `commit-msg`

Requires `CHANGELOG.md` to be staged according to the repository's current
per-commit changelog policy.

## Policy

Do not use `--no-verify` as a normal way to bypass a failing repository hook.
Fix the cause or document a deliberate exception in the pull request.

If hooks appear not to run, inspect:

```bash
git config --show-origin --get core.hooksPath
git status --short
```

CI reruns the important repository governance checks independently, so a local
hook installation problem must not make a PR appear validated.
