def test_bulk_db_falls_back_to_business_connection_when_loader_is_unavailable(monkeypatch):
    import app.db as db_module

    events = []

    class FakeConnection:
        def __init__(self, url):
            events.append(("connect", url))
            if url == "mysql+pymysql://loader:bad@mysql/lean_market":
                raise RuntimeError("loader unavailable")

        def execute(self, sql, parameters=None):
            events.append(("execute", sql))

        def commit(self):
            events.append(("commit",))

        def rollback(self):
            events.append(("rollback",))

        def close(self):
            events.append(("close",))

    monkeypatch.setattr(db_module, "database_backend", lambda: "mysql")
    monkeypatch.setattr(db_module, "DATABASE_URL", "mysql+pymysql://business:ok@mysql/lean_market")
    monkeypatch.setattr(db_module, "MySQLConnection", FakeConnection)
    monkeypatch.setenv("LEAN_LOADER_DATABASE_URL", "mysql+pymysql://loader:bad@mysql/lean_market")
    monkeypatch.setenv("LEAN_MYSQL_BULK_DISABLE_BINLOG", "1")

    with db_module.bulk_db() as connection:
        connection.execute("select 1")

    assert events == [
        ("connect", "mysql+pymysql://loader:bad@mysql/lean_market"),
        ("connect", "mysql+pymysql://business:ok@mysql/lean_market"),
        ("execute", "select 1"),
        ("commit",),
        ("close",),
    ]
