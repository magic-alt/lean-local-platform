from __future__ import annotations

from contextvars import ContextVar, Token


_trace_id: ContextVar[str | None] = ContextVar("lean_trace_id", default=None)
_workflow_id: ContextVar[str | None] = ContextVar("lean_workflow_id", default=None)


def current_trace_id() -> str | None:
    return _trace_id.get()


def current_workflow_id() -> str | None:
    return _workflow_id.get()


def set_request_context(trace_id: str | None, workflow_id: str | None) -> tuple[Token, Token]:
    return _trace_id.set(trace_id), _workflow_id.set(workflow_id)


def reset_request_context(tokens: tuple[Token, Token]) -> None:
    trace_token, workflow_token = tokens
    _trace_id.reset(trace_token)
    _workflow_id.reset(workflow_token)
