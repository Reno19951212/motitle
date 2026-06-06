#!/usr/bin/env bash
# motitle-service.sh — install/manage the MoTitle macOS LaunchDaemons.
# Usage: sudo ./motitle-service.sh <install|uninstall|start|stop|restart|status|logs>
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
LDAEMONS="/Library/LaunchDaemons"
SERVER_LABEL="com.motitle.server"
OLLAMA_LABEL="com.motitle.ollama"
PORT="${FLASK_PORT:-5001}"

INSTALL_USER="${SUDO_USER:-$(whoami)}"
OLLAMA_BIN="$(command -v ollama || echo /opt/homebrew/bin/ollama)"

_need_root() { [[ "$(id -u)" == "0" ]] || { echo "Run with sudo." >&2; exit 1; }; }

_render() {
  sed -e "s|__USER__|${INSTALL_USER}|g" \
      -e "s|__REPO__|${REPO_ROOT}|g" \
      -e "s|__OLLAMA_BIN__|${OLLAMA_BIN}|g" \
      "$1" > "$2"
  chown root:wheel "$2"
  chmod 644 "$2"
}

cmd_install() {
  _need_root
  mkdir -p "${REPO_ROOT}/backend/data/logs"
  chown "${INSTALL_USER}" "${REPO_ROOT}/backend/data/logs"
  sudo -u "${INSTALL_USER}" brew services stop ollama 2>/dev/null || true
  _render "${SCRIPT_DIR}/com.motitle.ollama.plist.template" "${LDAEMONS}/${OLLAMA_LABEL}.plist"
  _render "${SCRIPT_DIR}/com.motitle.server.plist.template" "${LDAEMONS}/${SERVER_LABEL}.plist"
  launchctl bootstrap system "${LDAEMONS}/${OLLAMA_LABEL}.plist"
  launchctl bootstrap system "${LDAEMONS}/${SERVER_LABEL}.plist"
  echo "Installed + loaded: ${OLLAMA_LABEL}, ${SERVER_LABEL}"
}

cmd_uninstall() {
  _need_root
  launchctl bootout "system/${SERVER_LABEL}" 2>/dev/null || true
  launchctl bootout "system/${OLLAMA_LABEL}" 2>/dev/null || true
  rm -f "${LDAEMONS}/${SERVER_LABEL}.plist" "${LDAEMONS}/${OLLAMA_LABEL}.plist"
  echo "Uninstalled."
}

cmd_start()   { _need_root; launchctl kickstart  "system/${OLLAMA_LABEL}"; launchctl kickstart  "system/${SERVER_LABEL}"; echo "started"; }
cmd_stop()    { _need_root; launchctl kill SIGTERM "system/${SERVER_LABEL}" 2>/dev/null || true; launchctl kill SIGTERM "system/${OLLAMA_LABEL}" 2>/dev/null || true; echo "stopped"; }
cmd_restart() { _need_root; launchctl kickstart -k "system/${OLLAMA_LABEL}"; launchctl kickstart -k "system/${SERVER_LABEL}"; echo "restarted"; }

cmd_status() {
  echo "== launchd =="
  launchctl print "system/${SERVER_LABEL}" 2>/dev/null | grep -E "state =|pid =" || echo "${SERVER_LABEL}: not loaded"
  launchctl print "system/${OLLAMA_LABEL}" 2>/dev/null | grep -E "state =|pid =" || echo "${OLLAMA_LABEL}: not loaded"
  echo "== health =="
  curl -sk "http://localhost:${PORT}/api/ready" || echo "(server not responding on ${PORT})"
  echo ""
  "${OLLAMA_BIN}" ps 2>/dev/null || echo "(ollama not responding)"
}

cmd_logs() {
  tail -n 50 -F "${REPO_ROOT}/backend/data/logs/server.err.log" "${REPO_ROOT}/backend/data/logs/server.out.log"
}

case "${1:-}" in
  install)   cmd_install ;;
  uninstall) cmd_uninstall ;;
  start)     cmd_start ;;
  stop)      cmd_stop ;;
  restart)   cmd_restart ;;
  status)    cmd_status ;;
  logs)      cmd_logs ;;
  *) echo "Usage: sudo $0 <install|uninstall|start|stop|restart|status|logs>"; exit 1 ;;
esac
