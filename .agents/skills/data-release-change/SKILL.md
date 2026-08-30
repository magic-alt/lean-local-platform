---
name: data-release-change
description: Implement or review canonical market-data, PIT, provider, source-gate, DataRelease, release-identity, or checksum changes in platform.
---

# DataRelease Change

Start with the smallest relevant symbols in `web/backend/app/services/`, especially `data_sync.py`, `data_releases.py`, `dataset_releases.py`, `data_provider_manager.py`, `source_gate.py`, `data_quality.py`, `release_identity.py`, and the PIT services. Do not scan a large service file end-to-end when symbol search and targeted reads suffice.

Trace:

```text
source -> raw observation -> normalization -> PIT/as-of semantics
-> quality/source gate -> immutable release -> identity/checksum -> consumer
```

Verify as-of date, provider provenance and fallback, deduplication, rerun idempotency, partial failure, immutable publication, historical correction policy, PIT constituent membership, calendar semantics, and deterministic checksums.

Never silently mutate or reinterpret a published DataRelease. Keep network/provider calls and persistent data mutation out of normal verification; use mocks, fakes, and fixtures unless explicitly authorized.
