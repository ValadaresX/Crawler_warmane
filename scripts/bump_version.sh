#!/usr/bin/env bash
# bump_version.sh — Atualiza VERSION, pyproject.toml e tui_rs/Cargo.toml de uma vez.
# Uso: ./scripts/bump_version.sh 1.2.3
set -euo pipefail

NEW_VERSION="${1:-}"
if [ -z "$NEW_VERSION" ]; then
  echo "Uso: $0 <nova-versao>  (ex: 1.2.0)" >&2
  exit 1
fi

if ! echo "$NEW_VERSION" | grep -qE '^[0-9]+\.[0-9]+\.[0-9]+$'; then
  echo "Erro: versao deve seguir formato X.Y.Z (ex: 1.2.0)" >&2
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

OLD_VERSION="$(cat "$ROOT/VERSION" | tr -d '[:space:]')"
echo "Atualizando versao: $OLD_VERSION -> $NEW_VERSION"

# VERSION
printf '%s\n' "$NEW_VERSION" > "$ROOT/VERSION"

# pyproject.toml
sed -i "s/^version = \"$OLD_VERSION\"/version = \"$NEW_VERSION\"/" "$ROOT/pyproject.toml"

# tui_rs/Cargo.toml
sed -i "s/^version = \"$OLD_VERSION\"/version = \"$NEW_VERSION\"/" "$ROOT/tui_rs/Cargo.toml"

echo "Feito. Arquivos atualizados:"
echo "  VERSION             -> $NEW_VERSION"
echo "  pyproject.toml      -> $NEW_VERSION"
echo "  tui_rs/Cargo.toml   -> $NEW_VERSION"
echo ""
echo "Proximo passo: editar CHANGELOG.md, commit e tag."
