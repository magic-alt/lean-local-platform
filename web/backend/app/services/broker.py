from __future__ import annotations

from typing import Any, Iterable

from kombu import Connection

from ..core.config import CELERY_BROKER_URL


CELERY_QUEUES = (
    "default",
    "data-bulk",
    "data-lineage",
    "data-demand",
    "backtest",
    "ml",
)


def check_broker() -> dict[str, Any]:
    with Connection(CELERY_BROKER_URL, connect_timeout=2) as connection:
        connection.ensure_connection(max_retries=1)
    return {
        "service": "broker",
        "engine": "rabbitmq",
        "ok": True,
        "detail": "configured AMQP endpoint",
    }


def queue_depths(queue_names: Iterable[str] = CELERY_QUEUES) -> dict[str, int]:
    """Read ready-message counts through AMQP passive declarations."""

    depths: dict[str, int] = {}
    with Connection(CELERY_BROKER_URL, connect_timeout=2) as connection:
        connection.ensure_connection(max_retries=1)
        channel = connection.channel()
        try:
            for name in queue_names:
                result = channel.queue_declare(queue=name, passive=True)
                depths[name] = int(
                    getattr(result, "message_count", result[1] if len(result) > 1 else 0)
                )
        finally:
            channel.close()
    return depths
