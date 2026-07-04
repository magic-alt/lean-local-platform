import os
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[2]
WEB_DIR = BACKEND_DIR.parent
PLATFORM_DIR = WEB_DIR.parent
WORKSPACE_ROOT = PLATFORM_DIR.parent
REPO_ROOT = WORKSPACE_ROOT


def _load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].strip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not key:
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        os.environ.setdefault(key, value)


for _env_file in (PLATFORM_DIR / ".env", BACKEND_DIR / ".env"):
    _load_env_file(_env_file)


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
JOB_TIMEOUT_SECONDS = int(os.environ.get("BACKTEST_JOB_TIMEOUT_SECONDS", "7200"))
MAX_CONCURRENT_JOBS = int(os.environ.get("BACKTEST_MAX_CONCURRENT_JOBS", "1"))
LOG_LEVEL = os.environ.get("LEAN_WEB_LOG_LEVEL", "INFO")

CLICKHOUSE_ENABLED = os.environ.get("CLICKHOUSE_ENABLED", "1").lower() not in {"0", "false", "no", "off"}
CLICKHOUSE_HOST = os.environ.get("CLICKHOUSE_HOST", "127.0.0.1")
CLICKHOUSE_PORT = int(os.environ.get("CLICKHOUSE_PORT", "8123"))
CLICKHOUSE_USERNAME = os.environ.get("CLICKHOUSE_USERNAME", "lean")
CLICKHOUSE_PASSWORD = os.environ.get("CLICKHOUSE_PASSWORD", "lean")
CLICKHOUSE_DATABASE = os.environ.get("CLICKHOUSE_DATABASE", "lean_market")

PROMETHEUS_URL = os.environ.get("PROMETHEUS_URL", "http://127.0.0.1:9090")
GRAFANA_URL = os.environ.get("GRAFANA_URL", "http://127.0.0.1:3000")
TUSHARE_TOKEN = os.environ.get("TUSHARE_TOKEN", "")
