from __future__ import annotations

from typing import Any


class LeanWebError(Exception):
    """Expected application error suitable for structured API responses."""

    status_code = 400
    error_code = "LEAN_WEB_ERROR"
    category = "application"
    retryable = False

    def __init__(
        self,
        message: str | None = None,
        *,
        error_code: str | None = None,
        category: str | None = None,
        retryable: bool | None = None,
        status_code: int | None = None,
        details: Any | None = None,
    ) -> None:
        super().__init__(message or self.error_code)
        if error_code is not None:
            self.error_code = error_code
        if category is not None:
            self.category = category
        if retryable is not None:
            self.retryable = retryable
        if status_code is not None:
            self.status_code = status_code
        self.details = details


class NotFoundError(LeanWebError):
    """Requested local resource does not exist."""

    status_code = 404
    error_code = "NOT_FOUND"
    category = "not_found"


def error_payload(
    message: str,
    *,
    error_code: str,
    category: str,
    retryable: bool = False,
    details: Any | None = None,
    trace_id: str | None = None,
    workflow_id: str | None = None,
) -> dict[str, Any]:
    payload = {
        "detail": message,
        "message": message,
        "error_code": error_code,
        "category": category,
        "retryable": retryable,
    }
    if details is not None:
        payload["details"] = details
    if trace_id:
        payload["trace_id"] = trace_id
    if workflow_id:
        payload["workflow_id"] = workflow_id
    return payload


def http_error_code(status_code: int) -> tuple[str, str, bool]:
    if status_code == 400:
        return ("BAD_REQUEST", "validation", False)
    if status_code == 401:
        return ("UNAUTHORIZED", "auth", False)
    if status_code == 403:
        return ("FORBIDDEN", "auth", False)
    if status_code == 404:
        return ("NOT_FOUND", "not_found", False)
    if status_code == 409:
        return ("CONFLICT", "state", False)
    if status_code == 422:
        return ("VALIDATION_ERROR", "validation", False)
    if status_code == 429:
        return ("RATE_LIMITED", "rate_limit", True)
    if status_code == 503:
        return ("SERVICE_UNAVAILABLE", "infrastructure", True)
    if status_code >= 500:
        return ("INTERNAL_ERROR", "internal", True)
    return ("HTTP_ERROR", "http", False)
