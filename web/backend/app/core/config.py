import os
from collections.abc import Mapping
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[2]
WEB_DIR = BACKEND_DIR.parent
PLATFORM_DIR = WEB_DIR.parent
WORKSPACE_ROOT = PLATFORM_DIR.parent
REPO_ROOT = WORKSPACE_ROOT
GIT_ROOT = Path(os.environ.get("LEAN_GIT_ROOT", PLATFORM_DIR)).expanduser().resolve()
HOST_PLATFORM_DIR = Path(os.environ.get("LEAN_HOST_PLATFORM_DIR", PLATFORM_DIR)).expanduser().resolve()


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
HOST_DATA_DIR = Path(os.environ.get("LEAN_HOST_DATA_DIR", DATA_DIR)).expanduser().resolve()
FRONTEND_DIST = WEB_DIR / "frontend" / "dist"

RUNTIME_DIR = WEB_DIR / "runtime"
RUNS_DIR = RUNTIME_DIR / "runs"
UPLOADS_DIR = RUNTIME_DIR / "uploads"
PROJECTS_DIR = RUNTIME_DIR / "projects"
RESEARCH_DIR = RUNTIME_DIR / "research"
OBJECT_STORE_DIR = RUNTIME_DIR / "object-store"
REPORTS_DIR = RUNTIME_DIR / "reports"
PARQUET_DIR = Path(os.environ.get("LEAN_PARQUET_DIR", DATA_DIR / "parquet")).expanduser()
HOST_PARQUET_DIR = Path(os.environ.get("LEAN_HOST_PARQUET_DIR", PARQUET_DIR)).expanduser().resolve()
PARQUET_COMPRESSION = os.environ.get("LEAN_PARQUET_COMPRESSION", "zstd")
PARQUET_PARTITION_ROWS = max(50_000, int(os.environ.get("LEAN_PARQUET_PARTITION_ROWS", "100000")))
MYSQL_HOST = os.environ.get("LEAN_MYSQL_HOST", "127.0.0.1")
MYSQL_PORT = int(os.environ.get("LEAN_MYSQL_PORT", "3306"))
MYSQL_DATABASE = os.environ.get("LEAN_MYSQL_DATABASE", "lean_market")
MYSQL_USER = os.environ.get("LEAN_MYSQL_USER", "lean")
MYSQL_PASSWORD = os.environ.get("LEAN_MYSQL_PASSWORD", "lean")
DEFAULT_MYSQL_DATABASE_URL = (
    f"mysql+pymysql://{MYSQL_USER}:{MYSQL_PASSWORD}@{MYSQL_HOST}:{MYSQL_PORT}/{MYSQL_DATABASE}"
)
DATABASE_URL = os.environ.get("LEAN_DATABASE_URL") or os.environ.get("DATABASE_URL") or DEFAULT_MYSQL_DATABASE_URL
DB_OBJECT_CHUNK_BYTES = int(os.environ.get("LEAN_DB_OBJECT_CHUNK_BYTES", str(1024 * 1024)))
DB_OBJECT_STORE_ENABLED = os.environ.get("LEAN_DB_OBJECT_STORE_ENABLED", "1").lower() not in {"0", "false", "no", "off"}

DEFAULT_DOCKER_IMAGE = os.environ.get(
    "LEAN_DOCKER_IMAGE",
    "quantconnect/lean@sha256:19e3633d2da1e8b378dd6af4b999b0ca6cf0660a1bf557a0518a2e43fc270823",
)
DEFAULT_RESEARCH_IMAGE = os.environ.get(
    "LEAN_RESEARCH_IMAGE",
    "quantconnect/research@sha256:1548cafe8d696c1a30774413fc6f7c0d7f0205104f2f78110d9a84906ac65634",
)
ALLOWED_LEAN_DOCKER_IMAGES = tuple(
    dict.fromkeys(
        [
            DEFAULT_DOCKER_IMAGE,
            *[
                item.strip()
                for item in os.environ.get("LEAN_ALLOWED_DOCKER_IMAGES", "").split(",")
                if item.strip()
            ],
        ]
    )
)
ALLOWED_RESEARCH_DOCKER_IMAGES = tuple(
    dict.fromkeys(
        [
            DEFAULT_RESEARCH_IMAGE,
            *[
                item.strip()
                for item in os.environ.get("LEAN_ALLOWED_RESEARCH_IMAGES", "").split(",")
                if item.strip()
            ],
        ]
    )
)
LEAN_DOCKER_NETWORK = os.environ.get("LEAN_DOCKER_NETWORK", "none").strip() or "none"
LEAN_DOCKER_CPUS = os.environ.get("LEAN_DOCKER_CPUS", "2").strip() or "2"
LEAN_DOCKER_MEMORY = os.environ.get("LEAN_DOCKER_MEMORY", "4g").strip() or "4g"
LEAN_DOCKER_PIDS_LIMIT = int(os.environ.get("LEAN_DOCKER_PIDS_LIMIT", "512"))
LEAN_DOCKER_READ_ONLY = os.environ.get("LEAN_DOCKER_READ_ONLY", "1").lower() not in {"0", "false", "no", "off"}
RESEARCH_DOCKER_CPUS = os.environ.get("LEAN_RESEARCH_CPUS", "2").strip() or "2"
RESEARCH_DOCKER_MEMORY = os.environ.get("LEAN_RESEARCH_MEMORY", "4g").strip() or "4g"
RESEARCH_DOCKER_PIDS_LIMIT = int(os.environ.get("LEAN_RESEARCH_PIDS_LIMIT", "512"))
REDIS_URL = os.environ.get("REDIS_URL", "redis://127.0.0.1:6379/0")
JOB_TIMEOUT_SECONDS = int(os.environ.get("BACKTEST_JOB_TIMEOUT_SECONDS", "7200"))
MAX_CONCURRENT_JOBS = int(os.environ.get("BACKTEST_MAX_CONCURRENT_JOBS", "1"))
LOG_LEVEL = os.environ.get("LEAN_WEB_LOG_LEVEL", "INFO")
API_AUTH_REQUIRED = os.environ.get("LEAN_API_AUTH_REQUIRED", "1").lower() not in {"0", "false", "no", "off"}
API_TOKEN_FILE = Path(
    os.environ.get("LEAN_API_TOKEN_FILE", RUNTIME_DIR / "secrets" / "api_token")
).expanduser()
try:
    _api_token_from_file = API_TOKEN_FILE.read_text(encoding="utf-8").strip()
except OSError:
    _api_token_from_file = ""
API_TOKEN = os.environ.get("LEAN_API_TOKEN", "").strip() or _api_token_from_file
BACKTEST_EXECUTION_DELEGATED = os.environ.get("LEAN_BACKTEST_EXECUTION_DELEGATED", "0").lower() in {"1", "true", "yes", "on"}

CLICKHOUSE_ENABLED = os.environ.get("CLICKHOUSE_ENABLED", "1").lower() not in {"0", "false", "no", "off"}
CLICKHOUSE_HOST = os.environ.get("CLICKHOUSE_HOST", "127.0.0.1")
CLICKHOUSE_PORT = int(os.environ.get("CLICKHOUSE_PORT", "8123"))
CLICKHOUSE_USERNAME = os.environ.get("CLICKHOUSE_USERNAME", "lean")
CLICKHOUSE_PASSWORD = os.environ.get("CLICKHOUSE_PASSWORD", "lean")
CLICKHOUSE_DATABASE = os.environ.get("CLICKHOUSE_DATABASE", "lean_market")

PROMETHEUS_URL = os.environ.get("PROMETHEUS_URL", "http://127.0.0.1:9090")
GRAFANA_URL = os.environ.get("GRAFANA_URL", "http://127.0.0.1:3000")
TUSHARE_TOKEN = os.environ.get("TUSHARE_TOKEN", "")
QUEUED_TASK_TIMEOUT_MINUTES = int(os.environ.get("QUEUED_TASK_TIMEOUT_MINUTES", "15"))

# Optional multi-provider analysis service. Secrets remain environment-only.
_INSIGHTS_LLM_PROVIDERS = {
    "deepseek": {
        "api_key_names": ("DEEPSEEK_API_KEY",),
        "base_url": "https://api.deepseek.com",
        "model": "deepseek-v4-flash",
    },
    "zhipu": {
        "api_key_names": ("ZHIPU_API_KEY", "ZAI_API_KEY"),
        "base_url": "https://open.bigmodel.cn/api/paas/v4",
        "model": "glm-5.2",
    },
    "kimi": {
        "api_key_names": ("KIMI_API_KEY", "MOONSHOT_API_KEY"),
        "base_url": "https://api.moonshot.cn/v1",
        "model": "kimi-k2.6",
    },
    "openai": {
        "api_key_names": ("OPENAI_API_KEY",),
        "base_url": "https://api.openai.com/v1",
        "model": "gpt-5-mini",
    },
    "anthropic": {
        "api_key_names": ("ANTHROPIC_API_KEY",),
        "base_url": "https://api.anthropic.com/v1",
        "model": "claude-sonnet-4-6",
    },
}


def _resolve_insights_llm(environ: Mapping[str, str]) -> dict[str, str]:
    requested_provider = environ.get("LEAN_INSIGHTS_LLM_PROVIDER", "").strip().lower()
    provider = requested_provider or next(
        (
            name
            for name, settings in _INSIGHTS_LLM_PROVIDERS.items()
            if any(environ.get(key_name, "").strip() for key_name in settings["api_key_names"])
        ),
        "deepseek",
    )
    settings = _INSIGHTS_LLM_PROVIDERS.get(provider)
    if settings is None:
        return {"provider": provider, "api_key": "", "base_url": "", "model": ""}
    api_key = next(
        (
            environ.get(key_name, "").strip()
            for key_name in settings["api_key_names"]
            if environ.get(key_name, "").strip()
        ),
        "",
    )
    return {
        "provider": provider,
        "api_key": api_key,
        "base_url": environ.get("LEAN_INSIGHTS_LLM_BASE_URL", "").strip() or settings["base_url"],
        "model": environ.get("LEAN_INSIGHTS_LLM_MODEL", "").strip() or settings["model"],
    }


_INSIGHTS_LLM = _resolve_insights_llm(os.environ)
INSIGHTS_LLM_PROVIDER = _INSIGHTS_LLM["provider"]
INSIGHTS_LLM_BASE_URL = _INSIGHTS_LLM["base_url"]
INSIGHTS_LLM_API_KEY = _INSIGHTS_LLM["api_key"]
INSIGHTS_LLM_MODEL = _INSIGHTS_LLM["model"]
INSIGHTS_LLM_TIMEOUT_SECONDS = int(os.environ.get("LEAN_INSIGHTS_LLM_TIMEOUT_SECONDS", "60"))

# A-share technology report. The observation pool and rule thresholds are code-versioned;
# only operational timings and cross-check tolerance are configurable here.
ASHARE_TECH_REPORT_HOUR = int(os.environ.get("LEAN_ASHARE_TECH_REPORT_HOUR", "17"))
ASHARE_TECH_REPORT_MINUTE = int(os.environ.get("LEAN_ASHARE_TECH_REPORT_MINUTE", "30"))
ASHARE_TECH_RETRY_MINUTES = int(os.environ.get("LEAN_ASHARE_TECH_RETRY_MINUTES", "30"))
ASHARE_TECH_CLOSE_TOLERANCE_PCT = float(os.environ.get("LEAN_ASHARE_TECH_CLOSE_TOLERANCE_PCT", "0.15"))
ASHARE_TECH_AGENT_MODE = os.environ.get("LEAN_ASHARE_TECH_AGENT_MODE", "hybrid_multi_agent").strip().lower()
ASHARE_TECH_EVALUATION_HOUR = int(os.environ.get("LEAN_ASHARE_TECH_EVALUATION_HOUR", "18"))
ASHARE_TECH_EVALUATION_MINUTE = int(os.environ.get("LEAN_ASHARE_TECH_EVALUATION_MINUTE", "45"))
PAPER_WALKFORWARD_HOUR = int(os.environ.get("LEAN_PAPER_WALKFORWARD_HOUR", "18"))
PAPER_WALKFORWARD_MINUTE = int(os.environ.get("LEAN_PAPER_WALKFORWARD_MINUTE", "45"))
DERIVED_MAINTENANCE_HOUR = int(os.environ.get("LEAN_DERIVED_MAINTENANCE_HOUR", "19"))
DERIVED_MAINTENANCE_MINUTE = int(os.environ.get("LEAN_DERIVED_MAINTENANCE_MINUTE", "30"))
MYSQL_BACKUP_HOUR = int(os.environ.get("LEAN_MYSQL_BACKUP_HOUR", "3"))
MYSQL_BACKUP_MINUTE = int(os.environ.get("LEAN_MYSQL_BACKUP_MINUTE", "0"))
SCHEDULED_AUTOMATION_ENABLED = os.environ.get(
    "LEAN_SCHEDULED_AUTOMATION_ENABLED",
    "1",
).lower() in {"1", "true", "yes", "on"}
PAPER_ORDER_PIPELINE_V2_ENABLED = os.environ.get(
    "LEAN_PAPER_ORDER_PIPELINE_V2_ENABLED",
    "1",
).lower() in {"1", "true", "yes", "on"}
