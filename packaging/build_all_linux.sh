#!/bin/bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
PYTHON="${PYTHON:-$ROOT/.venv/bin/python}"
if [ ! -x "$PYTHON" ]; then
  python3 -m venv "$ROOT/.venv"
fi
"$PYTHON" build_installer.py --mode onefile
SKIP_INSTALLER_BUILD=1 bash packaging/linux/build_deb.sh
SKIP_INSTALLER_BUILD=1 bash packaging/linux/build_appimage.sh
