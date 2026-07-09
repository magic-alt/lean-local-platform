import pytest
from fastapi import HTTPException


class _FakeAsyncResult:
    def __init__(self, task_id: str):
        self.id = task_id


def test_dispatch_task_fails_fast_without_celery_worker(monkeypatch):
    import app.api.common as common

    update_calls = []

    def fake_update_task(task_id: str, **fields):
        update_calls.append((task_id, fields))

    monkeypatch.setattr(common, "_celery_workers_available", lambda: False)
    monkeypatch.setattr(common, "update_task", fake_update_task)

    class Signature:
        def apply_async(self):
            raise AssertionError("apply_async should not run when no worker exists")

    with pytest.raises(HTTPException) as exc:
        common.dispatch_task(Signature(), "task-1")

    assert exc.value.status_code == 503
    assert update_calls == [("task-1", {"status": "failed", "error": "No active Celery worker found. Start redis-server and the Celery worker."})]


def test_dispatch_task_dispatches_when_worker_available(monkeypatch):
    import app.api.common as common

    update_calls = []
    apply_calls = []

    def fake_update_task(task_id: str, **fields):
        update_calls.append((task_id, fields))

    def fake_apply_async():
        apply_calls.append("apply")
        return _FakeAsyncResult("celery-1")

    class Signature:
        apply_async = staticmethod(fake_apply_async)

    monkeypatch.setattr(common, "_celery_workers_available", lambda: True)
    monkeypatch.setattr(common, "update_task", fake_update_task)

    result = common.dispatch_task(Signature(), "task-2")

    assert result == "celery-1"
    assert apply_calls == ["apply"]
    assert ("task-2", {"celery_task_id": "celery-1", "status": "queued"}) in update_calls
