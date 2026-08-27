# Current Release Status

Last reviewed: 2026-08-27.

This file defines the shape of current certification evidence; it does not promote the repository to a certified production release.

| Binding | Current documentation baseline |
| --- | --- |
| Git SHA | `e84383243627340ab18f2fd5452ada99f5889628` |
| Runtime database | PostgreSQL 17 |
| Task broker | RabbitMQ 4.3.5 |
| Market authority | Parquet |
| Research contract | Artifact Contract v2 + content-addressed `TARGET_PORTFOLIO` |
| Live activation | Disabled (P9 not enabled) |

Release certification must additionally record the applied PostgreSQL migration revision/checksum, generated OpenAPI hash, frontend digest, runtime/image lock identities, DataRelease contract version, Windows host certification when applicable, and current fault/restore/soak evidence.

The [2026-08-04 final seal](audit/final-seal-certification-2026-08-04.md) is a historical snapshot for the pre-PostgreSQL/RabbitMQ architecture. Its 233-path, migration 0043, MySQL/Redis and failure evidence must not be used to certify the current release.

Until a post-migration evidence bundle binds all fields above, status remains **NOT CERTIFIED**. Historical passes remain valuable evidence but do not survive an architecture, database, broker, runtime-manager or API-contract change automatically.
