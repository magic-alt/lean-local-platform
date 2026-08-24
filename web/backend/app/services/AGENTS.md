# Service Layer

Trace service changes to their API/task callers, repositories or database writes, external integrations, lifecycle transitions, and tests. Prefer existing service helpers and ownership boundaries over new cross-domain abstractions.

Classify side effects using the root `AGENTS.md` categories. DataRelease publication, LEAN validation, Paper state, and broker observations have distinct contracts; do not blur them in shared convenience code.

Preserve fail-closed behavior and idempotency at external, task, and lifecycle boundaries. A successful task status alone must not substitute for valid persisted evidence.
