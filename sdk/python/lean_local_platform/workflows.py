from __future__ import annotations

import json
import uuid
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen


class WorkflowClientError(RuntimeError):
    def __init__(self, message: str, *, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


class WorkflowClient:
    """Thin HTTP client; all workflow semantics remain server-owned."""

    def __init__(self, base_url: str, *, token: str | None = None, timeout: float = 10.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.token = token or ""
        self.timeout = float(timeout)

    def _request(
        self,
        path: str,
        *,
        method: str = "GET",
        operation_id: str | None = None,
    ) -> dict[str, Any]:
        headers = {"Accept": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        if method != "GET":
            headers["Idempotency-Key"] = operation_id or str(uuid.uuid4())
        request = Request(f"{self.base_url}{path}", method=method, headers=headers)
        try:
            with urlopen(request, timeout=self.timeout) as response:
                raw = response.read()
        except HTTPError as exc:
            detail = exc.reason
            try:
                payload = json.loads(exc.read().decode("utf-8"))
                detail = payload.get("detail") or payload.get("error_code") or detail
            except (ValueError, UnicodeDecodeError):
                pass
            raise WorkflowClientError(str(detail), status=exc.code) from exc
        except URLError as exc:
            raise WorkflowClientError(f"workflow_api_unavailable:{exc.reason}") from exc
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError) as exc:
            raise WorkflowClientError("workflow_api_invalid_json") from exc
        if not isinstance(payload, dict):
            raise WorkflowClientError("workflow_api_response_not_object")
        return payload

    def status(self, import_id: str) -> dict[str, Any]:
        return self._request(f"/api/integrated-workflows/{quote(import_id, safe='')}/status")

    def plan(self, import_id: str) -> dict[str, Any]:
        return self._request(f"/api/integrated-workflows/{quote(import_id, safe='')}/plan")

    def explain(self, import_id: str) -> dict[str, Any]:
        return self._request(f"/api/integrated-workflows/{quote(import_id, safe='')}/explain")

    def compare(self, left_import_id: str, right_import_id: str) -> dict[str, Any]:
        query = urlencode({"left": left_import_id, "right": right_import_id})
        return self._request(f"/api/integrated-workflows/compare?{query}")

    def resume(self, import_id: str, *, operation_id: str | None = None) -> dict[str, Any]:
        return self._request(
            f"/api/integrated-workflows/{quote(import_id, safe='')}/resume",
            method="POST",
            operation_id=operation_id,
        )
