from __future__ import annotations

import uuid
from typing import Any, Iterable, Mapping

from ..db import json_dump, utc_now


QLIB_TYPES = {
    "MODEL_RELEASE",
    "STRATEGY_POLICY",
    "SIGNAL_SNAPSHOT",
    "TARGET_PORTFOLIO",
    "VALIDATION_RESULT",
}
QLIB_STATUSES = {"CANDIDATE", "RESEARCH_REVIEW", "RESEARCH_PROMOTED", "REJECTED"}


def register_qlib_artifacts(connection: Any, artifacts: Iterable[Mapping[str, Any]]) -> None:
    items = [dict(item) for item in artifacts]
    item_ids = {str(item["artifactId"]) for item in items}
    now = utc_now()
    for item in items:
        artifact_id = str(item["artifactId"])
        existing = connection.execute(
            "select artifact_type,payload_sha256,data_release_id from artifact_registry where artifact_id=?",
            (artifact_id,),
        ).fetchone()
        if existing:
            identity = (item["artifactType"], item["payloadSha256"], item["dataReleaseId"])
            if tuple(existing[key] for key in ("artifact_type", "payload_sha256", "data_release_id")) != identity:
                raise ValueError(f"Artifact ID already exists with different content: {artifact_id}")
            continue
        payload_ref = dict(item.get("payloadRef") or {})
        connection.execute(
            """insert into artifact_registry
               (artifact_id,schema_version,artifact_type,owner,promotion_status,data_release_id,
                universe_release_id,model_release_id,strategy_policy_id,git_commit,container_digest,
                as_of_time,signal_date,trade_date,timezone,currency,payload_sha256,object_key,
                media_type,row_count,metadata_json,created_at)
               values (?,?,?,'qlib',?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                artifact_id,
                item["schemaVersion"],
                item["artifactType"],
                item["promotionStatus"],
                item["dataReleaseId"],
                item.get("universeReleaseId"),
                item.get("modelReleaseId"),
                item.get("strategyPolicyId"),
                item["gitCommit"],
                item["containerDigest"],
                item["asOfTime"],
                item.get("signalDate"),
                item.get("tradeDate"),
                item["timezone"],
                item["currency"],
                item["payloadSha256"],
                payload_ref.get("objectKey"),
                payload_ref.get("mediaType"),
                payload_ref.get("rows"),
                json_dump(item.get("metadata") or {}),
                now,
            ),
        )
        connection.execute(
            """insert into artifact_promotion_events
               (id,artifact_id,from_status,to_status,owner,reason,evidence_json,created_at)
               values (?,?,null,?,'qlib','initial_import',?,?)""",
            (str(uuid.uuid4()), artifact_id, item["promotionStatus"], json_dump({}), now),
        )
    for item in items:
        child = str(item["artifactId"])
        for parent in item.get("parentArtifactIds") or []:
            parent_id = str(parent)
            if parent_id not in item_ids:
                exists = connection.execute(
                    "select artifact_id from artifact_registry where artifact_id=?", (parent_id,)
                ).fetchone()
                if not exists:
                    raise ValueError(f"Artifact parent does not exist: {parent_id}")
            connection.execute(
                """insert into artifact_lineage_edges
                   (parent_artifact_id,child_artifact_id,created_at) values (?,?,?)
                   on conflict(parent_artifact_id,child_artifact_id) do update
                   set created_at=artifact_lineage_edges.created_at""",
                (parent_id, child, now),
            )
