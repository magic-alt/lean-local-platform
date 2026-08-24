from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException
import hashlib
import hmac
import logging
import os
import secrets
import uuid

from .api import ashare, ashare_tech_insights, backtests, cbond, compare, data, examples, experiment_batches, factors, futures, health, help_docs, level3plus, maintenance, object_store, observability, optimization, paper_accounts, pit, portfolios, projects, reports, research, settings, strategies, tasks, universes, workflows
from .core.config import (
    API_AUTH_REQUIRED,
    API_TOKEN,
    FRONTEND_DIST,
    MAINTENANCE_READ_ONLY,
    assert_runtime_v2_environment,
)
from .core.errors import LeanWebError, error_payload, http_error_code
from .core.request_context import reset_request_context, set_request_context
from .db import DatabaseUnavailableError, init_db
from .services.projects import consolidate_automatic_copies
from .services.workflows import record_workflow_event
from .services import api_idempotency
from .services.backtest_trust import reconcile_backtest_trust
from .observability.metrics import metrics_middleware


class SPAStaticFiles(StaticFiles):
    async def get_response(self, path: str, scope):
        try:
            return await super().get_response(path, scope)
        except StarletteHTTPException as exc:
            if exc.status_code == 404 and not path.startswith("api/"):
                return await super().get_response("index.html", scope)
            raise


app = FastAPI(title="Local LEAN Web Platform", redirect_slashes=False)
app.middleware("http")(metrics_middleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
logger = logging.getLogger(__name__)
_BROWSER_SESSION_COOKIE = "lean_local_session"
_MUTATING_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


def _browser_session_token() -> str:
    if not API_TOKEN:
        return ""
    return hmac.new(
        API_TOKEN.encode("utf-8"),
        b"lean-local-browser-session-v1",
        hashlib.sha256,
    ).hexdigest()


@app.middleware("http")
async def idempotency_middleware(request: Request, call_next):
    if request.method not in {"POST", "PUT", "PATCH", "DELETE"} or not request.url.path.startswith("/api/"):
        return await call_next(request)
    key = request.headers.get("Idempotency-Key", "").strip()
    if not key:
        return await call_next(request)
    if len(key) > 255 or any(character.isspace() for character in key):
        return JSONResponse(
            status_code=400,
            content=error_payload(
                "Idempotency-Key must be at most 255 non-whitespace characters.",
                error_code="INVALID_IDEMPOTENCY_KEY",
                category="validation",
                details={"field": "Idempotency-Key"},
                trace_id=getattr(request.state, "trace_id", None),
                workflow_id=getattr(request.state, "workflow_id", None),
            ),
        )
    body = await request.body()
    digest = api_idempotency.request_digest(body, request.url.query)
    record = api_idempotency.begin(
        key=key,
        method=request.method,
        path=request.url.path,
        digest=digest,
        trace_id=getattr(request.state, "trace_id", None),
    )


    if record.state == "conflict":
        return JSONResponse(
            status_code=409,
            content=error_payload(
                "Idempotency-Key was reused with a different request payload.",
                error_code="IDEMPOTENCY_KEY_CONFLICT",
                category="state",
                details={"field": "Idempotency-Key"},
                trace_id=getattr(request.state, "trace_id", None),
                workflow_id=getattr(request.state, "workflow_id", None),
            ),
        )
    if record.state == "pending":
        return JSONResponse(
            status_code=409,
            content=error_payload(
                "A request with this Idempotency-Key is still in progress.",
                error_code="IDEMPOTENCY_REQUEST_IN_PROGRESS",
                category="state",
                retryable=True,
                details={"field": "Idempotency-Key"},
                trace_id=getattr(request.state, "trace_id", None),
                workflow_id=getattr(request.state, "workflow_id", None),
            ),
            headers={"Retry-After": "1"},
        )
    if record.state == "replay":
        return Response(
            content=record.response_body or "",
            status_code=record.response_status or 200,
            media_type=record.response_content_type or "application/json",
            headers={"Idempotent-Replayed": "true"},
        )
    try:
        response = await call_next(request)
    except Exception:
        api_idempotency.abandon(key=key, method=request.method, path=request.url.path)
        raise
    content_type = str(response.headers.get("content-type") or "")
    if response.status_code >= 500 or not content_type.startswith("application/json"):
        api_idempotency.abandon(key=key, method=request.method, path=request.url.path)
        return response
    response_body = b"".join([chunk async for chunk in response.body_iterator])
    api_idempotency.complete(
        key=key,
        method=request.method,
        path=request.url.path,
        response_status=response.status_code,
        response_body=response_body.decode("utf-8"),
        response_content_type=content_type,
    )
    headers = dict(response.headers)
    headers["Idempotency-Key"] = key
    return Response(
        content=response_body,
        status_code=response.status_code,
        headers=headers,
        background=response.background,
    )


@app.middleware("http")
async def maintenance_read_only_middleware(request: Request, call_next):
    """Fail closed for writes while an operator rebuilds market data.

    This intentionally does not allow route-level exceptions: queued work and
    ad-hoc writes would otherwise race the destructive maintenance command.
    """
    if (
        MAINTENANCE_READ_ONLY
        and request.method in _MUTATING_METHODS
        and request.url.path.startswith("/api/")
        and not request.url.path.startswith("/api/health")
    ):
        return JSONResponse(
            status_code=503,
            content={
                "detail": "The API is read-only during scheduled database maintenance.",
                "error_code": "MAINTENANCE_READ_ONLY",
            },
            headers={"Retry-After": "60"},
        )
    return await call_next(request)


@app.middleware("http")
async def api_auth_middleware(request: Request, call_next):
    path = request.url.path
    is_protected = path.startswith("/api/") or path in {
        "/metrics",
        "/openapi.json",
        "/docs",
        "/redoc",
    }
    if not is_protected:
        response = await call_next(request)
        if (
            API_AUTH_REQUIRED
            and API_TOKEN
            and request.method == "GET"
            and str(response.headers.get("content-type") or "").startswith("text/html")
        ):
            # The built frontend can be served directly by FastAPI without
            # exposing the operator bearer token to JavaScript. SameSite=Strict
            # keeps the derived session credential out of cross-site requests.
            response.set_cookie(
                _BROWSER_SESSION_COOKIE,
                _browser_session_token(),
                httponly=True,
                samesite="strict",
                secure=False,
                path="/",
            )
        return response
    if (
        not API_AUTH_REQUIRED
        or request.method == "OPTIONS"
        or path.startswith("/api/health")
    ):
        return await call_next(request)
    if not API_TOKEN:
        return JSONResponse(
            status_code=503,
            content={
                "detail": "API authentication is required but LEAN_API_TOKEN is not configured.",
                "error_code": "API_AUTH_NOT_CONFIGURED",
            },
        )
    authorization = request.headers.get("Authorization", "")
    bearer = authorization[7:].strip() if authorization.lower().startswith("bearer ") else ""
    supplied = bearer or request.headers.get("X-LEAN-API-Key", "")
    browser_session = request.cookies.get(_BROWSER_SESSION_COOKIE, "")
    bearer_valid = bool(supplied) and secrets.compare_digest(supplied, API_TOKEN)
    session_token = _browser_session_token()
    session_valid = bool(browser_session and session_token) and secrets.compare_digest(browser_session, session_token)
    if not bearer_valid and not session_valid:
        return JSONResponse(
            status_code=401,
            content={"detail": "Valid API credentials are required.", "error_code": "UNAUTHORIZED"},
            headers={"WWW-Authenticate": "Bearer"},
        )
    return await call_next(request)


@app.middleware("http")
async def trace_workflow_middleware(request: Request, call_next):
    trace_id = request.headers.get("X-Trace-ID") or str(uuid.uuid4())
    workflow_id = request.headers.get("X-Workflow-ID") or trace_id
    request.state.trace_id = trace_id
    request.state.workflow_id = workflow_id
    context_tokens = set_request_context(trace_id, workflow_id)
    try:
        response = await call_next(request)
    finally:
        reset_request_context(context_tokens)
    response.headers["X-Trace-ID"] = trace_id
    response.headers["X-Workflow-ID"] = workflow_id
    if (
        response.status_code >= 400
        and request.url.path.startswith("/api/")
        and not getattr(request.state, "database_unavailable", False)
    ):
        try:
            record_workflow_event(
                workflow_id=workflow_id,
                trace_id=trace_id,
                stage=request.url.path.split("/", 3)[2],
                action=request.method.lower(),
                status="failed",
                error_code=f"HTTP_{response.status_code}",
                message=f"{request.method} {request.url.path}",
                details={"path": request.url.path, "status_code": response.status_code},
            )
        except Exception:
            logger.exception("Unable to persist workflow failure event")
    return response


@app.on_event("startup")
def startup() -> None:
    if os.environ.get("LEAN_STRICT_RUNTIME_V2", "0").lower() in {"1", "true", "yes", "on"}:
        assert_runtime_v2_environment()
    try:
        init_db()
        trust = reconcile_backtest_trust()
        if trust["count"]:
            logger.info("Backtest trust reconciliation: %s", trust["counts"])
        consolidation = consolidate_automatic_copies()
        if consolidation["merged"] or consolidation["renamed"]:
            logger.info("Project copy consolidation: %s", consolidation)
    except Exception as exc:
        logger.warning("Database initialization failed at startup; continuing in degraded mode: %s", exc)


@app.exception_handler(LeanWebError)
async def lean_web_error_handler(request: Request, exc: LeanWebError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content=error_payload(
            str(exc),
            error_code=exc.error_code,
            category=exc.category,
            retryable=exc.retryable,
            details=exc.details,
            trace_id=getattr(request.state, "trace_id", None),
            workflow_id=getattr(request.state, "workflow_id", None),
        ),
    )


@app.exception_handler(DatabaseUnavailableError)
async def database_unavailable_handler(request: Request, exc: DatabaseUnavailableError) -> JSONResponse:
    request.state.database_unavailable = True
    return JSONResponse(
        status_code=503,
        content=error_payload(
            str(exc),
            error_code="DATABASE_UNAVAILABLE",
            category="infrastructure",
            retryable=True,
            details={"retryAfterSeconds": 10},
            trace_id=getattr(request.state, "trace_id", None),
            workflow_id=getattr(request.state, "workflow_id", None),
        ),
        headers={"Retry-After": "10"},
    )


@app.exception_handler(StarletteHTTPException)
async def http_error_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    embedded = exc.detail if isinstance(exc.detail, dict) else None
    message = (
        str(embedded.get("message") or embedded.get("detail") or "HTTP request failed.")
        if embedded is not None
        else str(exc.detail)
    )
    default_code, default_category, default_retryable = http_error_code(exc.status_code)
    code = str(embedded.get("code") or embedded.get("error_code") or default_code) if embedded else default_code
    category = str(embedded.get("category") or default_category) if embedded else default_category
    retryable = bool(embedded.get("retryable", default_retryable)) if embedded else default_retryable
    return JSONResponse(
        status_code=exc.status_code,
        content=error_payload(
            message,
            error_code=code,
            category=category,
            retryable=retryable,
            details=embedded,
            trace_id=getattr(request.state, "trace_id", None),
            workflow_id=getattr(request.state, "workflow_id", None),
        ),
    )


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content=error_payload(
            "Request validation failed.",
            error_code="VALIDATION_ERROR",
            category="validation",
            retryable=False,
            details=exc.errors(),
            trace_id=getattr(request.state, "trace_id", None),
            workflow_id=getattr(request.state, "workflow_id", None),
        ),
    )


app.include_router(health.router)
app.include_router(observability.router)
app.include_router(universes.router)
app.include_router(level3plus.router)
app.include_router(settings.router)
app.include_router(strategies.router)
app.include_router(examples.router)
app.include_router(help_docs.router)
app.include_router(projects.router)
app.include_router(data.router)
app.include_router(ashare.router)
app.include_router(pit.router)
app.include_router(factors.router)
app.include_router(cbond.router)
app.include_router(futures.router)
app.include_router(tasks.router)
app.include_router(backtests.router)
app.include_router(experiment_batches.router)
app.include_router(optimization.router)
app.include_router(portfolios.router)
app.include_router(compare.router)
app.include_router(paper_accounts.router)
app.include_router(research.router)
app.include_router(reports.router)
app.include_router(ashare_tech_insights.router)
app.include_router(ashare_tech_insights.legacy_router)
app.include_router(object_store.router)
app.include_router(maintenance.router)
app.include_router(workflows.router)

if FRONTEND_DIST.exists():
    app.mount("/", SPAStaticFiles(directory=FRONTEND_DIST, html=True), name="frontend")
