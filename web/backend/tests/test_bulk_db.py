def test_bulk_db_uses_the_standard_transactional_connection(monkeypatch):
    import app.db as db_module

    events = []

    class FakeConnection:
        def execute(self, sql, parameters=None):
            events.append(("execute", sql))

        def commit(self):
            events.append(("commit",))

        def rollback(self):
            events.append(("rollback",))

        def close(self):
            events.append(("close",))

    connection = FakeConnection()
    monkeypatch.setattr(db_module, "connect", lambda: connection)

    with db_module.bulk_db() as opened:
        assert opened is connection
        opened.execute("select 1")

    assert events == [("execute", "select 1"), ("commit",), ("close",)]
