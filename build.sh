#!/bin/bash

# Build script para Elyra
# Cria executáveis para Windows, Mac e Linux

set -e

echo "🏗️  Elyra Build System v1.0"
echo "================================"

# Check if PyInstaller is installed
if ! command -v pyinstaller &> /dev/null; then
    echo "❌ PyInstaller não encontrado. Instalando..."
    pip install PyInstaller>=6.0
fi

# Clean old builds
echo "🧹 Limpando builds antigos..."
rm -rf build/ dist/ *.spec 2>/dev/null || true

# Create build
echo "📦 Compilando Elyra..."
pyinstaller \
    --name Elyra \
    --onefile \
    --windowed \
    --icon=web/icon.ico \
    --add-data="web:web" \
    --add-data="system_prompt.txt:." \
    --collect-all=pywebview \
    --collect-all=edge_tts \
    --collect-all=speech_recognition \
    --hidden-import=pywebview.api \
    app.py

echo "✅ Build completo!"
echo ""
echo "📁 Arquivo executável em: dist/Elyra"
echo ""
echo "🚀 Para distribuir:"
echo "   - Windows: Compacte o diretório 'dist/Elyra' e distribua"
echo "   - Linux: Execute './dist/Elyra/Elyra' ou crie um .deb com o arquivo .desktop"
echo "   - Mac: Use 'dist/Elyra.app'"
