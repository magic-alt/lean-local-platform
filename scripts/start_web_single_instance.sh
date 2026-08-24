#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE_PROJECT_NAME="${LEAN_COMPOSE_PROJECT_NAME:-lean-platform}"
START_COMPOSE_SERVICES="${LEAN_START_COMPOSE_SERVICES:-1}"
COMPOSE_STARTED=0
LOG_STREAM_PID=""
SHUTTING_DOWN=0
LOCK_DIR="${LEAN_SINGLE_INSTANCE_LOCK_DIR:-/tmp/${COMPOSE_PROJECT_NAME}-web-single-instance.lock}"
LOCK_ACQUIRED=0

log() {
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"
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
    log "已有启动脚本实例正在运行（PID ${owner_pid}）。"
    return 1
  fi
  rm -f "${LOCK_DIR}/pid"
  rmdir "${LOCK_DIR}" 2>/dev/null || true
  mkdir "${LOCK_DIR}"
  printf '%s\n' "$$" >"${LOCK_DIR}/pid"
  LOCK_ACQUIRED=1
}

shutdown() {
  local exit_code="${1:-0}"
  if [[ "${SHUTTING_DOWN}" == "1" ]]; then
    return "${exit_code}"
  fi
  SHUTTING_DOWN=1
  log "收到退出信号，正在清理前台日志进程。"
  if [[ -n "${LOG_STREAM_PID:-}" ]] && kill -0 "${LOG_STREAM_PID}" 2>/dev/null; then
    kill "${LOG_STREAM_PID}" 2>/dev/null || true
    wait "${LOG_STREAM_PID}" 2>/dev/null || true
  fi
  if [[ "${LEAN_COMPOSE_DOWN_ON_EXIT:-0}" == "1" && "${COMPOSE_STARTED:-0}" == "1" ]]; then
    "${PYTHON:-python3}" "${ROOT_DIR}/scripts/platformctl.py" --mode docker stop || true
  fi
  if [[ "${LOCK_ACQUIRED:-0}" == "1" ]]; then
    rm -f "${LOCK_DIR}/pid"
    rmdir "${LOCK_DIR}" 2>/dev/null || true
    LOCK_ACQUIRED=0
  fi
  trap - EXIT INT TERM
  return "${exit_code}"
}

main() {
  acquire_single_instance_lock
  trap 'shutdown 130; exit 130' INT
  trap 'shutdown 143; exit 143' TERM
  trap 'code=$?; shutdown "$code"; exit "$code"' EXIT
  local mode="${LEAN_DEPLOYMENT_MODE:-docker}"
  local profile="${LEAN_DEPLOYMENT_PROFILE:-full}"
  if [[ "${START_COMPOSE_SERVICES}" == "1" ]]; then
    "${PYTHON:-python3}" "${ROOT_DIR}/scripts/platformctl.py" --mode "${mode}" --profile "${profile}" start
    COMPOSE_STARTED=1
  fi
  log "平台已启动；FastAPI 同时提供 /api 与已构建的 React 静态文件。"
  if [[ "${mode}" == "docker" ]]; then
    docker compose --project-directory "${ROOT_DIR}" -p "${COMPOSE_PROJECT_NAME}" logs --follow --tail=100 api &
    LOG_STREAM_PID=$!
    wait "${LOG_STREAM_PID}"
  else
    while true; do sleep 3600; done
  fi
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  main "$@"
fi
