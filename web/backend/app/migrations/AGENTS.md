# Database Migrations

Do not apply migrations against persistent environments without explicit authorization.

Every migration change must document:

- forward behavior;
- compatibility impact;
- rollback or recovery strategy;
- data migration requirements;
- affected tests.

MySQL is the canonical runtime metadata store. Do not reintroduce SQLite as a runtime default. Keep migration verification isolated from persistent environments.
