from __future__ import annotations

import hashlib
import json
import uuid
from typing import Any

from ..db import db, json_dump, rows_to_dicts, utc_now


def contract_digest(value: Any) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def record_edge(
    *,
    parent_type: str,
    parent_id: str,
    child_type: str,
    child_id: str,
    relation: str,
    contract: Any | None = None,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    edge_id = str(uuid.uuid5(
        uuid.NAMESPACE_URL,
        f"lean-lineage:{parent_type}:{parent_id}:{child_type}:{child_id}:{relation}",
    ))
    digest = contract_digest(contract) if contract is not None else None
    with db() as connection:
        connection.execute(
            """
            insert into workflow_lineage_edges
                (id,parent_type,parent_id,child_type,child_id,relation,
                 contract_digest,details_json,created_at)
            values (?,?,?,?,?,?,?,?,?)
            on conflict(parent_type,parent_id,child_type,child_id,relation)
            do update set contract_digest=excluded.contract_digest,
                          details_json=excluded.details_json
            """,
            (
                edge_id,
                parent_type,
                parent_id,
                child_type,
                child_id,
                relation,
                digest,
                json_dump(details or {}),
                utc_now(),
            ),
        )
        row = connection.execute(
            "select * from workflow_lineage_edges where id=?",
            (edge_id,),
        ).fetchone()
    return dict(row)


def graph(resource_type: str, resource_id: str) -> dict[str, Any]:
    with db() as connection:
        parents = connection.execute(
            """
            select * from workflow_lineage_edges
            where child_type=? and child_id=?
            order by created_at,id
            """,
            (resource_type, resource_id),
        ).fetchall()
        children = connection.execute(
            """
            select * from workflow_lineage_edges
            where parent_type=? and parent_id=?
            order by created_at,id
            """,
            (resource_type, resource_id),
        ).fetchall()
    return {
        "resource": {"type": resource_type, "id": resource_id},
        "parents": rows_to_dicts(parents),
        "children": rows_to_dicts(children),
    }
