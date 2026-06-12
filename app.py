from __future__ import annotations

import asyncio
import base64
import importlib.util
import json
import os
import re
import sqlite3
import sys
import threading
import uuid
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

try:
    import discord
except ImportError:
    discord = None


BASE_DIR = Path(__file__).resolve().parent
APP_NAME = "Elyra"


def user_data_dir() -> Path:
    if os.name == "nt":
        root = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    elif sys.platform == "darwin":
        root = Path.home() / "Library" / "Application Support"
    else:
        root = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))

    path = root / APP_NAME
    path.mkdir(parents=True, exist_ok=True)
    return path


DATA_DIR = user_data_dir()
DB_PATH = DATA_DIR / "chat_memory.sqlite3"
SETTINGS_PATH = DATA_DIR / "elyra_settings.json"
LEGACY_DB_PATH = BASE_DIR / "chat_memory.sqlite3"
LEGACY_SETTINGS_PATH = BASE_DIR / "elyra_settings.json"
TOOLS_DIR = BASE_DIR / "tools"
VOICE_NAME = "pt-BR-FranciscaNeural"
APP_USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36"
SHORT_TERM_LIMIT = 28
LONG_TERM_LIMIT = 12
DEFAULT_CHAT_TITLE = "Conversa 1"
MEMORY_EXTRACTION_TIMEOUT = 75
DISCORD_GUILD_ID = 1514764708283154472
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
        "needs_key": True,
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


def extract_json_object(text: str) -> dict[str, Any]:
    clean = text.strip()
    if clean.startswith("```"):
        clean = re.sub(r"^```(?:json)?", "", clean, flags=re.IGNORECASE).strip()
        clean = re.sub(r"```$", "", clean).strip()

    try:
        data = json.loads(clean)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", clean, flags=re.DOTALL)
        if not match:
            return {}
        try:
            data = json.loads(match.group(0))
        except json.JSONDecodeError:
            return {}

    return data if isinstance(data, dict) else {}


def migrate_legacy_user_files() -> None:
    migrations = (
        (LEGACY_DB_PATH, DB_PATH),
        (LEGACY_SETTINGS_PATH, SETTINGS_PATH),
    )
    for source, target in migrations:
        if not source.exists() or target.exists():
            continue
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(source.read_bytes())
        except OSError:
            continue


def secure_file_permissions(path: Path) -> None:
    if os.name == "nt":
        return
    try:
        path.chmod(0o600)
    except OSError:
        pass


MEMORY_STOPWORDS = {
    "a",
    "agora",
    "ao",
    "aos",
    "as",
    "assim",
    "com",
    "como",
    "da",
    "das",
    "de",
    "dei",
    "do",
    "dos",
    "e",
    "ela",
    "ele",
    "em",
    "entao",
    "essa",
    "esse",
    "esta",
    "este",
    "eu",
    "isso",
    "ja",
    "mais",
    "mas",
    "me",
    "meu",
    "minha",
    "na",
    "nas",
    "no",
    "nos",
    "o",
    "os",
    "ou",
    "para",
    "por",
    "porque",
    "que",
    "se",
    "sem",
    "ser",
    "sou",
    "sua",
    "suo",
    "te",
    "tem",
    "ter",
    "um",
    "uma",
    "voce",
}

MEMORY_PATTERNS = [
    r"\blembre(?:-se)? que\b",
    r"\bguarde que\b",
    r"\bmemorize que\b",
    r"\bn[aã]o esque[çc]a que\b",
    r"\bmeu nome [ée]\b",
    r"\bminha idade [ée]\b",
    r"\beu sou\b",
    r"\beu trabalho\b",
    r"\beu estudo\b",
    r"\beu moro\b",
    r"\beu gosto\b",
    r"\beu n[aã]o gosto\b",
    r"\beu odeio\b",
    r"\beu prefiro\b",
    r"\bminha prefer[eê]ncia\b",
    r"\bmeu objetivo\b",
    r"\bmeu projeto\b",
    r"\bminha ia\b",
]


def strip_accents(text: str) -> str:
    replacements = str.maketrans(
        "áàãâäéèêëíìîïóòõôöúùûüçñÁÀÃÂÄÉÈÊËÍÌÎÏÓÒÕÔÖÚÙÛÜÇÑ",
        "aaaaaeeeeiiiiooooouuuucnAAAAAEEEEIIIIOOOOOUUUUCN",
    )
    return text.translate(replacements)


def normalize_memory_text(text: str) -> str:
    clean = re.sub(r"\s+", " ", text).strip()
    clean = clean.strip(" .;,:")
    if len(clean) < 8:
        return ""
    if len(clean) > 420:
        clean = clean[:420].rsplit(" ", 1)[0].strip()
    return clean


def normalize_chat_title(text: str) -> str:
    clean = re.sub(r"\s+", " ", text).strip()
    clean = clean.strip(" .;,:")
    if len(clean) > 80:
        clean = clean[:80].rsplit(" ", 1)[0].strip()
    return clean


def extract_keywords(text: str) -> list[str]:
    normalized = strip_accents(text.lower())
    words = re.findall(r"[a-z0-9_]{3,}", normalized)
    keywords: list[str] = []
    for word in words:
        if word in MEMORY_STOPWORDS or word in keywords:
            continue
        keywords.append(word)
    return keywords[:24]


def extract_long_term_memory_candidates(user_text: str) -> list[str]:
    clean = normalize_memory_text(user_text)
    if not clean:
        return []

    lowered = clean.lower()
    candidates: list[str] = []
    for pattern in MEMORY_PATTERNS:
        match = re.search(pattern, lowered)
        if not match:
            continue

        content = clean[match.start() :]
        content = re.sub(
            r"^(lembre(?:-se)? que|guarde que|memorize que|n[aã]o esque[çc]a que)\s+",
            "",
            content,
            flags=re.IGNORECASE,
        )
        content = normalize_memory_text(content)
        if not content:
            continue

        should_add = True
        for index, existing in enumerate(list(candidates)):
            if content.lower() in existing.lower():
                should_add = False
                break
            if existing.lower() in content.lower():
                candidates[index] = content
                should_add = False
                break
        if should_add:
            candidates.append(content)

    return candidates[:4]


@dataclass
class ToolDefinition:
    name: str
    description: str
    run: Any
    path: Path


class ToolRegistry:
    def __init__(self, tools_dir: Path) -> None:
        self.tools_dir = tools_dir
        self.tools: dict[str, ToolDefinition] = {}
        self.load_errors: dict[str, str] = {}
        self.reload()

    def reload(self) -> None:
        self.tools = {}
        self.load_errors = {}
        if not self.tools_dir.exists():
            return

        for path in sorted(self.tools_dir.glob("*.py")):
            if path.name.startswith("_"):
                continue
            try:
                module_name = f"elyra_tool_{path.stem}_{abs(hash(path))}"
                spec = importlib.util.spec_from_file_location(module_name, path)
                if spec is None or spec.loader is None:
                    raise RuntimeError("Não consegui carregar o módulo da ferramenta.")
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)

                name = str(getattr(module, "TOOL_NAME", path.stem)).strip()
                description = str(getattr(module, "TOOL_DESCRIPTION", "")).strip()
                runner = getattr(module, "run", None)
                if not name or not callable(runner):
                    raise RuntimeError("Ferramenta precisa definir TOOL_NAME e run(raw_request, context).")
                self.tools[name] = ToolDefinition(name=name, description=description, run=runner, path=path)
            except Exception as error:
                self.load_errors[path.name] = str(error)

    def names(self) -> list[str]:
        return sorted(self.tools)

    def descriptions(self) -> list[dict[str, str]]:
        return [
            {"name": tool.name, "description": tool.description}
            for tool in sorted(self.tools.values(), key=lambda item: item.name)
        ]

    def execute(self, name: str, raw_request: str, context: dict[str, Any]) -> dict[str, Any]:
        tool = self.tools.get(name)
        if tool is None:
            available = ", ".join(self.names()) or "nenhuma"
            return {
                "ok": False,
                "error": f"Ainda não existe uma ferramenta chamada '{name}'. Ferramentas disponíveis: {available}.",
                "result": "",
            }

        try:
            result = tool.run(raw_request, context)
        except Exception as error:
            return {"ok": False, "error": f"A ferramenta {name} falhou: {error}", "result": ""}

        if not isinstance(result, dict):
            return {"ok": True, "result": str(result), "error": ""}

        return {
            "ok": bool(result.get("ok", True)),
            "result": result.get("result", ""),
            "error": str(result.get("error", "")),
        }


class IntentRouter:
    def __init__(self, registry: ToolRegistry) -> None:
        self.registry = registry

    def route(self, api: Any, raw_request: str, context: dict[str, Any]) -> dict[str, Any]:
        heuristic = self.heuristic_route(raw_request)
        if not api.model:
            return heuristic

        tools_json = json.dumps(self.registry.descriptions(), ensure_ascii=False)
        router_system = (
            "Você é o roteador de intenção da Elyra. "
            "Decida se o pedido deve ser respondido normalmente, se precisa de uma ferramenta modular, "
            "ou se falta contexto essencial. "
            "Use ferramentas quando o usuário pedir configuração, memória, status, consulta operacional da Elyra "
            "ou qualquer ação que pareça exigir capacidade externa. "
            "Se o pedido exigir uma ferramenta que não existe, retorne action='tool' com um nome provável para ela. "
            "Responda somente JSON válido neste formato: "
            "{\"action\":\"answer|tool|clarify\",\"tool\":\"nome_opcional\",\"reason\":\"curto\",\"question\":\"pergunta_opcional\"}."
        )
        router_payload = {
            "pedido": raw_request,
            "origem": context.get("origin"),
            "config_atual": context.get("settings"),
            "historico_recente": context.get("history", [])[-8:],
            "memorias_relevantes": context.get("memories", []),
            "ferramentas_disponiveis": tools_json,
        }

        try:
            raw = api._complete_messages(
                [
                    {"role": "system", "content": router_system},
                    {"role": "user", "content": json.dumps(router_payload, ensure_ascii=False)},
                ],
                timeout=90,
                temperature=0,
            )
            decision = extract_json_object(raw)
        except RuntimeError:
            return heuristic

        action = str(decision.get("action", "")).strip().lower()
        if action not in {"answer", "tool", "clarify"}:
            return heuristic

        if action == "tool":
            tool_name = str(decision.get("tool", "")).strip()
            if not tool_name:
                return heuristic
            return {"action": "tool", "tool": tool_name, "reason": str(decision.get("reason", ""))}

        if action == "clarify":
            question = str(decision.get("question", "")).strip()
            return {"action": "clarify", "question": question or "Pode me dar mais contexto?"}

        return {"action": "answer", "reason": str(decision.get("reason", ""))}

    def heuristic_route(self, raw_request: str) -> dict[str, Any]:
        lowered = strip_accents(raw_request.lower())
        if re.search(r"\b(provider|provedor|modelo|prompt|system prompt|configur)", lowered):
            return {"action": "tool", "tool": "settings_tool", "reason": "pedido de configuração"}
        if re.search(r"\b(lembra|lembrar|memoriza|memoria|guarda|recorda|salva que)\b", lowered):
            return {"action": "tool", "tool": "memory_tool", "reason": "pedido de memória"}
        if re.search(
            r"\b(sistema|computador|pc|linux|windows|macos|arquivo|pasta|diretorio|mover|move|mova|"
            r"transferir|transfere|colocar|coloca|manda|joga)\b",
            lowered,
        ):
            return {"action": "tool", "tool": "local_system_tool", "reason": "pedido de sistema local"}
        if re.search(r"\b(status|estado|diagnostico|discord|config atual|configuracao atual)\b", lowered):
            return {"action": "tool", "tool": "status_tool", "reason": "pedido de status"}
        if re.search(
            r"\b(abrir|abre|open|executa|executar|roda|rodar|comando|navegador|terminal|mover|move|mova|"
            r"transferir|transfere|colocar|coloca|manda|joga|"
            r"listar|lista|ler|leia)\b",
            lowered,
        ):
            return {"action": "tool", "tool": "local_system_tool", "reason": "pedido de sistema local"}
        return {"action": "answer", "reason": "conversa normal"}


class MemoryStore:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        return connection

    def _init_db(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS chats (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chat_id TEXT,
                    role TEXT NOT NULL CHECK (role IN ('user', 'assistant', 'system')),
                    content TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (chat_id) REFERENCES chats(id) ON DELETE CASCADE
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS long_term_memories (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    content TEXT NOT NULL UNIQUE,
                    keywords TEXT NOT NULL DEFAULT '',
                    score INTEGER NOT NULL DEFAULT 1,
                    source TEXT NOT NULL DEFAULT 'heuristic',
                    confidence REAL NOT NULL DEFAULT 0.6,
                    evidence TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    last_used_at TEXT
                )
                """
            )
            self._ensure_message_chat_column(connection)
            self._ensure_long_term_memory_columns(connection)
            self._ensure_default_chat(connection)

    def _ensure_message_chat_column(self, connection: sqlite3.Connection) -> None:
        columns = connection.execute("PRAGMA table_info(messages)").fetchall()
        if not any(row["name"] == "chat_id" for row in columns):
            connection.execute("ALTER TABLE messages ADD COLUMN chat_id TEXT")

    def _ensure_long_term_memory_columns(self, connection: sqlite3.Connection) -> None:
        columns = {row["name"] for row in connection.execute("PRAGMA table_info(long_term_memories)").fetchall()}
        migrations = {
            "source": "ALTER TABLE long_term_memories ADD COLUMN source TEXT NOT NULL DEFAULT 'heuristic'",
            "confidence": "ALTER TABLE long_term_memories ADD COLUMN confidence REAL NOT NULL DEFAULT 0.6",
            "evidence": "ALTER TABLE long_term_memories ADD COLUMN evidence TEXT NOT NULL DEFAULT ''",
            "last_used_at": "ALTER TABLE long_term_memories ADD COLUMN last_used_at TEXT",
        }
        for column, statement in migrations.items():
            if column not in columns:
                connection.execute(statement)

    def _ensure_default_chat(self, connection: sqlite3.Connection) -> str:
        chat = connection.execute("SELECT id FROM chats ORDER BY created_at ASC LIMIT 1").fetchone()
        if chat:
            default_chat_id = str(chat["id"])
        else:
            default_chat_id = uuid.uuid4().hex
            connection.execute(
                "INSERT INTO chats (id, title) VALUES (?, ?)",
                (default_chat_id, DEFAULT_CHAT_TITLE),
            )

        connection.execute(
            "UPDATE messages SET chat_id = ? WHERE chat_id IS NULL OR chat_id = ''",
            (default_chat_id,),
        )
        return default_chat_id

    def create_chat(self, title: str | None = None) -> dict[str, str]:
        chat_id = uuid.uuid4().hex
        with self._connect() as connection:
            count = connection.execute("SELECT COUNT(*) AS count FROM chats").fetchone()
            fallback_title = f"Conversa {int(count['count']) + 1 if count else 1}"
            clean_title = normalize_chat_title(title or "") if title else ""
            connection.execute(
                "INSERT INTO chats (id, title) VALUES (?, ?)",
                (chat_id, clean_title or fallback_title),
            )
        return {"id": chat_id, "title": clean_title or fallback_title}

    def list_chats(self) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT c.id, c.title, c.created_at, c.updated_at, COUNT(m.id) AS message_count
                FROM chats c
                LEFT JOIN messages m ON m.chat_id = c.id
                GROUP BY c.id
                ORDER BY c.updated_at DESC, c.created_at DESC
                """
            ).fetchall()

        return [
            {
                "id": str(row["id"]),
                "title": str(row["title"]),
                "created_at": str(row["created_at"]),
                "updated_at": str(row["updated_at"]),
                "message_count": int(row["message_count"]),
            }
            for row in rows
        ]

    def delete_chat(self, chat_id: str) -> None:
        with self._connect() as connection:
            connection.execute("DELETE FROM messages WHERE chat_id = ?", (chat_id,))
            connection.execute("DELETE FROM chats WHERE id = ?", (chat_id,))
            remaining = connection.execute("SELECT COUNT(*) AS count FROM chats").fetchone()
            if int(remaining["count"]) == 0:
                self._ensure_default_chat(connection)

    def chat_exists(self, chat_id: str) -> bool:
        with self._connect() as connection:
            row = connection.execute("SELECT 1 FROM chats WHERE id = ?", (chat_id,)).fetchone()
        return row is not None

    def load_messages(self, chat_id: str, limit: int = 80) -> list[dict[str, str]]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT role, content
                FROM messages
                WHERE chat_id = ?
                ORDER BY id DESC
                LIMIT ?
                """,
                (chat_id, limit),
            ).fetchall()

        return [{"role": row["role"], "content": row["content"]} for row in reversed(rows)]

    def load_short_term_messages(self, chat_id: str, limit: int = SHORT_TERM_LIMIT) -> list[dict[str, str]]:
        return self.load_messages(chat_id, limit)

    def save_message(self, chat_id: str, role: str, content: str) -> None:
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO messages (chat_id, role, content) VALUES (?, ?, ?)",
                (chat_id, role, content),
            )
            connection.execute(
                "UPDATE chats SET updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (chat_id,),
            )

    def clear_messages(self, chat_id: str) -> None:
        with self._connect() as connection:
            connection.execute("DELETE FROM messages WHERE chat_id = ?", (chat_id,))
            connection.execute(
                "UPDATE chats SET updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (chat_id,),
            )

    def save_long_term_memory(self, content: str, source: str = "manual", confidence: float = 0.8, evidence: str = "") -> bool:
        clean_content = normalize_memory_text(content)
        if not clean_content:
            return False

        keywords = " ".join(extract_keywords(clean_content))
        clean_evidence = normalize_memory_text(evidence) if evidence else ""
        safe_confidence = max(0.0, min(float(confidence), 1.0))
        with self._connect() as connection:
            existing = connection.execute(
                "SELECT id, score FROM long_term_memories WHERE lower(content) = lower(?)",
                (clean_content,),
            ).fetchone()

            if existing:
                connection.execute(
                    """
                    UPDATE long_term_memories
                    SET score = ?,
                        keywords = ?,
                        source = ?,
                        confidence = MAX(confidence, ?),
                        evidence = CASE WHEN ? != '' THEN ? ELSE evidence END,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                    """,
                    (
                        int(existing["score"]) + 1,
                        keywords,
                        source,
                        safe_confidence,
                        clean_evidence,
                        clean_evidence,
                        int(existing["id"]),
                    ),
                )
                return True

            connection.execute(
                """
                INSERT OR IGNORE INTO long_term_memories (content, keywords, source, confidence, evidence)
                VALUES (?, ?, ?, ?, ?)
                """,
                (clean_content, keywords, source, safe_confidence, clean_evidence),
            )
        return True

    def load_relevant_long_term_memories(self, query: str, limit: int = LONG_TERM_LIMIT) -> list[str]:
        query_keywords = set(extract_keywords(query))
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT content, keywords, score, updated_at
                FROM long_term_memories
                ORDER BY score DESC, updated_at DESC
                LIMIT 80
                """
            ).fetchall()

        ranked: list[tuple[int, str]] = []
        for row in rows:
            memory_keywords = set(str(row["keywords"]).split())
            overlap = len(query_keywords & memory_keywords)
            score = int(row["score"]) + (overlap * 4)
            if overlap or score > 1:
                ranked.append((score, str(row["content"])))

        ranked.sort(key=lambda item: item[0], reverse=True)
        selected = [content for _, content in ranked[:limit]]
        if selected:
            with self._connect() as connection:
                connection.executemany(
                    "UPDATE long_term_memories SET last_used_at = CURRENT_TIMESTAMP WHERE content = ?",
                    [(content,) for content in selected],
                )
        return selected

    def load_all_long_term_memories(self, limit: int = 200) -> list[str]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT content
                FROM long_term_memories
                ORDER BY score DESC, updated_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [str(row["content"]) for row in rows]

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
        self.settings_path.parent.mkdir(parents=True, exist_ok=True)
        with self.settings_path.open("w", encoding="utf-8") as file:
            json.dump(settings, file, ensure_ascii=False, indent=2)
        secure_file_permissions(self.settings_path)


class DiscordBotManager:
    def __init__(self) -> None:
        self.client: Any | None = None
        self.loop: asyncio.AbstractEventLoop | None = None
        self.thread: threading.Thread | None = None
        self.api: ChatApi | None = None
        self.guild_id = DISCORD_GUILD_ID
        self.token: str = ""
        self.status: str = "desconectado"
        self.bot_name: str = ""
        self.last_error: str = ""
        self._lock = threading.Lock()

    def configure(self, api: ChatApi, guild_id: int = DISCORD_GUILD_ID) -> None:
        self.api = api
        self.guild_id = guild_id

    def start(self, token: str) -> tuple[bool, str]:
        clean_token = token.strip()
        if not clean_token:
            return False, "Informe o token do bot depois de /token."

        if discord is None:
            self._set_status("erro", "Instale a dependência discord.py para usar o bot.")
            return False, "Instale a dependência discord.py com: pip install -r requirements.txt"

        with self._lock:
            if self.thread and self.thread.is_alive() and self.token == clean_token:
                return True, self._status_message()

        self.stop()
        self.token = clean_token
        self.status = "conectando"
        self.bot_name = ""
        self.last_error = ""
        self.thread = threading.Thread(target=self._run_bot, args=(clean_token,), daemon=True)
        self.thread.start()
        return True, "Token salvo. Bot do Discord conectando em segundo plano."

    def stop(self) -> None:
        client = self.client
        loop = self.loop
        if client and loop and loop.is_running():
            try:
                asyncio.run_coroutine_threadsafe(client.close(), loop)
            except RuntimeError:
                pass

    def public_status(self) -> dict[str, str]:
        return {
            "status": self.status,
            "bot_name": self.bot_name,
            "error": self.last_error,
            "guild_id": str(self.guild_id),
        }

    def _run_bot(self, token: str) -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        self.loop = loop

        intents = discord.Intents.default()
        intents.message_content = True
        client = discord.Client(intents=intents)
        tree = discord.app_commands.CommandTree(client)
        self.client = client
        guild_object = discord.Object(id=self.guild_id)

        async def is_allowed_guild(interaction: Any) -> bool:
            return bool(interaction.guild_id == self.guild_id)

        async def send_interaction_reply(interaction: Any, content: str, ephemeral: bool = True) -> None:
            if interaction.response.is_done():
                await interaction.followup.send(content[:2000], ephemeral=ephemeral)
            else:
                await interaction.response.send_message(content[:2000], ephemeral=ephemeral)

        @tree.command(name="provider", description="Lista ou troca o provider da Elyra.", guild=guild_object)
        async def provider_command(interaction: Any, provider: str = "") -> None:
            if not await is_allowed_guild(interaction):
                await send_interaction_reply(interaction, "Este bot está configurado apenas para o servidor autorizado.")
                return
            if self.api is None:
                await send_interaction_reply(interaction, "API da Elyra ainda não está pronta.")
                return
            await interaction.response.defer(ephemeral=True)
            reply = await asyncio.to_thread(self.api.discord_provider_command, provider)
            await interaction.followup.send(reply[:2000], ephemeral=True)

        @tree.command(name="modelo", description="Lista ou troca o modelo da Elyra.", guild=guild_object)
        async def model_command(interaction: Any, modelo: str = "") -> None:
            if not await is_allowed_guild(interaction):
                await send_interaction_reply(interaction, "Este bot está configurado apenas para o servidor autorizado.")
                return
            if self.api is None:
                await send_interaction_reply(interaction, "API da Elyra ainda não está pronta.")
                return
            await interaction.response.defer(ephemeral=True)
            reply = await asyncio.to_thread(self.api.discord_model_command, modelo)
            await interaction.followup.send(reply[:2000], ephemeral=True)

        @tree.command(name="prompt", description="Mostra ou troca o prompt da IA.", guild=guild_object)
        async def prompt_command(interaction: Any, prompt: str = "") -> None:
            if not await is_allowed_guild(interaction):
                await send_interaction_reply(interaction, "Este bot está configurado apenas para o servidor autorizado.")
                return
            if self.api is None:
                await send_interaction_reply(interaction, "API da Elyra ainda não está pronta.")
                return
            await interaction.response.defer(ephemeral=True)
            reply = await asyncio.to_thread(self.api.discord_prompt_command, prompt)
            await interaction.followup.send(reply[:2000], ephemeral=True)

        @provider_command.autocomplete("provider")
        async def provider_autocomplete(interaction: Any, current: str) -> list[Any]:
            if interaction.guild_id != self.guild_id:
                return []
            query = current.lower()
            return [
                discord.app_commands.Choice(name=f"{config['name']} ({provider_id})", value=provider_id)
                for provider_id, config in PROVIDERS.items()
                if not query or query in provider_id.lower() or query in str(config["name"]).lower()
            ][:25]

        @model_command.autocomplete("modelo")
        async def model_autocomplete(interaction: Any, current: str) -> list[Any]:
            if interaction.guild_id != self.guild_id or self.api is None:
                return []
            query = current.lower()
            models = await asyncio.to_thread(self.api.discord_model_choices)
            return [
                discord.app_commands.Choice(name=model[:100], value=model[:100])
                for model in models
                if not query or query in model.lower()
            ][:25]

        @client.event
        async def on_ready() -> None:
            user = client.user
            self.bot_name = str(user) if user else "bot conectado"
            self._set_status("conectado", "")

        @client.event
        async def setup_hook() -> None:
            await tree.sync(guild=guild_object)

        @client.event
        async def on_message(message: Any) -> None:
            if self.api is None or message.author.bot or not message.guild:
                return
            if message.guild.id != self.guild_id:
                return
            if client.user is None or client.user not in message.mentions:
                return

            user_text = message.content
            for mention in [client.user.mention, f"<@!{client.user.id}>"]:
                user_text = user_text.replace(mention, "")
            user_text = user_text.strip()
            if not user_text:
                user_text = "Responda ao usuário de forma breve."

            async with message.channel.typing():
                reply = await asyncio.to_thread(self.api.discord_generate_reply, user_text)
            await message.reply(reply[:2000], mention_author=False)

        try:
            loop.run_until_complete(client.start(token, reconnect=True))
        except Exception as error:
            self._set_status("erro", str(error))
        finally:
            if not client.is_closed():
                try:
                    loop.run_until_complete(client.close())
                except RuntimeError:
                    pass
            if self.status != "erro":
                self._set_status("desconectado", self.last_error)
            try:
                loop.close()
            except RuntimeError:
                pass

    def _set_status(self, status: str, error: str = "") -> None:
        with self._lock:
            self.status = status
            self.last_error = error

    def _status_message(self) -> str:
        if self.status == "conectado":
            return f"Bot do Discord conectado como {self.bot_name}."
        if self.status == "conectando":
            return "Bot do Discord ainda está conectando."
        if self.status == "erro":
            return f"Discord retornou erro: {self.last_error}"
        return "Bot do Discord desconectado."


@dataclass
class ChatApi:
    memory: MemoryStore = field(default_factory=lambda: MemoryStore(DB_PATH))
    settings_store: SettingsStore = field(default_factory=lambda: SettingsStore(SETTINGS_PATH))
    discord_bot: DiscordBotManager = field(default_factory=DiscordBotManager)
    tool_registry: ToolRegistry = field(default_factory=lambda: ToolRegistry(TOOLS_DIR))
    histories: dict[str, list[dict[str, str]]] = field(default_factory=dict)
    discord_history: list[dict[str, str]] = field(default_factory=list)
    settings_lock: threading.RLock = field(default_factory=threading.RLock)
    provider_id: str = "ollama"
    base_url: str = PROVIDERS["ollama"]["base_url"]
    api_key: str = ""
    model: str = ""
    system_prompt: str = DEFAULT_SYSTEM_PROMPT
    discord_token: str = ""
    intent_router: IntentRouter | None = None

    def __post_init__(self) -> None:
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
        self.discord_token = saved_settings.get("discord_token", self.discord_token)
        self.intent_router = IntentRouter(self.tool_registry)
        self.discord_bot.configure(self, DISCORD_GUILD_ID)
        if self.discord_token:
            self.discord_bot.start(self.discord_token)

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
        return to_json({"ok": True, "providers": providers, "settings": self._public_settings()})

    def get_provider_configs(self) -> dict[str, dict[str, Any]]:
        return PROVIDERS

    def save_settings(self, provider_id: str, base_url: str, api_key: str, model: str, system_prompt: str = "") -> str:
        if provider_id not in PROVIDERS:
            return to_json({"ok": False, "error": "Provedor inválido."})

        self.provider_id = provider_id
        self.base_url = base_url.strip() or PROVIDERS[provider_id]["base_url"]
        if api_key.strip():
            self.api_key = api_key.strip()
        self.model = model.strip()
        self.system_prompt = system_prompt.strip() or DEFAULT_SYSTEM_PROMPT
        self.settings_store.save(self._settings())

        return to_json({"ok": True, "settings": self._public_settings()})

    def discord_provider_command(self, provider: str = "") -> str:
        clean_provider = provider.strip().lower()
        if not clean_provider:
            lines = ["Providers disponíveis:"]
            for provider_id, config in PROVIDERS.items():
                marker = " atual" if provider_id == self.provider_id else ""
                lines.append(f"- {provider_id}: {config['name']}{marker}")
            lines.append("Use /provider provider:<id> para trocar.")
            return "\n".join(lines)

        if clean_provider not in PROVIDERS:
            return "Provider inválido. Use /provider sem valor para ver a lista."

        with self.settings_lock:
            self.provider_id = clean_provider
            self.base_url = PROVIDERS[clean_provider]["base_url"]
            self.model = ""
            self.settings_store.save(self._settings())
        return f"Provider alterado para {PROVIDERS[clean_provider]['name']}. Agora use /modelo para escolher um modelo."

    def discord_model_command(self, model: str = "") -> str:
        clean_model = model.strip()
        if clean_model:
            with self.settings_lock:
                self.model = clean_model
                self.settings_store.save(self._settings())
            return f"Modelo alterado para {clean_model}."

        models = self.discord_model_choices()
        if not models:
            return "Não consegui carregar modelos. Verifique provider, base URL e API key no painel da Elyra."

        current = f" atual: {self.model}" if self.model else " nenhum modelo selecionado"
        lines = [f"Modelos disponíveis ({current}):"]
        lines.extend(f"- {model}" for model in models[:40])
        if len(models) > 40:
            lines.append(f"... e mais {len(models) - 40}. Digite parte do nome no campo modelo para usar autocomplete.")
        lines.append("Use /modelo modelo:<nome> para trocar.")
        return "\n".join(lines)

    def discord_model_choices(self) -> list[str]:
        try:
            models_payload = self.list_models(self.provider_id, self.base_url, self.api_key)
            response = json.loads(models_payload)
        except (RuntimeError, json.JSONDecodeError):
            return []

        if not response.get("ok"):
            return []

        raw_models = response.get("models", [])
        names = [
            str(item.get("id") or item.get("name"))
            for item in raw_models
            if isinstance(item, dict) and (item.get("id") or item.get("name"))
        ]
        return sorted(names, key=str.lower)

    def discord_prompt_command(self, prompt: str = "") -> str:
        clean_prompt = prompt.strip()
        if not clean_prompt:
            current = self.system_prompt.strip() or DEFAULT_SYSTEM_PROMPT
            return f"Prompt atual:\n{current[:1800]}"

        with self.settings_lock:
            self.system_prompt = clean_prompt
            self.settings_store.save(self._settings())
        return "Prompt da IA atualizado para este app e para o servidor do Discord."

    def discord_generate_reply(self, user_text: str) -> str:
        clean_text = user_text.strip()
        if not clean_text:
            return "Me marque junto com uma mensagem para eu responder."

        history = self.discord_history[-SHORT_TERM_LIMIT:]
        reply = self._handle_routed_request(
            clean_text,
            origin="discord",
            history=history + [{"role": "user", "content": clean_text}],
        )
        self.discord_history = (
            history + [{"role": "user", "content": clean_text}, {"role": "assistant", "content": reply}]
        )[-SHORT_TERM_LIMIT:]
        return reply

    def _handle_routed_request(self, text: str, origin: str, history: list[dict[str, str]], chat_id: str = "") -> str:
        context = self._tool_context(text, origin, history, chat_id)
        router = self.intent_router or IntentRouter(self.tool_registry)
        decision = router.route(self, text, context)
        action = str(decision.get("action", "answer")).lower()

        if action == "clarify":
            return str(decision.get("question") or "Pode me dar mais contexto?")

        if action == "tool":
            tool_name = str(decision.get("tool", "")).strip()
            tool_result = self.tool_registry.execute(tool_name, text, context)
            if not tool_result.get("ok"):
                return str(tool_result.get("error") or "A ferramenta não conseguiu executar o pedido.")
            return self._naturalize_tool_result(text, tool_name, tool_result, context)

        if not self.model:
            return "Escolha um modelo antes de enviar mensagens ou use um pedido de configuração/memória/status."

        try:
            return self._complete_messages(self._messages_for_direct_context(history), timeout=300)
        except RuntimeError as error:
            return str(error)

    def _tool_context(
        self,
        text: str,
        origin: str,
        history: list[dict[str, str]],
        chat_id: str = "",
    ) -> dict[str, Any]:
        memories = self.memory.load_relevant_long_term_memories(text)
        return {
            "api": self,
            "origin": origin,
            "chat_id": chat_id,
            "message": text,
            "history": history[-SHORT_TERM_LIMIT:],
            "memories": memories,
            "settings": {
                "provider_id": self.provider_id,
                "provider_name": PROVIDERS.get(self.provider_id, {}).get("name", self.provider_id),
                "base_url": self.base_url,
                "model": self.model,
                "system_prompt": self.system_prompt,
                "has_api_key": bool(self.api_key),
                "discord": self.discord_bot.public_status(),
            },
            "tools": self.tool_registry.descriptions(),
            "tool_errors": self.tool_registry.load_errors,
        }

    def _messages_for_direct_context(self, history: list[dict[str, str]]) -> list[dict[str, str]]:
        messages: list[dict[str, str]] = []
        if self.system_prompt.strip():
            messages.append({"role": "system", "content": self.system_prompt.strip()})
        messages.extend(history[-SHORT_TERM_LIMIT:])
        return messages

    def _naturalize_tool_result(
        self,
        user_text: str,
        tool_name: str,
        tool_result: dict[str, Any],
        context: dict[str, Any],
    ) -> str:
        result_text = str(tool_result.get("result", "")).strip()
        if not self.model:
            return result_text or "Ferramenta executada."

        system_message = (
            "Você é Elyra. Explique ao usuário, em português do Brasil, o resultado da ferramenta de forma natural, "
            "curta e útil. Não invente ações além do resultado recebido."
        )
        payload = {
            "pedido_usuario": user_text,
            "ferramenta": tool_name,
            "resultado": tool_result,
            "origem": context.get("origin"),
        }
        try:
            return self._complete_messages(
                [
                    {"role": "system", "content": system_message},
                    {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
                ],
                timeout=120,
                temperature=0.3,
            )
        except RuntimeError:
            return result_text or "Ferramenta executada."

    def list_chats(self) -> str:
        chats = self.memory.list_chats()
        return to_json({"ok": True, "chats": chats})

    def create_chat(self, title: str = "") -> str:
        chat = self.memory.create_chat(title)
        self.histories[chat["id"]] = []
        return to_json({"ok": True, "chat": {**chat, "messages": []}})

    def delete_chat(self, chat_id: str) -> str:
        if not self.memory.chat_exists(chat_id):
            return to_json({"ok": False, "error": "Conversa não encontrada."})
        self.memory.delete_chat(chat_id)
        self.histories.pop(chat_id, None)
        return to_json({"ok": True, "chats": self.memory.list_chats()})

    def list_models(self, provider_id: str, base_url: str, api_key: str) -> str:
        if provider_id not in PROVIDERS:
            return to_json({"ok": False, "error": "Provedor inválido."})

        config = PROVIDERS[provider_id]
        target_base_url = base_url.strip() or config["base_url"]
        if not target_base_url:
            return to_json({"ok": False, "error": "Informe a base URL do provedor."})

        if config["needs_key"] and not (api_key.strip() or self.api_key):
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

    def send_message(self, chat_id: str, message: str) -> str:
        if not self.memory.chat_exists(chat_id):
            return to_json({"ok": False, "reply": "Conversa não encontrada."})

        text = message.strip()
        if not text:
            return to_json({"ok": False, "reply": "Digite uma mensagem para conversar."})

        token_match = re.fullmatch(r"/token\s+(.+)", text, flags=re.IGNORECASE | re.DOTALL)
        if token_match:
            token = token_match.group(1).strip()
            ok, reply = self.discord_bot.start(token)
            if ok:
                self.discord_token = token
                self.settings_store.save(self._settings())
            return to_json({"ok": ok, "reply": reply, "command": "discord_token"})

        if re.fullmatch(r"/discord(?:\s+status)?", text, flags=re.IGNORECASE):
            status = self.discord_bot.public_status()
            if status["status"] == "conectado":
                reply = f"Bot do Discord conectado como {status['bot_name']}."
            elif status["status"] == "erro":
                reply = f"Discord com erro: {status['error']}"
            else:
                reply = f"Discord: {status['status']}."
            return to_json({"ok": status["status"] != "erro", "reply": reply, "command": "discord_status"})

        user_message = {"role": "user", "content": text}
        history = self._history_for_chat(chat_id)
        history.append(user_message)
        for memory_candidate in extract_long_term_memory_candidates(text):
            self.memory.save_long_term_memory(memory_candidate, source="explicit", confidence=0.95, evidence=text)

        reply = self._handle_routed_request(text, origin="app", history=history, chat_id=chat_id)

        assistant_message = {"role": "assistant", "content": reply}
        history.append(assistant_message)
        self.memory.save_message(chat_id, user_message["role"], user_message["content"])
        self.memory.save_message(chat_id, assistant_message["role"], assistant_message["content"])
        self._schedule_memory_extraction(chat_id, text, reply)
        return to_json({"ok": True, "reply": reply})

    def clear_chat(self, chat_id: str) -> str:
        if not self.memory.chat_exists(chat_id):
            return to_json({"ok": False, "error": "Conversa não encontrada."})
        self.histories[chat_id] = []
        self.memory.clear_messages(chat_id)
        return to_json({"ok": True})

    def get_history(self, chat_id: str) -> str:
        if not self.memory.chat_exists(chat_id):
            return to_json({"ok": False, "history": []})
        return to_json({"ok": True, "history": self._history_for_chat(chat_id)})

    def get_memory(self) -> str:
        chats = self.memory.list_chats()
        first_chat_id = chats[0]["id"] if chats else self.memory.create_chat(DEFAULT_CHAT_TITLE)["id"]
        return to_json(
            {
                "ok": True,
                "short_term": self.memory.load_short_term_messages(first_chat_id),
                "long_term": self.memory.load_all_long_term_memories(),
            }
        )

    def remember(self, content: str) -> str:
        clean_content = normalize_memory_text(content)
        if not clean_content:
            return to_json({"ok": False, "error": "Memória vazia ou curta demais."})
        self.memory.save_long_term_memory(clean_content, source="manual", confidence=1.0)
        return to_json({"ok": True, "memory": clean_content})

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
            "discord_token": self.discord_token,
        }

    def _public_settings(self) -> dict[str, Any]:
        return {
            "provider_id": self.provider_id,
            "base_url": self.base_url,
            "api_key": "",
            "has_api_key": bool(self.api_key),
            "model": self.model,
            "system_prompt": self.system_prompt,
            "discord": self.discord_bot.public_status(),
            "has_discord_token": bool(self.discord_token),
        }

    def _history_for_chat(self, chat_id: str) -> list[dict[str, str]]:
        if chat_id not in self.histories:
            self.histories[chat_id] = self.memory.load_short_term_messages(chat_id)
        return self.histories[chat_id]

    def _schedule_memory_extraction(self, chat_id: str, user_text: str, assistant_text: str) -> None:
        thread = threading.Thread(
            target=self._extract_and_save_long_term_memories,
            args=(chat_id, user_text, assistant_text),
            daemon=True,
        )
        thread.start()

    def _extract_and_save_long_term_memories(self, chat_id: str, user_text: str, assistant_text: str) -> None:
        try:
            memories = self._suggest_long_term_memories(chat_id, user_text, assistant_text)
        except RuntimeError:
            memories = []

        if not memories:
            memories = [
                {"content": candidate, "confidence": 0.75, "evidence": user_text}
                for candidate in extract_long_term_memory_candidates(user_text)
            ]

        for memory in memories[:5]:
            content = normalize_memory_text(str(memory.get("content", "")))
            if not content:
                continue
            confidence = memory.get("confidence", 0.75)
            evidence = str(memory.get("evidence", user_text))
            try:
                self.memory.save_long_term_memory(content, source="model", confidence=float(confidence), evidence=evidence)
            except (TypeError, ValueError):
                self.memory.save_long_term_memory(content, source="model", confidence=0.75, evidence=evidence)

    def _suggest_long_term_memories(
        self,
        chat_id: str,
        user_text: str,
        assistant_text: str,
    ) -> list[dict[str, Any]]:
        recent_context = self._history_for_chat(chat_id)[-6:]
        existing_memories = self.memory.load_relevant_long_term_memories(user_text, limit=8)
        system_message = (
            "Você é o seletor de memória longa da Elyra. "
            "Analise a última troca e decida se há fatos estáveis e úteis para conversas futuras. "
            "Guarde apenas preferências, identidade, objetivos, projetos, estilo de trabalho, restrições, "
            "decisões duradouras ou contexto recorrente. "
            "Não guarde senhas, tokens, chaves de API, dados bancários, endereços completos, conteúdo íntimo, "
            "informações médicas sensíveis ou tarefas passageiras. "
            "Não invente nada. Se não houver algo bom para memorizar, retorne uma lista vazia. "
            "Responda somente JSON válido no formato: "
            "{\"memories\":[{\"content\":\"fato em uma frase\",\"confidence\":0.0,\"evidence\":\"trecho curto\"}]}"
        )
        user_payload = {
            "memorias_existentes": existing_memories,
            "historico_recente": recent_context,
            "ultima_mensagem_usuario": user_text,
            "ultima_resposta_elyra": assistant_text[:1200],
        }
        raw = self._complete_messages(
            [
                {"role": "system", "content": system_message},
                {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
            ],
            timeout=MEMORY_EXTRACTION_TIMEOUT,
            temperature=0,
        )
        data = extract_json_object(raw)
        raw_memories = data.get("memories", [])
        if not isinstance(raw_memories, list):
            return []

        memories: list[dict[str, Any]] = []
        for item in raw_memories:
            if isinstance(item, str):
                memories.append({"content": item, "confidence": 0.65, "evidence": user_text})
            elif isinstance(item, dict):
                memories.append(item)
        return memories

    def _messages_for_provider(self, chat_id: str) -> list[dict[str, str]]:
        messages: list[dict[str, str]] = []
        if self.system_prompt.strip():
            messages.append({"role": "system", "content": self.system_prompt.strip()})

        history = self._history_for_chat(chat_id)
        current_user_text = ""
        for message in reversed(history):
            if message.get("role") == "user":
                current_user_text = message.get("content", "")
                break

        long_term_memories = self.memory.load_relevant_long_term_memories(current_user_text)
        if long_term_memories:
            memory_context = "Memória longa da Elyra sobre o usuário:\n" + "\n".join(
                f"- {memory}" for memory in long_term_memories
            )
            messages.append({"role": "system", "content": memory_context})

        messages.extend(history[-SHORT_TERM_LIMIT:])
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

    def _complete_messages(self, messages: list[dict[str, str]], timeout: int = 300, temperature: float = 0.7) -> str:
        config = PROVIDERS[self.provider_id]
        if config["kind"] == "ollama":
            payload = {
                "model": self.model,
                "messages": messages,
                "stream": False,
                "options": {"temperature": temperature},
            }
            request = Request(
                urljoin(normalize_base_url(self.base_url), "api/chat"),
                data=json.dumps(payload).encode("utf-8"),
                headers=self._headers(),
                method="POST",
            )
            data = read_response(request, timeout=timeout)
            content = data.get("message", {}).get("content")
            if not content:
                raise RuntimeError("O provedor respondeu sem conteúdo.")
            return str(content)

        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
        }
        request = Request(
            urljoin(normalize_base_url(self.base_url), "chat/completions"),
            data=json.dumps(payload).encode("utf-8"),
            headers=self._headers(),
            method="POST",
        )
        data = read_response(request, timeout=timeout)
        choices = data.get("choices", [])
        if not choices:
            raise RuntimeError("O provedor respondeu sem escolhas de mensagem.")
        content = choices[0].get("message", {}).get("content")
        if not content:
            raise RuntimeError("O provedor respondeu sem conteúdo.")
        return str(content)

    def _chat_ollama(self, chat_id: str) -> str:
        return self._complete_messages(self._messages_for_provider(chat_id), timeout=300)

    def _chat_openai_compatible(self, chat_id: str) -> str:
        return self._complete_messages(self._messages_for_provider(chat_id), timeout=300)


def main() -> None:
    migrate_legacy_user_files()
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
