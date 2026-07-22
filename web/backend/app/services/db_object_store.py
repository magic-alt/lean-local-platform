from __future__ import annotations

import hashlib
import mimetypes
import uuid
from pathlib import Path
from typing import Any

from ..core.config import DB_OBJECT_CHUNK_BYTES, DB_OBJECT_STORE_ENABLED
from ..db import bulk_db, db, json_dump, row_to_dict, rows_to_dicts, utc_now


OBJECT_ID_NAMESPACE = uuid.UUID("bf2f81f8-7a4f-4d88-a5f9-cabdc356b0f3")


def object_id(namespace: str, key: str, sha256: str) -> str:
    return str(uuid.uuid5(OBJECT_ID_NAMESPACE, f"{namespace}:{key}:{sha256}"))


def put_bytes(
    namespace: str,
    key: str,
    data: bytes,
    *,
    content_type: str | None = None,
    source_path: str | None = None,
    metadata: dict[str, Any] | None = None,
    bulk: bool = False,
) -> dict[str, Any]:
    if not DB_OBJECT_STORE_ENABLED:
        return {}
    namespace = namespace.strip()
    key = key.strip().replace("\\", "/")
    if not namespace or not key:
        raise ValueError("namespace and key are required for database object storage.")
    digest = hashlib.sha256(data).hexdigest()
    item_id = object_id(namespace, key, digest)
    now = utc_now()
    chunk_size = max(1, int(DB_OBJECT_CHUNK_BYTES))
    metadata = metadata or {}
    connection_factory = bulk_db if bulk else db
    with connection_factory() as connection:
        if bulk:
            existing = connection.execute(
                "select id from stored_objects where id = ?",
                (item_id,),
            ).fetchone()
            if existing:
                return get_object(item_id) or {}
        connection.execute(
            """
            insert into stored_objects
                (id, namespace, object_key, content_type, encoding, size, sha256, storage_mode,
                 source_path, metadata_json, created_at, updated_at)
            values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            on conflict(namespace, object_key, sha256) do update set
                content_type = excluded.content_type,
                encoding = excluded.encoding,
                size = excluded.size,
                storage_mode = excluded.storage_mode,
                source_path = excluded.source_path,
                metadata_json = excluded.metadata_json,
                updated_at = excluded.updated_at
            """,
            (
                item_id,
                namespace,
                key,
                content_type,
                "binary",
                len(data),
                digest,
                "database",
                source_path,
                json_dump(metadata),
                now,
                now,
            ),
        )
        connection.execute("delete from stored_object_chunks where object_id = ?", (item_id,))
        chunks = []
        for index, start in enumerate(range(0, len(data), chunk_size)):
            chunk = data[start : start + chunk_size]
            chunks.append((item_id, index, chunk, len(chunk), hashlib.sha256(chunk).hexdigest()))
        if chunks:
            connection.executemany(
                """
                insert into stored_object_chunks (object_id, chunk_index, data, size, sha256)
                values (?, ?, ?, ?, ?)
                """,
                chunks,
            )
    return get_object(item_id) or {}


def put_file(
    namespace: str,
    key: str,
    path: Path | str,
    *,
    content_type: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    file_path = Path(path)
    if not file_path.exists() or not file_path.is_file():
        raise FileNotFoundError(str(file_path))
    guessed_type = content_type or mimetypes.guess_type(file_path.name)[0]
    return put_bytes(
        namespace,
        key,
        file_path.read_bytes(),
        content_type=guessed_type,
        source_path=str(file_path),
        metadata={
            "mtime": file_path.stat().st_mtime,
            "source_path": str(file_path),
            **(metadata or {}),
        },
    )


def get_object(object_id_value: str) -> dict[str, Any] | None:
    with db() as connection:
        row = connection.execute("select * from stored_objects where id = ?", (object_id_value,)).fetchone()
    return row_to_dict(row)


def latest_object(namespace: str, key: str) -> dict[str, Any] | None:
    with db() as connection:
        row = connection.execute(
            """
            select * from stored_objects
            where namespace = ? and object_key = ?
            order by updated_at desc
            limit 1
            """,
            (namespace, key),
        ).fetchone()
    return row_to_dict(row)


def read_bytes(object_id_value: str) -> bytes:
    with db() as connection:
        stored = connection.execute(
            "select size, sha256 from stored_objects where id = ?",
            (object_id_value,),
        ).fetchone()
        chunks = connection.execute(
            """
            select data from stored_object_chunks
            where object_id = ?
            order by chunk_index asc
            """,
            (object_id_value,),
        ).fetchall()
    if not stored:
        raise ValueError(f"stored_object_missing:{object_id_value}")
    payload = b"".join(bytes(row["data"]) for row in chunks)
    if len(payload) != int(stored["size"] or 0) or hashlib.sha256(payload).hexdigest() != stored["sha256"]:
        raise ValueError(f"stored_object_checksum_mismatch:{object_id_value}")
    return payload


def restore_to_path(object_id_value: str, target: Path | str) -> Path:
    path = Path(target)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(read_bytes(object_id_value))
    return path


def delete_object(object_id_value: str) -> None:
    with db() as connection:
        archive = connection.execute(
            "select id from provider_raw_archives where object_id = ? limit 1",
            (object_id_value,),
        ).fetchone()
        if archive:
            raise ValueError(f"stored_object_referenced_by_provider_archive:{archive['id']}")
        connection.execute("delete from stored_object_chunks where object_id = ?", (object_id_value,))
        connection.execute("delete from stored_objects where id = ?", (object_id_value,))


def integrity_report() -> dict[str, Any]:
    with db() as connection:
        orphan_archives = rows_to_dicts(
            connection.execute(
                """
                select a.id, a.provider, a.dataset_key, a.object_id
                from provider_raw_archives a
                left join stored_objects o on o.id = a.object_id
                where o.id is null
                order by a.created_at desc
                """
            ).fetchall()
        )
        objects_without_chunks = rows_to_dicts(
            connection.execute(
                """
                select o.id, o.namespace, o.object_key, o.size
                from stored_objects o
                where o.size > 0 and not exists (
                    select 1 from stored_object_chunks c where c.object_id = o.id
                )
                order by o.updated_at desc
                """
            ).fetchall()
        )
    return {
        "passed": not orphan_archives and not objects_without_chunks,
        "orphanArchives": orphan_archives,
        "objectsWithoutChunks": objects_without_chunks,
    }


def list_objects(
    namespace: str | None = None,
    *,
    object_key: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> dict[str, Any]:
    clauses = []
    values: list[Any] = []
    if namespace:
        clauses.append("namespace = ?")
        values.append(namespace)
    if object_key:
        clauses.append("object_key like ?")
        values.append(f"%{object_key.strip()}%")
    sql = "select * from stored_objects"
    count_sql = "select count(*) as count from stored_objects"
    if clauses:
        where = " where " + " and ".join(clauses)
        sql += where
        count_sql += where
    bounded_limit = max(1, min(int(limit), 1000))
    bounded_offset = max(0, int(offset))
    sql += " order by updated_at desc, id desc limit ? offset ?"
    with db() as connection:
        count = connection.execute(count_sql, values).fetchone()["count"]
        rows = connection.execute(sql, [*values, bounded_limit, bounded_offset]).fetchall()
    return {"items": rows_to_dicts(rows), "count": count, "limit": bounded_limit, "offset": bounded_offset}
