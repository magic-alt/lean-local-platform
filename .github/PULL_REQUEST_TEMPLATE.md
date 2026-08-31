## Summary

<!-- What changed? Keep this focused on observable behavior and architecture. -->

## Motivation

<!-- What problem does this solve? Link an issue when applicable. -->

## Side-effect classification

Select the highest side-effect level touched by this change:

- [ ] `READ_ONLY`
- [ ] `LOCAL_TEST_WRITE`
- [ ] `DATA_CONTROL_PLANE_WRITE`
- [ ] `PAPER_STATE_WRITE`
- [ ] `BROKER_OBSERVATION`
- [ ] `BROKER_WRITE` — requires explicit architecture/security review
- [ ] `LIVE_ACTIVATION` — requires explicit architecture/security review

## Changes

- 

## Architecture / contract impact

- [ ] No architecture boundary changes
- [ ] Changes storage/source-of-truth behavior
- [ ] Changes API or Artifact Contract behavior
- [ ] Changes DataRelease / PIT / QA / certification behavior
- [ ] Changes execution / runner behavior
- [ ] Changes Paper / ledger / checkpoint behavior
- [ ] Changes broker-facing or live-execution boundaries

Explain any checked impact:

<!-- Keep Parquet/PostgreSQL/RabbitMQ authority and qlib-platform handoff explicit. -->

## Developer automation / repository governance

- [ ] No `.agents`, `.codex`, `.githooks`, `.github`, `AGENTS.md`, release-policy, or repository-setting changes
- [ ] Developer automation / governance changed and is described below
- [ ] Any version-sensitive Codex/GitHub syntax was checked against current upstream documentation
- [ ] No required check, CODEOWNERS rule, command guardrail, secret filter, or release protection was weakened

Details:

## Data and migrations

- [ ] No schema or migration changes
- [ ] Migration added and tested
- [ ] Data backfill / rebuild required
- [ ] Data certification or release evidence invalidated

Details:

## Security

- [ ] No authentication, authorization, credential, sandbox, image, filesystem, or broker-boundary changes
- [ ] Security-sensitive behavior changed and is described below

Details:

## Validation

List the exact commands run and their results.

```text
python scripts/check_repository_hygiene.py
python scripts/check_developer_governance.py
python scripts/check_oss_governance.py

# add relevant backend/frontend/integration commands here
```

For remote GitHub checks, distinguish an actual scan/review step from a
bootstrap warning or skipped lane.

Intentionally skipped validation lanes and why:

## UI evidence

<!-- Required for visible UI changes. Add screenshots or recordings; otherwise write N/A. -->

N/A

## Documentation

- [ ] README / current docs updated when user or operator behavior changed
- [ ] OpenAPI / help references updated when API behavior changed
- [ ] Historical evidence under `docs/history/` was not rewritten as current guidance
- [ ] No documentation update required

## Checklist

- [ ] The change is focused and does not include runtime/downloaded/generated artifacts.
- [ ] I preserved the documented Research / Execution boundary.
- [ ] I did not bypass fail-closed data, PIT, benchmark, lineage, hash, or certification gates.
- [ ] I did not introduce broker writes or live activation as an incidental change.
- [ ] I did not weaken developer-automation or repository-governance safety controls to make validation pass.
- [ ] I updated the `Unreleased` section of `CHANGELOG.md`.
- [ ] I reviewed the contribution and security policies.
