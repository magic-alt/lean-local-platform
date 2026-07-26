from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass

from ..db import db, row_to_dict, utc_now


@dataclass(frozen=True)
class IdempotencyRecord:
    state: str
    response_status: int | None = None
    response_body: str | None = None
    response_content_type: str | None = None


def request_digest(body: bytes, query: str) -> str:
    digest = hashlib.sha256()
    digest.update(query.encode("utf-8"))
    digest.update(b"\0")
    digest.update(body)
    return digest.hexdigest()


def _path_digest(path: str) -> str:
    return hashlib.sha256(path.encode("utf-8")).hexdigest()


def begin(
    *,
    key: str,
    method: str,
    path: str,
    digest: str,
    trace_id: str | None,
) -> IdempotencyRecord:
    path_digest = _path_digest(path)
    with db() as connection:
        row = connection.execute(
            """
            select * from api_idempotency_keys
            where idempotency_key=? and method=? and request_path_sha256=?
            """,
            (key, method, path_digest),
        ).fetchone()
        existing = row_to_dict(row)
        if existing is None:
            now = utc_now()
            try:
                connection.execute(
                    """
                    insert into api_idempotency_keys
                        (id,idempotency_key,method,request_path,request_path_sha256,
                         request_sha256,status,
                         trace_id,created_at,updated_at)
                    values (?,?,?,?,?,?,'pending',?,?,?)
                    """,
                    (
                        str(uuid.uuid4()),
                        key,
                        method,
                        path,
                        path_digest,
                        digest,
                        trace_id,
                        now,
                        now,
                    ),
                )
                return IdempotencyRecord("new")
            except Exception:
                row = connection.execute(
                    """
                    select * from api_idempotency_keys
                    where idempotency_key=? and method=? and request_path_sha256=?
                    """,
                    (key, method, path_digest),
                ).fetchone()
                existing = row_to_dict(row)
                if existing is None:
                    raise
    if str(existing["request_sha256"]) != digest:
        return IdempotencyRecord("conflict")
    if str(existing["status"]) == "completed":
        return IdempotencyRecord(
            "replay",
            response_status=int(existing["response_status"]),
            response_body=str(existing.get("response_body") or ""),
            response_content_type=str(existing.get("response_content_type") or "application/json"),
        )
    return IdempotencyRecord("pending")


def complete(
    *,
    key: str,
    method: str,
    path: str,
    response_status: int,
    response_body: str,
    response_content_type: str,
) -> None:
    path_digest = _path_digest(path)
    with db() as connection:
        connection.execute(
            """
            update api_idempotency_keys
            set status='completed',response_status=?,response_body=?,
                response_content_type=?,updated_at=?
            where idempotency_key=? and method=? and request_path_sha256=? and status='pending'
            """,
            (
                int(response_status),
                response_body,
                response_content_type,
                utc_now(),
                key,
                method,
                path_digest,
            ),
        )


def abandon(*, key: str, method: str, path: str) -> None:
    path_digest = _path_digest(path)
    with db() as connection:
        connection.execute(
            """
            delete from api_idempotency_keys
            where idempotency_key=? and method=? and request_path_sha256=? and status='pending'
            """,
            (key, method, path_digest),
        )
