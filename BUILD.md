# 🚀 Guia de Build e Distribuição - Elyra

Este guia explica como criar executáveis profissionais para distribuir o Elyra.

## 📋 Pré-requisitos

- Python 3.10+
- pip
- Git (opcional)

### Instalar dependências de build:

```bash
pip install -r requirements-build.txt
```

## 🔨 Criando Executáveis

### 1. Linux - Executável .AppImage

```bash
# Instalar ferramenta AppImage
pip install AppImage

# Executar script de build
chmod +x build.sh
./build.sh

# Resultado: dist/Elyra (executável direto)
./dist/Elyra/Elyra
```

### 2. Windows - .exe pelo Windows

```bash
# No Windows CMD ou PowerShell:
packaging\windows\build_exe.bat
```

Resultado: `dist\Elyra Installer.exe`

### 3. Windows - .exe pelo Linux

PyInstaller não faz cross-build Windows usando Python Linux puro. Para gerar `.exe` no Linux, use Wine com Python Windows instalado dentro do Wine:

```bash
sudo apt install wine
# Instale Python para Windows no Wine, se ainda não tiver:
# wine python-3.12.4-amd64.exe

chmod +x packaging/windows/build_exe.sh
packaging/windows/build_exe.sh
```

Resultado: `dist/windows/Elyra Installer.exe`

Para gerar uma pasta em vez de arquivo único:

```bash
packaging/windows/build_exe.sh onedir
```

### 4. macOS - App Bundle

```bash
# Em Mac:
pip install -r requirements-build.txt

pyinstaller \
    --name Elyra \
    --onefile \
    --windowed \
    --icon=web/icon.icns \
    --add-data="web:web" \
    --add-data="system_prompt.txt:." \
    --collect-all=pywebview \
    --collect-all=edge_tts \
    --collect-all=speech_recognition \
    --hidden-import=pywebview.api \
    app.py
```

Resultado: `dist/Elyra.app`

## 📦 Criando Instalador

### Windows - Usando NSIS

1. Instale [NSIS](https://nsis.sourceforge.io/)
2. Crie arquivo `installer.nsi`:

```nsis
!include "MUI2.nsh"

Name "Elyra v1.0.0"
OutFile "Elyra-Installer.exe"
InstallDir "$PROGRAMFILES\Elyra"

!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_LANGUAGE "PortugueseBR"

Section "Install"
    SetOutPath "$INSTDIR"
    File /r "dist\Elyra\*.*"
    CreateDirectory "$SMPROGRAMS\Elyra"
    CreateShortCut "$SMPROGRAMS\Elyra\Elyra.lnk" "$INSTDIR\Elyra.exe"
    CreateShortCut "$DESKTOP\Elyra.lnk" "$INSTDIR\Elyra.exe"
SectionEnd
```

3. Compile: `makensis installer.nsi`

### Linux - Usando .desktop

```bash
# Copie o executável
sudo cp dist/Elyra/Elyra /usr/local/bin/elyra

# Copie o arquivo .desktop
sudo cp elyra.desktop /usr/share/applications/

# Torne executável
sudo chmod +x /usr/local/bin/elyra
```

## 📤 Distribuição

### Opção 1: GitHub Releases

```bash
git tag -a v1.0.0 -m "Version 1.0.0"
git push origin v1.0.0
```

Depois crie um Release no GitHub e faça upload dos artefatos gerados. Não commite `dist/` ou `build/` no repositório.
- `Elyra.exe` (Windows)
- `Elyra.dmg` (macOS)
- `Elyra.AppImage` (Linux)

### Opção 2: Compartilhar no YouTube/Social

Prepare para seus vídeos:
1. Crie pasta `releases/` com executáveis
2. Teste cada um antes de compartilhar
3. Crie link de download (Google Drive, Mega, etc.)

## ✅ Checklist de Release

- [ ] Testar executável em cada SO
- [ ] Adicionar icon profissional
- [ ] Verificar version numbers
- [ ] Testar instalação limpa
- [ ] Documentar dependências de runtime
- [ ] Criar changelog
- [ ] Testar atualização automática

## 🐛 Troubleshooting

### "Arquivo não encontrado"
Verifique se web/ e system_prompt.txt estão nas opções `--add-data` do PyInstaller

### "Erro de permissão no Linux"
```bash
chmod +x dist/Elyra/Elyra
```

### "Executável muito grande"
Use `--onefile` para comprimir tudo em um único arquivo

## 📝 Versioning

Atualize a versão em:
1. `setup.py` - `version="1.0.0"`
2. `web/index.html` - `<span class="version">v1.0.0</span>`
3. `elyra.spec` - comentário no topo

## 🔐 Segurança

- Não inclua `elyra_settings.json` (contém API keys)
- Use variáveis de ambiente para configurações sensíveis
- Considere assinar executáveis para evitar avisos de segurança

## 📞 Suporte

Para problemas com PyInstaller, consulte:
- [Documentação PyInstaller](https://pyinstaller.org/)
- [PyWebView Documentation](https://pywebview.kivy.org/)
