from pathlib import Path
from typing import Any

from ..core.config import OBJECT_STORE_DIR
from ..core.errors import NotFoundError
from ..core.files import ensure_child_path
from ..db import db, rows_to_dicts, utc_now


def list_items() -> list[dict[str, Any]]:
    with db() as connection:
        rows = connection.execute("select * from object_store_items order by updated_at desc").fetchall()
    return rows_to_dicts(rows)


def put_item(key: str, data: bytes) -> dict[str, Any]:
    target = ensure_child_path(OBJECT_STORE_DIR, key)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    updated_at = utc_now()
    size = target.stat().st_size
    with db() as connection:
        connection.execute(
            """
            insert into object_store_items (key, file_path, size, updated_at)
            values (?, ?, ?, ?)
            on conflict(key) do update set
                file_path = excluded.file_path,
                size = excluded.size,
                updated_at = excluded.updated_at
            """,
            (key, str(target), size, updated_at),
        )
    return {"key": key, "file_path": str(target), "size": size, "updated_at": updated_at}


def get_item_path(key: str) -> Path:
    target = ensure_child_path(OBJECT_STORE_DIR, key)
    if not target.exists() or not target.is_file():
        raise NotFoundError("Object Store item not found.")
    return target


def delete_item(key: str) -> None:
    target = get_item_path(key)
    target.unlink()
    with db() as connection:
        connection.execute("delete from object_store_items where key = ?", (key,))
