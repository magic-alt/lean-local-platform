from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException
import logging
import uuid

from .api import ashare, ashare_tech_insights, backtests, cbond, compare, data, examples, experiment_batches, factors, futures, health, help_docs, insights, level3plus, maintenance, object_store, observability, optimization, paper, pit, portfolios, projects, reports, research, settings, strategies, tasks, universes, workflows
from .core.config import FRONTEND_DIST
from .core.errors import LeanWebError, error_payload, http_error_code
from .db import init_db
from .services.projects import consolidate_automatic_copies
from .services.workflows import record_workflow_event
from .observability.metrics import metrics_middleware


class SPAStaticFiles(StaticFiles):
    async def get_response(self, path: str, scope):
        try:
            return await super().get_response(path, scope)
        except StarletteHTTPException as exc:
            if exc.status_code == 404 and not path.startswith("api/"):
                return await super().get_response("index.html", scope)
            raise


app = FastAPI(title="Local LEAN Web Platform")
app.middleware("http")(metrics_middleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
logger = logging.getLogger(__name__)


@app.middleware("http")
async def trace_workflow_middleware(request: Request, call_next):
    trace_id = request.headers.get("X-Trace-ID") or str(uuid.uuid4())
    workflow_id = request.headers.get("X-Workflow-ID") or trace_id
    request.state.trace_id = trace_id
    request.state.workflow_id = workflow_id
    response = await call_next(request)
    response.headers["X-Trace-ID"] = trace_id
    response.headers["X-Workflow-ID"] = workflow_id
    if response.status_code >= 400 and request.url.path.startswith("/api/"):
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
    try:
        init_db()
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


@app.exception_handler(StarletteHTTPException)
async def http_error_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    message = exc.detail if isinstance(exc.detail, str) else "HTTP request failed."
    code, category, retryable = http_error_code(exc.status_code)
    return JSONResponse(
        status_code=exc.status_code,
        content=error_payload(
            message,
            error_code=code,
            category=category,
            retryable=retryable,
            details=None if isinstance(exc.detail, str) else exc.detail,
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
app.include_router(paper.router)
app.include_router(research.router)
app.include_router(reports.router)
app.include_router(ashare_tech_insights.router)
app.include_router(ashare_tech_insights.legacy_router)
app.include_router(insights.router)
app.include_router(object_store.router)
app.include_router(maintenance.router)
app.include_router(workflows.router)

if FRONTEND_DIST.exists():
    app.mount("/", SPAStaticFiles(directory=FRONTEND_DIST, html=True), name="frontend")
