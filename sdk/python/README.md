# LEAN Local Platform Python SDK

This lightweight client exposes the integrated workflow read/command contract without duplicating platform business logic.

```python
from lean_local_platform import WorkflowClient

client = WorkflowClient("http://127.0.0.1:8000", token="...")
status = client.status("<qlib-import-id>")
plan = client.plan("<qlib-import-id>")
```

`resume()` sends an `Idempotency-Key`, but the API response is only a safe owner/next-action decision. Canonical LEAN/Paper transitions remain on the platform's existing services and writers.
