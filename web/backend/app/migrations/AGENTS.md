# Database Migrations

Do not apply migrations against persistent environments without explicit authorization.

Every migration change must document:

- forward behavior;
- compatibility impact;
- rollback or recovery strategy;
- data migration requirements;
- affected tests.

PostgreSQL is the canonical runtime metadata store. Legacy migrations are immutable lineage evidence and are not replayed on fresh PostgreSQL databases. Do not reintroduce SQLite as a runtime default. Keep migration verification isolated from persistent environments.
