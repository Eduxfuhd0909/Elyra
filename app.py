from __future__ import annotations

import asyncio
import base64
import json
import os
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from socket import timeout as SocketTimeout
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import Request, urlopen


os.environ.setdefault("QTWEBENGINE_CHROMIUM_FLAGS", "--disable-gpu")

import edge_tts
import speech_recognition as sr
import webview


BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "chat_memory.sqlite3"
SETTINGS_PATH = BASE_DIR / "elyra_settings.json"
VOICE_NAME = "pt-BR-FranciscaNeural"
APP_USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36"
DEFAULT_SYSTEM_PROMPT = """Você é Elyra, uma assistente pessoal inspirada no estilo Jarvis.
Fale em português do Brasil por padrão, com tom calmo, inteligente, direto e levemente sofisticado.
Sua função é ajudar o usuário a pensar, decidir, organizar tarefas, explicar assuntos, escrever textos, programar e resolver problemas com precisão.

Comportamento:
- Seja proativa, mas não invente capacidades que não possui.
- Quando faltar contexto, faça perguntas curtas e úteis.
- Seja objetiva em tarefas simples e mais detalhada quando o problema for complexo.
- Evite enrolação, exageros e respostas genéricas.
- Mantenha memória conversacional quando houver histórico disponível.
- Se o usuário pedir algo técnico, responda como uma assistente de engenharia cuidadosa.
- Se houver risco, incerteza ou limitação, explique com clareza.

Identidade:
- Seu nome é Elyra.
- Você não é uma pessoa; você é uma IA assistente local conectada ao provedor/modelo escolhido pelo usuário.
- Nunca diga que executou ações externas se apenas sugeriu ou explicou.
"""

PROVIDERS: dict[str, dict[str, Any]] = {
    "ollama": {
        "name": "Ollama",
        "base_url": "http://localhost:11434",
        "kind": "ollama",
        "needs_key": False,
    },
    "lmstudio": {
        "name": "LM Studio",
        "base_url": "http://localhost:1234/v1",
        "kind": "openai",
        "needs_key": False,
    },
    "openrouter": {
        "name": "OpenRouter",
        "base_url": "https://openrouter.ai/api/v1",
        "kind": "openai",
        "needs_key": False,
    },
    "groq": {
        "name": "Groq",
        "base_url": "https://api.groq.com/openai/v1",
        "kind": "openai",
        "needs_key": True,
    },
    "custom": {
        "name": "OpenAI Compatível",
        "base_url": "",
        "kind": "openai",
        "needs_key": False,
    },
}


def to_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False)


def normalize_base_url(base_url: str) -> str:
    return base_url.strip().rstrip("/") + "/"


def describe_http_error(status_code: int, detail: str) -> str:
    if status_code == 401:
        return "HTTP 401: API key inválida ou ausente."
    if status_code == 403:
        return (
            "HTTP 403: o provedor bloqueou a requisição. "
            "Confira a API key, a Base URL e se sua conta tem acesso aos modelos. "
            f"Detalhe: {detail[:300]}"
        )
    return f"HTTP {status_code}: {detail[:600]}"


def read_response(request: Request, timeout: int = 45) -> Any:
    try:
        with urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8")
            return json.loads(body) if body else {}
    except HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(describe_http_error(error.code, detail)) from error
    except URLError as error:
        raise RuntimeError(f"Conexão falhou: {error.reason}") from error
    except TimeoutError as error:
        raise RuntimeError("Tempo limite esgotado. O modelo pode estar carregando; tente novamente ou use um modelo menor.") from error
    except SocketTimeout as error:
        raise RuntimeError("Tempo limite esgotado. O modelo pode estar carregando; tente novamente ou use um modelo menor.") from error


class MemoryStore:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        return connection

    def _init_db(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    role TEXT NOT NULL CHECK (role IN ('user', 'assistant', 'system')),
                    content TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )

    def load_messages(self, limit: int = 80) -> list[dict[str, str]]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT role, content
                FROM messages
                ORDER BY id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()

        return [{"role": row["role"], "content": row["content"]} for row in reversed(rows)]

    def save_message(self, role: str, content: str) -> None:
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO messages (role, content) VALUES (?, ?)",
                (role, content),
            )

    def clear_messages(self) -> None:
        with self._connect() as connection:
            connection.execute("DELETE FROM messages")

    def load_legacy_settings(self) -> dict[str, str]:
        try:
            with self._connect() as connection:
                table = connection.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'settings'"
                ).fetchone()
                if not table:
                    return {}

                rows = connection.execute("SELECT key, value FROM settings").fetchall()
        except sqlite3.Error:
            return {}

        return {row["key"]: row["value"] for row in rows}

class SettingsStore:
    def __init__(self, settings_path: Path) -> None:
        self.settings_path = settings_path

    def load(self) -> dict[str, str]:
        if not self.settings_path.exists():
            return {}

        try:
            with self.settings_path.open("r", encoding="utf-8") as file:
                data = json.load(file)
        except (OSError, json.JSONDecodeError):
            return {}

        if not isinstance(data, dict):
            return {}

        return {str(key): str(value) for key, value in data.items()}

    def save(self, settings: dict[str, str]) -> None:
        with self.settings_path.open("w", encoding="utf-8") as file:
            json.dump(settings, file, ensure_ascii=False, indent=2)


@dataclass
class ChatApi:
    memory: MemoryStore = field(default_factory=lambda: MemoryStore(DB_PATH))
    settings_store: SettingsStore = field(default_factory=lambda: SettingsStore(SETTINGS_PATH))
    history: list[dict[str, str]] = field(default_factory=list)
    provider_id: str = "ollama"
    base_url: str = PROVIDERS["ollama"]["base_url"]
    api_key: str = ""
    model: str = ""
    system_prompt: str = DEFAULT_SYSTEM_PROMPT

    def __post_init__(self) -> None:
        self.history = self.memory.load_messages()
        saved_settings = self.settings_store.load()
        if not saved_settings:
            saved_settings = self.memory.load_legacy_settings()
            if saved_settings:
                self.settings_store.save(saved_settings)

        saved_provider_id = saved_settings.get("provider_id", self.provider_id)

        if saved_provider_id in PROVIDERS:
            self.provider_id = saved_provider_id

        self.base_url = saved_settings.get("base_url") or PROVIDERS[self.provider_id]["base_url"]
        self.api_key = saved_settings.get("api_key", self.api_key)
        self.model = saved_settings.get("model", self.model)
        self.system_prompt = saved_settings.get("system_prompt", self.system_prompt)

    def get_providers(self) -> str:
        providers = [
            {
                "id": provider_id,
                "name": config["name"],
                "base_url": config["base_url"],
                "needs_key": config["needs_key"],
            }
            for provider_id, config in PROVIDERS.items()
        ]
        return to_json({"ok": True, "providers": providers, "settings": self._settings()})

    def save_settings(self, provider_id: str, base_url: str, api_key: str, model: str, system_prompt: str = "") -> str:
        if provider_id not in PROVIDERS:
            return to_json({"ok": False, "error": "Provedor inválido."})

        self.provider_id = provider_id
        self.base_url = base_url.strip() or PROVIDERS[provider_id]["base_url"]
        self.api_key = api_key.strip()
        self.model = model.strip()
        self.system_prompt = system_prompt.strip() or DEFAULT_SYSTEM_PROMPT
        self.settings_store.save(self._settings())

        return to_json({"ok": True, "settings": self._settings()})

    def list_models(self, provider_id: str, base_url: str, api_key: str) -> str:
        if provider_id not in PROVIDERS:
            return to_json({"ok": False, "error": "Provedor inválido."})

        config = PROVIDERS[provider_id]
        target_base_url = base_url.strip() or config["base_url"]
        if not target_base_url:
            return to_json({"ok": False, "error": "Informe a base URL do provedor."})

        if config["needs_key"] and not api_key.strip():
            return to_json({"ok": False, "error": "Informe a API key para listar os modelos."})

        try:
            models = (
                self._list_ollama_models(target_base_url)
                if config["kind"] == "ollama"
                else self._list_openai_models(provider_id, target_base_url, api_key)
            )
            return to_json({"ok": True, "models": models})
        except RuntimeError as error:
            return to_json({"ok": False, "error": str(error)})

    def send_message(self, message: str) -> str:
        text = message.strip()
        if not text:
            return to_json({"ok": False, "reply": "Digite uma mensagem para conversar."})

        if not self.model:
            return to_json({"ok": False, "reply": "Escolha um modelo antes de enviar mensagens."})

        user_message = {"role": "user", "content": text}
        self.history.append(user_message)

        try:
            config = PROVIDERS[self.provider_id]
            if config["kind"] == "ollama":
                reply = self._chat_ollama()
            else:
                reply = self._chat_openai_compatible()
        except RuntimeError as error:
            self.history.pop()
            return to_json({"ok": False, "reply": str(error)})

        assistant_message = {"role": "assistant", "content": reply}
        self.history.append(assistant_message)
        self.memory.save_message(user_message["role"], user_message["content"])
        self.memory.save_message(assistant_message["role"], assistant_message["content"])
        return to_json({"ok": True, "reply": reply})

    def clear_chat(self) -> str:
        self.history.clear()
        self.memory.clear_messages()
        return to_json({"ok": True})

    def get_history(self) -> str:
        return to_json({"ok": True, "history": self.history})

    def listen_once(self) -> str:
        recognizer = sr.Recognizer()

        try:
            with sr.Microphone() as source:
                recognizer.adjust_for_ambient_noise(source, duration=0.6)
                audio = recognizer.listen(source, timeout=8, phrase_time_limit=18)
            text = recognizer.recognize_google(audio, language="pt-BR")
            return to_json({"ok": True, "text": text})
        except sr.WaitTimeoutError:
            return to_json({"ok": False, "error": "Não ouvi nada. Tente falar mais perto do microfone."})
        except sr.UnknownValueError:
            return to_json({"ok": False, "error": "Não consegui entender o áudio."})
        except sr.RequestError as error:
            return to_json({"ok": False, "error": f"Serviço de reconhecimento indisponível: {error}"})
        except OSError as error:
            return to_json({"ok": False, "error": f"Microfone indisponível: {error}"})

    def speak_text(self, text: str) -> str:
        clean_text = text.strip()
        if not clean_text:
            return to_json({"ok": False, "error": "Não há texto para falar."})

        try:
            audio = asyncio.run(self._edge_tts_bytes(clean_text))
            encoded = base64.b64encode(audio).decode("ascii")
            return to_json({"ok": True, "audio": encoded, "mime": "audio/mpeg"})
        except Exception as error:
            return to_json({"ok": False, "error": f"Não consegui gerar voz: {error}"})

    def _settings(self) -> dict[str, str]:
        return {
            "provider_id": self.provider_id,
            "base_url": self.base_url,
            "api_key": self.api_key,
            "model": self.model,
            "system_prompt": self.system_prompt,
        }

    def _messages_for_provider(self) -> list[dict[str, str]]:
        messages: list[dict[str, str]] = []
        if self.system_prompt.strip():
            messages.append({"role": "system", "content": self.system_prompt.strip()})
        messages.extend(self.history)
        return messages

    def _headers(self, api_key: str = "", provider_id: str | None = None) -> dict[str, str]:
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": APP_USER_AGENT,
        }
        token = api_key.strip() or self.api_key
        if token:
            headers["Authorization"] = f"Bearer {token}"
        if (provider_id or self.provider_id) == "openrouter":
            headers["HTTP-Referer"] = "http://localhost"
            headers["X-Title"] = "Elyra"
        return headers

    async def _edge_tts_bytes(self, text: str) -> bytes:
        communicate = edge_tts.Communicate(text, VOICE_NAME)
        audio_parts: list[bytes] = []

        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                audio_parts.append(chunk["data"])

        if not audio_parts:
            raise RuntimeError("edgeTTS não retornou áudio.")

        return b"".join(audio_parts)

    def _list_ollama_models(self, base_url: str) -> list[dict[str, str]]:
        request = Request(
            urljoin(normalize_base_url(base_url), "api/tags"),
            headers=self._headers(),
        )
        data = read_response(request)
        models = data.get("models", [])
        return sorted(
            [{"id": item.get("name", ""), "name": item.get("name", "")} for item in models if item.get("name")],
            key=lambda item: item["name"].lower(),
        )

    def _list_openai_models(self, provider_id: str, base_url: str, api_key: str) -> list[dict[str, str]]:
        request = Request(
            urljoin(normalize_base_url(base_url), "models"),
            headers=self._headers(api_key, provider_id),
        )
        data = read_response(request)
        models = data.get("data", [])
        return sorted(
            [{"id": item.get("id", ""), "name": item.get("id", "")} for item in models if item.get("id")],
            key=lambda item: item["name"].lower(),
        )

    def _chat_ollama(self) -> str:
        payload = {
            "model": self.model,
            "messages": self._messages_for_provider(),
            "stream": False,
        }
        request = Request(
            urljoin(normalize_base_url(self.base_url), "api/chat"),
            data=json.dumps(payload).encode("utf-8"),
            headers=self._headers(),
            method="POST",
        )
        data = read_response(request, timeout=300)
        content = data.get("message", {}).get("content")
        if not content:
            raise RuntimeError("O provedor respondeu sem conteúdo.")
        return content

    def _chat_openai_compatible(self) -> str:
        payload = {
            "model": self.model,
            "messages": self._messages_for_provider(),
            "temperature": 0.7,
        }
        request = Request(
            urljoin(normalize_base_url(self.base_url), "chat/completions"),
            data=json.dumps(payload).encode("utf-8"),
            headers=self._headers(),
            method="POST",
        )
        data = read_response(request, timeout=300)
        choices = data.get("choices", [])
        if not choices:
            raise RuntimeError("O provedor respondeu sem escolhas de mensagem.")
        content = choices[0].get("message", {}).get("content")
        if not content:
            raise RuntimeError("O provedor respondeu sem conteúdo.")
        return content


def main() -> None:
    html_path = BASE_DIR / "web" / "index.html"
    api = ChatApi()

    webview.create_window(
        "Elyra",
        html_path.as_uri(),
        js_api=api,
        width=1120,
        height=760,
        min_size=(520, 620),
    )
    webview.start(gui="qt", debug=False)


if __name__ == "__main__":
    main()
