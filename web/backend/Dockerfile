FROM python:3.12-slim

ENV PIP_DEFAULT_TIMEOUT=120 \
    PIP_RETRIES=10 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends docker-cli \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /workspace
COPY web/backend/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir --timeout 120 --retries 10 -r /tmp/requirements.txt

COPY . /workspace
WORKDIR /workspace/web/backend
ENV PYTHONPATH=/workspace/web/backend

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
