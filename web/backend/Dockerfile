FROM python:3.12-slim@sha256:423ed6ab25b1921a477529254bfeeabf5855151dc2c3141699a1bfc852199fbf

ENV PIP_DEFAULT_TIMEOUT=120 \
    PIP_RETRIES=10 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends postgresql-client docker-cli git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /workspace
COPY web/backend/requirements.lock /tmp/requirements.lock
RUN pip install --no-cache-dir --timeout 120 --retries 10 --require-hashes -r /tmp/requirements.lock

COPY . /workspace
WORKDIR /workspace/web/backend
ENV PYTHONPATH=/workspace/web/backend

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
