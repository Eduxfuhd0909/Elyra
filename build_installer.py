#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent
SEPARATOR = ";" if os.name == "nt" else ":"


def venv_python() -> Path:
    if os.name == "nt":
        return ROOT / ".venv" / "Scripts" / "python.exe"
    return ROOT / ".venv" / "bin" / "python"


def ensure_build_venv() -> None:
    if os.environ.get("ELYRA_BUILD_IN_VENV") == "1":
        return
    if sys.prefix != sys.base_prefix:
        return

    python = venv_python()
    if not python.exists():
        subprocess.run([sys.executable, "-m", "venv", str(ROOT / ".venv")], cwd=ROOT, check=True)

    env = os.environ.copy()
    env["ELYRA_BUILD_IN_VENV"] = "1"
    subprocess.run([str(python), *sys.argv], cwd=ROOT, env=env, check=True)
    raise SystemExit(0)


def main() -> None:
    ensure_build_venv()

    parser = argparse.ArgumentParser(description="Build Elyra Installer with PyInstaller.")
    parser.add_argument(
        "--mode",
        choices=("onefile", "onedir"),
        default="onefile",
        help="Use onefile for single executable or onedir for app bundles.",
    )
    args = parser.parse_args()

    subprocess.run([sys.executable, "-m", "pip", "install", "--upgrade", "pip"], cwd=ROOT, check=True)
    subprocess.run([sys.executable, "-m", "pip", "install", "pyinstaller>=6.0", "pywebview[qt6]>=5.0"], cwd=ROOT, check=True)
    mode_flag = "--onefile" if args.mode == "onefile" else "--onedir"
    output_name = "Elyra Installer.exe" if os.name == "nt" and args.mode == "onefile" else "Elyra Installer"
    output_path = ROOT / "dist" / output_name
    app_path = ROOT / "dist" / "Elyra Installer.app"

    if output_path.exists():
        if output_path.is_dir():
            shutil.rmtree(output_path)
        else:
            output_path.unlink()
    if app_path.exists():
        shutil.rmtree(app_path)

    subprocess.run(
        [
            sys.executable,
            "-m",
            "PyInstaller",
            "--noconfirm",
            "--clean",
            "--name",
            "Elyra Installer",
            mode_flag,
            "--windowed",
            "--add-data",
            f"installer_web{SEPARATOR}installer_web",
            "installer_app.py",
        ],
        cwd=ROOT,
        check=True,
    )


if __name__ == "__main__":
    main()
