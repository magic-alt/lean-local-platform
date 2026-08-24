---
name: ci-validation
description: Select and run proportionate platform validation before handoff or commit, including backend tests, repository hygiene, frontend build, and opt-in LEAN integration.
---

# CI Validation

Choose the narrowest meaningful sequence and expand only when warranted:

```text
changed files -> targeted tests -> related subsystem tests
-> repository hygiene -> full backend pytest
-> frontend build if affected -> opt-in LEAN Docker integration if needed
```

Use the repository's documented local Python environment. Keep provider, broker, and persistent-environment access out of tests. LEAN Docker integration remains opt-in.

Before a commit, verify that `CHANGELOG.md` has a concise entry under `Unreleased`. Report commands run, results, skipped gates, and why each skip was appropriate.
