#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

MODE="${1:-onefile}"
if [[ "$MODE" != "onefile" && "$MODE" != "onedir" ]]; then
  echo "Uso: $0 [onefile|onedir]"
  exit 2
fi

if ! command -v wine >/dev/null 2>&1; then
  cat <<'MSG'
Wine não encontrado.

Para gerar .exe Windows no Linux, instale Wine e Python Windows dentro do Wine.

Ubuntu/Debian:
  sudo apt install wine

Depois instale Python para Windows pelo Wine ou use um prefixo Wine que já tenha Python.
MSG
  exit 1
fi

if wine py -3 --version >/dev/null 2>&1; then
  WIN_PYTHON=(wine py -3)
elif wine python --version >/dev/null 2>&1; then
  WIN_PYTHON=(wine python)
else
  cat <<'MSG'
Python Windows não encontrado dentro do Wine.

Instale Python para Windows dentro do Wine. Exemplo:
  wine python-3.12.4-amd64.exe

Depois teste:
  wine py -3 --version
ou:
  wine python --version
MSG
  exit 1
fi

echo "Python Windows detectado:"
"${WIN_PYTHON[@]}" --version

echo "Instalando dependências de build no Python Windows..."
"${WIN_PYTHON[@]}" -m pip install --upgrade pip
"${WIN_PYTHON[@]}" -m pip install \
  "pyinstaller>=6.0" \
  "PyQt6==6.7.1" \
  "PyQt6-WebEngine==6.7.0" \
  "pythonnet" \
  "bottle" \
  "typing_extensions" \
  "QtPy"

if ! "${WIN_PYTHON[@]}" - <<'PY' >/dev/null 2>&1
import proxy_tools
PY
then
  echo "Instalando proxy_tools manualmente para contornar bug CopyFile2 do Wine..."
  cache_dir=".cache/proxy-tools"
  rm -rf "$cache_dir"
  mkdir -p "$cache_dir"
  curl -L --fail -o "$cache_dir/proxy_tools-0.1.0.tar.gz" \
    "https://files.pythonhosted.org/packages/source/p/proxy_tools/proxy_tools-0.1.0.tar.gz"
  tar -xzf "$cache_dir/proxy_tools-0.1.0.tar.gz" -C "$cache_dir"
  win_site="$("${WIN_PYTHON[@]}" - <<'PY'
import site
print(site.getsitepackages()[-1])
PY
)"
  linux_site="$(winepath -u "$win_site")"
  cp -R "$cache_dir/proxy_tools-0.1.0/proxy_tools" "$linux_site/"
  cp -R "$cache_dir/proxy_tools-0.1.0/proxy_tools.egg-info" "$linux_site/"
fi

"${WIN_PYTHON[@]}" -m pip install --no-deps "pywebview>=5.0"
"${WIN_PYTHON[@]}" -m pip check

mode_flag="--onefile"
if [[ "$MODE" == "onedir" ]]; then
  mode_flag="--onedir"
fi

echo "Limpando build Windows anterior..."
rm -rf "build/windows" "dist/windows"

echo "Gerando Elyra Installer.exe..."
installer_web_path="$(winepath -w "$ROOT/installer_web")"
"${WIN_PYTHON[@]}" -m PyInstaller \
  --noconfirm \
  --clean \
  --name "Elyra Installer" \
  "$mode_flag" \
  --windowed \
  --distpath "dist/windows" \
  --workpath "build/windows" \
  --specpath "build/windows" \
  --add-data "$installer_web_path;installer_web" \
  "installer_app.py"

if [[ "$MODE" == "onefile" ]]; then
  echo "EXE gerado em: dist/windows/Elyra Installer.exe"
else
  echo "Build gerado em: dist/windows/Elyra Installer/"
fi
