# Level 4 / Level 5 upgrade execution — 2026-07-24

This record supplements, and does not replace, the independent audit failure
records dated 2026-07-22 through 2026-07-24.

## Implemented

- Persisted train/validation/OOS windows, validation candidates, selection
  events, feature fits, leakage checks and OOS evaluations.
- Made OOS dispatch conditional on validation-only parameter selection and
  added fail-closed frozen lineage requirements.
- Added immutable Paper constraint decisions, deterministic matching evidence,
  append-only ledger extensions and daily reconciliation records.
- Added durable, idempotent Paper daily jobs with legal transitions,
  completion markers, optimistic versions and orphan recovery.
- Moved LEAN Docker execution behind a dedicated allowlisted runner; removed
  the Docker socket from the general backtest worker.

## Verification performed

- Backend: `376 passed, 2 skipped`.
- Frontend build: passed.
- Chromium E2E: `15 passed, 1 skipped`.
- Repository hygiene and 29 help documents: passed.
- Real restricted-runner LEAN smoke
  `spy-20200102-20200228-20260724135943`: success, exit code 0.
- Real MySQL revisions 0023 through 0026 and the runner success audit record
  were verified in the running MySQL container.

## Hard gates still open

- No certified production dataset was available for an independent full Level
  4 rerun.
- No new compliant 21-day real LEAN Paper session proved same-session fills
  and constraint rejects.
- F1–F6 interruption recovery was not compared to a clean ledger baseline.
- The complete isolated service/resource/concurrency fault matrix, production
  scale encrypted off-volume restore, RPO/RTO measurement, complete credential
  rotation and trusted release signing were not completed.

Therefore the result remains:

```text
LEVEL3_PASS
LEVEL4_FAIL
LEVEL5_REPLAY_FAIL
LEVEL5_OPERATIONAL_NOT_READY
LIVE_NOT_READY
```
