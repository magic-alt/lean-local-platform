from __future__ import annotations

import gzip
import json
import os
import uuid
from typing import Any

from ..db import db, row_to_dict, utc_now
from .db_object_store import read_bytes
from .tushare_typed_source import persist_typed_source_rows


LINEAGE_JOB_NAMESPACE = uuid.UUID("4758622c-150f-45ad-a47b-71b0a1ce494c")


def async_lineage_enabled() -> bool:
    return os.environ.get("LEAN_TUSHARE_LINEAGE_ASYNC", "0").lower() in {
        "1", "true", "yes", "on",
    }


def enqueue_lineage_job(
    *,
    run_id: str,
    dataset_key: str,
    object_id: str,
    row_count: int,
) -> dict[str, Any]:
    job_id = str(uuid.uuid5(LINEAGE_JOB_NAMESPACE, f"{run_id}:{dataset_key}:{object_id}"))
    now = utc_now()
    with db() as connection:
        connection.execute(
            """
            insert into data_sync_lineage_jobs
                (id,run_id,dataset_key,object_id,row_count,status,attempts,created_at)
            values (?,?,?,?,?,'pending',0,?)
            on conflict(run_id,dataset_key,object_id) do update set
                row_count=excluded.row_count,
                status=case when data_sync_lineage_jobs.status='success'
                            then data_sync_lineage_jobs.status else 'pending' end,
                error=case when data_sync_lineage_jobs.status='success'
                           then data_sync_lineage_jobs.error else null end
            """,
            (job_id, run_id, dataset_key, object_id, max(0, int(row_count)), now),
        )
    try:
        from ..tasks.celery_app import celery_app

        celery_app.send_task(
            "lean_web.persist_tushare_lineage",
            args=[job_id],
            queue="data-lineage",
        )
    except Exception:
        # The durable pending row is recovered by the periodic reconciler.
        pass
    return {"jobId": job_id, "status": "pending"}


def process_lineage_job(job_id: str) -> dict[str, Any]:
    now = utc_now()
    with db() as connection:
        row = connection.execute(
            "select * from data_sync_lineage_jobs where id=?",
            (job_id,),
        ).fetchone()
        job = row_to_dict(row)
        if not job:
            raise ValueError(f"Unknown TuShare lineage job: {job_id}")
        if job.get("status") == "success":
            return job
        connection.execute(
            """
            update data_sync_lineage_jobs
            set status='running',attempts=attempts+1,started_at=?,finished_at=null,error=null
            where id=?
            """,
            (now, job_id),
        )
    try:
        compressed = read_bytes(str(job["object_id"]))
        payload = json.loads(gzip.decompress(compressed).decode("utf-8"))
        if not isinstance(payload, list):
            raise ValueError("TuShare lineage archive must contain a JSON row array.")
        expected = int(job.get("row_count") or 0)
        if expected != len(payload):
            raise ValueError(f"TuShare lineage row mismatch: expected={expected} actual={len(payload)}")
        result = persist_typed_source_rows(
            str(job["dataset_key"]),
            [dict(item) for item in payload],
            str(job["run_id"]),
        )
    except Exception as exc:
        with db() as connection:
            connection.execute(
                "update data_sync_lineage_jobs set status='failed',error=?,finished_at=? where id=?",
                (str(exc)[:4000], utc_now(), job_id),
            )
        raise
    with db() as connection:
        connection.execute(
            "update data_sync_lineage_jobs set status='success',error=null,finished_at=? where id=?",
            (utc_now(), job_id),
        )
    return {"jobId": job_id, "status": "success", "typedSource": result}


def recover_lineage_jobs(limit: int = 100) -> list[str]:
    with db() as connection:
        rows = connection.execute(
            """
            select id from data_sync_lineage_jobs
            where status in ('pending','failed') and attempts<8
            order by created_at limit ?
            """,
            (max(1, min(int(limit), 1000)),),
        ).fetchall()
    return [str(row["id"]) for row in rows]


def lineage_metrics(run_id: str, dataset_key: str) -> dict[str, Any]:
    with db() as connection:
        rows = connection.execute(
            """
            select status,count(*) as batches,coalesce(sum(row_count),0) as rows
            from data_sync_lineage_jobs where run_id=? and dataset_key=? group by status
            """,
            (run_id, dataset_key),
        ).fetchall()
    counts = {str(row["status"]): {"batches": int(row["batches"]), "rows": int(row["rows"])} for row in rows}
    failed = counts.get("failed", {"batches": 0, "rows": 0})
    pending_batches = sum(counts.get(key, {}).get("batches", 0) for key in ("pending", "running"))
    pending_rows = sum(counts.get(key, {}).get("rows", 0) for key in ("pending", "running"))
    status = "failed" if failed["batches"] else "pending" if pending_batches else "success"
    return {
        "lineageStatus": status,
        "lineagePendingBatches": pending_batches,
        "lineagePendingRows": pending_rows,
        "lineageFailedBatches": failed["batches"],
    }
