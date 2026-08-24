def test_postgres_iter_batches_uses_named_server_cursor():
    import app.db as db_module

    class Cursor:
        def __init__(self):
            self.calls = 0
            self.executed = None
            self.closed = False

        def execute(self, sql, parameters):
            self.executed = (sql, parameters)

        def fetchmany(self, size):
            self.calls += 1
            return [{"id": self.calls}] if self.calls <= 2 else []

        def close(self):
            self.closed = True

    cursor = Cursor()

    class RawConnection:
        def cursor(self, *, name):
            assert name.startswith("platform_stream_")
            return cursor

    connection = object.__new__(db_module.PostgresConnection)
    connection._connection = RawConnection()

    batches = list(connection.iter_batches("select * from sample where id=?", (1,), batch_size=1))

    assert batches == [[{"id": 1}], [{"id": 2}]]
    assert cursor.executed == ("select * from sample where id=%s", (1,))
    assert cursor.closed is True
