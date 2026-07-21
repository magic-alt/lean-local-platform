from fastapi import APIRouter, HTTPException

from ..services.tasks import cancel_task, delete_task, get_task, list_tasks, task_logs

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
