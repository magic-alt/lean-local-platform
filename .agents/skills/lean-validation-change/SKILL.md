---
name: lean-validation-change
description: Implement or review authoritative LEAN backtest, execution validation, validation result, or promotion-gate changes.
---

# LEAN Validation Change

Trace the strategy/artifact input, DataRelease and target hash binding, LEAN execution assumptions, validation output, persisted evidence, and promotion consumer.

Verify that validation is fail closed; result identity is deterministic and immutable; execution assumptions are explicit; failures, timeouts, retries, and reconciliation cannot produce a successful gate; and promotion uses the exact validated `artifactId`, `DataReleaseId`, and `targetWeightsSha256`.

Do not let API status, task completion, or a partial artifact stand in for a valid `VALIDATION_RESULT`. Run focused unit tests first. LEAN Docker integration is opt-in and requires Docker availability and explicit authorization when it would access external resources or persistent runtime state.
