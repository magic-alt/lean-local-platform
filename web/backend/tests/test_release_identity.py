from contextlib import contextmanager

from app.services import release_identity


class _MigrationRows:
    def __init__(self, rows):
        self.rows = rows

    def execute(self, _sql):
        return self

    def fetchall(self):
        return self.rows


def test_schema_identity_uses_postgres_migration_chain(monkeypatch):
    migrations = [
        {"revision": "P0001_baseline", "checksum": "one"},
        {"revision": "P0002_followup", "checksum": "two"},
    ]

    @contextmanager
    def fake_db():
        yield _MigrationRows(
            [
                {"revision": "P0001_baseline", "checksum": "one"},
                {"revision": "P0002_followup", "checksum": "two"},
            ]
        )

    monkeypatch.setattr(release_identity, "database_backend", lambda: "postgresql")
    monkeypatch.setattr(release_identity, "migration_files", lambda _path: migrations)
    monkeypatch.setattr(release_identity, "db", fake_db)

    result = release_identity._schema_identity()

    assert result["latestSourceMigration"] == "P0002_followup"
    assert result["latestAppliedMigration"] == "P0002_followup"
    assert result["aligned"] is True
