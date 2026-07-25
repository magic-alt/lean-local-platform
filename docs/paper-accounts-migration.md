# Paper Accounts migration and compatibility

Migration `0029_paper_accounts` is additive. It creates account, generation,
risk profile, deployment, execution cycle/event, signal, checkpoint,
projection, daily snapshot/report and notification outbox tables. It also adds
nullable account/deployment/cycle bridge columns and fixed-point mirrors to the
existing Paper v2 intent, fill and ledger tables.

No legacy Paper session, order, fill, ledger, daily job, reconciliation,
checkpoint or audit row is backfilled or deleted. Existing APIs remain under
`/api/paper/{sessionId}` and the frontend exposes them at `/paper/legacy`.
New account APIs use `/api/paper/accounts`, `/api/paper/deployments`,
`/api/paper/signals` and `/api/paper/execution-cycles`.

Money uses `DECIMAL(28,8)` and rate/weight fields use `DECIMAL(20,12)`.
The API emits these facts as decimal strings. Existing REAL columns remain for
legacy compatibility, while all new account-linked writes also populate the
precise mirrors. MySQL is the only runtime fact database; SQLite support remains
limited to isolated unit tests.

Each new account owns a shadow Paper v2 session so the production execution
engine, restricted runner, global scheduler lease, 13-state transitions, fills,
ledger and six checkpoint phases are reused. The shadow session does not define
cash or positions: the opening and subsequent account-tagged ledger entries are
canonical. Account projections can be rebuilt at any time.

Rollback requires first pausing account scheduling and retaining exported
evidence. Dropping 0029 tables or nullable bridge columns loses the new account
read model and linkage, so rollback is intentionally not automatic. It does not
require modifying legacy records.
