#!/bin/bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
APPDIR="$ROOT/packaging/linux/AppDir"
BIN_SOURCE="$ROOT/dist/Elyra Installer"
APPIMAGETOOL="$ROOT/packaging/linux/appimagetool-x86_64.AppImage"
OUT_DIR="$ROOT/dist"
OUT="$OUT_DIR/Elyra-Installer-x86_64.AppImage"

cd "$ROOT"
if [ "${SKIP_INSTALLER_BUILD:-0}" != "1" ]; then
  PYTHON="${PYTHON:-$ROOT/.venv/bin/python}"
  if [ ! -x "$PYTHON" ]; then
    python3 -m venv "$ROOT/.venv"
  fi
  "$PYTHON" build_installer.py --mode onefile
fi

rm -rf "$APPDIR"
mkdir -p "$APPDIR/usr/bin" "$APPDIR/usr/share/applications"
mkdir -p "$APPDIR/usr/share/icons/hicolor/256x256/apps"

cp "$BIN_SOURCE" "$APPDIR/usr/bin/elyra-installer"
chmod +x "$APPDIR/usr/bin/elyra-installer"
cp "$ROOT/packaging/linux/elyra-installer.desktop" "$APPDIR/elyra-installer.desktop"
cp "$ROOT/packaging/linux/elyra-installer.desktop" "$APPDIR/usr/share/applications/elyra-installer.desktop"
cp "$ROOT/packaging/linux/elyra-installer.svg" "$APPDIR/elyra-installer.svg"
cp "$ROOT/packaging/linux/elyra-installer.svg" "$APPDIR/usr/share/icons/hicolor/256x256/apps/elyra-installer.svg"

cat > "$APPDIR/AppRun" <<'APPRUN'
#!/bin/bash
HERE="$(dirname "$(readlink -f "$0")")"
exec "$HERE/usr/bin/elyra-installer" "$@"
APPRUN
chmod +x "$APPDIR/AppRun"

if [ ! -x "$APPIMAGETOOL" ]; then
  echo "Baixando appimagetool..."
  curl -L -o "$APPIMAGETOOL" "https://github.com/AppImage/AppImageKit/releases/download/continuous/appimagetool-x86_64.AppImage"
  chmod +x "$APPIMAGETOOL"
fi

mkdir -p "$OUT_DIR"
rm -f "$OUT"
ARCH=x86_64 "$APPIMAGETOOL" "$APPDIR" "$OUT"
echo "AppImage gerado: $OUT"
