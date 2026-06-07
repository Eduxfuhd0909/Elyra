# Elyra

Projeto de chatbot multi-provedor usando Python e `pywebview` para abrir um painel desktop com HTML, CSS e JavaScript.

O painel permite abrir um modal de configurações para escolher provedor, informar API key/base URL, carregar os modelos disponíveis e pesquisar em uma lista rolável para selecionar o modelo exato.

As conversas ficam salvas em uma memória local SQLite no arquivo `chat_memory.sqlite3`.
As configurações ficam salvas em `elyra_settings.json`.

Elyra também pode ouvir pelo microfone com `SpeechRecognition` e falar as respostas com `edge-tts`.

## Provedores suportados

- Ollama: `http://localhost:11434`
- LM Studio: `http://localhost:1234/v1`
- OpenRouter: `https://openrouter.ai/api/v1`
- Groq: `https://api.groq.com/openai/v1`
- OpenAI Compatível: use qualquer base URL compatível com `/models` e `/chat/completions`

## Como executar

Crie e ative um ambiente virtual:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Instale as dependências:

```bash
pip install -r requirements.txt
```

No Linux, o projeto usa o backend Qt instalado pelo `pip`. Se ainda aparecer erro de backend gráfico, atualize as dependências dentro do ambiente virtual:

```bash
pip install --upgrade -r requirements.txt
```

Alternativa GTK no Ubuntu/Debian:

```bash
sudo apt install python3-gi gir1.2-webkit2-4.1
```

Se o microfone não funcionar no Linux, instale também os pacotes de áudio:

```bash
sudo apt install portaudio19-dev python3-pyaudio
```

Execute o app:

```bash
python app.py
```

## Como usar

1. Clique em `Configurações`.
2. Escolha o provedor no modal.
3. Confira ou edite a Base URL.
4. Informe a API key quando o provedor exigir.
5. Clique em `Carregar modelos`.
6. Pesquise e selecione o modelo desejado na lista.
7. Salve e envie mensagens no chat.

Use `Mic` para falar uma mensagem. Use `Voz`/`Mudo` para ativar ou desativar a fala das respostas.

O reconhecimento de fala usa `SpeechRecognition` com `recognize_google` em português do Brasil.

## Memória

O app salva mensagens de usuário e assistente em SQLite. Ao abrir novamente, ele recarrega as últimas mensagens e envia esse histórico como contexto para o provedor.

O botão `Limpar conversa` apaga a tela e também limpa a memória salva.

## Configurações

Provedor, Base URL, API key, modelo selecionado e system prompt ficam salvos em `elyra_settings.json`.

O system prompt padrão faz a Elyra agir como uma assistente pessoal inspirada no estilo Jarvis: objetiva, calma, proativa e cuidadosa com limitações.

## Estrutura

```text
.
├── app.py
├── requirements.txt
├── README.md
└── web
    ├── index.html
    ├── styles.css
    └── app.js
```

## Próximos passos possíveis

- Conectar uma API de IA.
- Salvar histórico de conversas em arquivo.
- Criar múltiplos chats.
- Gerar um executável com PyInstaller.
