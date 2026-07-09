# AgentBridge Install Guide

AgentBridge supports Windows, macOS, and Linux with the same Python application code. The scripts in `scripts/` create a virtual environment, install dependencies, create local config files when missing, and run a diagnostic check.

## Requirements

- Python 3.11 or newer.
- Network access for `pip install`.
- Optional: Node.js with `npx` when using `python -m app.tools.configure_cursor --tunnel cloudflared`.
- Optional: Cursor installed when using `python -m app.tools.configure_cursor`.
- Optional: authenticated Grok CLI and Codex CLI for live agent execution.

## Windows

```powershell
git clone https://github.com/Zulut30/AgentBridge.git
cd AgentBridge

Set-ExecutionPolicy -Scope Process Bypass
.\scripts\install.ps1
.\scripts\run.ps1
```

In another PowerShell window:

```powershell
.\scripts\check.ps1 -Server
```

Configure Cursor with a public HTTPS tunnel when Cursor blocks local/private network providers:

```powershell
python -m app.tools.configure_cursor --tunnel cloudflared --force --open
```

## macOS

```bash
git clone https://github.com/Zulut30/AgentBridge.git
cd AgentBridge

chmod +x scripts/*.sh
./scripts/install.sh
./scripts/run.sh
```

In another terminal:

```bash
./scripts/check.sh --server
```

Configure Cursor:

```bash
python -m app.tools.configure_cursor --tunnel cloudflared --force --open
```

## Linux

```bash
git clone https://github.com/Zulut30/AgentBridge.git
cd AgentBridge

chmod +x scripts/*.sh
./scripts/install.sh
./scripts/run.sh
```

In another terminal:

```bash
./scripts/check.sh --server
```

If Cursor is running in the same desktop session, configure it with:

```bash
python -m app.tools.configure_cursor --tunnel cloudflared --force --open
```

## Manual Install

```bash
python -m venv .venv
. ./.venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt

cp .env.example .env
cp examples/agentbridge.yaml agentbridge.yaml

python -m uvicorn app.main:app --host 127.0.0.1 --port 8787
```

## Diagnostics

Run local install checks:

```bash
python -m app.tools.doctor
```

Run local install checks plus HTTP endpoint checks against the configured server:

```bash
python -m app.tools.doctor --server
```

The doctor checks Python version, importable dependencies, config loading, project root, optional Grok/Codex CLI availability, model preset count, and OpenAI-compatible HTTP endpoints when `--server` is used.
