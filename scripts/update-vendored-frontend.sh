#!/usr/bin/env bash
# update-vendored-frontend.sh
#
# Rebuild the Vite frontend bundle and vendor it into:
#   1. src/epochix/_frontend/dist/   (Python package)
#   2. epochix-vscode/webview-dist/  (VS Code extension)
#
# Usage:
#   bash scripts/update-vendored-frontend.sh
#   bash scripts/update-vendored-frontend.sh --vscode-only
#   bash scripts/update-vendored-frontend.sh --python-only

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FRONTEND_DIR="$REPO_ROOT/frontend"
PYTHON_DIST="$REPO_ROOT/src/epochix/_frontend/dist"
VSCODE_DIST="$REPO_ROOT/epochix-vscode/webview-dist"

PYTHON_ONLY=false
VSCODE_ONLY=false

for arg in "$@"; do
  case $arg in
    --python-only) PYTHON_ONLY=true ;;
    --vscode-only) VSCODE_ONLY=true ;;
  esac
done

echo "▶  Building frontend bundle..."
cd "$FRONTEND_DIR"
npm ci --silent
npm run build

BUILT="$FRONTEND_DIR/dist"

if [ ! -d "$BUILT" ]; then
  echo "✗  Build failed — $BUILT not found."
  exit 1
fi

if [ "$VSCODE_ONLY" = false ]; then
  echo "▶  Vendoring into Python package ($PYTHON_DIST)..."
  rm -rf "$PYTHON_DIST"
  cp -r "$BUILT" "$PYTHON_DIST"
  echo "   Done: $(find "$PYTHON_DIST" -type f | wc -l) files"
fi

if [ "$PYTHON_ONLY" = false ]; then
  # NOT a copy of the server build above. The extension ships the output of
  # `build:webview` (vite.webview.config.js) — one nonce'd ./main.js and one
  # ./main.css, because the webview CSP admits exactly one script — and that is
  # what `vsce package` rebuilds via `vscode:prepublish`. Copying the server
  # bundle here meant local testing exercised an artifact that never ships,
  # which is how a blank standalone panel went out in 0.7.5 - 0.7.10.
  echo "▶  Building the webview bundle into $VSCODE_DIST..."
  cd "$FRONTEND_DIR"
  npm run build:webview
  echo "   Done: $(find "$VSCODE_DIST" -type f | wc -l) files"
fi

echo "✓  Frontend vendoring complete."
