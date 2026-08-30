---
name: qlib-handoff-review
description: Review or change the qlib-platform to platform Artifact Contract v2 handoff, promotion lineage, TARGET_PORTFOLIO binding, or lifecycle gates.
---

# Qlib Handoff Review

Inspect the relevant symbols in `qlib_import_v2.py`, `qlib_promotion.py`, `artifact_registry.py`, `release_identity.py`, `backtest_execution_validation.py`, `backtest_validation.py`, and `workflow_lineage.py`.

Preserve the exact binding among `artifactId`, `DataReleaseId`, `targetWeightsSha256`, `VALIDATION_RESULT`, and lifecycle lineage. Imported artifacts fail closed; never repair or reinterpret invalid input silently.

The required lifecycle is:

```text
TARGET_PORTFOLIO -> LEAN validation -> VALIDATION_RESULT
-> LEAN_VALIDATED -> PAPER
```

Never permit direct `TARGET_PORTFOLIO -> PAPER`. Before `LEAN_VALIDATED`, require the LEAN run to bind the same DataRelease ID and target-weight hash as the original TARGET_PORTFOLIO. Before Paper deployment, require valid matching LEAN validation evidence. P9 remains unavailable.
