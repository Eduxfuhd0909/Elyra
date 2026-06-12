import os
import platform
import re
import shutil
import shlex
import subprocess
import sys
import unicodedata
import webbrowser
from pathlib import Path


TOOL_NAME = "local_system_tool"
TOOL_DESCRIPTION = (
    "Ferramenta local multiplataforma para Linux, Windows e macOS. "
    "Mostra informações do sistema, lista pastas, lê arquivos pequenos, abre URLs/caminhos/apps "
    "move arquivos/pastas entre diretórios do usuário e executa comandos informativos permitidos."
)

MAX_READ_BYTES = 80_000
MAX_LIST_ITEMS = 80
MAX_COMMAND_OUTPUT = 12_000

SAFE_COMMANDS = {
    "date",
    "dir",
    "df",
    "echo",
    "free",
    "hostname",
    "ip",
    "ipconfig",
    "ls",
    "pwd",
    "uname",
    "ver",
    "whoami",
}

BLOCKED_TOKENS = {
    "rm",
    "del",
    "erase",
    "rmdir",
    "format",
    "mkfs",
    "shutdown",
    "reboot",
    "poweroff",
    "sudo",
    "su",
    "chmod",
    "chown",
    "mv",
    "move",
    "cp",
    "copy",
    "curl",
    "wget",
    "python",
    "python3",
    "pip",
    "npm",
    "git",
}


KNOWN_FOLDER_ALIASES = {
    "desktop": ("Desktop", "Área de Trabalho", "Area de Trabalho", "Área de trabalho", "area de trabalho"),
    "area de trabalho": ("Desktop", "Área de Trabalho", "Area de Trabalho", "Área de trabalho", "area de trabalho"),
    "downloads": ("Downloads", "downloads"),
    "download": ("Downloads", "downloads"),
    "documentos": ("Documents", "Documentos", "documents"),
    "documents": ("Documents", "Documentos", "documents"),
    "imagens": ("Pictures", "Imagens", "images"),
    "pictures": ("Pictures", "Imagens", "images"),
    "musicas": ("Music", "Músicas", "Musicas", "music"),
    "music": ("Music", "Músicas", "Musicas", "music"),
    "videos": ("Videos", "Vídeos", "videos"),
}

MOVE_SEPARATORS = (
    r"\s+(?:para|pra|pro|p/|->)\s+",
    r"\s+(?:ate|até)\s+",
)


def _system_name():
    if sys.platform.startswith("win"):
        return "windows"
    if sys.platform == "darwin":
        return "macos"
    if sys.platform.startswith("linux"):
        return "linux"
    return sys.platform


def _extract_after(text, patterns):
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE | re.DOTALL)
        if match:
            return match.group(1).strip(" .:;\"'")
    return ""


def _strip_natural_path_noise(raw_path):
    cleaned = raw_path.strip().strip("\"'")
    cleaned = re.sub(r"\bdfo\b", "do", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\b(a|o|os|as|uma|um)\s+", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\b(pasta|diret[oó]rio|folder)\b", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(
        r"\b(do|da|de|no|na|em)\s+(meu|minha|este|esse|nesse|neste|seu|sua)\s+"
        r"(pc|computador|linux|windows|mac|macos|sistema|m[aá]quina)\b",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(r"\b(do|da|de|no|na|em)\s+(pc|computador|sistema|m[aá]quina)\b", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip(" .:;\"'")


def _fold_text(text):
    normalized = unicodedata.normalize("NFKD", text)
    return "".join(char for char in normalized if not unicodedata.combining(char)).lower()


def _xdg_user_dir(kind):
    if not sys.platform.startswith("linux"):
        return None
    try:
        completed = subprocess.run(
            ["xdg-user-dir", kind],
            capture_output=True,
            text=True,
            timeout=5,
            shell=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    path = Path(completed.stdout.strip())
    return path if completed.returncode == 0 and path.exists() else None


def _known_folder_path(cleaned):
    lowered = _fold_text(cleaned)
    for alias, candidates in KNOWN_FOLDER_ALIASES.items():
        if alias not in lowered:
            continue

        if alias in {"desktop", "area de trabalho"}:
            xdg_path = _xdg_user_dir("DESKTOP")
            if xdg_path:
                return xdg_path
        if alias in {"downloads", "download"}:
            xdg_path = _xdg_user_dir("DOWNLOAD")
            if xdg_path:
                return xdg_path
        if alias in {"documentos", "documents"}:
            xdg_path = _xdg_user_dir("DOCUMENTS")
            if xdg_path:
                return xdg_path
        if alias in {"imagens", "pictures"}:
            xdg_path = _xdg_user_dir("PICTURES")
            if xdg_path:
                return xdg_path
        if alias in {"musicas", "music"}:
            xdg_path = _xdg_user_dir("MUSIC")
            if xdg_path:
                return xdg_path
        if alias == "videos":
            xdg_path = _xdg_user_dir("VIDEOS")
            if xdg_path:
                return xdg_path

        for candidate in candidates:
            path = Path.home() / candidate
            if path.exists():
                return path.resolve()
        return (Path.home() / candidates[0]).resolve()
    return None


def _resolve_path(raw_path):
    if not raw_path:
        return Path.home()
    cleaned = _strip_natural_path_noise(raw_path)
    cleaned = cleaned.replace("minha home", "~").replace("meu home", "~")
    cleaned = cleaned.replace("pasta home", "~")
    expanded = Path(os.path.expandvars(os.path.expanduser(cleaned)))
    if expanded.is_absolute() or "/" in cleaned or "\\" in cleaned:
        return expanded.resolve()
    known_path = _known_folder_path(cleaned)
    if known_path:
        return known_path
    return expanded.resolve()


def _resolve_child_in_folder(child_name, folder_hint):
    parent = _resolve_path(folder_hint)
    child = _strip_natural_path_noise(child_name)
    child = re.sub(r"^(arquivo|pasta|diret[oó]rio|folder)\s+", "", child, flags=re.IGNORECASE).strip()
    if not child:
        return parent
    direct = Path(os.path.expandvars(os.path.expanduser(child)))
    if direct.is_absolute():
        return direct.resolve()
    return (parent / child).resolve()


def _system_info():
    return (
        "Sistema local:\n"
        f"- plataforma: {_system_name()}\n"
        f"- SO: {platform.platform()}\n"
        f"- release: {platform.release()}\n"
        f"- máquina: {platform.machine()}\n"
        f"- python: {platform.python_version()}\n"
        f"- usuário: {os.environ.get('USERNAME') or os.environ.get('USER') or 'desconhecido'}\n"
        f"- home: {Path.home()}\n"
        f"- diretório atual: {Path.cwd()}"
    )


def _list_path(path):
    target = _resolve_path(path)
    if not target.exists():
        return {"ok": False, "error": f"Caminho não encontrado: {target}", "result": ""}
    if not target.is_dir():
        return {"ok": False, "error": f"Não é uma pasta: {target}", "result": ""}

    entries = []
    for item in sorted(target.iterdir(), key=lambda value: (not value.is_dir(), value.name.lower()))[:MAX_LIST_ITEMS]:
        kind = "pasta" if item.is_dir() else "arquivo"
        entries.append(f"- [{kind}] {item.name}")

    suffix = ""
    try:
        total = sum(1 for _ in target.iterdir())
        if total > MAX_LIST_ITEMS:
            suffix = f"\n... e mais {total - MAX_LIST_ITEMS} item(ns)."
    except OSError:
        pass

    return {"ok": True, "result": f"Conteúdo de {target}:\n" + "\n".join(entries) + suffix, "error": ""}


def _parse_move_request(text):
    clean_text = re.sub(r"\bdfo\b", "do", text.strip(), flags=re.IGNORECASE)
    clean_text = re.sub(r"^(?:consegue|pode|por favor|pfv|favor)\s+", "", clean_text, flags=re.IGNORECASE).strip()

    move_match = re.search(
        r"(?:mover|move|mova|mov[eê]r|transferir|transfere|colocar|coloca|manda|joga)\s+(.+)$",
        clean_text,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if not move_match:
        return "", ""

    payload = move_match.group(1).strip()
    separator_pattern = "|".join(MOVE_SEPARATORS)
    parts = re.split(separator_pattern, payload, maxsplit=1, flags=re.IGNORECASE)
    if len(parts) != 2:
        return "", ""

    source_phrase = parts[0].strip()
    destination_phrase = parts[1].strip()
    source_match = re.search(
        r"(.+?)\s+(?:do|da|de|no|na|em)\s+(.+)$",
        source_phrase,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if source_match:
        source = _resolve_child_in_folder(source_match.group(1), source_match.group(2))
    else:
        source = _resolve_path(source_phrase)

    destination = _resolve_path(destination_phrase)
    return str(source), str(destination)


def _move_path(source_text, destination_text):
    source = _resolve_path(source_text)
    destination = _resolve_path(destination_text)
    if not source.exists():
        return {"ok": False, "error": f"Origem não encontrada: {source}", "result": ""}
    if not destination.exists():
        return {"ok": False, "error": f"Destino não encontrado: {destination}", "result": ""}
    if not destination.is_dir():
        return {"ok": False, "error": f"Destino não é uma pasta: {destination}", "result": ""}
    target = destination / source.name
    if target.exists():
        return {"ok": False, "error": f"Já existe um item com esse nome no destino: {target}", "result": ""}

    try:
        moved_to = shutil.move(str(source), str(destination))
    except OSError as error:
        return {"ok": False, "error": f"Não consegui mover: {error}", "result": ""}

    return {"ok": True, "result": f"Movido de {source} para {Path(moved_to).resolve()}.", "error": ""}


def _read_file(path):
    target = _resolve_path(path)
    if not target.exists():
        return {"ok": False, "error": f"Arquivo não encontrado: {target}", "result": ""}
    if not target.is_file():
        return {"ok": False, "error": f"Não é um arquivo: {target}", "result": ""}
    if target.stat().st_size > MAX_READ_BYTES:
        return {"ok": False, "error": f"Arquivo muito grande para leitura direta: {target}", "result": ""}

    try:
        content = target.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        content = target.read_text(encoding="latin-1", errors="replace")
    return {"ok": True, "result": f"Conteúdo de {target}:\n{content}", "error": ""}


def _open_target(target):
    if re.match(r"^https?://", target, flags=re.IGNORECASE):
        webbrowser.open(target)
        return {"ok": True, "result": f"URL aberta: {target}", "error": ""}

    path = Path(os.path.expandvars(os.path.expanduser(target.strip("\"'"))))
    if path.exists():
        if sys.platform.startswith("win"):
            os.startfile(str(path))  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(path)])
        else:
            subprocess.Popen(["xdg-open", str(path)])
        return {"ok": True, "result": f"Caminho aberto: {path.resolve()}", "error": ""}

    command = target.strip()
    if not command:
        return {"ok": False, "error": "Informe o que devo abrir.", "result": ""}
    try:
        if sys.platform.startswith("win"):
            subprocess.Popen(["cmd", "/c", "start", "", command], shell=False)
        elif sys.platform == "darwin":
            subprocess.Popen(["open", "-a", command])
        else:
            subprocess.Popen([command])
    except OSError as error:
        return {"ok": False, "error": f"Não consegui abrir '{command}': {error}", "result": ""}
    return {"ok": True, "result": f"Tentei abrir o aplicativo: {command}", "error": ""}


def _run_safe_command(command_text):
    try:
        parts = shlex.split(command_text, posix=not sys.platform.startswith("win"))
    except ValueError as error:
        return {"ok": False, "error": f"Comando inválido: {error}", "result": ""}

    if not parts:
        return {"ok": False, "error": "Informe um comando.", "result": ""}

    executable = Path(parts[0]).name.lower()
    lowered_parts = {Path(part).name.lower() for part in parts}
    if executable not in SAFE_COMMANDS or lowered_parts & BLOCKED_TOKENS:
        return {
            "ok": False,
            "error": (
                "Por segurança, esta ferramenta só executa comandos informativos permitidos. "
                f"Permitidos: {', '.join(sorted(SAFE_COMMANDS))}."
            ),
            "result": "",
        }

    try:
        completed = subprocess.run(
            parts,
            capture_output=True,
            text=True,
            timeout=20,
            shell=False,
            cwd=str(Path.home()),
        )
    except OSError as error:
        return {"ok": False, "error": f"Falha ao executar comando: {error}", "result": ""}
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "Comando excedeu o tempo limite.", "result": ""}

    output = (completed.stdout or completed.stderr or "").strip()
    if len(output) > MAX_COMMAND_OUTPUT:
        output = output[:MAX_COMMAND_OUTPUT] + "\n... saída truncada."
    status = "ok" if completed.returncode == 0 else f"código {completed.returncode}"
    return {"ok": completed.returncode == 0, "result": f"Comando finalizado ({status}):\n{output}", "error": ""}


def run(raw_request, context):
    text = raw_request.strip()
    lowered = text.lower()

    if re.search(r"\b(mover|move|mova|mov[eê]r|transferir|transfere|colocar|coloca|manda|joga)\b", lowered):
        source, destination = _parse_move_request(text)
        if not source or not destination:
            return {
                "ok": False,
                "error": "Não entendi origem e destino. Exemplo: mover a pasta chtbot da área de trabalho para imagens.",
                "result": "",
            }
        return _move_path(source, destination)

    if re.search(r"\b(sistema|pc|computador|linux|windows|macos|mac|so|operacional|status)\b", lowered):
        if not re.search(r"\b(abr|listar|lista|ler|leia|comando|executa|roda)\b", lowered):
            return {"ok": True, "result": _system_info(), "error": ""}

    if re.search(r"\b(listar|lista|mostra arquivos|mostrar arquivos|ver pasta|ls|dir)\b", lowered):
        path = _extract_after(
            text,
            [
                r"(?:listar|lista|ver pasta|ls|dir)\s+(?:a\s+)?(?:pasta\s+)?(.+)$",
                r"(?:arquivos|conteúdo|conteudo)\s+(?:de|da|do|em)\s+(.+)$",
            ],
        )
        return _list_path(path)

    if re.search(r"\b(ler|leia|abrir conteudo|mostrar conteudo|cat)\b", lowered):
        path = _extract_after(
            text,
            [
                r"(?:ler|leia|cat)\s+(?:o\s+)?(?:arquivo\s+)?(.+)$",
                r"(?:conteúdo|conteudo)\s+(?:do|de|da)\s+(?:arquivo\s+)?(.+)$",
            ],
        )
        return _read_file(path)

    if re.search(r"\b(abrir|abre|open|inicia|iniciar)\b", lowered):
        target = _extract_after(
            text,
            [
                r"(?:abrir|abre|open|inicia|iniciar)\s+(.+)$",
            ],
        )
        return _open_target(target)

    if re.search(r"\b(comando|executa|executar|roda|rodar)\b", lowered):
        command = _extract_after(
            text,
            [
                r"(?:comando|executa|executar|roda|rodar)\s+(.+)$",
            ],
        )
        return _run_safe_command(command)

    return {"ok": True, "result": _system_info(), "error": ""}
