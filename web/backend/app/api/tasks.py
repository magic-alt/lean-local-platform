from fastapi import APIRouter, HTTPException

from .common import paged_items
from ..services.tasks import cancel_task, delete_task, get_task, list_tasks, task_log_window

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


@router.get("")
def tasks(limit: int = 100, offset: int = 0, paged: bool = True):
    return paged_items(list_tasks(), limit=limit, offset=offset, paged=paged)


@router.get("/{task_id}")
def task_detail(task_id: str):
    try:
        return get_task(task_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Task not found.") from exc


@router.get("/{task_id}/logs")
def logs(task_id: str, offset: int | None = None, cursor: str | None = None, limit: int = 65536):
    try:
        return task_log_window(task_id, offset=offset, cursor=cursor, limit=limit)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Task not found.") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={"message": str(exc), "field": "cursor"}) from exc


@router.post("/{task_id}/cancel")
def cancel(task_id: str):
    try:
        return cancel_task(task_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Task not found.") from exc


@router.delete("/{task_id}")
@router.delete("/{task_id}/")
def delete(task_id: str):
    try:
        return delete_task(task_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Task not found.") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
