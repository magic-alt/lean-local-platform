import sqlite3


def test_init_db_adds_data_assets_status_before_status_index(tmp_path, monkeypatch):
    import app.db as db_module

    db_path = tmp_path / "legacy.sqlite3"
    monkeypatch.setattr(db_module, "DB_PATH", db_path)
    monkeypatch.setattr(db_module, "DATABASE_URL", f"sqlite:///{db_path}")
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            """
            create table data_assets (
                id integer primary key autoincrement,
                symbol text not null,
                source text not null,
                rows integer not null,
                first_date text not null,
                last_date text not null,
                lean_file text not null,
                metadata_json text not null,
                created_at text not null
            )
            """
        )

    db_module.init_db()

    with sqlite3.connect(db_path) as connection:
        columns = {row[1] for row in connection.execute("pragma table_info(data_assets)").fetchall()}
        index_row = connection.execute(
            "select name from sqlite_master where type = 'index' and name = 'idx_data_assets_status_created'"
        ).fetchone()
    assert "status" in columns
    assert index_row is not None
