#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_DIR="${ROOT_DIR}/web/backend"
FRONTEND_DIR="${ROOT_DIR}/web/frontend"

LEAN_WEB_HOST="${LEAN_WEB_HOST:-127.0.0.1}"
LEAN_WEB_PORT="${LEAN_WEB_PORT:-8000}"
VITE_HOST="${VITE_HOST:-127.0.0.1}"
VITE_PORT="${VITE_PORT:-5173}"
LEAN_DATABASE_URL="${LEAN_DATABASE_URL:-mysql+pymysql://lean:lean@127.0.0.1:3306/lean_market}"

BACKEND_VENV_PY="${BACKEND_DIR}/.venv/bin/python"
BACKEND_LOG="/tmp/lean_backend_single_${LEAN_WEB_PORT}.log"
FRONTEND_LOG="/tmp/lean_frontend_single_${VITE_PORT}.log"

timestamp() {
  date "+%Y-%m-%d %H:%M:%S"
}

log() {
  echo "[$(timestamp)] $*"
}

wait_for_port() {
  local label="$1"
  local host="$2"
  local port="$3"
  local timeout="${4:-30}"

  local i=0
  while ((i < timeout)); do
    if command -v curl >/dev/null 2>&1; then
      if curl -sSf "http://${host}:${port}/api/health" >/dev/null 2>&1; then
        log "${label} 已就绪：http://${host}:${port}"
        return 0
      fi
    fi

    sleep 1
    ((i += 1))
  done

  log "${label} 在 ${timeout}s 内未就绪"
  return 1
}

cleanup_previous_instances() {
  log "清理旧实例（${LEAN_WEB_HOST}:${LEAN_WEB_PORT} / ${VITE_HOST}:${VITE_PORT}）"
  pkill -f "python -m uvicorn app.main:app --host ${LEAN_WEB_HOST} --port ${LEAN_WEB_PORT}" || true
  pkill -f "uvicorn app.main:app --host ${LEAN_WEB_HOST} --port ${LEAN_WEB_PORT}" || true
  pkill -f "vite --host ${VITE_HOST} --port ${VITE_PORT}" || true
  pkill -f "npm run dev -- --host ${VITE_HOST} --port ${VITE_PORT}" || true
}

check_dependencies() {
  if [[ ! -x "${BACKEND_VENV_PY}" ]]; then
    log "缺少 Python 可执行文件: ${BACKEND_VENV_PY}"
    log "请先执行：cd ${BACKEND_DIR} && python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt"
    exit 1
  fi

  if [[ ! -d "${FRONTEND_DIR}/node_modules" ]]; then
    log "缺少前端依赖：node_modules"
    log "请先执行：cd ${FRONTEND_DIR} && npm install"
    exit 1
  fi
}

start_backend() {
  log "启动后端: ${LEAN_WEB_HOST}:${LEAN_WEB_PORT}"
  log "数据库配置: ${LEAN_DATABASE_URL}"
  (cd "${BACKEND_DIR}" && \
    LEAN_DATABASE_URL="${LEAN_DATABASE_URL}" \
    ./.venv/bin/python -m uvicorn app.main:app --host "${LEAN_WEB_HOST}" --port "${LEAN_WEB_PORT}" \
    >"${BACKEND_LOG}" 2>&1 & echo $! > /tmp/lean_backend_single.pid)
  BACKEND_PID="$(cat /tmp/lean_backend_single.pid)"
}

start_frontend() {
  log "启动前端: ${VITE_HOST}:${VITE_PORT}"
  (cd "${FRONTEND_DIR}" && \
    npm run dev -- --host "${VITE_HOST}" --port "${VITE_PORT}" \
    >"${FRONTEND_LOG}" 2>&1 & echo $! > /tmp/lean_frontend_single.pid)
  FRONTEND_PID="$(cat /tmp/lean_frontend_single.pid)"
}

shutdown() {
  log "收到退出信号，清理服务..."
  if [[ -n "${BACKEND_PID:-}" ]]; then
    kill "${BACKEND_PID}" >/dev/null 2>&1 || true
  fi
  if [[ -n "${FRONTEND_PID:-}" ]]; then
    kill "${FRONTEND_PID}" >/dev/null 2>&1 || true
  fi
  wait || true
}

trap shutdown INT TERM EXIT

cleanup_previous_instances
check_dependencies
start_backend
if ! wait_for_port "后端" "${LEAN_WEB_HOST}" "${LEAN_WEB_PORT}" 45; then
  log "后端启动失败，以下是日志片段："
  tail -n 80 "${BACKEND_LOG}" || true
  exit 1
fi

start_frontend
if ! wait_for_port "前端" "${VITE_HOST}" "${VITE_PORT}" 45; then
  log "前端启动失败，以下是日志片段："
  tail -n 80 "${FRONTEND_LOG}" || true
  exit 1
fi

log "健康检查："
curl -sS "http://${LEAN_WEB_HOST}:${LEAN_WEB_PORT}/api/health" || true
echo
curl -sS "http://${LEAN_WEB_HOST}:${LEAN_WEB_PORT}/api/health/dependencies" || true
echo
log "后端日志: ${BACKEND_LOG}"
log "前端日志: ${FRONTEND_LOG}"
log "后端PID: ${BACKEND_PID}"
log "前端PID: ${FRONTEND_PID}"
log "访问地址: http://${VITE_HOST}:${VITE_PORT}"

wait
