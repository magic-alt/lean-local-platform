from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from .api import backtests, capabilities, data, health, object_store, optimization, projects, reports, research, tasks, universes
from .core.config import FRONTEND_DIST
from .db import init_db


class SPAStaticFiles(StaticFiles):
    async def get_response(self, path: str, scope):
        try:
            return await super().get_response(path, scope)
        except StarletteHTTPException as exc:
            if exc.status_code == 404:
                return await super().get_response("index.html", scope)
            raise


app = FastAPI(title="Local LEAN Web Platform")
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


app.include_router(health.router)
app.include_router(capabilities.router)
app.include_router(universes.router)
app.include_router(projects.router)
app.include_router(data.router)
app.include_router(tasks.router)
app.include_router(backtests.router)
app.include_router(optimization.router)
app.include_router(research.router)
app.include_router(reports.router)
app.include_router(object_store.router)

if FRONTEND_DIST.exists():
    app.mount("/", SPAStaticFiles(directory=FRONTEND_DIST, html=True), name="frontend")
