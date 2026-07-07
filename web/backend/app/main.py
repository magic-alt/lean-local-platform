from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from .api import ashare, backtests, cbond, compare, data, factors, futures, health, object_store, observability, optimization, paper, pit, projects, reports, research, settings, strategies, tasks, universes
from .core.config import FRONTEND_DIST
from .core.errors import LeanWebError, error_payload, http_error_code
from .db import init_db
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


@app.on_event("startup")
def startup() -> None:
    init_db()


@app.exception_handler(LeanWebError)
async def lean_web_error_handler(_request: Request, exc: LeanWebError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content=error_payload(
            str(exc),
            error_code=exc.error_code,
            category=exc.category,
            retryable=exc.retryable,
        ),
    )


@app.exception_handler(StarletteHTTPException)
async def http_error_handler(_request: Request, exc: StarletteHTTPException) -> JSONResponse:
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
        ),
    )


@app.exception_handler(RequestValidationError)
async def validation_error_handler(_request: Request, exc: RequestValidationError) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content=error_payload(
            "Request validation failed.",
            error_code="VALIDATION_ERROR",
            category="validation",
            retryable=False,
            details=exc.errors(),
        ),
    )


app.include_router(health.router)
app.include_router(observability.router)
app.include_router(universes.router)
app.include_router(settings.router)
app.include_router(strategies.router)
app.include_router(projects.router)
app.include_router(data.router)
app.include_router(ashare.router)
app.include_router(pit.router)
app.include_router(factors.router)
app.include_router(cbond.router)
app.include_router(futures.router)
app.include_router(tasks.router)
app.include_router(backtests.router)
app.include_router(optimization.router)
app.include_router(compare.router)
app.include_router(paper.router)
app.include_router(research.router)
app.include_router(reports.router)
app.include_router(object_store.router)

if FRONTEND_DIST.exists():
    app.mount("/", SPAStaticFiles(directory=FRONTEND_DIST, html=True), name="frontend")
