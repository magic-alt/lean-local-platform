from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import FileResponse

from ..core.errors import LeanWebError, NotFoundError
from ..services import object_store

router = APIRouter(prefix="/api/object-store", tags=["object-store"])


@router.get("")
def list_items():
    return object_store.list_items()


@router.get("/_stored-objects")
def list_stored_objects(
    namespace: str | None = None,
    objectKey: str | None = None,
    limit: int = 100,
    offset: int = 0,
):
    return object_store.list_stored_objects(namespace=namespace, object_key=objectKey, limit=limit, offset=offset)


@router.post("/{key:path}")
async def put_item(key: str, file: UploadFile = File(...)):
    try:
        return object_store.put_item(key, await file.read())
    except LeanWebError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/{key:path}")
def get_item(key: str):
    try:
        return FileResponse(object_store.get_item_path(key))
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except LeanWebError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/{key:path}")
def delete_item(key: str):
    try:
        object_store.delete_item(key)
        return {"deleted": True}
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except LeanWebError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
