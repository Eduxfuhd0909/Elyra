#!/bin/bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
PYTHON="${PYTHON:-$ROOT/.venv/bin/python}"
if [ ! -x "$PYTHON" ]; then
  python3 -m venv "$ROOT/.venv"
fi
"$PYTHON" build_installer.py --mode onedir

if [ -d "dist/Elyra Installer.app" ]; then
  echo "APP gerado em: dist/Elyra Installer.app"
else
  echo "Build terminou, mas o .app não foi encontrado. Confira a pasta dist/."
  exit 1
fi
