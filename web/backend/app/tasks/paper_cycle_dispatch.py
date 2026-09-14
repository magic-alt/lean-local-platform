from __future__ import annotations

import os

from .celery_app import celery_app
from ..services import paper_cycle_dispatch


# Loaded before app.tasks.worker so its task uses the guarded begin_cycle path.
paper_cycle_dispatch.install_worker_guard()


@celery_app.task(name="lean_web.recover_stale_paper_cycle_dispatches")
def recover_stale_paper_cycle_dispatches_task(
    stale_seconds: int | None = None,
) -> dict:
    configured = int(
        stale_seconds
        if stale_seconds is not None
        else os.environ.get("LEAN_PAPER_DISPATCH_STALE_SECONDS", "120")
    )

    def publish(cycle_id: str):
        return celery_app.send_task(
            "lean_web.run_paper_execution_cycle",
            args=[cycle_id],
            queue="default",
        )

    return paper_cycle_dispatch.recover_stale_queued_dispatches(
        publish,
        stale_seconds=max(0, configured),
    )
