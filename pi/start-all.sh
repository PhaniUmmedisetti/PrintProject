#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="${ROOT_DIR}/backend"
FRONTEND_DIR="${ROOT_DIR}/frontend"
USER_NAME="${USER:-$(whoami)}"
ENABLE_KIOSK_UI="${PRINTPROJECT_ENABLE_KIOSK_UI:-0}"

BACKEND_PID_FILE="/tmp/printproject-pi-backend.pid"
FRONTEND_PID_FILE="/tmp/printproject-pi-frontend.pid"
KIOSK_PID_FILE="/tmp/printproject-pi-kiosk.pid"

log() {
  printf '[printproject] %s\n' "$1"
}

should_start_kiosk() {
  [[ "${ENABLE_KIOSK_UI}" == "1" ]]
}

start_services() {
  log "Building frontend"
  (
    cd "${FRONTEND_DIR}"
    npm run build
  )

  log "Restarting systemd services for ${USER_NAME}"
  sudo systemctl restart "printproject-pi@${USER_NAME}"
  sudo systemctl restart "printproject-frontend-serve@${USER_NAME}"
  if should_start_kiosk; then
    sudo systemctl restart "printproject-kiosk@${USER_NAME}"
  else
    log "Kiosk UI launch skipped (set PRINTPROJECT_ENABLE_KIOSK_UI=1 to enable)"
  fi

  log "Stack started via systemd"
  log "Check backend: sudo systemctl status printproject-pi@${USER_NAME} --no-pager"
  if should_start_kiosk; then
    log "Check kiosk:   sudo systemctl status printproject-kiosk@${USER_NAME} --no-pager"
  fi
}

stop_manual_process_if_running() {
  local pid_file="$1"
  if [[ -f "${pid_file}" ]]; then
    local pid
    pid="$(cat "${pid_file}")"
    if [[ -n "${pid}" ]] && kill -0 "${pid}" >/dev/null 2>&1; then
      kill "${pid}" >/dev/null 2>&1 || true
    fi
    rm -f "${pid_file}"
  fi
}

start_manual() {
  if [[ ! -x "${BACKEND_DIR}/venv/bin/python" ]]; then
    echo "Missing backend venv at ${BACKEND_DIR}/venv/bin/python" >&2
    exit 1
  fi

  log "Building frontend"
  (
    cd "${FRONTEND_DIR}"
    npm run build
  )

  stop_manual_process_if_running "${BACKEND_PID_FILE}"
  stop_manual_process_if_running "${FRONTEND_PID_FILE}"
  stop_manual_process_if_running "${KIOSK_PID_FILE}"

  log "Starting backend"
  (
    cd "${BACKEND_DIR}"
    nohup "${BACKEND_DIR}/venv/bin/python" -m uvicorn app.main:app --host 127.0.0.1 --port 8001 --log-level info \
      > /tmp/printproject-backend.log 2>&1 &
    echo $! > "${BACKEND_PID_FILE}"
  )

  log "Starting frontend preview"
  (
    cd "${FRONTEND_DIR}"
    nohup /usr/bin/npx vite preview --host 127.0.0.1 --port 4173 --strictPort \
      > /tmp/printproject-frontend.log 2>&1 &
    echo $! > "${FRONTEND_PID_FILE}"
  )

  sleep 3

  if should_start_kiosk; then
    log "Starting kiosk browser"
    (
      cd "${FRONTEND_DIR}"
      nohup /bin/bash "${FRONTEND_DIR}/start-kiosk.sh" http://localhost:4173 \
        > /tmp/printproject-kiosk.log 2>&1 &
      echo $! > "${KIOSK_PID_FILE}"
    )
  else
    log "Kiosk UI launch skipped (set PRINTPROJECT_ENABLE_KIOSK_UI=1 to enable)"
  fi

  log "Stack started manually"
  log "Backend log:  /tmp/printproject-backend.log"
  log "Frontend log: /tmp/printproject-frontend.log"
  if should_start_kiosk; then
    log "Kiosk log:    /tmp/printproject-kiosk.log"
  fi
}

if command -v systemctl >/dev/null 2>&1 && \
   [[ -f /etc/systemd/system/printproject-pi@.service ]] && \
   [[ -f /etc/systemd/system/printproject-frontend-serve@.service ]] && \
   [[ -f /etc/systemd/system/printproject-kiosk@.service ]]; then
  start_services
else
  start_manual
fi
