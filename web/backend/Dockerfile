FROM python:3.14-slim@sha256:cae66f2ef0ec51a9891263eeee7f987dacf0a9879e8aa9353d5606e0530619a5 AS python-base

ENV PIP_DEFAULT_TIMEOUT=120 \
    PIP_RETRIES=10 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

FROM python-base AS backend-builder

RUN apt-get update \
    && apt-get install -y --no-install-recommends gcc libc6-dev \
    && rm -rf /var/lib/apt/lists/*

COPY web/backend/requirements.lock /tmp/requirements.lock
RUN pip install --no-cache-dir --timeout 120 --retries 10 --require-hashes \
    --prefix=/install -r /tmp/requirements.lock

FROM python-base

RUN apt-get update \
    && apt-get install -y --no-install-recommends postgresql-client docker-cli git \
    && rm -rf /var/lib/apt/lists/*

COPY --from=backend-builder /install/ /usr/local/

COPY . /workspace
WORKDIR /workspace/web/backend
ENV PYTHONPATH=/workspace/web/backend

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
