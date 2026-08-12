#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_DIR="${ROOT_DIR}/web/backend"
FRONTEND_DIR="${ROOT_DIR}/web/frontend"
COMPOSE_PROJECT_DIR="${ROOT_DIR}"
COMPOSE_SERVICES="${LEAN_COMPOSE_SERVICES:-mysql redis clickhouse prometheus grafana api worker data-worker data-lineage-worker data-demand-worker backtest-worker beat}"
COMPOSE_PROJECT_NAME="${LEAN_COMPOSE_PROJECT_NAME:-lean-platform}"
START_COMPOSE_SERVICES="${LEAN_START_COMPOSE_SERVICES:-1}"
COMPOSE_BUILD="${LEAN_COMPOSE_BUILD:-0}"
DOCKER_BUILD_CACHE_MAX="${LEAN_DOCKER_BUILD_CACHE_MAX:-2GB}"
PRUNE_BUILD_CACHE="${LEAN_PRUNE_BUILD_CACHE:-0}"
ALLOW_ACTIVE_SYNC_RECREATE="${LEAN_ALLOW_ACTIVE_SYNC_RECREATE:-0}"
ALLOW_ACTIVE_SYNC_SHUTDOWN="${LEAN_ALLOW_ACTIVE_SYNC_SHUTDOWN:-0}"
RUNTIME_SECRETS_DIR="${LEAN_RUNTIME_SECRETS_DIR:-${ROOT_DIR}/web/runtime/secrets}"
MYSQL_LOADER_PASSWORD_FILE="${LEAN_MYSQL_LOADER_PASSWORD_FILE:-${RUNTIME_SECRETS_DIR}/mysql_loader_password}"
API_TOKEN_FILE="${LEAN_API_TOKEN_FILE:-${RUNTIME_SECRETS_DIR}/api_token}"

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
LEAN_MYSQL_ROOT_PASSWORD="${LEAN_MYSQL_ROOT_PASSWORD:-lean-root}"

BACKEND_VENV_PY="${BACKEND_DIR}/.venv/bin/python"
BACKEND_LOG=""
FRONTEND_LOG=""
# Database/API/worker containers are persistent local platform services. Keep
# them running when the foreground launcher exits unless cleanup is explicit.
COMPOSE_DOWN_ON_EXIT="${LEAN_COMPOSE_DOWN_ON_EXIT:-0}"
BACKEND_PID=""
FRONTEND_PID=""
LOG_STREAM_PID=""
COMPOSE_STARTED=0
ACTIVE_DATA_SYNC=0
SHUTTING_DOWN=0
LOCK_DIR="${LEAN_SINGLE_INSTANCE_LOCK_DIR:-/tmp/${COMPOSE_PROJECT_NAME}-web-single-instance.lock}"
LOCK_ACQUIRED=0

timestamp() {
  date "+%Y-%m-%d %H:%M:%S"
}

log() {
  echo "[$(timestamp)] $*"
}

log_stderr() {
  echo "[$(timestamp)] $*" >&2
}

acquire_single_instance_lock() {
  local owner_pid=""
  if mkdir "${LOCK_DIR}" 2>/dev/null; then
    printf '%s\n' "$$" >"${LOCK_DIR}/pid"
    LOCK_ACQUIRED=1
    return 0
  fi

  if [[ -f "${LOCK_DIR}/pid" ]]; then
    IFS= read -r owner_pid <"${LOCK_DIR}/pid" || true
  fi
  if [[ "${owner_pid}" =~ ^[0-9]+$ ]] && kill -0 "${owner_pid}" 2>/dev/null; then
    log_stderr "已有启动脚本实例正在运行（PID ${owner_pid}）。请使用现有页面，或先停止该实例。"
    return 1
  fi

  rm -f "${LOCK_DIR}/pid"
  rmdir "${LOCK_DIR}" 2>/dev/null || true
  if ! mkdir "${LOCK_DIR}" 2>/dev/null; then
    log_stderr "无法取得单实例锁：${LOCK_DIR}"
    return 1
  fi
  printf '%s\n' "$$" >"${LOCK_DIR}/pid"
  LOCK_ACQUIRED=1
}

existing_loader_password() {
  local container_id=""
  local line=""
  container_id="$(docker compose -p "${COMPOSE_PROJECT_NAME}" --project-directory "${COMPOSE_PROJECT_DIR}" \
    ps -q data-worker 2>/dev/null || true)"
  if [[ -z "${container_id}" ]]; then
    return 1
  fi
  while IFS= read -r line; do
    case "${line}" in
      LEAN_LOADER_DATABASE_URL=mysql+pymysql://lean_loader:*@mysql:3306/lean_market)
        line="${line#LEAN_LOADER_DATABASE_URL=mysql+pymysql://lean_loader:}"
        line="${line%@mysql:3306/lean_market}"
        if [[ -n "${line}" && "${line}" != "loader-not-configured" ]]; then
          printf '%s\n' "${line}"
          return 0
        fi
        ;;
    esac
  done < <(docker inspect --format '{{range .Config.Env}}{{println .}}{{end}}' "${container_id}" 2>/dev/null || true)
  return 1
}

initialize_mysql_loader_password() {
  local generated=""
  if [[ -n "${LEAN_MYSQL_LOADER_PASSWORD:-}" ]]; then
    export LEAN_MYSQL_LOADER_PASSWORD
    return 0
  fi

  if [[ -f "${MYSQL_LOADER_PASSWORD_FILE}" ]]; then
    IFS= read -r LEAN_MYSQL_LOADER_PASSWORD <"${MYSQL_LOADER_PASSWORD_FILE}" || true
  elif command -v docker >/dev/null 2>&1; then
    LEAN_MYSQL_LOADER_PASSWORD="$(existing_loader_password || true)"
  fi
  if [[ "${LEAN_MYSQL_LOADER_PASSWORD:-}" == "loader-not-configured" ]]; then
    LEAN_MYSQL_LOADER_PASSWORD=""
  fi

  if [[ -z "${LEAN_MYSQL_LOADER_PASSWORD:-}" ]]; then
    if command -v openssl >/dev/null 2>&1; then
      generated="$(openssl rand -hex 24)"
    else
      generated="loader-$(date +%s)-${RANDOM}${RANDOM}"
    fi
    LEAN_MYSQL_LOADER_PASSWORD="${generated}"
  fi

  if [[ ! -s "${MYSQL_LOADER_PASSWORD_FILE}" ]]; then
    (umask 077 && mkdir -p "${RUNTIME_SECRETS_DIR}" && printf '%s\n' "${LEAN_MYSQL_LOADER_PASSWORD}" >"${MYSQL_LOADER_PASSWORD_FILE}")
  fi
  chmod 600 "${MYSQL_LOADER_PASSWORD_FILE}" 2>/dev/null || true
  export LEAN_MYSQL_LOADER_PASSWORD
}

initialize_api_token() {
  local generated=""
  if [[ -n "${LEAN_API_TOKEN:-}" ]]; then
    export LEAN_API_TOKEN
    return 0
  fi
  if [[ -f "${API_TOKEN_FILE}" ]]; then
    IFS= read -r LEAN_API_TOKEN <"${API_TOKEN_FILE}" || true
  fi
  if [[ -z "${LEAN_API_TOKEN:-}" ]]; then
    if command -v openssl >/dev/null 2>&1; then
      generated="$(openssl rand -hex 32)"
    else
      generated="api-$(date +%s)-${RANDOM}${RANDOM}${RANDOM}"
    fi
    LEAN_API_TOKEN="${generated}"
  fi
  if [[ ! -s "${API_TOKEN_FILE}" ]]; then
    (umask 077 && mkdir -p "${RUNTIME_SECRETS_DIR}" && printf '%s\n' "${LEAN_API_TOKEN}" >"${API_TOKEN_FILE}")
  fi
  chmod 600 "${API_TOKEN_FILE}" 2>/dev/null || true
  export LEAN_API_TOKEN
}

data_sync_is_active() {
  local payload=""
  local active_count=""
  if command -v curl >/dev/null 2>&1; then
    payload="$(curl -fsS --max-time 3 -H "Authorization: Bearer ${LEAN_API_TOKEN:-}" "http://${LEAN_WEB_HOST}:${LEAN_WEB_PORT}/api/data/catalog" 2>/dev/null || true)"
    if grep -Eq '"activeRun"[[:space:]]*:[[:space:]]*\{' <<<"${payload}"; then
      return 0
    fi
  fi
  if command -v docker >/dev/null 2>&1; then
    active_count="$(docker compose --project-directory "${COMPOSE_PROJECT_DIR}" -p "${COMPOSE_PROJECT_NAME}" \
      exec -T mysql mysql -uroot "-p${LEAN_MYSQL_ROOT_PASSWORD}" -Nse \
      "select count(*) from lean_market.data_sync_runs where status in ('queued','running','cancelling')" \
      2>/dev/null || true)"
  fi
  [[ "${active_count}" =~ ^[1-9][0-9]*$ ]]
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
    log_stderr "端口配置无效: ${start_port}，将不做自动降级"
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
    log_stderr "端口 ${port} 被占用，自动尝试下一个端口"
    port=$((port + 1))
  done

  log_stderr "在 ${start_port} 起始的端口范围内未找到可用端口"
  return 1
}

compose_project_host_port() {
  local service="$1"
  local container_port="$2"
  local published=""

  if ! command -v docker >/dev/null 2>&1; then
    return 1
  fi
  published="$(docker compose -p "${COMPOSE_PROJECT_NAME}" --project-directory "${COMPOSE_PROJECT_DIR}" \
    port "${service}" "${container_port}" 2>/dev/null | head -n 1 || true)"
  if [[ -n "${published}" && "${published##*:}" =~ ^[0-9]+$ ]]; then
    echo "${published##*:}"
    return 0
  fi
  return 1
}

resolve_compose_port() {
  local service="$1"
  local container_port="$2"
  local requested_host_port="$3"
  local existing_host_port=""
  if existing_host_port="$(compose_project_host_port "${service}" "${container_port}")"; then
    echo "${existing_host_port}"
  else
    find_next_available_port "${requested_host_port}" 200
  fi
}

resolve_ports() {
  if [[ "${START_COMPOSE_SERVICES}" == "1" ]]; then
    LEAN_REDIS_PORT="$(resolve_compose_port redis 6379 "${LEAN_REDIS_PORT}")"
    LEAN_MYSQL_PORT="$(resolve_compose_port mysql 3306 "${LEAN_MYSQL_PORT}")"
    if [[ "${COMPOSE_SERVICES}" == *"clickhouse"* ]]; then
      LEAN_CLICKHOUSE_HTTP_PORT="$(resolve_compose_port clickhouse 8123 "${LEAN_CLICKHOUSE_HTTP_PORT}")"
      LEAN_CLICKHOUSE_NATIVE_PORT="$(resolve_compose_port clickhouse 9000 "${LEAN_CLICKHOUSE_NATIVE_PORT}")"
    fi
    if [[ "${COMPOSE_SERVICES}" == *"prometheus"* ]]; then
      LEAN_PROMETHEUS_PORT="$(resolve_compose_port prometheus 9090 "${LEAN_PROMETHEUS_PORT}")"
    fi
    if [[ "${COMPOSE_SERVICES}" == *"grafana"* ]]; then
      LEAN_GRAFANA_PORT="$(resolve_compose_port grafana 3000 "${LEAN_GRAFANA_PORT}")"
    fi
    if [[ "${COMPOSE_SERVICES}" == *"api"* ]]; then
      LEAN_API_PORT="$(resolve_compose_port api 8000 "${LEAN_API_PORT}")"
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
  log "清理旧本地前后端进程（${LEAN_WEB_HOST}:${LEAN_WEB_PORT} / ${VITE_HOST}:${VITE_PORT}）"
  # `docker compose up -d` below is idempotent and reconciles changed service
  # definitions. Do not tear down MySQL/API/workers here: doing so interrupts
  # checkpoints and makes an already-open frontend return HTTP 500.
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

bound_docker_build_cache() {
  if [[ "${START_COMPOSE_SERVICES}" != "1" || "${COMPOSE_BUILD}" != "1" || "${PRUNE_BUILD_CACHE}" != "1" ]]; then
    return 0
  fi
  docker builder prune -af \
    --max-used-space "${DOCKER_BUILD_CACHE_MAX}" \
    --reserved-space 512MB >/dev/null 2>&1 || true
  log "Docker 构建缓存上限: ${DOCKER_BUILD_CACHE_MAX}"
}

start_backend() {
  log "启动后端: ${LEAN_WEB_HOST}:${LEAN_WEB_PORT}"
  log "数据库配置: ${LEAN_DATABASE_URL}"
  (
    cd "${BACKEND_DIR}"
    LEAN_DATABASE_URL="${LEAN_DATABASE_URL}" \
      LEAN_API_AUTH_REQUIRED=1 LEAN_API_TOKEN="${LEAN_API_TOKEN}" \
      ./.venv/bin/python -m uvicorn app.main:app --host "${LEAN_WEB_HOST}" --port "${LEAN_WEB_PORT}"
  ) >"${BACKEND_LOG}" 2>&1 &
  BACKEND_PID=$!
}

start_compose_services() {
  local -a services=()
  read -r -a services <<<"${COMPOSE_SERVICES}"
  log "启动 compose 服务: ${COMPOSE_SERVICES}"
  if [[ "${COMPOSE_BUILD}" == "1" ]]; then
    log "开启 compose 镜像重建: docker compose --build"
  else
    log "跳过 compose 镜像重建: docker compose"
  fi
  (
    cd "${COMPOSE_PROJECT_DIR}"
    if [[ "${COMPOSE_BUILD}" == "1" ]]; then
      docker compose --project-directory "${COMPOSE_PROJECT_DIR}" -p "${COMPOSE_PROJECT_NAME}" --profile app up -d --build "${services[@]}"
    else
      docker compose --project-directory "${COMPOSE_PROJECT_DIR}" -p "${COMPOSE_PROJECT_NAME}" --profile app up -d "${services[@]}"
    fi
  )
  COMPOSE_STARTED=1
}

configure_mysql_loader() {
  local i=0
  while ((i < COMPOSE_START_TIMEOUT)); do
    if docker compose --project-directory "${COMPOSE_PROJECT_DIR}" -p "${COMPOSE_PROJECT_NAME}" \
      exec -T mysql mysqladmin ping -h 127.0.0.1 -uroot "-p${LEAN_MYSQL_ROOT_PASSWORD}" --silent >/dev/null 2>&1; then
      break
    fi
    sleep 1
    ((i += 1))
  done
  if ((i >= COMPOSE_START_TIMEOUT)); then
    log "MySQL loader 账户配置超时；批量同步将拒绝关闭 binlog"
    return 1
  fi
  docker compose --project-directory "${COMPOSE_PROJECT_DIR}" -p "${COMPOSE_PROJECT_NAME}" \
    exec -T mysql mysql -uroot "-p${LEAN_MYSQL_ROOT_PASSWORD}" -e \
    "CREATE USER IF NOT EXISTS 'lean_loader'@'%' IDENTIFIED BY '${LEAN_MYSQL_LOADER_PASSWORD}'; ALTER USER 'lean_loader'@'%' IDENTIFIED BY '${LEAN_MYSQL_LOADER_PASSWORD}'; GRANT SELECT, INSERT, UPDATE, DELETE, CREATE TEMPORARY TABLES ON lean_market.* TO 'lean_loader'@'%'; GRANT FILE, SESSION_VARIABLES_ADMIN ON *.* TO 'lean_loader'@'%'; FLUSH PRIVILEGES;" >/dev/null
  log "已配置仅用于可重建市场数据的 MySQL loader 会话"
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
    VITE_API_PROXY_TARGET="http://${LEAN_WEB_HOST}:${LEAN_WEB_PORT}" \
      VITE_API_TOKEN="${LEAN_API_TOKEN}" \
      npm run dev -- --host "${VITE_HOST}" --port "${VITE_PORT}"
  ) >"${FRONTEND_LOG}" 2>&1 &
  FRONTEND_PID=$!
}

stop_child_process() {
  local pid="$1"
  local label="$2"
  local attempt=0
  if [[ -z "${pid}" ]] || ! kill -0 "${pid}" 2>/dev/null; then
    return 0
  fi
  kill "${pid}" >/dev/null 2>&1 || true
  while kill -0 "${pid}" 2>/dev/null && ((attempt < 30)); do
    sleep 0.1
    attempt=$((attempt + 1))
  done
  if kill -0 "${pid}" 2>/dev/null; then
    log "${label} 未在 3 秒内退出，发送 SIGKILL"
    kill -KILL "${pid}" >/dev/null 2>&1 || true
  fi
  wait "${pid}" 2>/dev/null || true
}

shutdown() {
  local exit_code="${1:-0}"
  if [[ "${SHUTTING_DOWN}" == "1" ]]; then
    return 0
  fi
  SHUTTING_DOWN=1
  trap '' INT TERM
  trap - EXIT
  log "收到退出信号，清理启动脚本子进程..."
  stop_child_process "${LOG_STREAM_PID}" "Compose 日志跟随进程"
  stop_child_process "${FRONTEND_PID}" "前端进程"
  stop_child_process "${BACKEND_PID}" "后端进程"
  if [[ "${START_COMPOSE_SERVICES}" == "1" && "${COMPOSE_DOWN_ON_EXIT}" == "1" ]] && data_sync_is_active; then
    ACTIVE_DATA_SYNC=1
  fi
  if [[ "${START_COMPOSE_SERVICES}" == "1" && "${COMPOSE_STARTED}" == "1" && "${COMPOSE_DOWN_ON_EXIT}" == "1" && "${ACTIVE_DATA_SYNC}" == "1" && "${ALLOW_ACTIVE_SYNC_SHUTDOWN}" != "1" ]]; then
    log "检测到数据同步仍在运行，忽略 LEAN_COMPOSE_DOWN_ON_EXIT=1；如确需关闭请设置 LEAN_ALLOW_ACTIVE_SYNC_SHUTDOWN=1"
  elif [[ "${START_COMPOSE_SERVICES}" == "1" && "${COMPOSE_STARTED}" == "1" && "${COMPOSE_DOWN_ON_EXIT}" == "1" ]]; then
    (
      cd "${COMPOSE_PROJECT_DIR}"
      docker compose --project-directory "${COMPOSE_PROJECT_DIR}" -p "${COMPOSE_PROJECT_NAME}" down --timeout 10
    )
  elif [[ "${START_COMPOSE_SERVICES}" == "1" && "${COMPOSE_STARTED}" == "1" ]]; then
    log "保留 MySQL、API 与 worker 容器运行；如需退出时清理，请设置 LEAN_COMPOSE_DOWN_ON_EXIT=1"
  fi
  if [[ "${LOCK_ACQUIRED}" == "1" ]]; then
    rm -f "${LOCK_DIR}/pid"
    rmdir "${LOCK_DIR}" 2>/dev/null || true
  fi
  exit "${exit_code}"
}

main() {
  trap 'shutdown 130' INT
  trap 'shutdown 143' TERM
  trap 'shutdown $?' EXIT
  parse_args "$@"
  acquire_single_instance_lock
  initialize_mysql_loader_password
  initialize_api_token

  cleanup_previous_instances
  resolve_ports
  check_dependencies
  if [[ "${START_COMPOSE_SERVICES}" == "1" ]]; then
    if data_sync_is_active; then
      ACTIVE_DATA_SYNC=1
      if [[ "${ALLOW_ACTIVE_SYNC_RECREATE}" == "1" ]]; then
        log "警告：检测到活动数据同步，但 LEAN_ALLOW_ACTIVE_SYNC_RECREATE=1，继续协调 Compose 服务"
        bound_docker_build_cache
        start_compose_services
        configure_mysql_loader
      else
        log "检测到活动数据同步，跳过 Compose 协调和 loader 密码变更，保护 worker 检查点"
        if [[ "${COMPOSE_BUILD}" == "1" ]]; then
          log "本次 --build 已延后；同步结束后重新运行脚本即可应用镜像更新"
        fi
      fi
    else
      bound_docker_build_cache
      start_compose_services
      configure_mysql_loader
    fi
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
    docker compose --project-directory "${COMPOSE_PROJECT_DIR}" -p "${COMPOSE_PROJECT_NAME}" logs -f --tail=120 api worker data-worker data-lineage-worker data-demand-worker beat &
    LOG_STREAM_PID=$!
    wait "${LOG_STREAM_PID}"
    LOG_STREAM_PID=""
  else
    log "后端PID: ${BACKEND_PID}"
    log "前端PID: ${FRONTEND_PID}"
    wait "${BACKEND_PID}" "${FRONTEND_PID}"
  fi
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  main "$@"
fi
