#!/usr/bin/env bash
set -Eeuo pipefail

BASE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$BASE_DIR"

if [ -f "$HOME/.cargo/env" ]; then
  # shellcheck disable=SC1090
  . "$HOME/.cargo/env"
fi

if ! command -v cargo >/dev/null 2>&1; then
  echo "[erro] cargo nao encontrado. Instale rustup/rust antes."
  exit 1
fi

# SSD pode estar em ro. Usa alvo de build fora do SSD por padrao.
export CARGO_TARGET_DIR="${CARGO_TARGET_DIR:-$HOME/.cargo-target-rpi}"
mkdir -p "$CARGO_TARGET_DIR"

BIN_NAME="crawler_tui_rs"
BIN_PATH="$CARGO_TARGET_DIR/release/$BIN_NAME"
STAMP_PATH="$CARGO_TARGET_DIR/release/.${BIN_NAME}.buildstamp"
FORCE_BUILD="${TUI_RS_FORCE_BUILD:-0}"
NEEDS_BUILD=0

calc_build_fingerprint() {
  if command -v sha256sum >/dev/null 2>&1; then
    (
      cd "$BASE_DIR"
      {
        sha256sum Cargo.toml Cargo.lock
        find src -type f -name '*.rs' -print0 | sort -z | xargs -0 sha256sum
      } | sha256sum | awk '{print $1}'
    )
    return
  fi
  (
    cd "$BASE_DIR"
    {
      cksum Cargo.toml Cargo.lock
      find src -type f -name '*.rs' -print0 | sort -z | xargs -0 cksum
    } | cksum | awk '{print $1}'
  )
}

CURRENT_FINGERPRINT="$(calc_build_fingerprint)"
STORED_FINGERPRINT=""
if [[ -f "$STAMP_PATH" ]]; then
  STORED_FINGERPRINT="$(cat "$STAMP_PATH" 2>/dev/null || true)"
fi

if [[ "$FORCE_BUILD" == "1" ]]; then
  NEEDS_BUILD=1
elif [[ ! -x "$BIN_PATH" ]]; then
  NEEDS_BUILD=1
elif [[ "$CURRENT_FINGERPRINT" != "$STORED_FINGERPRINT" ]]; then
  NEEDS_BUILD=1
fi

if [[ "$NEEDS_BUILD" == "1" ]]; then
  echo "[info] Compilando TUI Rust (release)..."
  cargo build --release
  printf '%s\n' "$CURRENT_FINGERPRINT" > "$STAMP_PATH"
else
  echo "[info] Binario TUI Rust em cache (sem recompilar): $BIN_PATH"
fi

exec "$BIN_PATH" "$@"
