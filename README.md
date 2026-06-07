# ⚡ Elyra - Assistente IA Profissional

[![Python 3.8+](https://img.shields.io/badge/Python-3.8+-blue?style=flat-square)](https://www.python.org/)
[![License MIT](https://img.shields.io/badge/License-MIT-green?style=flat-square)](LICENSE)
[![Status Estável](https://img.shields.io/badge/Status-Estável-brightgreen?style=flat-square)](https://github.com/Eduxfuhd0909/Elyra)

**Elyra** é um assistente IA multi-provedor profissional com interface desktop moderna, suporte a voz, histórico local e exportação de conversas.

> **Perfeito para vídeos, produtores de conteúdo e uso pessoal!**

## ✨ Características

- 🎤 **Reconhecimento de Voz** - Fale com a assistente usando SpeechRecognition
- 🔊 **Síntese de Voz** - Respostas em áudio com edge-tts
- 💾 **Histórico Local** - Conversas salvas em SQLite
- 🔄 **Múltiplas Abas** - Organize conversas em abas separadas
- 📤 **Exportar** - Salve conversas em Markdown
- 🌓 **Tema Claro/Escuro** - Interface adaptável
- ⚙️ **Configurável** - Suporte a múltiplos provedores
- 📱 **Interface Moderna** - Design profissional e responsivo
- 🚀 **Executáveis** - Distribua como .exe, .app ou Linux AppImage

## 🚀 Começar Rápido

### Executável (Recomendado)

1. Baixe o executável correspondente ao seu SO:
   - [Windows](https://github.com/Eduxfuhd0909/Elyra/releases)
   - [macOS](https://github.com/Eduxfuhd0909/Elyra/releases)
   - [Linux](https://github.com/Eduxfuhd0909/Elyra/releases)

2. Execute o arquivo
3. Configure um provedor nas configurações

### Código Fonte

#### Linux/macOS:
```bash
git clone https://github.com/Eduxfuhd0909/Elyra.git
cd Elyra
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

#### Windows:
```bash
git clone https://github.com/Eduxfuhd0909/Elyra.git
cd Elyra
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

## ⚙️ Provedores Suportados

| Provedor | URL | API Key | Requer Setup |
|----------|-----|---------|-------------|
| **Ollama** | `http://localhost:11434` | Não | Sim (install Ollama) |
| **LM Studio** | `http://localhost:1234/v1` | Não | Sim (install LM Studio) |
| **OpenRouter** | `https://openrouter.ai/api/v1` | Sim | Não |
| **Groq** | `https://api.groq.com/openai/v1` | Sim | Não |
| **Customizado** | Qualquer URL | Depende | Compatível com OpenAI |

## 📖 Como Usar

### 1️⃣ Configurar Provedor
- Abra **Configurações** (⚙️)
- Escolha um provedor da lista
- Insira Base URL (pré-preenchida)
- Adicione API Key se necessário

### 2️⃣ Carregar Modelos
- Clique em **Carregar modelos**
- Pesquise o modelo desejado
- Clique para selecionar
- Salve configuração

### 3️⃣ Conversar
- Digite uma mensagem ou clique 🎤 para falar
- Use 🔊 para ativar/desativar áudio das respostas
- **Alt+Enter** para enviar
- 💾 para exportar conversa

## 📁 Estrutura do Projeto

```
Elyra/
├── app.py                   # Backend Python/PyWebView
├── requirements.txt         # Dependências runtime
├── requirements-build.txt   # Dependências para build
├── setup.py                 # Setup.py para instalação
├── elyra.spec              # Configuração PyInstaller
├── elyra.desktop           # Atalho Linux
├── build.sh                # Script de build
├── BUILD.md                # Guia de build/distribuição
├── system_prompt.txt       # Instruções da assistente
├── chat_memory.sqlite3     # Histórico (gerado)
├── elyra_settings.json     # Configurações (gerado)
└── web/
    ├── index.html          # Interface HTML
    ├── styles.css          # Estilos modernos
    └── app.js              # Lógica frontend
```

## 🏗️ Build & Distribuição

### Criar Executável

```bash
# Instale dependências de build
pip install -r requirements-build.txt

# Execute o script (Linux/Mac)
chmod +x build.sh
./build.sh

# Ou manualmente com PyInstaller
pyinstaller elyra.spec
```

Para guia completo, veja [BUILD.md](BUILD.md)

### Distribuir para Usuários

O executável compilado está em `dist/Elyra`:
- **Windows**: `dist/Elyra.exe`
- **macOS**: `dist/Elyra.app`
- **Linux**: `dist/Elyra` (executável)

Comprima e compartilhe via:
- GitHub Releases
- Google Drive / Dropbox
- Mega
- Seu site

## 🎨 Personalização

### Mudar o System Prompt

Edite `system_prompt.txt`:
```
Você é Elyra, uma assistente pessoal inspirada no estilo Jarvis...
```

### Mudar Cores/Tema

Edite `web/styles.css`:
```css
:root {
  --accent-color: #0f766e;
  --bg-primary: #ffffff;
  /* ... mais cores ... */
}
```

## 🔒 Segurança

⚠️ **Importante:**
- `elyra_settings.json` contém suas API keys - **NÃO compartilhe**
- Use variáveis de ambiente para chaves sensíveis
- Não commite `elyra_settings.json` no Git

## 🐛 Troubleshooting

### "Erro de backend gráfico no Linux"
```bash
sudo apt install python3-gi gir1.2-webkit2-4.1
pip install --upgrade pywebview
```

### "Microfone não funciona"
```bash
sudo apt install portaudio19-dev python3-pyaudio
```

### "Executável muito grande"
Use `--onefile` no PyInstaller para um arquivo único

## 📊 Requisitos

- **Python**: 3.8+
- **RAM**: 512MB mínimo
- **Disco**: 200MB (com dependências)
- **Rede**: Para conectar a provedores online

## 📄 Licença

[MIT License](LICENSE) - Livre para uso pessoal e comercial

## 🤝 Contribuir

Contribuições são bem-vindas! Abra uma [issue](https://github.com/Eduxfuhd0909/Elyra/issues) ou faça um [pull request](https://github.com/Eduxfuhd0909/Elyra/pulls)

## 🎥 Para Criadores de Conteúdo

Elyra é perfeito para vídeos sobre:
- IA e LLMs
- Produtividade
- Programação
- Demonstrações de modelos

**Baixe o executável e use livremente em seus vídeos!**
- Salvar histórico de conversas em arquivo.
- Criar múltiplos chats.
- Gerar um executável com PyInstaller.
