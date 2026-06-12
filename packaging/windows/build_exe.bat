@echo off
setlocal
cd /d "%~dp0\..\.."

set "PYTHON=python"
py -3 --version >nul 2>nul
if %ERRORLEVEL% equ 0 set "PYTHON=py -3"

if not exist ".venv\Scripts\python.exe" (
  %PYTHON% -m venv .venv
)

set "PYTHON=.venv\Scripts\python.exe"
%PYTHON% build_installer.py --mode onefile
if %ERRORLEVEL% neq 0 exit /b %ERRORLEVEL%
echo EXE gerado em dist\Elyra Installer.exe
