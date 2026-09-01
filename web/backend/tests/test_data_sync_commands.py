import pytest


def test_create_run_marks_sync_failed_when_dispatch_fails(monkeypatch):
    from app.services import data_sync_commands

    failed: list[tuple[str, str]] = []
    monkeypatch.setattr(
        data_sync_commands.data_sync,
        "create_sync_run",
        lambda **kwargs: {"id": "sync-1"},
    )
    monkeypatch.setattr(data_sync_commands, "create_task", lambda *args, **kwargs: {"id": "task-1"})
    monkeypatch.setattr(data_sync_commands.data_sync, "bind_task", lambda *args: None)
    monkeypatch.setattr(
        data_sync_commands.data_sync,
        "mark_run_failed",
        lambda run_id, error: failed.append((run_id, error)),
    )
    monkeypatch.setattr(
        data_sync_commands,
        "_dispatch",
        lambda *args: (_ for _ in ()).throw(ConnectionError("broker unavailable")),
    )

    with pytest.raises(ConnectionError, match="broker unavailable"):
        data_sync_commands.create_run(datasets=None, mode="incremental", scope=None)

    assert failed == [("sync-1", "Task dispatch failed: broker unavailable")]
