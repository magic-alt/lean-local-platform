#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_DIR="${ROOT_DIR}/web/backend"
FRONTEND_DIR="${ROOT_DIR}/web/frontend"
COMPOSE_PROJECT_DIR="${ROOT_DIR}"
COMPOSE_SERVICES="${LEAN_COMPOSE_SERVICES:-mysql redis clickhouse prometheus grafana api worker}"
COMPOSE_PROJECT_NAME="${LEAN_COMPOSE_PROJECT_NAME:-lean-platform}"
START_COMPOSE_SERVICES="${LEAN_START_COMPOSE_SERVICES:-1}"
COMPOSE_BUILD="${LEAN_COMPOSE_BUILD:-0}"

LEAN_WEB_HOST="${LEAN_WEB_HOST:-127.0.0.1}"
VITE_HOST="${VITE_HOST:-127.0.0.1}"
VITE_PORT="${VITE_PORT:-5173}"
LEAN_WEB_PORT="${LEAN_WEB_PORT:-8000}"
LEAN_DATABASE_URL="${LEAN_DATABASE_URL:-mysql+pymysql://lean:lean@127.0.0.1:3306/lean_market}"
LEAN_OPEN_WEB="${LEAN_OPEN_WEB:-1}"
COMPOSE_START_TIMEOUT="${COMPOSE_START_TIMEOUT:-120}"
LEAN_API_PORT="${LEAN_API_PORT:-8000}"
LEAN_REDIS_PORT="${LEAN_REDIS_PORT:-6379}"
LEAN_MYSQL_PORT="${LEAN_MYSQL_PORT:-3306}"
LEAN_CLICKHOUSE_HTTP_PORT="${LEAN_CLICKHOUSE_HTTP_PORT:-8123}"
LEAN_CLICKHOUSE_NATIVE_PORT="${LEAN_CLICKHOUSE_NATIVE_PORT:-9000}"
LEAN_PROMETHEUS_PORT="${LEAN_PROMETHEUS_PORT:-9090}"
LEAN_GRAFANA_PORT="${LEAN_GRAFANA_PORT:-3000}"

BACKEND_VENV_PY="${BACKEND_DIR}/.venv/bin/python"
BACKEND_LOG=""
FRONTEND_LOG=""
COMPOSE_DOWN_ON_EXIT="${LEAN_COMPOSE_DOWN_ON_EXIT:-1}"
BACKEND_PID=""
FRONTEND_PID=""
COMPOSE_STARTED=0

timestamp() {
  date "+%Y-%m-%d %H:%M:%S"
}

log() {
  echo "[$(timestamp)] $*"
}

is_port_in_use() {
  local port="$1"
  if command -v lsof >/dev/null 2>&1; then
    if lsof -nP -iTCP -sTCP:LISTEN 2>/dev/null | grep -E "[:.]${port} " | grep -q "(LISTEN)"; then
      return 0
    fi
  elif command -v ss >/dev/null 2>&1; then
    if ss -ltn 2>/dev/null | awk '{print $4}' | tr -d "[]" | grep -Eq "(:|\\.)${port}$"; then
      return 0
    fi
  fi

  if (echo >/dev/tcp/127.0.0.1/"$port") >/dev/null 2>&1; then
    return 0
  fi

  return 1
}

find_next_available_port() {
  local start_port="$1"
  local port="${start_port}"
  local max_tries="${2:-200}"

  if ! [[ "${start_port}" =~ ^[0-9]+$ ]]; then
    log "端口配置无效: ${start_port}，将不做自动降级"
    echo "${start_port}"
    return 0
  fi

  while ((port <= 65535)); do
    if ! is_port_in_use "${port}"; then
      echo "${port}"
      return 0
    fi

    if ((max_tries <= 0)); then
      break
    fi
    max_tries=$((max_tries - 1))
    log "端口 ${port} 被占用，自动尝试下一个端口"
    port=$((port + 1))
  done

  log "在 ${start_port} 起始的端口范围内未找到可用端口"
  return 1
}

resolve_ports() {
  if [[ "${START_COMPOSE_SERVICES}" == "1" ]]; then
    LEAN_REDIS_PORT="$(find_next_available_port "${LEAN_REDIS_PORT}" 200)"
    LEAN_MYSQL_PORT="$(find_next_available_port "${LEAN_MYSQL_PORT}" 200)"
    if [[ "${COMPOSE_SERVICES}" == *"clickhouse"* ]]; then
      LEAN_CLICKHOUSE_HTTP_PORT="$(find_next_available_port "${LEAN_CLICKHOUSE_HTTP_PORT}" 200)"
      LEAN_CLICKHOUSE_NATIVE_PORT="$(find_next_available_port "${LEAN_CLICKHOUSE_NATIVE_PORT}" 200)"
    fi
    if [[ "${COMPOSE_SERVICES}" == *"prometheus"* ]]; then
      LEAN_PROMETHEUS_PORT="$(find_next_available_port "${LEAN_PROMETHEUS_PORT}" 200)"
    fi
    if [[ "${COMPOSE_SERVICES}" == *"grafana"* ]]; then
      LEAN_GRAFANA_PORT="$(find_next_available_port "${LEAN_GRAFANA_PORT}" 200)"
    fi
    if [[ "${COMPOSE_SERVICES}" == *"api"* ]]; then
      LEAN_API_PORT="$(find_next_available_port "${LEAN_API_PORT}" 200)"
      LEAN_WEB_PORT="${LEAN_API_PORT}"
    fi
    export LEAN_REDIS_PORT LEAN_MYSQL_PORT LEAN_CLICKHOUSE_HTTP_PORT LEAN_CLICKHOUSE_NATIVE_PORT LEAN_PROMETHEUS_PORT LEAN_GRAFANA_PORT LEAN_API_PORT
  fi

  if [[ "${START_COMPOSE_SERVICES}" == "0" ]]; then
    LEAN_WEB_PORT="$(find_next_available_port "${LEAN_WEB_PORT}" 200)"
    VITE_PORT="$(find_next_available_port "${VITE_PORT}" 200)"
  fi

  BACKEND_LOG="/tmp/lean_backend_single_${LEAN_WEB_PORT}.log"
  FRONTEND_LOG="/tmp/lean_frontend_single_${VITE_PORT}.log"

  log "端口映射: "
  if [[ "${START_COMPOSE_SERVICES}" == "1" ]]; then
    log "  redis: ${LEAN_REDIS_PORT}, mysql: ${LEAN_MYSQL_PORT}, api: ${LEAN_API_PORT}, frontend: ${VITE_PORT}, backend-check: ${LEAN_WEB_PORT}"
    if [[ "${COMPOSE_SERVICES}" == *"clickhouse"* ]]; then
      log "  clickhouse: ${LEAN_CLICKHOUSE_HTTP_PORT}/${LEAN_CLICKHOUSE_NATIVE_PORT}"
    fi
    if [[ "${COMPOSE_SERVICES}" == *"prometheus"* ]]; then
      log "  prometheus: ${LEAN_PROMETHEUS_PORT}"
    fi
    if [[ "${COMPOSE_SERVICES}" == *"grafana"* ]]; then
      log "  grafana: ${LEAN_GRAFANA_PORT}"
    fi
  else
    log "  backend: ${LEAN_WEB_PORT}, frontend: ${VITE_PORT}"
  fi
}

parse_args() {
  for arg in "$@"; do
    case "${arg}" in
      --build)
        COMPOSE_BUILD="1"
        ;;
      --no-build)
        COMPOSE_BUILD="0"
        ;;
      *)
        echo "不支持的参数: ${arg}" >&2
        echo "支持参数: --build / --no-build" >&2
        exit 1
        ;;
    esac
  done
}

wait_for_port() {
  local label="$1"
  local host="$2"
  local port="$3"
  local timeout="${4:-45}"

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

open_frontend_in_browser() {
  if [[ "${LEAN_OPEN_WEB}" != "1" ]]; then
    return 0
  fi

  local frontend_url="http://${VITE_HOST}:${VITE_PORT}"
  if command -v open >/dev/null 2>&1; then
    log "尝试打开浏览器：${frontend_url}"
    (open "${frontend_url}" >/dev/null 2>&1 &) || log "open 命令执行失败，已跳过自动打开"
  elif command -v xdg-open >/dev/null 2>&1; then
    log "尝试打开浏览器：${frontend_url}"
    (xdg-open "${frontend_url}" >/dev/null 2>&1 &) || log "xdg-open 命令执行失败，已跳过自动打开"
  elif command -v start >/dev/null 2>&1; then
    log "尝试打开浏览器：${frontend_url}"
    (start "${frontend_url}" >/dev/null 2>&1 &) || log "start 命令执行失败，已跳过自动打开"
  else
    log "未检测到可用的浏览器打开命令（open/xdg-open/start），请手动打开 ${frontend_url}"
  fi
}

cleanup_previous_instances() {
  log "清理旧实例（${LEAN_WEB_HOST}:${LEAN_WEB_PORT} / ${VITE_HOST}:${VITE_PORT}）"
  if [[ "${START_COMPOSE_SERVICES}" == "1" ]]; then
    docker compose -p "${COMPOSE_PROJECT_NAME}" --project-directory "${COMPOSE_PROJECT_DIR}" down --remove-orphans >/dev/null 2>&1 || true
  fi
  pkill -f "vite --host ${VITE_HOST} --port ${VITE_PORT}" || true
  pkill -f "npm run dev -- --host ${VITE_HOST} --port ${VITE_PORT}" || true
  pkill -f "python -m uvicorn app.main:app --host ${LEAN_WEB_HOST} --port ${LEAN_WEB_PORT}" || true
  pkill -f "uvicorn app.main:app --host ${LEAN_WEB_HOST} --port ${LEAN_WEB_PORT}" || true
}

check_dependencies() {
  if [[ "${START_COMPOSE_SERVICES}" == "0" && ! -x "${BACKEND_VENV_PY}" ]]; then
    log "缺少 Python 可执行文件: ${BACKEND_VENV_PY}"
    log "请先执行：cd ${BACKEND_DIR} && python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt"
    exit 1
  fi

  if [[ "${START_COMPOSE_SERVICES}" == "1" && -z "$(command -v docker || true)" ]]; then
    log "缺少 docker 命令，无法启动 compose 服务。请安装 Docker 或将 LEAN_START_COMPOSE_SERVICES=0"
    exit 1
  fi
  if [[ "${START_COMPOSE_SERVICES}" == "1" ]] && ! docker compose version >/dev/null 2>&1; then
    log "缺少 docker compose，可执行命令 'docker compose'，请安装 docker compose plugin"
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
  (
    cd "${BACKEND_DIR}"
    LEAN_DATABASE_URL="${LEAN_DATABASE_URL}" \
      ./.venv/bin/python -m uvicorn app.main:app --host "${LEAN_WEB_HOST}" --port "${LEAN_WEB_PORT}"
  ) >"${BACKEND_LOG}" 2>&1 &
  BACKEND_PID=$!
}

start_compose_services() {
  log "启动 compose 服务: ${COMPOSE_SERVICES}"
  if [[ "${COMPOSE_BUILD}" == "1" ]]; then
    log "开启 compose 镜像重建: docker compose --build"
  else
    log "跳过 compose 镜像重建: docker compose"
  fi
  (
    cd "${COMPOSE_PROJECT_DIR}"
    if [[ "${COMPOSE_BUILD}" == "1" ]]; then
      docker compose --project-directory "${COMPOSE_PROJECT_DIR}" -p "${COMPOSE_PROJECT_NAME}" --profile app up -d --build ${COMPOSE_SERVICES}
    else
      docker compose --project-directory "${COMPOSE_PROJECT_DIR}" -p "${COMPOSE_PROJECT_NAME}" --profile app up -d ${COMPOSE_SERVICES}
    fi
  )
  COMPOSE_STARTED=1
}

wait_for_compose_service() {
  local service="$1"
  local health_url="$2"
  local timeout="${COMPOSE_START_TIMEOUT}"
  local i=0
  while ((i < timeout)); do
    if docker compose -p "${COMPOSE_PROJECT_NAME}" --project-directory "${COMPOSE_PROJECT_DIR}" \
      ps --status running "${service}" | grep -q "Up"; then
      if [[ -n "${health_url}" ]]; then
        if command -v curl >/dev/null 2>&1 && curl -sSf "${health_url}" >/dev/null 2>&1; then
          return 0
        fi
      else
        return 0
      fi
    fi
    sleep 1
    ((i += 1))
  done
  return 1
}

start_frontend() {
  log "启动前端: ${VITE_HOST}:${VITE_PORT}"
  (
    cd "${FRONTEND_DIR}"
    npm run dev -- --host "${VITE_HOST}" --port "${VITE_PORT}"
  ) >"${FRONTEND_LOG}" 2>&1 &
  FRONTEND_PID=$!
}

shutdown() {
  log "收到退出信号，清理服务..."
  if [[ -n "${BACKEND_PID}" ]]; then
    kill "${BACKEND_PID}" >/dev/null 2>&1 || true
  fi
  if [[ -n "${FRONTEND_PID}" ]]; then
    kill "${FRONTEND_PID}" >/dev/null 2>&1 || true
  fi
  if [[ "${START_COMPOSE_SERVICES}" == "1" && "${COMPOSE_STARTED}" == "1" && "${COMPOSE_DOWN_ON_EXIT}" == "1" ]]; then
    (
      cd "${COMPOSE_PROJECT_DIR}"
      docker compose --project-directory "${COMPOSE_PROJECT_DIR}" -p "${COMPOSE_PROJECT_NAME}" down
    )
  fi
  wait || true
}

trap shutdown INT TERM EXIT
parse_args "$@"
resolve_ports

cleanup_previous_instances
check_dependencies
if [[ "${START_COMPOSE_SERVICES}" == "1" ]]; then
  start_compose_services
  if ! wait_for_compose_service api "http://${LEAN_WEB_HOST}:${LEAN_WEB_PORT}/api/health"; then
    log "后端容器未就绪，以下是 api 近况："
    docker compose --project-directory "${COMPOSE_PROJECT_DIR}" -p "${COMPOSE_PROJECT_NAME}" logs --tail=120 api || true
    exit 1
  fi
else
  start_backend
  if ! wait_for_port "后端" "${LEAN_WEB_HOST}" "${LEAN_WEB_PORT}" 45; then
    log "后端启动失败，以下是日志片段："
    tail -n 80 "${BACKEND_LOG}" || true
    exit 1
  fi
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
if [[ "${START_COMPOSE_SERVICES}" == "1" ]]; then
  log "后端日志: compose service api (${COMPOSE_PROJECT_NAME})"
else
  log "后端日志: ${BACKEND_LOG}"
fi
log "前端日志: ${FRONTEND_LOG}"
log "访问地址: http://${VITE_HOST}:${VITE_PORT}"
open_frontend_in_browser

if [[ "${START_COMPOSE_SERVICES}" == "1" ]]; then
  docker compose --project-directory "${COMPOSE_PROJECT_DIR}" -p "${COMPOSE_PROJECT_NAME}" logs -f --tail=120 api worker
else
  log "后端PID: ${BACKEND_PID}"
  log "前端PID: ${FRONTEND_PID}"
  wait "${BACKEND_PID}" "${FRONTEND_PID}"
fi
