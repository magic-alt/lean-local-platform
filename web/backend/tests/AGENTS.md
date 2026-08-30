# Backend Tests

Tests must not contact real brokers, production accounts, live order endpoints, or live provider credentials. Use mocks, fakes, and fixtures for broker and provider behavior.

LEAN Docker integration remains opt-in. Ordinary tests must not activate schedulers, apply migrations to persistent environments, submit broker writes, or trigger live activation.

Prefer focused behavioral tests for lifecycle gates, idempotency, retry/replay, immutable identity, and fail-closed error paths.
