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

# No whoami fallback: a sudo install must carry SUDO_USER. Empty here is checked
# in cmd_install (and anywhere INSTALL_USER is used) so we fail early + clearly.
INSTALL_USER="${SUDO_USER:-}"
OLLAMA_BIN="$(command -v ollama || echo /opt/homebrew/bin/ollama)"

_need_root() { [[ "$(id -u)" == "0" ]] || { echo "Run with sudo." >&2; exit 1; }; }

_need_install_user() {
  [[ -n "${INSTALL_USER}" ]] || { echo "Must run with sudo (SUDO_USER unset)." >&2; exit 1; }
}

# Make a token value safe to drop into a plist <string>…</string> via sed.
# Two layers, applied in order:
#   1) XML-escape the chars that are illegal in XML text content (& < >) so the
#      rendered plist is well-formed (plutil-lint clean) even for a path like
#      "/tmp/a & b".
#   2) Backslash-escape the chars that are special on the REPLACEMENT side of a
#      sed `s|…|…|` (backslash, ampersand, and the `|` delimiter) — note the
#      `&amp;` produced by step 1 itself contains a literal `&` that sed would
#      otherwise reinterpret as "the whole match".
_xml_escape() {
  printf '%s' "$1" | sed -e 's/&/\&amp;/g' -e 's/</\&lt;/g' -e 's/>/\&gt;/g'
}
_sed_escape_repl() {
  printf '%s' "$1" | sed -e 's/[\\&|]/\\&/g'
}
_render_token() {
  _sed_escape_repl "$(_xml_escape "$1")"
}

_render() {
  local user_e repo_e ollama_e
  user_e="$(_render_token "${INSTALL_USER}")"
  repo_e="$(_render_token "${REPO_ROOT}")"
  ollama_e="$(_render_token "${OLLAMA_BIN}")"
  sed -e "s|__USER__|${user_e}|g" \
      -e "s|__REPO__|${repo_e}|g" \
      -e "s|__OLLAMA_BIN__|${ollama_e}|g" \
      "$1" > "$2"
  chown root:wheel "$2"
  chmod 640 "$2"
}

cmd_install() {
  _need_root
  _need_install_user
  mkdir -p "${REPO_ROOT}/backend/data/logs"
  chmod 700 "${REPO_ROOT}/backend/data/logs"
  chown "${INSTALL_USER}" "${REPO_ROOT}/backend/data/logs"
  # The launchd daemon runs as INSTALL_USER and writes runtime files to these
  # dirs: backend/config (license.json from license activation, profile managers)
  # and backend/assets/fonts (custom font uploads). If setup-mac.sh was run by a
  # different user, ensure the service user owns them or activation/upload fails.
  mkdir -p "${REPO_ROOT}/backend/assets/fonts"
  chown -R "${INSTALL_USER}" "${REPO_ROOT}/backend/config" "${REPO_ROOT}/backend/assets/fonts"
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

cmd_stop() {
  _need_root
  launchctl bootout "system/${SERVER_LABEL}" 2>/dev/null || true
  launchctl bootout "system/${OLLAMA_LABEL}" 2>/dev/null || true
  echo "stopped (services will auto-start again on next reboot)"
}

cmd_start() {
  _need_root
  # Re-bootstrap from disk; RunAtLoad=true launches immediately (no kickstart needed).
  launchctl bootstrap system "${LDAEMONS}/${OLLAMA_LABEL}.plist"
  launchctl bootstrap system "${LDAEMONS}/${SERVER_LABEL}.plist"
  echo "started"
}

cmd_restart() {
  _need_root
  launchctl bootout "system/${SERVER_LABEL}" 2>/dev/null || true
  launchctl bootout "system/${OLLAMA_LABEL}" 2>/dev/null || true
  launchctl bootstrap system "${LDAEMONS}/${OLLAMA_LABEL}.plist"
  launchctl bootstrap system "${LDAEMONS}/${SERVER_LABEL}.plist"
  echo "restarted"
}

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
  local log_dir="${REPO_ROOT}/backend/data/logs"
  local err_log="${log_dir}/server.err.log"
  local out_log="${log_dir}/server.out.log"
  if [[ ! -d "${log_dir}" ]] || { [[ ! -f "${err_log}" ]] && [[ ! -f "${out_log}" ]]; }; then
    echo "No logs yet — run install first."
    return 0
  fi
  tail -n 50 -F "${err_log}" "${out_log}"
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
