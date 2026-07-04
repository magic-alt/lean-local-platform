import os
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[2]
WEB_DIR = BACKEND_DIR.parent
PLATFORM_DIR = WEB_DIR.parent
WORKSPACE_ROOT = PLATFORM_DIR.parent
REPO_ROOT = WORKSPACE_ROOT

DATA_DIR = Path(os.environ.get("LEAN_DATA_DIR", WORKSPACE_ROOT / "Data")).expanduser()
ALGORITHM_PATH = PLATFORM_DIR / "DockerDemoAlgorithm.py"
PLOT_SCRIPT = PLATFORM_DIR / "plot_results.py"
FRONTEND_DIST = WEB_DIR / "frontend" / "dist"

RUNTIME_DIR = WEB_DIR / "runtime"
RUNS_DIR = RUNTIME_DIR / "runs"
UPLOADS_DIR = RUNTIME_DIR / "uploads"
PROJECTS_DIR = RUNTIME_DIR / "projects"
RESEARCH_DIR = RUNTIME_DIR / "research"
OBJECT_STORE_DIR = RUNTIME_DIR / "object-store"
REPORTS_DIR = RUNTIME_DIR / "reports"
DB_PATH = RUNTIME_DIR / "lean_web.sqlite3"

DEFAULT_DOCKER_IMAGE = os.environ.get("LEAN_DOCKER_IMAGE", "quantconnect/lean:latest")
DEFAULT_RESEARCH_IMAGE = os.environ.get("LEAN_RESEARCH_IMAGE", "quantconnect/research:latest")
REDIS_URL = os.environ.get("REDIS_URL", "redis://127.0.0.1:6379/0")

CLICKHOUSE_ENABLED = os.environ.get("CLICKHOUSE_ENABLED", "1").lower() not in {"0", "false", "no", "off"}
CLICKHOUSE_HOST = os.environ.get("CLICKHOUSE_HOST", "127.0.0.1")
CLICKHOUSE_PORT = int(os.environ.get("CLICKHOUSE_PORT", "8123"))
CLICKHOUSE_USERNAME = os.environ.get("CLICKHOUSE_USERNAME", "lean")
CLICKHOUSE_PASSWORD = os.environ.get("CLICKHOUSE_PASSWORD", "lean")
CLICKHOUSE_DATABASE = os.environ.get("CLICKHOUSE_DATABASE", "lean_market")

PROMETHEUS_URL = os.environ.get("PROMETHEUS_URL", "http://127.0.0.1:9090")
GRAFANA_URL = os.environ.get("GRAFANA_URL", "http://127.0.0.1:3000")
