#!/usr/bin/env bash
set -Eeuo pipefail

BASE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$BASE_DIR"

if command -v df >/dev/null 2>&1; then
  FREE_MB="$(df -Pm "$BASE_DIR" | awk 'NR==2 {print $4}')"
  if [[ "${FREE_MB:-0}" -lt 512 ]]; then
    echo "[warn] Espaço livre baixo (${FREE_MB} MB). Recomenda-se >= 512 MB."
  fi
fi

# Auto-reexec em tmux quando --tui-rs for solicitado fora de sessão tmux.
# Evita o erro operacional mais comum no uso via VNC.
ORIGINAL_ARGS=("$@")
WANT_TUI_RS=0
TAKEOVER_ON_LOCK=0
for arg in "${ORIGINAL_ARGS[@]}"; do
  case "$arg" in
    --tui-rs) WANT_TUI_RS=1 ;;
    --no-tui-rs) WANT_TUI_RS=0 ;;
    --takeover-running|--force-takeover) TAKEOVER_ON_LOCK=1 ;;
    --no-takeover-running) TAKEOVER_ON_LOCK=0 ;;
  esac
done
TAKEOVER_WAIT_SECONDS="${TAKEOVER_WAIT_SECONDS:-20}"
AUTO_TMUX_FOR_TUI_RS="${AUTO_TMUX_FOR_TUI_RS:-1}"
if [[ "$AUTO_TMUX_FOR_TUI_RS" == "1" && "$WANT_TUI_RS" == "1" && -z "${TMUX:-}" && -z "${CRAWLER_AUTO_TMUX_REEXEC:-}" ]]; then
  if command -v tmux >/dev/null 2>&1; then
    SESSION_BASE="${AUTO_TMUX_SESSION_NAME:-crawler}"
    SESSION_NAME="$SESSION_BASE"
    if tmux has-session -t "$SESSION_NAME" >/dev/null 2>&1; then
      SESSION_NAME="${SESSION_BASE}_$(date +%H%M%S)"
    fi

    REEXEC_BASH_BIN="${BASH:-bash}"
    printf -v REEXEC_CMD '%q %q ' "$REEXEC_BASH_BIN" "$BASE_DIR/run_crawler_rpi.sh"
    printf -v REEXEC_ARGS '%q ' "${ORIGINAL_ARGS[@]}"
    REEXEC_CMD="${REEXEC_CMD}${REEXEC_ARGS}"
    REEXEC_CMD="CRAWLER_AUTO_TMUX_REEXEC=1 $REEXEC_CMD"
    AUTO_TMUX_SHELL="${AUTO_TMUX_SHELL:-bash}"
    if ! command -v "$AUTO_TMUX_SHELL" >/dev/null 2>&1; then
      AUTO_TMUX_SHELL="sh"
    fi

    echo "[info] --tui-rs detectado fora de tmux. Abrindo sessão automaticamente: $SESSION_NAME"
    if ! tmux new-session -d -s "$SESSION_NAME" -c "$BASE_DIR" "$AUTO_TMUX_SHELL" >/dev/null 2>&1; then
      echo "[erro] Falha ao criar sessão tmux automática."
      exit 1
    fi
    # Habilita mouse no tmux para que scroll do mouse entre em copy-mode
    # em vez de vazar escape sequences (^[[A/^[[B) no stdin do crawler.
    tmux set-option -t "$SESSION_NAME" mouse on >/dev/null 2>&1 || true
    tmux send-keys -t "$SESSION_NAME:0.0" "$REEXEC_CMD" C-m
    exec tmux attach -t "$SESSION_NAME"
  else
    echo "[warn] --tui-rs foi solicitado, mas tmux não está instalado."
    echo "[warn] Instale tmux para habilitar TUI sincronizada com o crawler."
  fi
fi

# Habilita mouse no tmux para que scroll entre em copy-mode (sem vazar ^[[A/^[[B no stdin).
if [[ -n "${TMUX:-}" ]] && command -v tmux >/dev/null 2>&1; then
  tmux set-option mouse on >/dev/null 2>&1 || true
fi

LOCK_FILE=".crawler.lock"
CURRENT_BOOT_ID="$(cat /proc/sys/kernel/random/boot_id 2>/dev/null || true)"
LOCK_PID=""
LOCK_START_TICKS=""
LOCK_BOOT_ID=""

proc_start_ticks() {
  local pid="$1"
  awk '{print $22}' "/proc/$pid/stat" 2>/dev/null || true
}

proc_cmdline() {
  local pid="$1"
  tr '\0' ' ' < "/proc/$pid/cmdline" 2>/dev/null || true
}

wait_pid_exit() {
  local pid="$1"
  local timeout_secs="$2"
  local waited=0
  while kill -0 "$pid" >/dev/null 2>&1; do
    if (( waited >= timeout_secs )); then
      return 1
    fi
    sleep 1
    waited=$((waited + 1))
  done
  return 0
}

read_lock_file() {
  LOCK_PID=""
  LOCK_START_TICKS=""
  LOCK_BOOT_ID=""
  [[ -f "$LOCK_FILE" ]] || return 1

  if grep -q '^pid=' "$LOCK_FILE" 2>/dev/null; then
    while IFS='=' read -r key value; do
      case "$key" in
        pid) LOCK_PID="$value" ;;
        start_ticks) LOCK_START_TICKS="$value" ;;
        boot_id) LOCK_BOOT_ID="$value" ;;
      esac
    done < "$LOCK_FILE"
  else
    # Compatibilidade com lock legado (somente PID em texto puro).
    LOCK_PID="$(head -n1 "$LOCK_FILE" 2>/dev/null || true)"
  fi
  [[ "$LOCK_PID" =~ ^[0-9]+$ ]]
}

lock_owner_looks_like_crawler() {
  local pid="$1"
  local cmdline
  cmdline="$(proc_cmdline "$pid")"
  if [[ -z "$cmdline" ]]; then
    # Sem acesso ao cmdline: mantém lock por segurança.
    return 0
  fi
  [[ "$cmdline" == *"run_crawler_rpi.sh"* || "$cmdline" == *"-m crawler"* || "$cmdline" == *"adaptive_graph_crawler.py"* ]]
}

write_lock_file() {
  local self_start_ticks
  self_start_ticks="$(proc_start_ticks "$$")"
  cat > "$LOCK_FILE" <<EOF
pid=$$
start_ticks=${self_start_ticks:-unknown}
boot_id=${CURRENT_BOOT_ID:-unknown}
base_dir=$BASE_DIR
created_epoch=$(date +%s)
EOF
}

if read_lock_file; then
  if kill -0 "$LOCK_PID" >/dev/null 2>&1; then
    lock_is_valid=1
    stale_reason=""

    if [[ -n "$LOCK_BOOT_ID" && -n "$CURRENT_BOOT_ID" && "$LOCK_BOOT_ID" != "$CURRENT_BOOT_ID" ]]; then
      lock_is_valid=0
      stale_reason="boot diferente (lock antigo)"
    fi

    if [[ "$lock_is_valid" == "1" && -n "$LOCK_START_TICKS" && "$LOCK_START_TICKS" != "unknown" ]]; then
      PROC_START_TICKS="$(proc_start_ticks "$LOCK_PID")"
      if [[ -n "$PROC_START_TICKS" && "$PROC_START_TICKS" != "$LOCK_START_TICKS" ]]; then
        lock_is_valid=0
        stale_reason="PID reutilizado por outro processo"
      fi
    fi

    if [[ "$lock_is_valid" == "1" ]] && ! lock_owner_looks_like_crawler "$LOCK_PID"; then
      lock_is_valid=0
      stale_reason="PID ativo não parece ser do crawler"
    fi

    if [[ "$lock_is_valid" == "1" ]]; then
      if [[ "$TAKEOVER_ON_LOCK" == "1" ]]; then
        echo "[warn] Execução em andamento detectada (PID $LOCK_PID)."
        echo "[warn] --takeover-running ativo: solicitando parada graciosa da execução anterior..."
        kill -INT "$LOCK_PID" >/dev/null 2>&1 || true
        if ! wait_pid_exit "$LOCK_PID" "$TAKEOVER_WAIT_SECONDS"; then
          echo "[erro] A execução anterior não encerrou em ${TAKEOVER_WAIT_SECONDS}s (PID $LOCK_PID)."
          echo "[erro] Finalize manualmente e tente de novo: kill -INT $LOCK_PID"
          exit 1
        fi
        echo "[info] Execução anterior encerrada com sucesso. Prosseguindo..."
        rm -f "$LOCK_FILE"
      else
        echo "[erro] Já existe execução em andamento (PID $LOCK_PID)."
        echo "[erro] Pare o processo atual ou aguarde finalizar."
        echo "[erro] Dica: adicione --takeover-running para encerrar a execução anterior automaticamente."
        exit 1
      fi
    fi

    echo "[warn] Lock stale detectado ($stale_reason). Limpando automaticamente: $LOCK_FILE"
    rm -f "$LOCK_FILE"
  else
    echo "[warn] Lock órfão detectado (PID não existe). Limpando automaticamente: $LOCK_FILE"
    rm -f "$LOCK_FILE"
  fi
elif [[ -f "$LOCK_FILE" ]]; then
  echo "[warn] Lock inválido/corrompido detectado. Limpando automaticamente: $LOCK_FILE"
  rm -f "$LOCK_FILE"
fi

write_lock_file
TUI_WINDOW_RS=""
TUI_RS_QUIT_MONITOR_PID=""
OWNER_EXIT_MONITOR_PID=""
STATE_STALE_MONITOR_PID=""
CRAWLER_PID=""
CLEANUP_DONE=0
kill_and_wait() {
  local pid="$1"
  if [[ -n "$pid" ]]; then
    kill "$pid" >/dev/null 2>&1 || true
    wait "$pid" 2>/dev/null || true
  fi
}
cleanup() {
  [[ "$CLEANUP_DONE" == "1" ]] && return
  CLEANUP_DONE=1
  trap - EXIT HUP TERM INT
  if [[ -n "$TUI_WINDOW_RS" ]] && command -v tmux >/dev/null 2>&1; then
    tmux kill-window -t "$TUI_WINDOW_RS" >/dev/null 2>&1 || true
  fi
  kill_and_wait "$TUI_RS_QUIT_MONITOR_PID"
  kill_and_wait "$OWNER_EXIT_MONITOR_PID"
  kill_and_wait "$STATE_STALE_MONITOR_PID"
  if [[ -n "$CRAWLER_PID" ]] && kill -0 "$CRAWLER_PID" >/dev/null 2>&1; then
    kill -INT "$CRAWLER_PID" >/dev/null 2>&1 || true
    # Esperar crawler terminar checkpoint (max 15s)
    local i=0
    while kill -0 "$CRAWLER_PID" >/dev/null 2>&1 && (( i < 15 )); do
      sleep 1
      i=$((i + 1))
    done
    # Forçar se ainda vivo
    kill -KILL "$CRAWLER_PID" >/dev/null 2>&1 || true
  fi
  wait 2>/dev/null || true
  if [[ -n "${TUI_RS_QUIT_FILE:-}" ]]; then
    rm -f "$TUI_RS_QUIT_FILE" >/dev/null 2>&1 || true
  fi
  rm -f "$LOCK_FILE"
  # Matar sessão tmux auto-criada para eliminar a barra verde residual
  if [[ "${CRAWLER_AUTO_TMUX_REEXEC:-}" == "1" ]] && command -v tmux >/dev/null 2>&1 && [[ -n "${TMUX:-}" ]]; then
    tmux kill-session >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT HUP TERM INT

TUI_RS_ENABLED="${TUI_RS_ENABLED:-0}"
TUI_RS_MODE="${TUI_RS_MODE:-live}"
TUI_RS_REFRESH_SECONDS="${TUI_RS_REFRESH_SECONDS:-0.80}"
TUI_RS_FPS="${TUI_RS_FPS:-10}"
TUI_RS_STATE_FILE="${TUI_RS_STATE_FILE:-data/raw/adaptive_crawler_runtime.json}"
TUI_RS_STATE_FILE_EXPLICIT=0
TUI_RS_QUIT_FILE="${TUI_RS_QUIT_FILE:-.tui_rs_quit.signal}"
TUI_RS_ESC_QUIT="${TUI_RS_ESC_QUIT:-1}"
TUI_RS_HEALTH_FILE="${TUI_RS_HEALTH_FILE:-data/raw/tui_rs_health.json}"
TUI_RS_HEALTH_INTERVAL_SECONDS="${TUI_RS_HEALTH_INTERVAL_SECONDS:-1.00}"
TUI_RS_FOCUS="${TUI_RS_FOCUS:-tui}"
TUI_RS_RETRY_ON_EARLY_EXIT="${TUI_RS_RETRY_ON_EARLY_EXIT:-1}"
RUNTIME_STATE_ENABLED="${RUNTIME_STATE_ENABLED:-1}"
RUNTIME_STATE_FILE="${RUNTIME_STATE_FILE:-data/raw/adaptive_crawler_runtime.json}"
RUNTIME_STATE_INTERVAL_SECONDS="${RUNTIME_STATE_INTERVAL_SECONDS:-2.0}"
STOP_ON_OWNER_EXIT="${STOP_ON_OWNER_EXIT:-1}"
OWNER_EXIT_GRACE_SECONDS="${OWNER_EXIT_GRACE_SECONDS:-5}"
STATE_STALE_STOP_SECONDS="${STATE_STALE_STOP_SECONDS:-180}"
STATE_STALE_CHECK_INTERVAL_SECONDS="${STATE_STALE_CHECK_INTERVAL_SECONDS:-5}"
require_arg_value() {
  local name="$1" count="$2"
  if [[ "$count" -lt 2 ]]; then
    echo "[erro] $name requer valor."
    exit 1
  fi
}
PASSTHRU_ARGS=()
while [[ "$#" -gt 0 ]]; do
  case "$1" in
    --tui-rs)
      TUI_RS_ENABLED=1
      shift
      ;;
    --takeover-running|--force-takeover)
      TAKEOVER_ON_LOCK=1
      shift
      ;;
    --no-takeover-running)
      TAKEOVER_ON_LOCK=0
      shift
      ;;
    --no-tui-rs)
      TUI_RS_ENABLED=0
      shift
      ;;
    --tui-rs-mode)
      require_arg_value "$1" "$#"; TUI_RS_MODE="$2"; shift 2 ;;
    --tui-rs-refresh-seconds)
      require_arg_value "$1" "$#"; TUI_RS_REFRESH_SECONDS="$2"; shift 2 ;;
    --tui-rs-fps)
      require_arg_value "$1" "$#"; TUI_RS_FPS="$2"; shift 2 ;;
    --tui-rs-state-file)
      require_arg_value "$1" "$#"; TUI_RS_STATE_FILE="$2"; TUI_RS_STATE_FILE_EXPLICIT=1; shift 2 ;;
    --tui-rs-focus)
      require_arg_value "$1" "$#"; TUI_RS_FOCUS="$2"; shift 2 ;;
    --tui-rs-quit-file)
      require_arg_value "$1" "$#"; TUI_RS_QUIT_FILE="$2"; shift 2 ;;
    --tui-rs-esc-quit)
      TUI_RS_ESC_QUIT=1; shift ;;
    --no-tui-rs-esc-quit)
      TUI_RS_ESC_QUIT=0; shift ;;
    --tui-rs-health-file)
      require_arg_value "$1" "$#"; TUI_RS_HEALTH_FILE="$2"; shift 2 ;;
    --tui-rs-health-interval-seconds)
      require_arg_value "$1" "$#"; TUI_RS_HEALTH_INTERVAL_SECONDS="$2"; shift 2 ;;
    --runtime-state-file)
      require_arg_value "$1" "$#"; RUNTIME_STATE_FILE="$2"; shift 2 ;;
    --runtime-state-interval-seconds)
      require_arg_value "$1" "$#"; RUNTIME_STATE_INTERVAL_SECONDS="$2"; shift 2 ;;
    --no-runtime-state)
      RUNTIME_STATE_ENABLED=0; shift ;;
    --stop-on-owner-exit)
      STOP_ON_OWNER_EXIT=1; shift ;;
    --no-stop-on-owner-exit)
      STOP_ON_OWNER_EXIT=0; shift ;;
    --owner-exit-grace-seconds)
      require_arg_value "$1" "$#"; OWNER_EXIT_GRACE_SECONDS="$2"; shift 2 ;;
    --state-stale-stop-seconds)
      require_arg_value "$1" "$#"; STATE_STALE_STOP_SECONDS="$2"; shift 2 ;;
    --state-stale-check-interval-seconds)
      require_arg_value "$1" "$#"; STATE_STALE_CHECK_INTERVAL_SECONDS="$2"; shift 2 ;;
    --no-state-stale-stop)
      STATE_STALE_STOP_SECONDS=0
      shift
      ;;
    *)
      PASSTHRU_ARGS+=("$1")
      shift
      ;;
  esac
done
set -- "${PASSTHRU_ARGS[@]}"

if [[ "$TUI_RS_STATE_FILE_EXPLICIT" == "0" ]]; then
  TUI_RS_STATE_FILE="$RUNTIME_STATE_FILE"
fi

PYTHON_BIN="${PYTHON_BIN:-python3}"
if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  echo "[erro] Python não encontrado. Defina PYTHON_BIN ou instale python3."
  exit 1
fi

if ! "$PYTHON_BIN" -c "import venv" >/dev/null 2>&1; then
  echo "[info] Módulo venv ausente. Tentando instalar python3-venv e python3-pip..."
  if command -v sudo >/dev/null 2>&1; then
    sudo apt-get update
    sudo apt-get install -y python3-venv python3-pip
  else
    apt-get update
    apt-get install -y python3-venv python3-pip
  fi
fi

VENV_DIR=".venv"
if [[ ! -x "$VENV_DIR/bin/python" ]]; then
  echo "[info] Criando ambiente virtual em $VENV_DIR"
  "$PYTHON_BIN" -m venv "$VENV_DIR"
fi

PY="$VENV_DIR/bin/python"
PIP="$VENV_DIR/bin/pip"

PIP_BOOTSTRAP_MARKER="$VENV_DIR/.pip_bootstrapped"
if [[ ! -f "$PIP_BOOTSTRAP_MARKER" ]]; then
  "$PY" -m ensurepip --upgrade >/dev/null 2>&1 || true
  "$PY" -m pip install --upgrade pip setuptools wheel --disable-pip-version-check
  touch "$PIP_BOOTSTRAP_MARKER"
fi

if [[ ! -f "requirements.txt" ]]; then
  echo "[erro] requirements.txt não encontrado na raiz do projeto."
  exit 1
fi

MISSING="$("$PY" - <<'PY'
import importlib.util

checks = [
    ("beautifulsoup4", "bs4"),
    ("diskcache", "diskcache"),
    ("httpx", "httpx"),
    ("tenacity", "tenacity"),
    ("numpy", "numpy"),
    ("pandas", "pandas"),
    ("scikit-learn", "sklearn"),
]

missing = [pkg for pkg, mod in checks if importlib.util.find_spec(mod) is None]
print(",".join(missing))
PY
)"

if [[ -n "$MISSING" ]]; then
  echo "[info] Dependências faltantes: $MISSING"
  if ! "$PY" - <<'PY'
import urllib.request
urllib.request.urlopen("https://pypi.org/simple", timeout=8).read(16)
print("ok")
PY
  then
    echo "[erro] Sem acesso ao PyPI no momento. Não foi possível instalar dependências."
    exit 1
  fi
  "$PIP" install -r requirements.txt --retries 5 --timeout 60 --disable-pip-version-check
else
  echo "[info] Dependências já instaladas."
fi

CRAWLER_PKG="crawler"
if [[ ! -d "$CRAWLER_PKG" ]]; then
  echo "[erro] Pacote principal não encontrado: $CRAWLER_PKG"
  exit 1
fi
TUI_RS_SCRIPT="tui_rs/run_tui_rs.sh"
STATE_FILE="data/raw/adaptive_crawler_state.json"
DATASET_JSON="data/processed/players_dataset.json"
DATASET_CSV="data/processed/players_dataset.csv"
DATASET_PARQUET="data/processed/players_dataset.parquet"
ITEMS_PARQUET="data/processed/players_items.parquet"

make_abs() {
  local varname="$1"
  local val="${!varname}"
  if [[ "$val" != /* ]]; then
    eval "$varname=\"$BASE_DIR/$val\""
  fi
}
make_abs RUNTIME_STATE_FILE

if [[ "$#" -eq 0 ]]; then
  if ! "$PY" - <<'PY'
import json
from pathlib import Path
p = Path("data/raw/adaptive_crawler_state.json")
if not p.exists():
    raise SystemExit(1)
s = json.loads(p.read_text(encoding="utf-8"))
players = s.get("players", {})
if not isinstance(players, dict) or len(players) == 0:
    raise SystemExit(1)
print("ok")
PY
  then
    echo "[erro] Sem URL seed e sem estado válido em data/raw/adaptive_crawler_state.json."
    echo "[erro] Passe a URL do personagem na primeira execução."
    exit 1
  fi
fi

if [[ "$TUI_RS_ENABLED" == "1" ]]; then
  make_abs TUI_RS_SCRIPT
  make_abs TUI_RS_STATE_FILE
  make_abs TUI_RS_QUIT_FILE
  make_abs TUI_RS_HEALTH_FILE
  if [[ "$RUNTIME_STATE_ENABLED" == "1" ]]; then
    echo "[info] Runtime state leve ativo: $RUNTIME_STATE_FILE (intervalo=${RUNTIME_STATE_INTERVAL_SECONDS}s)"
    echo "[info] TUI Rust lendo runtime state: $TUI_RS_STATE_FILE"
  fi
  rm -f "$TUI_RS_QUIT_FILE" >/dev/null 2>&1 || true
  if [[ ! -f "$TUI_RS_SCRIPT" ]]; then
    echo "[warn] --tui-rs ignorado: script TUI Rust não encontrado ($TUI_RS_SCRIPT)."
    TUI_RS_ENABLED=0
  elif [[ "$TUI_RS_MODE" != "live" && "$TUI_RS_MODE" != "demo" && "$TUI_RS_MODE" != "text" ]]; then
    echo "[warn] --tui-rs-mode inválido ($TUI_RS_MODE). Usando 'live'."
    TUI_RS_MODE="live"
  elif [[ "$TUI_RS_FOCUS" != "tui" && "$TUI_RS_FOCUS" != "crawler" && "$TUI_RS_FOCUS" != "none" ]]; then
    echo "[warn] --tui-rs-focus inválido ($TUI_RS_FOCUS). Usando 'tui'."
    TUI_RS_FOCUS="tui"
  fi
fi

if [[ "$TUI_RS_ENABLED" == "1" ]]; then
  if command -v tmux >/dev/null 2>&1 && [[ -n "${TMUX:-}" ]]; then
    CRAWLER_WINDOW_ID="$(tmux display-message -p '#{window_id}' 2>/dev/null || true)"
    if [[ -f "$HOME/.cargo/env" ]]; then
      # shellcheck disable=SC1090
      source "$HOME/.cargo/env"
    fi
    if ! command -v cargo >/dev/null 2>&1; then
      echo "[warn] --tui-rs ignorado: cargo/rust não encontrado no PATH."
      TUI_RS_ENABLED=0
    else
      chmod +x "$TUI_RS_SCRIPT" >/dev/null 2>&1 || true
      printf -v TUI_RS_CMD '%q ' \
        "$TUI_RS_SCRIPT" \
        --mode "$TUI_RS_MODE" \
        --state-file "$TUI_RS_STATE_FILE" \
        --refresh-seconds "$TUI_RS_REFRESH_SECONDS" \
        --fps "$TUI_RS_FPS" \
        --quit-file "$TUI_RS_QUIT_FILE"
      if [[ "$TUI_RS_ESC_QUIT" == "1" ]]; then
        printf -v TUI_RS_CMD '%s%q ' "$TUI_RS_CMD" --esc-quit
      fi
      printf -v TUI_RS_CMD '%s%q %q %q %q ' \
        "$TUI_RS_CMD" \
        --health-file "$TUI_RS_HEALTH_FILE" \
        --health-interval-seconds "$TUI_RS_HEALTH_INTERVAL_SECONDS"
      TUI_WINDOW_RS="$(tmux new-window -d -P -F '#{window_id}' -n crawler_tui_rs "$TUI_RS_CMD")"
      tmux set-window-option -t "$TUI_WINDOW_RS" remain-on-exit on >/dev/null 2>&1 || true
      echo "[info] TUI Rust ativa em janela tmux dedicada: $TUI_WINDOW_RS (nome: crawler_tui_rs)"
      echo "[info] Dica: troque para a TUI com 'tmux select-window -t $TUI_WINDOW_RS'"
      if [[ "$TUI_RS_ESC_QUIT" == "1" ]]; then
        echo "[info] Tecla ESC na TUI inicia quit total (crawler + TUI)."
      else
        echo "[info] Quit total da TUI: pressione q duas vezes em até 2s."
      fi
      echo "[info] Health snapshot TUI (sobrescreve, sem spam): $TUI_RS_HEALTH_FILE"
      if [[ -n "$CRAWLER_WINDOW_ID" ]]; then
        echo "[info] Janela do crawler atual: $CRAWLER_WINDOW_ID"
      fi
      sleep 0.8
      TUI_RS_PANE_DEAD="$(tmux list-panes -t "$TUI_WINDOW_RS" -F '#{pane_dead}' 2>/dev/null | head -n1 || true)"
      if [[ "$TUI_RS_PANE_DEAD" == "1" ]]; then
        echo "[erro] A janela da TUI Rust encerrou logo após iniciar. Últimas linhas:"
        tmux capture-pane -pt "$TUI_WINDOW_RS" -S -60 | tail -n 30 || true
        if [[ "$TUI_RS_RETRY_ON_EARLY_EXIT" == "1" ]]; then
          echo "[warn] Tentando relançar a TUI Rust uma única vez..."
          tmux kill-window -t "$TUI_WINDOW_RS" >/dev/null 2>&1 || true
          TUI_WINDOW_RS="$(tmux new-window -d -P -F '#{window_id}' -n crawler_tui_rs "$TUI_RS_CMD")"
          tmux set-window-option -t "$TUI_WINDOW_RS" remain-on-exit on >/dev/null 2>&1 || true
          sleep 0.8
          TUI_RS_PANE_DEAD="$(tmux list-panes -t "$TUI_WINDOW_RS" -F '#{pane_dead}' 2>/dev/null | head -n1 || true)"
          if [[ "$TUI_RS_PANE_DEAD" == "1" ]]; then
            echo "[erro] A TUI Rust encerrou cedo também no retry. Últimas linhas:"
            tmux capture-pane -pt "$TUI_WINDOW_RS" -S -60 | tail -n 30 || true
          fi
        fi
      fi

      # Em execução normal, evita "Pane is dead" preso na tela após quit.
      if [[ "$TUI_RS_PANE_DEAD" != "1" ]]; then
        tmux set-window-option -t "$TUI_WINDOW_RS" remain-on-exit off >/dev/null 2>&1 || true
      fi

      if [[ "$TUI_RS_PANE_DEAD" != "1" && "$TUI_RS_FOCUS" == "tui" ]]; then
        tmux select-window -t "$TUI_WINDOW_RS" >/dev/null 2>&1 || true
      elif [[ "$TUI_RS_PANE_DEAD" != "1" && "$TUI_RS_FOCUS" == "crawler" && -n "$CRAWLER_WINDOW_ID" ]]; then
        tmux select-window -t "$CRAWLER_WINDOW_ID" >/dev/null 2>&1 || true
      fi
    fi
  else
    echo "[warn] --tui-rs requer execução dentro de uma sessão tmux para exibição sincronizada."
    echo "[warn] Continuando sem TUI Rust. (Dica: rode 'tmux' e execute o mesmo comando.)"
    TUI_RS_ENABLED=0
  fi
fi

MAIN_PID="$$"
if [[ "${STATE_STALE_STOP_SECONDS:-0}" != "0" ]]; then
  STATE_FILE_MONITOR_PATH="$STATE_FILE"
  if [[ "$RUNTIME_STATE_ENABLED" == "1" ]]; then
    STATE_FILE_MONITOR_PATH="$RUNTIME_STATE_FILE"
  fi
  if [[ "$STATE_FILE_MONITOR_PATH" != /* ]]; then
    STATE_FILE_MONITOR_PATH="$BASE_DIR/$STATE_FILE_MONITOR_PATH"
  fi
  (
    last_mtime=""
    last_change_epoch="$(date +%s)"
    while kill -0 "$MAIN_PID" >/dev/null 2>&1; do
      if [[ -f "$STATE_FILE_MONITOR_PATH" ]]; then
        mtime="$(stat -c %Y "$STATE_FILE_MONITOR_PATH" 2>/dev/null || true)"
        now_epoch="$(date +%s)"
        if [[ -n "$mtime" && "$mtime" != "0" ]]; then
          if [[ "$mtime" != "$last_mtime" ]]; then
            last_mtime="$mtime"
            last_change_epoch="$now_epoch"
          fi
          stale_for=$((now_epoch - last_change_epoch))
          if (( stale_for >= STATE_STALE_STOP_SECONDS )); then
            echo "[erro] Arquivo monitorado sem atualização por ${stale_for}s (limite=${STATE_STALE_STOP_SECONDS}s)."
            echo "[erro] Arquivo: $STATE_FILE_MONITOR_PATH"
            echo "[erro] Encerrando crawler para evitar travamento silencioso."
            kill -INT "$MAIN_PID" >/dev/null 2>&1 || true
            break
          fi
        fi
      fi
      sleep "${STATE_STALE_CHECK_INTERVAL_SECONDS}"
    done
  ) &
  STATE_STALE_MONITOR_PID="$!"
  echo "[info] Monitor anti-freeze ativo em: $STATE_FILE_MONITOR_PATH (limite=${STATE_STALE_STOP_SECONDS}s, check=${STATE_STALE_CHECK_INTERVAL_SECONDS}s)."
fi

if [[ "$STOP_ON_OWNER_EXIT" == "1" ]]; then
  if command -v tmux >/dev/null 2>&1 && [[ -n "${TMUX:-}" ]]; then
    if [[ "${CRAWLER_AUTO_TMUX_REEXEC:-}" == "1" ]]; then
      # Sessão tmux auto-criada: o crawler deve sobreviver ao detach.
      # Não monitorar session_attached — a sessão existe para persistir.
      echo "[info] Monitor anti-órfão desativado (sessão tmux auto-criada, crawler persiste ao detach)."
    else
      TMUX_SESSION_ID="$(tmux display-message -p '#{session_id}' 2>/dev/null || true)"
      TMUX_ATTACHED_START="$(tmux display-message -p '#{session_attached}' 2>/dev/null || echo 0)"
      if [[ "$TMUX_ATTACHED_START" =~ ^[0-9]+$ ]] && (( TMUX_ATTACHED_START > 0 )) && [[ -n "$TMUX_SESSION_ID" ]]; then
        (
          detached_for=0
          while kill -0 "$MAIN_PID" >/dev/null 2>&1; do
            # Check if the tmux server is still alive; if not, treat as immediate detach
            if ! tmux list-sessions >/dev/null 2>&1; then
              echo "[warn] Tmux server encerrado. Finalizando crawler para evitar processo órfão."
              kill -INT "$MAIN_PID" >/dev/null 2>&1 || true
              break
            fi
            attached_now="$(tmux display-message -p -t "$TMUX_SESSION_ID" '#{session_attached}' 2>/dev/null || echo 0)"
            if [[ "$attached_now" =~ ^[0-9]+$ ]] && (( attached_now == 0 )); then
              detached_for=$((detached_for + 1))
              if (( detached_for >= OWNER_EXIT_GRACE_SECONDS )); then
                echo "[warn] Sessão tmux sem cliente anexado por ${OWNER_EXIT_GRACE_SECONDS}s. Encerrando crawler para evitar processo órfão."
                kill -INT "$MAIN_PID" >/dev/null 2>&1 || true
                break
              fi
            else
              detached_for=0
            fi
            sleep 1
          done
        ) &
        OWNER_EXIT_MONITOR_PID="$!"
        echo "[info] Monitor anti-órfão ativo (tmux): grace=${OWNER_EXIT_GRACE_SECONDS}s."
      fi
    fi
  else
    OWNER_PARENT_PID="$PPID"
    (
      while kill -0 "$MAIN_PID" >/dev/null 2>&1; do
        if ! kill -0 "$OWNER_PARENT_PID" >/dev/null 2>&1; then
          echo "[warn] Processo pai encerrado. Finalizando crawler para evitar processo órfão."
          kill -INT "$MAIN_PID" >/dev/null 2>&1 || true
          break
        fi
        sleep 1
      done
    ) &
    OWNER_EXIT_MONITOR_PID="$!"
    echo "[info] Monitor anti-órfão ativo (parent pid=$OWNER_PARENT_PID)."
  fi
fi

echo "[info] Iniciando crawler..."
echo "[info] Use Ctrl+C para parar com checkpoint seguro."
CRAWLER_RUNTIME_ARGS=()
if [[ "$RUNTIME_STATE_ENABLED" == "1" ]]; then
  CRAWLER_RUNTIME_ARGS+=(--runtime-state-file "$RUNTIME_STATE_FILE")
  CRAWLER_RUNTIME_ARGS+=(--runtime-state-interval-seconds "$RUNTIME_STATE_INTERVAL_SECONDS")
else
  CRAWLER_RUNTIME_ARGS+=(--no-runtime-state)
fi
if [[ "$TUI_RS_ENABLED" == "1" ]]; then
  CRAWLER_RUNTIME_ARGS+=(--start-paused)
fi
set +e
# Capturar mtime do dataset para decidir se backup é necessário após shutdown
_DATASET_MTIME_BEFORE=""
if [[ -f "$DATASET_JSON" ]]; then
  _DATASET_MTIME_BEFORE="$(stat -c %Y "$DATASET_JSON" 2>/dev/null || echo "")"
fi
"$PY" -m crawler --progress-mode "${PROGRESS_MODE:-inline}" "${CRAWLER_RUNTIME_ARGS[@]}" "$@" &
CRAWLER_PID="$!"

if [[ "$TUI_RS_ENABLED" == "1" ]]; then
  MAIN_PID="$$"
  CRAWLER_PID_MON="$CRAWLER_PID"
  (
    while true; do
      if [[ -f "$TUI_RS_QUIT_FILE" ]]; then
        echo "[info] Quit total solicitado pela TUI Rust (q/ESC). Encerrando crawler..."
        if [[ -n "$TUI_WINDOW_RS" ]] && command -v tmux >/dev/null 2>&1; then
          tmux kill-window -t "$TUI_WINDOW_RS" >/dev/null 2>&1 || true
        fi
        kill -INT "$CRAWLER_PID_MON" >/dev/null 2>&1 || true
        break
      fi
      if ! kill -0 "$CRAWLER_PID_MON" >/dev/null 2>&1; then
        break
      fi
      sleep 0.10
    done
  ) &
  TUI_RS_QUIT_MONITOR_PID="$!"
fi

# Esperar crawler terminar; re-wait se interrompido por sinal
while kill -0 "$CRAWLER_PID" >/dev/null 2>&1; do
  wait "$CRAWLER_PID" 2>/dev/null || true
done
wait "$CRAWLER_PID" 2>/dev/null
CRAWLER_RC="$?"
set -e

AUTO_BACKUP="${AUTO_BACKUP:-1}"
BACKUP_DIR_ROOT="${BACKUP_DIR_ROOT:-data/snapshots/crawler_runs}"
SYNC_TARGET_DIR="${SYNC_TARGET_DIR:-}"
TIMESTAMP="$(date +%Y%m%d_%H%M%S)"

BACKUP_FILES=("$STATE_FILE" "$DATASET_JSON" "$DATASET_CSV" "$DATASET_PARQUET" "$ITEMS_PARQUET")
copy_files_to() {
  local dest="$1"
  mkdir -p "$dest"
  for f in "${BACKUP_FILES[@]}"; do
    [[ -f "$f" ]] && cp -f "$f" "$dest/"
  done
}

# Verificar se dataset mudou (evitar backup desnecessário)
_DATASET_MTIME_AFTER=""
if [[ -f "$DATASET_JSON" ]]; then
  _DATASET_MTIME_AFTER="$(stat -c %Y "$DATASET_JSON" 2>/dev/null || echo "")"
fi
_DATASET_CHANGED=0
if [[ -n "$_DATASET_MTIME_AFTER" && "$_DATASET_MTIME_AFTER" != "$_DATASET_MTIME_BEFORE" ]]; then
  _DATASET_CHANGED=1
fi

if [[ "$AUTO_BACKUP" == "1" ]]; then
  if [[ "$_DATASET_CHANGED" == "1" ]]; then
    RUN_BACKUP_DIR="$BACKUP_DIR_ROOT/$TIMESTAMP"
    copy_files_to "$RUN_BACKUP_DIR"
    echo "[info] Backup local salvo em: $RUN_BACKUP_DIR"
  else
    echo "[info] Dataset inalterado — backup ignorado"
  fi
fi

if [[ -n "$SYNC_TARGET_DIR" ]]; then
  if [[ "$_DATASET_CHANGED" == "1" ]]; then
    copy_files_to "$SYNC_TARGET_DIR"
    echo "[info] Sync concluído para: $SYNC_TARGET_DIR"
  else
    echo "[info] Dataset inalterado — sync ignorado"
  fi
fi

exit "$CRAWLER_RC"
