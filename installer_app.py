#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import webview


APP_NAME = "Elyra"
REPO_URL = os.environ.get("ELYRA_APP_REPO_URL", "https://github.com/Eduxfuhd0909/Elyra.git")
BRANCH = os.environ.get("ELYRA_APP_BRANCH", "main")
SETUP_DIR = Path(__file__).resolve().parent
RESOURCE_DIR = Path(getattr(sys, "_MEIPASS", SETUP_DIR))
INSTALLER_HTML = RESOURCE_DIR / "installer_web" / "index.html"


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
INSTALL_DIR = DATA_DIR / "source"
SETTINGS_PATH = DATA_DIR / "elyra_settings.json"
BACKUP_SETTINGS_PATH = DATA_DIR / "elyra_settings.backup.json"

DEFAULT_SYSTEM_PROMPT = """Você é Elyra, uma assistente pessoal inspirada no estilo Jarvis.
Fale em português do Brasil por padrão, com tom calmo, inteligente, direto e levemente sofisticado.
Ajude o usuário a pensar, decidir, organizar tarefas, explicar assuntos, escrever textos, programar e resolver problemas com precisão.
Seja proativa, mas não invente capacidades que não possui."""

PROVIDERS = {
    "ollama": {"name": "Ollama", "base_url": "http://localhost:11434", "needs_key": False},
    "openrouter": {"name": "OpenRouter", "base_url": "https://openrouter.ai/api/v1", "needs_key": True},
    "groq": {"name": "Groq", "base_url": "https://api.groq.com/openai/v1", "needs_key": True},
    "custom": {"name": "OpenAI Compatível", "base_url": "", "needs_key": False},
}


def to_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False)


def secure_file_permissions(path: Path) -> None:
    if os.name == "nt":
        return
    try:
        path.chmod(0o600)
    except OSError:
        pass


class SetupApi:
    def __init__(self) -> None:
        self.last_log = ""

    def get_setup_data(self) -> str:
        providers = [{"id": provider_id, **config} for provider_id, config in PROVIDERS.items()]
        return to_json(
            {
                "ok": True,
                "repo_url": REPO_URL,
                "branch": BRANCH,
                "providers": providers,
                "settings": self._load_settings(),
                "default_system_prompt": DEFAULT_SYSTEM_PROMPT,
            }
        )

    def get_status(self) -> str:
        local_commit = self._git_output(["rev-parse", "--short", "HEAD"], required=False)
        system_python = self._system_python()
        return to_json(
            {
                "ok": True,
                "status": {
                    "platform": platform.platform(),
                    "setup_python": sys.executable,
                    "system_python": str(system_python) if system_python else "",
                    "data_dir": str(DATA_DIR),
                    "install_dir": str(INSTALL_DIR),
                    "settings_file": str(SETTINGS_PATH),
                    "settings_exists": SETTINGS_PATH.exists(),
                    "git_available": shutil.which("git") is not None,
                    "python_available": system_python is not None,
                    "repo_exists": self._repo_exists(),
                    "venv_exists": self._venv_python().exists(),
                    "dependencies_ok": self._dependencies_ok(),
                    "local_commit": local_commit.strip() if local_commit else "",
                },
                "log": self.last_log,
            }
        )

    def install_all(
        self,
        provider_id: str,
        base_url: str,
        api_key: str,
        model: str,
        system_prompt: str,
    ) -> str:
        steps = [
            ("Clonando repositório", lambda: self.clone_or_update_repo(initial=True)),
            ("Criando ambiente virtual", self.create_venv),
            ("Instalando dependências", self.install_dependencies),
            (
                "Salvando configuração inicial",
                lambda: self.save_settings(provider_id, base_url, api_key, model, system_prompt),
            ),
        ]
        return self._run_steps(steps)

    def auto_install(self) -> str:
        steps = [
            ("Baixando a Elyra", self.ensure_repo),
            ("Criando ambiente virtual", self.ensure_venv),
            ("Instalando dependências", self.ensure_dependencies),
        ]
        return self._run_steps(steps)

    def ensure_repo(self) -> str:
        if shutil.which("git") is None:
            return to_json({"ok": False, "error": "Git não encontrado. Instale o Git e tente novamente."})

        if self._repo_exists():
            self.last_log = f"Elyra já está instalada em {INSTALL_DIR}"
            return to_json({"ok": True, "log": self.last_log})

        if INSTALL_DIR.exists() and any(INSTALL_DIR.iterdir()):
            return to_json(
                {
                    "ok": False,
                    "error": f"A pasta de instalação já existe e não está vazia: {INSTALL_DIR}",
                }
            )

        INSTALL_DIR.parent.mkdir(parents=True, exist_ok=True)
        return self._run_commands([["git", "clone", "--branch", BRANCH, REPO_URL, str(INSTALL_DIR)]])

    def ensure_venv(self) -> str:
        if self._venv_python().exists():
            self.last_log = f".venv já existe em {INSTALL_DIR / '.venv'}"
            return to_json({"ok": True, "log": self.last_log})
        return self.create_venv()

    def ensure_dependencies(self) -> str:
        if self._dependencies_ok():
            self.last_log = "Dependências já estão instaladas."
            return to_json({"ok": True, "log": self.last_log})
        return self.install_dependencies()

    def clone_or_update_repo(self, initial: bool = False) -> str:
        if shutil.which("git") is None:
            return to_json({"ok": False, "error": "Git não encontrado. Instale o Git e tente novamente."})

        if self._repo_exists():
            command = ["git", "pull", "--ff-only", "origin", BRANCH]
        elif INSTALL_DIR.exists() and any(INSTALL_DIR.iterdir()):
            return to_json(
                {
                    "ok": False,
                    "error": f"A pasta de instalação já existe e não está vazia: {INSTALL_DIR}",
                }
            )
        else:
            INSTALL_DIR.parent.mkdir(parents=True, exist_ok=True)
            command = ["git", "clone", "--branch", BRANCH, REPO_URL, str(INSTALL_DIR)]

        return self._run_commands([command])

    def create_venv(self) -> str:
        python = self._system_python()
        if not python:
            return to_json(
                {
                    "ok": False,
                    "error": "Python não encontrado no sistema. Instale Python 3.10+ e tente novamente.",
                }
            )

        result = json.loads(self._run_commands([[str(python), "-m", "venv", str(INSTALL_DIR / ".venv")]]))
        if not result.get("ok"):
            return to_json(result)

        self.last_log = f".venv criado em {INSTALL_DIR / '.venv'}"
        return to_json({"ok": True, "log": self.last_log})

    def install_dependencies(self) -> str:
        requirements = INSTALL_DIR / "requirements.txt"
        if not requirements.exists():
            return to_json({"ok": False, "error": "requirements.txt não encontrado no repositório clonado."})

        if not self._venv_python().exists():
            result = json.loads(self.create_venv())
            if not result.get("ok"):
                return to_json(result)

        python = str(self._venv_python())
        commands = [
            [python, "-m", "pip", "install", "--upgrade", "pip"],
            [python, "-m", "pip", "install", "-r", str(requirements)],
        ]
        return self._run_commands(commands)

    def save_settings(
        self,
        provider_id: str,
        base_url: str,
        api_key: str,
        model: str,
        system_prompt: str,
    ) -> str:
        if provider_id not in PROVIDERS:
            return to_json({"ok": False, "error": "Provedor inválido."})

        settings = {
            "provider_id": provider_id,
            "base_url": base_url.strip() or PROVIDERS[provider_id]["base_url"],
            "api_key": api_key.strip(),
            "model": model.strip(),
            "system_prompt": system_prompt.strip() or DEFAULT_SYSTEM_PROMPT,
            "likes": "",
            "dislikes": "",
            "tools": "",
        }
        try:
            SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
            with SETTINGS_PATH.open("w", encoding="utf-8") as file:
                json.dump(settings, file, ensure_ascii=False, indent=2)
            secure_file_permissions(SETTINGS_PATH)
        except OSError as error:
            return to_json({"ok": False, "error": str(error)})

        self.last_log = f"Configurações salvas em {SETTINGS_PATH}"
        return to_json({"ok": True, "settings": settings, "log": self.last_log})

    def check_updates(self) -> str:
        if not self._repo_exists():
            return to_json({"ok": False, "error": "A Elyra ainda não foi instalada/clonada."})

        fetch = json.loads(self._run_commands([["git", "fetch", "origin", BRANCH]]))
        if not fetch.get("ok"):
            return to_json(fetch)

        local = self._git_output(["rev-parse", "HEAD"], required=False).strip()
        remote = self._git_output(["rev-parse", f"origin/{BRANCH}"], required=False).strip()
        remote_short = self._git_output(["rev-parse", "--short", f"origin/{BRANCH}"], required=False).strip()
        message = self._git_output(["log", "-1", "--format=%s", f"origin/{BRANCH}"], required=False).strip()
        author = self._git_output(["log", "-1", "--format=%an", f"origin/{BRANCH}"], required=False).strip()
        date = self._git_output(["log", "-1", "--format=%ci", f"origin/{BRANCH}"], required=False).strip()

        return to_json(
            {
                "ok": True,
                "update_available": bool(local and remote and local != remote),
                "local_commit": local[:12],
                "remote_commit": remote_short,
                "message": message,
                "author": author,
                "date": date,
                "log": "Atualização disponível." if local != remote else "A Elyra já está atualizada.",
            }
        )

    def update_app(self) -> str:
        if not self._repo_exists():
            return to_json({"ok": False, "error": "A Elyra ainda não foi instalada/clonada."})

        logs = []
        if SETTINGS_PATH.exists():
            try:
                shutil.copy2(SETTINGS_PATH, BACKUP_SETTINGS_PATH)
                logs.append(f"Backup das configurações: {BACKUP_SETTINGS_PATH}")
            except OSError as error:
                return to_json({"ok": False, "error": f"Falha ao criar backup: {error}"})

        result = json.loads(self._run_commands([["git", "pull", "--ff-only", "origin", BRANCH]]))
        logs.append(result.get("log") or result.get("error", ""))
        if not result.get("ok"):
            self.last_log = "\n\n".join(logs)
            return to_json({"ok": False, "error": result.get("error"), "log": self.last_log})

        deps = json.loads(self.install_dependencies())
        logs.append(deps.get("log") or deps.get("error", ""))
        if not deps.get("ok"):
            self.last_log = "\n\n".join(logs)
            return to_json({"ok": False, "error": deps.get("error"), "log": self.last_log})

        self.last_log = "\n\n".join(logs)
        return to_json({"ok": True, "log": self.last_log})

    def open_app(self) -> str:
        app_file = INSTALL_DIR / "app.py"
        if not app_file.exists():
            return to_json({"ok": False, "error": "A Elyra ainda não foi instalada."})
        if not self._venv_python().exists():
            return to_json({"ok": False, "error": "A .venv ainda não foi criada."})

        try:
            subprocess.Popen(
                [str(self._venv_python()), str(app_file)],
                cwd=INSTALL_DIR,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=os.name != "nt",
            )
        except OSError as error:
            return to_json({"ok": False, "error": str(error)})

        return to_json({"ok": True, "log": "Elyra aberta em uma janela separada."})

    def open_install_folder(self) -> str:
        try:
            if sys.platform.startswith("linux"):
                subprocess.Popen(["xdg-open", str(DATA_DIR)])
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(DATA_DIR)])
            elif os.name == "nt":
                os.startfile(DATA_DIR)  # type: ignore[attr-defined]
            else:
                return to_json({"ok": False, "error": "Sistema não suportado para abrir pasta."})
        except OSError as error:
            return to_json({"ok": False, "error": str(error)})
        return to_json({"ok": True, "log": f"Pasta aberta: {DATA_DIR}"})

    def choose_executable(self) -> str:
        try:
            # Open native file dialog and return selected file
            result = webview.create_file_dialog(dialog_type="open_file", allow_multiple=False)
        except Exception as error:
            return to_json({"ok": False, "error": str(error)})

        if not result:
            return to_json({"ok": False, "error": "Nenhum arquivo selecionado."})

        # result can be a list of paths or a single path depending on pywebview
        path = result[0] if isinstance(result, (list, tuple)) else result
        return to_json({"ok": True, "path": str(path)})

    def create_desktop_shortcut(self, executable_path: str, name: str) -> str:
        try:
            exe = Path(executable_path)
            if not exe.exists():
                return to_json({"ok": False, "error": f"Arquivo não encontrado: {executable_path}"})
            # determine desktop dir
            desktop_dir = None
            try:
                if shutil.which("xdg-user-dir"):
                    completed = subprocess.run(["xdg-user-dir", "DESKTOP"], stdout=subprocess.PIPE, text=True)
                    val = completed.stdout.strip()
                    if val:
                        desktop_dir = Path(val)
            except Exception:
                desktop_dir = None

            if not desktop_dir:
                # fallback to XDG config or ~/Desktop
                desktop_dir = Path(os.environ.get("XDG_DESKTOP_DIR", Path.home() / "Desktop"))

            desktop_dir.mkdir(parents=True, exist_ok=True)
            desktop_file = desktop_dir / f"{name}.desktop"
            content = """[Desktop Entry]
Type=Application
Name={name}
Exec={exec}
Terminal=false
Categories=Utility;
""".format(name=name, exec=str(exe))

            with desktop_file.open("w", encoding="utf-8") as f:
                f.write(content)

            # make executable
            try:
                desktop_file.chmod(desktop_file.stat().st_mode | 0o111)
            except Exception:
                pass

            return to_json({"ok": True, "path": str(desktop_file), "log": f"Atalho criado: {desktop_file}"})
        except Exception as error:
            return to_json({"ok": False, "error": str(error)})

    def create_app_shortcut(self, name: str = "Elyra") -> str:
        app_file = INSTALL_DIR / "app.py"
        python = self._venv_python()
        if not app_file.exists() or not python.exists():
            return to_json({"ok": False, "error": "A Elyra ainda não está instalada completamente."})

        try:
            desktop_dir = self._desktop_dir()
            desktop_dir.mkdir(parents=True, exist_ok=True)

            if os.name == "nt":
                shortcut = desktop_dir / f"{name}.bat"
                content = self._launcher_script_content(python, app_file)
                shortcut.write_text(content, encoding="utf-8")
            else:
                shortcut = desktop_dir / f"{name}.desktop"
                content = self._desktop_entry_content(name, python, app_file)
                shortcut.write_text(content, encoding="utf-8")
                shortcut.chmod(shortcut.stat().st_mode | 0o111)
        except OSError as error:
            return to_json({"ok": False, "error": str(error)})

        return to_json({"ok": True, "path": str(shortcut), "log": f"Atalho criado: {shortcut}"})

    def create_menu_shortcut(self, name: str = "Elyra") -> str:
        app_file = INSTALL_DIR / "app.py"
        python = self._venv_python()
        if not app_file.exists() or not python.exists():
            return to_json({"ok": False, "error": "A Elyra ainda não está instalada completamente."})

        try:
            if os.name == "nt":
                root = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
                menu_dir = root / "Microsoft" / "Windows" / "Start Menu" / "Programs"
                shortcut = menu_dir / f"{name}.bat"
                content = self._launcher_script_content(python, app_file)
            elif sys.platform == "darwin":
                menu_dir = Path.home() / "Applications"
                shortcut = menu_dir / f"{name}.command"
                content = f'#!/bin/sh\ncd "{INSTALL_DIR}"\n"{python}" "{app_file}"\n'
            else:
                menu_dir = Path.home() / ".local" / "share" / "applications"
                shortcut = menu_dir / f"{name.lower()}.desktop"
                content = self._desktop_entry_content(name, python, app_file)

            menu_dir.mkdir(parents=True, exist_ok=True)
            shortcut.write_text(content, encoding="utf-8")
            if os.name != "nt":
                shortcut.chmod(shortcut.stat().st_mode | 0o111)
        except OSError as error:
            return to_json({"ok": False, "error": str(error)})

        return to_json({"ok": True, "path": str(shortcut), "log": f"Atalho de menu criado: {shortcut}"})

    def _desktop_dir(self) -> Path:
        if os.name == "nt":
            return Path(os.environ.get("USERPROFILE", str(Path.home()))) / "Desktop"

        if shutil.which("xdg-user-dir"):
            completed = subprocess.run(["xdg-user-dir", "DESKTOP"], stdout=subprocess.PIPE, text=True)
            desktop = completed.stdout.strip()
            if desktop:
                return Path(desktop)

        return Path.home() / "Desktop"

    def _desktop_entry_content(self, name: str, python: Path, app_file: Path) -> str:
        return """[Desktop Entry]
Type=Application
Name={name}
Exec={python} {app}
Path={cwd}
Terminal=false
Categories=Utility;
""".format(name=name, python=str(python), app=str(app_file), cwd=str(INSTALL_DIR))

    def _launcher_script_content(self, python: Path, app_file: Path) -> str:
        return f'@echo off\r\ncd /d "{INSTALL_DIR}"\r\n"{python}" "{app_file}"\r\n'

    def _run_steps(self, steps: list[tuple[str, Any]]) -> str:
        logs = []
        for label, action in steps:
            result = json.loads(action())
            logs.append(f"## {label}\n{result.get('log') or result.get('error', '')}")
            if not result.get("ok"):
                self.last_log = "\n\n".join(logs)
                return to_json({"ok": False, "error": result.get("error"), "log": self.last_log})
        self.last_log = "\n\n".join(logs)
        return to_json({"ok": True, "log": self.last_log})

    def _run_commands(self, commands: list[list[str]]) -> str:
        output = []
        for command in commands:
            output.append(f"$ {' '.join(command)}")
            try:
                completed = subprocess.run(
                    command,
                    cwd=INSTALL_DIR if self._repo_exists() else DATA_DIR,
                    text=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    check=False,
                )
            except OSError as error:
                self.last_log = "\n".join(output + [str(error)])
                return to_json({"ok": False, "error": str(error), "log": self.last_log})
            output.append(completed.stdout.strip())
            if completed.returncode != 0:
                self.last_log = "\n".join(output)
                return to_json({"ok": False, "error": f"Comando falhou: {' '.join(command)}", "log": self.last_log})
        self.last_log = "\n".join(output)
        return to_json({"ok": True, "log": self.last_log})

    def _repo_exists(self) -> bool:
        return (INSTALL_DIR / ".git").exists()

    def _venv_python(self) -> Path:
        if os.name == "nt":
            return INSTALL_DIR / ".venv" / "Scripts" / "python.exe"
        return INSTALL_DIR / ".venv" / "bin" / "python"

    def _system_python(self) -> Path | None:
        candidates = ["python3", "python"] if os.name != "nt" else ["py", "python"]
        for candidate in candidates:
            executable = shutil.which(candidate)
            if not executable:
                continue

            command = [executable, "-3", "--version"] if candidate == "py" else [executable, "--version"]
            completed = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            if completed.returncode == 0:
                return Path(executable)
        return None

    def _dependencies_ok(self) -> bool:
        python = self._venv_python()
        if not python.exists():
            return False
        command = [
            str(python),
            "-c",
            "import importlib.util; raise SystemExit(0 if importlib.util.find_spec('webview') else 1)",
        ]
        return subprocess.run(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0

    def _git_output(self, args: list[str], required: bool = True) -> str:
        if not self._repo_exists():
            return ""
        completed = subprocess.run(
            ["git", *args],
            cwd=INSTALL_DIR,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        if required and completed.returncode != 0:
            raise RuntimeError(completed.stderr.strip())
        return completed.stdout

    def _load_settings(self) -> dict[str, str]:
        if not SETTINGS_PATH.exists():
            return {}
        try:
            with SETTINGS_PATH.open("r", encoding="utf-8") as file:
                data = json.load(file)
        except (OSError, json.JSONDecodeError):
            return {}
        if not isinstance(data, dict):
            return {}
        return {str(key): str(value) for key, value in data.items()}


def main() -> None:
    if not INSTALLER_HTML.exists():
        raise FileNotFoundError(f"Painel não encontrado: {INSTALLER_HTML}")

    webview.create_window(
        "Elyra Installer",
        INSTALLER_HTML.as_uri(),
        js_api=SetupApi(),
        width=1120,
        height=760,
        min_size=(900, 640),
    )
    webview.start(gui="qt")


if __name__ == "__main__":
    main()
