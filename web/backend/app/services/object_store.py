from pathlib import Path
from typing import Any

from ..core.config import OBJECT_STORE_DIR
from ..core.errors import NotFoundError
from ..core.files import ensure_child_path
from ..db import db, rows_to_dicts, utc_now
from .db_object_store import delete_object, latest_object, list_objects, put_bytes, restore_to_path


def list_items() -> list[dict[str, Any]]:
    with db() as connection:
        rows = connection.execute("select * from object_store_items order by updated_at desc").fetchall()
    return rows_to_dicts(rows)


def list_stored_objects(
    namespace: str | None = None,
    object_key: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> dict[str, Any]:
    return list_objects(namespace=namespace, object_key=object_key, limit=limit, offset=offset)


def put_item(key: str, data: bytes) -> dict[str, Any]:
    target = ensure_child_path(OBJECT_STORE_DIR, key)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    updated_at = utc_now()
    size = target.stat().st_size
    stored = put_bytes("object-store", key, data, source_path=str(target), metadata={"file_path": str(target)})
    with db() as connection:
        connection.execute(
            """
            insert into object_store_items (key, file_path, stored_object_id, size, updated_at)
            values (?, ?, ?, ?, ?)
            on conflict(key) do update set
                file_path = excluded.file_path,
                stored_object_id = excluded.stored_object_id,
                size = excluded.size,
                updated_at = excluded.updated_at
            """,
            (key, str(target), stored.get("id"), size, updated_at),
        )
    return {"key": key, "file_path": str(target), "stored_object_id": stored.get("id"), "size": size, "updated_at": updated_at}


def get_item_path(key: str) -> Path:
    target = ensure_child_path(OBJECT_STORE_DIR, key)
    if not target.exists() or not target.is_file():
        stored = latest_object("object-store", key)
        if not stored:
            raise NotFoundError("Object Store item not found.")
        restore_to_path(stored["id"], target)
    return target


def delete_item(key: str) -> None:
    target = ensure_child_path(OBJECT_STORE_DIR, key)
    stored_id = None
    with db() as connection:
        row = connection.execute("select stored_object_id from object_store_items where key = ?", (key,)).fetchone()
        stored_id = row["stored_object_id"] if row else None
    if not target.exists() and not stored_id and not latest_object("object-store", key):
        raise NotFoundError("Object Store item not found.")
    if target.exists():
        target.unlink()
    with db() as connection:
        connection.execute("delete from object_store_items where key = ?", (key,))
    if stored_id:
        delete_object(stored_id)
