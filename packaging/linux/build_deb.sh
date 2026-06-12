#!/bin/bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
VERSION="${VERSION:-1.0.0}"
ARCH="${ARCH:-amd64}"
PKG_DIR="$ROOT/packaging/linux/build/elyra-installer_${VERSION}_${ARCH}"
BIN_SOURCE="$ROOT/dist/Elyra Installer"
OUT="$ROOT/dist/elyra-installer_${VERSION}_${ARCH}.deb"

cd "$ROOT"
if [ "${SKIP_INSTALLER_BUILD:-0}" != "1" ]; then
  PYTHON="${PYTHON:-$ROOT/.venv/bin/python}"
  if [ ! -x "$PYTHON" ]; then
    python3 -m venv "$ROOT/.venv"
  fi
  "$PYTHON" build_installer.py --mode onefile
fi

rm -rf "$PKG_DIR"
rm -f "$OUT"
mkdir -p "$PKG_DIR/DEBIAN" "$PKG_DIR/usr/bin" "$PKG_DIR/usr/share/applications" "$PKG_DIR/usr/share/pixmaps"

cp "$BIN_SOURCE" "$PKG_DIR/usr/bin/elyra-installer"
chmod 755 "$PKG_DIR/usr/bin/elyra-installer"
cp "$ROOT/packaging/linux/elyra-installer.desktop" "$PKG_DIR/usr/share/applications/elyra-installer.desktop"

cat > "$PKG_DIR/DEBIAN/control" <<CONTROL
Package: elyra-installer
Version: $VERSION
Section: utils
Priority: optional
Architecture: $ARCH
Maintainer: Elyra <noreply@example.com>
Depends: git, python3, python3-venv
Description: Instalador e atualizador da Elyra
 Painel gráfico para clonar, instalar, configurar e atualizar a Elyra.
CONTROL

dpkg-deb --build "$PKG_DIR" "$OUT"
echo "Deb gerado: $OUT"
