# Architecture delta

## Before

- Walk-forward dispatched candidate OOS runs before validation selection.
- LEAN fills could be treated as Paper facts without a persisted constraint,
  matching, ledger and reconciliation chain.
- General backtest workers held the Docker socket.
- Paper scheduling did not have a durable per-session/per-date state machine.

## After this remediation

- Train and validation children run first; selection is validation-only,
  persisted and fingerprinted; only the selected candidate may enter OOS.
- A versioned leakage evaluator fails closed on overlap, label-boundary,
  future-reference, full-sample-fit, OOS-selection and revision violations.
- Paper v2 persists immutable LEAN intents, constraint decisions, legal state
  transitions, deterministic matches, fills, append-only ledger entries and
  daily reconciliation.
- Durable daily jobs use a unique session/date key, completion marker,
  optimistic versioning and orphan recovery.
- General backtest workers delegate an allowlisted job specification to a
  dedicated runner. The worker has no Docker socket; the runner has a
  read-only root filesystem, no network for LEAN jobs, fixed image digest,
  mount/command allowlists and resource/PID limits.

These code changes are not maturity certification. Missing production-like
evidence remains release-blocking.
