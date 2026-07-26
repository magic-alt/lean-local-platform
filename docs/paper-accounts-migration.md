# Paper Accounts migration and legacy retirement

Migration `0029_paper_accounts` is additive. It creates account, generation,
risk profile, deployment, execution cycle/event, signal, checkpoint,
projection, daily snapshot/report and notification outbox tables. It also adds
nullable account/deployment/cycle bridge columns and fixed-point mirrors to the
existing Paper v2 intent, fill and ledger tables.

Migration `0033_retire_legacy_paper_sessions` removes every Paper session not
owned as a `paper_accounts.shadow_session_id`, together with its session-owned
orders, signals, reports, jobs, checkpoints, reconciliation and ledger records.
The legacy session/replay API and frontend route are retired. Account APIs use
`/api/paper/accounts` and `/api/paper/deployments`.

Money uses `DECIMAL(28,8)` and rate/weight fields use `DECIMAL(20,12)`.
The API emits these facts as decimal strings. Internal execution bridge columns
remain while all account-linked writes populate the precise mirrors. MySQL is
the only runtime fact database; SQLite support remains limited to isolated unit
tests.

Each new account owns a shadow Paper v2 session so the production execution
engine, restricted runner, global scheduler lease, 13-state transitions, fills,
ledger and six checkpoint phases are reused. The shadow session does not define
cash or positions: the opening and subsequent account-tagged ledger entries are
canonical. Account projections can be rebuilt at any time.

Rollback requires first pausing account scheduling and retaining exported
evidence. The `0033` cleanup is irreversible without a verified pre-migration
backup. Dropping 0029 tables or nullable bridge columns loses the new account
read model and linkage, so rollback is intentionally not automatic.
