import pytest
from fastapi import HTTPException


class _FakeAsyncResult:
    def __init__(self, task_id: str):
        self.id = task_id


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

    monkeypatch.setattr(common, "update_task", fake_update_task)

    result = common.dispatch_task(Signature(), "task-2")

    assert result == "celery-1"
    assert apply_calls == ["apply"]
    assert ("task-2", {"celery_task_id": "celery-1", "status": "queued"}) in update_calls


def test_dispatch_task_marks_failed_when_celery_unavailable(monkeypatch):
    import app.api.common as common

    update_calls = []

    def fake_update_task(task_id: str, **fields):
        update_calls.append((task_id, fields))

    class Signature:
        def apply_async(self):
            raise OSError("broker unavailable")

    monkeypatch.setattr(common, "update_task", fake_update_task)

    with pytest.raises(HTTPException) as exc:
        common.dispatch_task(Signature(), "task-3")

    assert exc.value.status_code == 503
    assert exc.value.detail == "Redis/Celery unavailable. Start redis-server and the Celery worker."
    assert update_calls == [("task-3", {"status": "failed", "error": "Redis/Celery unavailable: broker unavailable"})]
