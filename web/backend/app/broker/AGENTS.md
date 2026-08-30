# Broker Subsystem

Current broker integration is observation-only.

QMT gateway must remain:

- loopback-only;
- query-only;
- broker-state read-only.

Do not add or exercise broker write operations during ordinary tasks. Any proposal involving submit/cancel/replace/live order routing must be treated as a P9 architecture and security change.

Never expose credentials in code, logs, fixtures, errors, screenshots, or review output. Tests use mocks/fakes and never contact real brokers or production accounts.
