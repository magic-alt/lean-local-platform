FROM python:3.12-slim@sha256:423ed6ab25b1921a477529254bfeeabf5855151dc2c3141699a1bfc852199fbf

ENV PIP_DEFAULT_TIMEOUT=120 \
    PIP_RETRIES=10 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends default-mysql-client git libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /workspace
COPY web/backend/requirements-ml.lock /tmp/requirements-ml.lock
RUN pip install --no-cache-dir --timeout 120 --retries 10 --require-hashes -r /tmp/requirements-ml.lock

COPY . /workspace
WORKDIR /workspace/web/backend
ENV PYTHONPATH=/workspace/web/backend

CMD ["celery", "-A", "app.tasks.celery_app", "worker", "--loglevel=info", "--queues=ml", "--concurrency=1"]
