# Contributing to Elyra

Thanks for wanting to improve Elyra.

## Development Setup

```bash
git clone https://github.com/Eduxfuhd0909/Elyra.git
cd Elyra
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

On Windows, activate the environment with:

```bat
.venv\Scripts\activate
```

## Before Opening a Pull Request

- Run `python3 -m compileall app.py installer_app.py build_installer.py setup.py`.
- Run `node --check web/app.js` if Node.js is installed.
- Do not commit `elyra_settings.json`, SQLite databases, API keys, build folders, or release binaries.
- Keep provider changes compatible with OpenAI-compatible APIs when possible.

## Feature Requests

Feature requests are welcome. Please explain the user workflow, not only the implementation idea, so the feature can fit naturally into Elyra.
