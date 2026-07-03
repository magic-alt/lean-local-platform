from fastapi import APIRouter, HTTPException

from ..services.tasks import get_task, list_tasks, task_logs, update_task

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


@router.get("")
def tasks():
    return list_tasks()


@router.get("/{task_id}")
def task_detail(task_id: str):
    try:
        return get_task(task_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Task not found.") from exc


@router.get("/{task_id}/logs")
def logs(task_id: str):
    try:
        return {"logs": task_logs(task_id)}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Task not found.") from exc


@router.post("/{task_id}/cancel")
def cancel(task_id: str):
    try:
        update_task(task_id, status="cancelled", error="Cancellation requested by user.")
        return get_task(task_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Task not found.") from exc
