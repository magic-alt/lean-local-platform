# Backend

The backend is a FastAPI API plus Celery worker. Redis is used as the broker/result backend, and SQLite stores local metadata under `docker-demo/web/runtime/`.

Install:

```bash
cd /Users/kaermax/Lean/docker-demo/web/backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Run API:

```bash
source .venv/bin/activate
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Run worker:

```bash
source .venv/bin/activate
celery -A app.tasks.celery_app worker --loglevel=info --pool=solo
```

Required supporting service:

```bash
redis-server --port 6379
```

Useful environment variables:

```bash
export REDIS_URL=redis://127.0.0.1:6379/0
export LEAN_DOCKER_IMAGE=quantconnect/lean:latest
export LEAN_RESEARCH_IMAGE=quantconnect/research:latest
```

Main modules:

- `app/api/`: HTTP routers.
- `app/services/`: project, task, and object-store domain services.
- `app/tasks/`: Celery app and worker jobs.
- `app/lean.py`: LEAN Docker command construction, data conversion helpers, and result parsing.
