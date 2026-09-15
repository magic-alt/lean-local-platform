# Current Release Status

Last reviewed: 2026-09-15.

This file defines the current certification boundary; it does not promote the repository to a certified production release.

| Binding | Current requirement |
| --- | --- |
| Git SHA / release ID | Must match the running release and certification bundle |
| Runtime database | PostgreSQL 17 |
| Task broker | RabbitMQ 4.3.5 |
| Market authority | Immutable DataRelease over Parquet |
| Research contract | Artifact Contract v2 + content-addressed `TARGET_PORTFOLIO` |
| Release identity | Migration revision/checksum + OpenAPI SHA-256 + frontend digest |
| Restore | Independent PostgreSQL restore with canonical digest checks; Paper additionally rebuilds projections |
| Fault evidence | Complete policy matrix with trace and invariant evidence |
| Paper soak | Real-time production-shape observation for at least 21 elapsed calendar days and 21 observed Asia/Shanghai dates |
| External alert | Real third-party persisted success observed for at least 24 hours |
| Live activation | Disabled (P9 not enabled) |

The machine-readable desired policy is [`config/certification/post-migration-v1.json`](../config/certification/post-migration-v1.json), and the operating procedure is [Post-Migration Release Certification](post-migration-certification.md). `scripts/release_certification.py` fails closed when required evidence is missing, malformed, failed, or bound to a different release identity.

The runtime exposes health, readiness, certification, and authorization separately. A previously generated certificate automatically becomes ineffective when its release identity no longer matches the running Git SHA, release ID, migration revision/checksum, OpenAPI digest, or frontend digest. Certification never enables Live Trading/P9.

The [2026-08-04 final seal](audit/final-seal-certification-2026-08-04.md) is a historical snapshot for the pre-PostgreSQL/RabbitMQ architecture. Its MySQL/Redis-era migration and failure evidence must not be used to certify the current release.

Current status remains **NOT CERTIFIED**. In particular, rapid historical Paper replay is functional acceptance only and is not interchangeable with the required real-time 21-day production-shape observation. Issue #61 must remain open until the current release's operational restore/fault/supply-chain/third-party alert/soak evidence has actually been collected and the identity-bound bundle evaluates to `CERTIFIED` for the intended profile/runtime.
