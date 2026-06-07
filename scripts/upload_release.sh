#!/usr/bin/env bash
set -euo pipefail

if ! command -v gh >/dev/null 2>&1; then
  echo "Por favor instale o GitHub CLI (gh) e autentique-se com 'gh auth login'." >&2
  exit 1
fi

if [ $# -lt 3 ]; then
  echo "Uso: $0 <tag> <release-name> <asset1> [asset2 ...]" >&2
  echo "Ex: $0 v1.0.0 \"Elyra Installer 1.0.0\" dist/Elyra-Installer-x86_64.AppImage dist/elyra-installer_1.0.0_amd64.deb" >&2
  exit 1
fi

tag="$1"; shift
name="$1"; shift

echo "Criando release '$tag' ('$name') e adicionando $# assets..."

# Create or update the release and upload assets
gh release create "$tag" --title "$name" --notes "Release $name" "$@"

echo "Upload concluído. Abra: https://github.com/<owner>/<repo>/releases/tag/$tag"
