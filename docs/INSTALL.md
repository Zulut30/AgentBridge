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
.\scripts\check.ps1 -Server -Cursor
```

Configure Cursor with a public HTTPS tunnel when Cursor blocks local/private network providers:

```powershell
python -m app.tools.configure_cursor --tunnel cloudflared --mcp --force --open
python -m app.tools.configure_cursor --mcp-only --mcp-json
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
./scripts/check.sh --server --cursor
```

Configure Cursor:

```bash
python -m app.tools.configure_cursor --tunnel cloudflared --mcp --force --open
python -m app.tools.configure_cursor --mcp-only --mcp-json
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
./scripts/check.sh --server --cursor
```

If Cursor is running in the same desktop session, configure it with:

```bash
python -m app.tools.configure_cursor --tunnel cloudflared --mcp --force --open
python -m app.tools.configure_cursor --mcp-only --mcp-json
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

Run Cursor-specific checks:

```bash
python -m app.tools.doctor --cursor --server
```

The doctor checks Python version, importable dependencies, config loading, project root, optional Grok/Codex CLI availability, model preset count, Grok subagent flag state, Cursor CLI support, Cursor provider state, Cursor MCP configuration, and OpenAI-compatible HTTP endpoints when `--server` is used.

## Cursor MCP Tools

AgentBridge can also register a local Cursor MCP server. This does not create `.cursor/rules` and does not force a model selection; you can keep switching models manually in Cursor.

Register through Cursor CLI:

```bash
python -m app.tools.configure_cursor --mcp-only
```

Write a project-local `.cursor/mcp.json`:

```bash
python -m app.tools.configure_cursor --mcp-only --mcp-json
```

The project-local MCP file is ignored by git because it contains absolute local paths and a local bearer token.
