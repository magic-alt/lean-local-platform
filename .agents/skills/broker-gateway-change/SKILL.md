---
name: broker-gateway-change
description: Implement or review QMT or broker gateway observation behavior, network exposure, credentials handling, and the broker read/write boundary.
---

# Broker Gateway Change

The current QMT gateway is loopback-only, GET-only, observation-only, and does not own a parallel ledger.

Allowed semantics are account, position, asset, order/fill observation, quote observation, and health/status queries.

Do not introduce in ordinary work: `submit_order`, `cancel_order`, `replace_order`, live target submission, automatic trading callbacks, broker-state mutation, OMS live writes, or local shadow-ledger ownership. Do not relax loopback/network exposure without an explicit security review.

Any broker write or `PAPER -> PRODUCTION` path is a P9 architecture/security change. Stop ordinary implementation and surface the boundary. Never call a real broker API in tests; use mocks/fakes and ensure credentials cannot appear in logs, fixtures, screenshots, or error payloads.
