from __future__ import annotations

import json
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
PLATFORM_STATUSES = {"LEAN_VALIDATED", "PAPER", "PRODUCTION", "RETIRED"}


def _metadata(value: object) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    if isinstance(value, str) and value.strip():
        loaded = json.loads(value)
        return dict(loaded) if isinstance(loaded, Mapping) else {}
    return {}


def _source_manifest_sha256(item: Mapping[str, Any]) -> str | None:
    value = str(_metadata(item.get("metadata")).get("sourceManifestSha256") or "").strip()
    return value or None


def _assert_acyclic(items: list[dict[str, Any]]) -> None:
    graph = {
        str(item["artifactId"]): [str(parent) for parent in item.get("parentArtifactIds") or []]
        for item in items
    }
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(artifact_id: str) -> None:
        if artifact_id in visited:
            return
        if artifact_id in visiting:
            raise ValueError(f"Artifact lineage cycle detected: {artifact_id}")
        visiting.add(artifact_id)
        for parent_id in graph.get(artifact_id, []):
            if parent_id in graph:
                visit(parent_id)
        visiting.remove(artifact_id)
        visited.add(artifact_id)

    for artifact_id in graph:
        visit(artifact_id)


def preflight_qlib_artifacts(connection: Any, artifacts: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Validate a complete Qlib artifact graph before the first registry write.

    This is a consumer-owned validation boundary. It deliberately does not call
    qlib-platform code and is run both by the import service and immediately
    before registry mutation so malformed/colliding graphs fail closed.
    """

    items = [dict(item) for item in artifacts]
    if not items:
        raise ValueError("Qlib artifact graph must not be empty")
    item_ids = [str(item.get("artifactId") or "") for item in items]
    if any(not artifact_id for artifact_id in item_ids):
        raise ValueError("Qlib artifactId is required")
    if len(item_ids) != len(set(item_ids)):
        raise ValueError("Duplicate Qlib artifactId in registry preflight")
    ids = set(item_ids)

    data_release_ids: set[str] = set()
    universe_values: list[str | None] = []
    source_values: list[str | None] = []
    for item in items:
        artifact_id = str(item["artifactId"])
        artifact_type = str(item.get("artifactType") or "")
        status = str(item.get("promotionStatus") or "")
        if artifact_type not in QLIB_TYPES:
            raise ValueError(f"Qlib cannot register artifact type: {artifact_type}")
        if status not in QLIB_STATUSES:
            raise ValueError(f"Qlib cannot register promotion status: {status}")
        data_release_id = str(item.get("dataReleaseId") or "").strip()
        if not data_release_id:
            raise ValueError(f"Qlib artifact missing dataReleaseId: {artifact_id}")
        data_release_ids.add(data_release_id)
        universe = str(item.get("universeReleaseId") or "").strip() or None
        universe_values.append(universe)
        source_values.append(_source_manifest_sha256(item))
        parents = [str(parent) for parent in item.get("parentArtifactIds") or []]
        if len(parents) != len(set(parents)):
            raise ValueError(f"Duplicate artifact parent: {artifact_id}")
        if artifact_id in parents:
            raise ValueError(f"Artifact cannot parent itself: {artifact_id}")
        item["parentArtifactIds"] = parents
        item["metadata"] = _metadata(item.get("metadata"))

    if len(data_release_ids) != 1:
        raise ValueError("Qlib registry graph must reference exactly one DataRelease")
    if any(universe_values):
        if not all(universe_values) or len(set(universe_values)) != 1:
            raise ValueError("Qlib registry graph has inconsistent UniverseRelease binding")
    if any(source_values):
        if not all(source_values) or len(set(source_values)) != 1:
            raise ValueError("Qlib registry graph has inconsistent sourceManifestSha256 binding")

    _assert_acyclic(items)

    for item in items:
        artifact_id = str(item["artifactId"])
        requested_parents = set(item["parentArtifactIds"])
        for parent_id in requested_parents:
            if parent_id not in ids:
                exists = connection.execute(
                    "select artifact_id from artifact_registry where artifact_id=?", (parent_id,)
                ).fetchone()
                if not exists:
                    raise ValueError(f"Artifact parent does not exist: {parent_id}")

        existing = connection.execute(
            """select artifact_type,payload_sha256,data_release_id,universe_release_id,metadata_json
               from artifact_registry where artifact_id=?""",
            (artifact_id,),
        ).fetchone()
        if not existing:
            continue
        existing_metadata = _metadata(existing["metadata_json"])
        existing_identity = (
            str(existing["artifact_type"]),
            str(existing["payload_sha256"]),
            str(existing["data_release_id"]),
            str(existing["universe_release_id"] or "") or None,
            str(existing_metadata.get("sourceManifestSha256") or "") or None,
        )
        requested_identity = (
            str(item["artifactType"]),
            str(item["payloadSha256"]),
            str(item["dataReleaseId"]),
            str(item.get("universeReleaseId") or "") or None,
            _source_manifest_sha256(item),
        )
        if existing_identity != requested_identity:
            raise ValueError(f"Artifact ID already exists with different content or lineage: {artifact_id}")
        existing_parents = {
            str(row["parent_artifact_id"])
            for row in connection.execute(
                "select parent_artifact_id from artifact_lineage_edges where child_artifact_id=?",
                (artifact_id,),
            ).fetchall()
        }
        if existing_parents != requested_parents:
            raise ValueError(f"Artifact ID already exists with different parent lineage: {artifact_id}")
    return items


def register_qlib_artifacts(connection: Any, artifacts: Iterable[Mapping[str, Any]]) -> None:
    items = preflight_qlib_artifacts(connection, artifacts)
    now = utc_now()
    for item in items:
        artifact_id = str(item["artifactId"])
        existing = connection.execute(
            "select artifact_id from artifact_registry where artifact_id=?",
            (artifact_id,),
        ).fetchone()
        if existing:
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
            connection.execute(
                """insert into artifact_lineage_edges
                   (parent_artifact_id,child_artifact_id,created_at) values (?,?,?)
                   on conflict(parent_artifact_id,child_artifact_id) do update
                   set created_at=artifact_lineage_edges.created_at""",
                (parent_id, child, now),
            )


def register_platform_artifact(connection: Any, artifact: Mapping[str, Any]) -> None:
    """Register immutable platform-owned evidence for a completed LEAN validation."""
    if str(artifact.get("promotionStatus") or "") not in PLATFORM_STATUSES:
        raise ValueError("Platform artifact must use a platform-owned promotion status")
    artifact_id = str(artifact["artifactId"])
    existing = connection.execute(
        "select artifact_type,payload_sha256,data_release_id,owner from artifact_registry where artifact_id=?",
        (artifact_id,),
    ).fetchone()
    identity = (artifact["artifactType"], artifact["payloadSha256"], artifact["dataReleaseId"], "platform")
    if existing:
        actual = tuple(existing[key] for key in ("artifact_type", "payload_sha256", "data_release_id", "owner"))
        if actual != identity:
            raise ValueError(f"Artifact ID already exists with different content: {artifact_id}")
        return
    payload_ref = dict(artifact.get("payloadRef") or {})
    now = utc_now()
    connection.execute(
        """insert into artifact_registry
           (artifact_id,schema_version,artifact_type,owner,promotion_status,data_release_id,
            universe_release_id,model_release_id,strategy_policy_id,git_commit,container_digest,
            as_of_time,signal_date,trade_date,timezone,currency,payload_sha256,object_key,
            media_type,row_count,metadata_json,created_at)
           values (?,?,?,'platform',?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            artifact_id,
            artifact["schemaVersion"],
            artifact["artifactType"],
            artifact["promotionStatus"],
            artifact["dataReleaseId"],
            artifact.get("universeReleaseId"),
            artifact.get("modelReleaseId"),
            artifact.get("strategyPolicyId"),
            artifact["gitCommit"],
            artifact["containerDigest"],
            artifact["asOfTime"],
            artifact.get("signalDate"),
            artifact.get("tradeDate"),
            artifact["timezone"],
            artifact["currency"],
            artifact["payloadSha256"],
            payload_ref.get("objectKey"),
            payload_ref.get("mediaType"),
            payload_ref.get("rows"),
            json_dump(artifact.get("metadata") or {}),
            now,
        ),
    )
    connection.execute(
        """insert into artifact_promotion_events
           (id,artifact_id,from_status,to_status,owner,reason,evidence_json,created_at)
           values (?,?,null,?,'platform','lean_validation',?,?)""",
        (str(uuid.uuid4()), artifact_id, artifact["promotionStatus"], json_dump({}), now),
    )
    for parent in artifact.get("parentArtifactIds") or []:
        parent_id = str(parent)
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
            (parent_id, artifact_id, now),
        )


def promote_target_to_platform_stage(
    connection: Any,
    *,
    artifact_id: str,
    target_status: str,
    reason: str,
    evidence: Mapping[str, Any],
) -> None:
    """Advance a Qlib TargetPortfolio only through platform-owned execution stages."""
    if target_status not in {"LEAN_VALIDATED", "PAPER"}:
        raise ValueError("Unsupported platform promotion stage")
    current = connection.execute(
        "select artifact_type,owner,promotion_status from artifact_registry where artifact_id=?",
        (artifact_id,),
    ).fetchone()
    if not current:
        raise KeyError(f"TargetPortfolio artifact not found: {artifact_id}")
    if current["artifact_type"] != "TARGET_PORTFOLIO" or current["owner"] != "qlib":
        raise ValueError("Only a Qlib TARGET_PORTFOLIO can enter platform execution stages")
    expected = "RESEARCH_PROMOTED" if target_status == "LEAN_VALIDATED" else "LEAN_VALIDATED"
    if current["promotion_status"] == target_status:
        return
    if current["promotion_status"] != expected:
        raise ValueError(f"TargetPortfolio must be {expected} before {target_status}")
    now = utc_now()
    connection.execute("update artifact_registry set promotion_status=? where artifact_id=?", (target_status, artifact_id))
    connection.execute(
        """insert into artifact_promotion_events
           (id,artifact_id,from_status,to_status,owner,reason,evidence_json,created_at)
           values (?,?,?,?,?,?,?,?)""",
        (str(uuid.uuid4()), artifact_id, expected, target_status, "platform", reason, json_dump(dict(evidence)), now),
    )
