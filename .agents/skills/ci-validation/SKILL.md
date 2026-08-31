---
name: ci-validation
description: Select and run proportionate platform validation before handoff or commit, including repository/developer governance, backend tests, frontend build, and opt-in LEAN integration.
---

# CI Validation

Choose the narrowest meaningful sequence and expand only when warranted:

```text
changed files
-> targeted tests
-> related subsystem tests
-> repository hygiene
-> developer-governance validation
-> open-source/repository-governance validation
-> backend pytest when affected
-> frontend build when affected
-> opt-in LEAN/native integration when required
```

## Always-on local governance baseline

Before handoff of repository or developer-automation changes run:

```bash
python scripts/check_repository_hygiene.py
python scripts/check_developer_governance.py
python scripts/check_oss_governance.py
```

Use the repository's documented local Python environment. Keep provider,
broker, and persistent-environment access out of ordinary tests. LEAN Docker,
native-runtime, provider, migration, and broker-facing integration remain
opt-in and must be justified by the changed surface.

GitHub `Governance`, `Dependency Review`, and `CodeQL` are remote evidence:
verify their actual job/step outcome after a PR is opened. A skipped or
bootstrap-only remote step must not be reported as if the underlying scan ran.

The `Release` workflow is manual release infrastructure, not a normal PR
validation lane.

Before a commit, verify that `CHANGELOG.md` has a concise entry under
`Unreleased` when the repository's changelog policy applies. Report commands
run, results, skipped gates, and why each skip was appropriate.
