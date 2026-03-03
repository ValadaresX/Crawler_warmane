#!/usr/bin/env bash
set -Eeuo pipefail

# Launcher simples para produção no Raspberry Pi 4.
# Edite apenas os valores abaixo.

# Suporte --rebuild-tui (substitui start_crawler_tui_rpi_rebuild.sh)
if [[ "${1:-}" == "--rebuild-tui" ]]; then
  export TUI_RS_FORCE_BUILD=1
  shift
fi

TAKEOVER_RUNNING=1

TUI_RS_MODE="live"
TUI_RS_FOCUS="tui"
TUI_RS_REFRESH_SECONDS="1.00"
TUI_RS_FPS="6"
TUI_RS_HEALTH_FILE="data/raw/tui_rs_health.json"
TUI_RS_HEALTH_INTERVAL_SECONDS="1.0"

RUNTIME_STATE_FILE="data/raw/adaptive_crawler_runtime.json"
RUNTIME_STATE_INTERVAL_SECONDS="1.0"
RUNTIME_CLASS_COUNTS_REFRESH_SECONDS="2.0"
STATE_STALE_STOP_SECONDS="180"
STATE_STALE_CHECK_INTERVAL_SECONDS="5"

PHASE="hybrid"
COLLECT_SURPLUS_CLASSES=1
RECOLLECT_AND_APPEND=1

PROFILES_PER_CYCLE="400"
HTTP_RPS="5.5"
HTTP_MAX_CONNECTIONS="10"
HTTP_MAX_RETRIES="6"
REQUEST_WALL_TIMEOUT_SECONDS="90"
MATCHINFO_REQUEST_WALL_TIMEOUT_SECONDS="45"
HISTORY_ROOT_MAX_SECONDS="180"
HISTORY_DETAIL_ERROR_STREAK_STOP="12"
CYCLE_MAX_SECONDS="420"

SKIP_FAILED=1
IDLE_STOP_SECONDS="120"
BLOCK_DETECT_CONSECUTIVE_ERRORS="8"

# Build forçado da TUI Rust no próximo start:
# 1 = recompila; 0 = usa cache quando possível
TUI_RS_FORCE_BUILD="${TUI_RS_FORCE_BUILD:-0}"

BASE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$BASE_DIR"

require_value() {
  local name="$1"
  local value="$2"
  if [[ -z "${value:-}" ]]; then
    echo "[erro] Valor vazio: $name"
    exit 1
  fi
}

require_value "BLOCK_DETECT_CONSECUTIVE_ERRORS" "$BLOCK_DETECT_CONSECUTIVE_ERRORS"
require_value "PROFILES_PER_CYCLE" "$PROFILES_PER_CYCLE"
require_value "HTTP_RPS" "$HTTP_RPS"
require_value "CYCLE_MAX_SECONDS" "$CYCLE_MAX_SECONDS"
require_value "HISTORY_ROOT_MAX_SECONDS" "$HISTORY_ROOT_MAX_SECONDS"

ARGS=()
if [[ "$TAKEOVER_RUNNING" == "1" ]]; then
  ARGS+=(--takeover-running)
fi

ARGS+=(
  --tui-rs
  --tui-rs-mode "$TUI_RS_MODE"
  --tui-rs-focus "$TUI_RS_FOCUS"
  --tui-rs-refresh-seconds "$TUI_RS_REFRESH_SECONDS"
  --tui-rs-fps "$TUI_RS_FPS"
  --tui-rs-health-file "$TUI_RS_HEALTH_FILE"
  --tui-rs-health-interval-seconds "$TUI_RS_HEALTH_INTERVAL_SECONDS"
  --runtime-state-file "$RUNTIME_STATE_FILE"
  --runtime-state-interval-seconds "$RUNTIME_STATE_INTERVAL_SECONDS"
  --runtime-class-counts-refresh-seconds "$RUNTIME_CLASS_COUNTS_REFRESH_SECONDS"
  --state-stale-stop-seconds "$STATE_STALE_STOP_SECONDS"
  --state-stale-check-interval-seconds "$STATE_STALE_CHECK_INTERVAL_SECONDS"
  --phase "$PHASE"
  --profiles-per-cycle "$PROFILES_PER_CYCLE"
  --http-rps "$HTTP_RPS"
  --http-max-connections "$HTTP_MAX_CONNECTIONS"
  --http-max-retries "$HTTP_MAX_RETRIES"
  --request-wall-timeout-seconds "$REQUEST_WALL_TIMEOUT_SECONDS"
  --matchinfo-request-wall-timeout-seconds "$MATCHINFO_REQUEST_WALL_TIMEOUT_SECONDS"
  --history-root-max-seconds "$HISTORY_ROOT_MAX_SECONDS"
  --history-detail-error-streak-stop "$HISTORY_DETAIL_ERROR_STREAK_STOP"
  --cycle-max-seconds "$CYCLE_MAX_SECONDS"
  --idle-stop-seconds "$IDLE_STOP_SECONDS"
  --block-detect-consecutive-errors "$BLOCK_DETECT_CONSECUTIVE_ERRORS"
)

append_flag() { [[ "${!1}" == "1" ]] && ARGS+=("$2"); }
append_flag COLLECT_SURPLUS_CLASSES --collect-surplus-classes
append_flag RECOLLECT_AND_APPEND --recollect-and-append
append_flag SKIP_FAILED --skip-failed

echo "[info] Iniciando via perfil fixo: start_crawler_tui_rpi.sh"
echo "[info] Para recompilar TUI Rust neste run: TUI_RS_FORCE_BUILD=1 ./start_crawler_tui_rpi.sh"

export TUI_RS_FORCE_BUILD
exec /usr/bin/bash "$BASE_DIR/run_crawler_rpi.sh" "${ARGS[@]}"
