from fastapi import APIRouter

router = APIRouter(prefix="/api/capabilities", tags=["capabilities"])


@router.get("")
def capabilities():
    return [
        {
            "key": "projects",
            "name": "Project editor",
            "group": "Local development",
            "status": "enabled",
            "surface": "Web",
            "notes": "Create, edit, and save local Python projects. C# files can be managed, but C# execution is disabled in this local v1.",
        },
        {
            "key": "data",
            "name": "Local data",
            "group": "Data",
            "status": "enabled",
            "surface": "Web + filesystem",
            "notes": "List local symbols, import CSV daily bars, and fetch Alpha Vantage daily bars into LEAN zip format.",
        },
        {
            "key": "backtest",
            "name": "Backtesting",
            "group": "Execution",
            "status": "enabled",
            "surface": "Docker quantconnect/lean",
            "notes": "Runs the open-source LEAN Docker image with local config, project files, data, results, and object store mounts.",
        },
        {
            "key": "optimization",
            "name": "Parameter optimization",
            "group": "Execution",
            "status": "enabled",
            "surface": "Celery worker",
            "notes": "Runs a local grid search by launching one Docker backtest per candidate.",
        },
        {
            "key": "research",
            "name": "Research container",
            "group": "Execution",
            "status": "experimental",
            "surface": "Docker",
            "notes": "Starts a detached research container mapped to a local port. Image behavior depends on the selected LEAN image.",
        },
        {
            "key": "reports",
            "name": "HTML reports",
            "group": "Results",
            "status": "enabled",
            "surface": "Web",
            "notes": "Builds standalone HTML reports from LEAN result JSON and serves artifacts from the run directory.",
        },
        {
            "key": "object-store",
            "name": "Local Object Store",
            "group": "State",
            "status": "enabled",
            "surface": "Web + Docker mount",
            "notes": "Upload, download, and delete files mounted into LEAN's LocalObjectStore path.",
        },
        {
            "key": "tasks",
            "name": "Task queue and logs",
            "group": "Operations",
            "status": "enabled",
            "surface": "Redis + Celery",
            "notes": "Backtests, optimizations, reports, and research starts run as background tasks with persisted logs.",
        },
        {
            "key": "cloud",
            "name": "QuantConnect cloud sync",
            "group": "Cloud",
            "status": "disabled",
            "surface": "Lean CLI / QuantConnect account",
            "notes": "Cloud project sync, cloud backtests, and cloud reports are intentionally not enabled in the open-source local Docker flow.",
        },
        {
            "key": "live",
            "name": "Live trading",
            "group": "Live",
            "status": "disabled",
            "surface": "Brokerage-specific configuration",
            "notes": "Live trading requires explicit broker credentials, risk controls, and a separate live-mode configuration.",
        },
    ]
