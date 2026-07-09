import argparse
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.config import get_settings


APPLICATION_USER_KEY = "src.vs.platform.reactivestorage.browser.reactiveStorageServiceImpl.persistentStorage.applicationUser"
OPENAI_KEY_CELL = "cursorAuth/openAIKey"


def main() -> int:
    parser = argparse.ArgumentParser(description="Configure Cursor to use AgentBridge.")
    parser.add_argument("--base-url", default=None)
    parser.add_argument("--api-key", default=None)
    parser.add_argument("--default-model", default="agentbridge-auto")
    parser.add_argument("--db-path", default=None)
    parser.add_argument("--backup-dir", default=None)
    parser.add_argument("--tunnel", choices=["none", "cloudflared"], default="none")
    parser.add_argument("--tunnel-timeout", type=int, default=45)
    parser.add_argument("--mcp", action="store_true", help="Also register AgentBridge as a Cursor MCP server.")
    parser.add_argument("--mcp-only", action="store_true", help="Only register the Cursor MCP server; do not edit model settings.")
    parser.add_argument("--mcp-json", action="store_true", help="Write project .cursor/mcp.json instead of using cursor --add-mcp.")
    parser.add_argument("--mcp-name", default="agentbridge", help="Cursor MCP server name.")
    parser.add_argument("--mcp-base-url", default=None, help="AgentBridge root URL for MCP tools. Defaults to local server root.")
    parser.add_argument("--force", action="store_true", help="Write even when Cursor appears to be running.")
    parser.add_argument("--open", action="store_true", help="Open Cursor on the configured project after writing.")
    args = parser.parse_args()

    settings = get_settings()
    db_path = Path(args.db_path).expanduser().resolve() if args.db_path else cursor_state_db_path()
    backup_dir = Path(args.backup_dir).expanduser().resolve() if args.backup_dir else settings.config_dir_path / ".agentbridge" / "cursor-backups"
    api_key = args.api_key or settings.api_key
    tunnel_summary: dict[str, Any] | None = None
    base_url = args.base_url
    mcp_base_url = args.mcp_base_url or f"http://{settings.server.host}:{settings.server.port}"

    if args.mcp_only:
        summary = configure_cursor_mcp(settings, args.mcp_name, mcp_base_url, api_key, write_json=args.mcp_json)
        if args.open:
            open_cursor(settings.project_root_path)
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0

    if not db_path.exists():
        raise SystemExit(f"Cursor state database not found: {db_path}")
    if is_cursor_running() and not args.force:
        raise SystemExit("Cursor is running. Quit Cursor first or pass --force.")

    if args.tunnel == "cloudflared":
        tunnel_summary = start_cloudflared_tunnel(settings, timeout_seconds=args.tunnel_timeout)
        base_url = f"{tunnel_summary['publicUrl'].rstrip('/')}/v1"
    if not base_url:
        base_url = f"http://{settings.server.host}:{settings.server.port}/v1"

    summary = configure_cursor(
        db_path=db_path,
        backup_dir=backup_dir,
        base_url=base_url,
        api_key=api_key,
        model_ids=settings.cursor_model_ids(),
        default_model=args.default_model,
    )
    if tunnel_summary:
        summary["tunnel"] = tunnel_summary
    if args.mcp:
        summary["mcp"] = configure_cursor_mcp(settings, args.mcp_name, mcp_base_url, api_key, write_json=args.mcp_json)

    if args.open:
        open_cursor(settings.project_root_path)

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


def cursor_state_db_path() -> Path:
    if sys.platform == "win32":
        appdata = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
        return appdata / "Cursor" / "User" / "globalStorage" / "state.vscdb"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "Cursor" / "User" / "globalStorage" / "state.vscdb"
    return Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "Cursor" / "User" / "globalStorage" / "state.vscdb"


def open_cursor(project_root: Path) -> None:
    cursor_bin = shutil.which("cursor") or shutil.which("cursor.cmd") or shutil.which("Cursor.exe")
    if cursor_bin:
        subprocess.Popen([cursor_bin, "--reuse-window", str(project_root)], close_fds=True)
        return

    if sys.platform == "darwin":
        subprocess.Popen(["open", "-a", "Cursor", str(project_root)], close_fds=True)
        return

    if sys.platform == "win32":
        local_appdata = Path(os.environ.get("LOCALAPPDATA", ""))
        candidate = local_appdata / "Programs" / "cursor" / "Cursor.exe"
        if candidate.exists():
            subprocess.Popen([str(candidate), "--reuse-window", str(project_root)], close_fds=True)
            return

    raise RuntimeError("Could not find Cursor launcher.")


def is_cursor_running() -> bool:
    if sys.platform == "win32":
        result = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq Cursor.exe"],
            capture_output=True,
            text=True,
            check=False,
        )
        return "Cursor.exe" in result.stdout
    result = subprocess.run(["pgrep", "-x", "Cursor"], capture_output=True, text=True, check=False)
    return result.returncode == 0


def cursor_executable() -> str:
    cursor_bin = shutil.which("cursor") or shutil.which("cursor.cmd") or shutil.which("Cursor.exe")
    if cursor_bin:
        return cursor_bin
    if sys.platform == "win32":
        local_appdata = Path(os.environ.get("LOCALAPPDATA", ""))
        candidate = local_appdata / "Programs" / "cursor" / "Cursor.exe"
        if candidate.exists():
            return str(candidate)
    raise RuntimeError("Could not find Cursor launcher.")


def install_cursor_mcp(
    *,
    settings: Any,
    name: str,
    base_url: str,
    api_key: str,
) -> dict[str, Any]:
    definition = _cursor_add_mcp_definition(settings, name, base_url, api_key)
    cursor_bin = cursor_executable()
    result = subprocess.run(
        [cursor_bin, "--add-mcp", json.dumps(definition, ensure_ascii=False, separators=(",", ":"))],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(
            "Cursor MCP registration failed.\n\n"
            f"stdout:\n{result.stdout.strip()}\n\n"
            f"stderr:\n{result.stderr.strip()}"
        )
    return {
        "ok": True,
        "mode": "cursor-cli",
        "name": name,
        "baseUrl": base_url.rstrip("/"),
        "cursorBin": cursor_bin,
        "definition": _redact_mcp_definition(definition, settings.server.api_key_env),
        "stdout": result.stdout.strip(),
        "stderr": result.stderr.strip(),
    }


def configure_cursor_mcp(
    settings: Any,
    name: str,
    base_url: str,
    api_key: str,
    *,
    write_json: bool,
) -> dict[str, Any]:
    if write_json:
        return write_project_mcp_json(settings, name, base_url, api_key)
    return install_cursor_mcp(settings=settings, name=name, base_url=base_url, api_key=api_key)


def _mcp_server_definition(settings: Any, base_url: str, api_key: str) -> dict[str, Any]:
    root = settings.config_dir_path
    config_path = root / "agentbridge.yaml"
    server_path = root / "app" / "tools" / "mcp_server.py"
    return {
        "type": "stdio",
        "command": sys.executable,
        "args": [
            str(server_path),
            "--base-url",
            base_url.rstrip("/"),
        ],
        "env": {
            "PYTHONPATH": str(root),
            "AGENTBRIDGE_CONFIG": str(config_path),
            settings.server.api_key_env: api_key,
        },
    }


def _cursor_add_mcp_definition(settings: Any, name: str, base_url: str, api_key: str) -> dict[str, Any]:
    server_definition = _mcp_server_definition(settings, base_url, api_key)
    return {
        "name": name,
        "command": server_definition["command"],
        "args": server_definition["args"],
        "env": server_definition["env"],
    }


def write_project_mcp_json(settings: Any, name: str, base_url: str, api_key: str) -> dict[str, Any]:
    mcp_dir = settings.config_dir_path / ".cursor"
    mcp_path = mcp_dir / "mcp.json"
    mcp_dir.mkdir(parents=True, exist_ok=True)
    if mcp_path.exists():
        data = json.loads(mcp_path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            data = {}
    else:
        data = {}
    servers = data.setdefault("mcpServers", {})
    if not isinstance(servers, dict):
        servers = {}
        data["mcpServers"] = servers
    server_definition = _mcp_server_definition(settings, base_url, api_key)
    servers[name] = server_definition
    mcp_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {
        "ok": True,
        "mode": "project-mcp-json",
        "name": name,
        "baseUrl": base_url.rstrip("/"),
        "path": str(mcp_path),
        "definition": _redact_mcp_definition(server_definition, settings.server.api_key_env),
    }


def _redact_mcp_definition(definition: dict[str, Any], api_key_env: str) -> dict[str, Any]:
    redacted = json.loads(json.dumps(definition))
    env = redacted.get("env")
    if isinstance(env, dict) and api_key_env in env:
        env[api_key_env] = "<redacted>"
    return redacted


def start_cloudflared_tunnel(settings: Any, timeout_seconds: int = 45) -> dict[str, Any]:
    tunnel_dir = settings.config_dir_path / ".agentbridge" / "tunnel"
    tunnel_dir.mkdir(parents=True, exist_ok=True)
    stdout_log = tunnel_dir / "cloudflared.out.log"
    stderr_log = tunnel_dir / "cloudflared.err.log"
    pid_file = tunnel_dir / "cloudflared.pid"
    url_file = tunnel_dir / "cloudflared.url"

    for path in [stdout_log, stderr_log]:
        path.unlink(missing_ok=True)

    local_url = f"http://{settings.server.host}:{settings.server.port}"
    command = [
        _npx_command(),
        "--yes",
        "cloudflared",
        "tunnel",
        "--url",
        local_url,
        "--no-autoupdate",
    ]

    stdout_handle = stdout_log.open("w", encoding="utf-8")
    stderr_handle = stderr_log.open("w", encoding="utf-8")
    try:
        process = subprocess.Popen(
            command,
            cwd=settings.config_dir_path,
            stdout=stdout_handle,
            stderr=stderr_handle,
            text=True,
            close_fds=True,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )
    finally:
        stdout_handle.close()
        stderr_handle.close()

    pid_file.write_text(str(process.pid), encoding="utf-8")

    public_url = _wait_for_tunnel_url(stderr_log, process, timeout_seconds)
    url_file.write_text(public_url, encoding="utf-8")
    return {
        "provider": "cloudflared",
        "pid": process.pid,
        "localUrl": local_url,
        "publicUrl": public_url,
        "stdoutLog": str(stdout_log),
        "stderrLog": str(stderr_log),
        "pidFile": str(pid_file),
    }


def _npx_command() -> str:
    if sys.platform == "win32":
        return shutil.which("npx.cmd") or shutil.which("npx") or "npx.cmd"
    return shutil.which("npx") or "npx"


def _wait_for_tunnel_url(log_path: Path, process: subprocess.Popen[Any], timeout_seconds: int) -> str:
    deadline = time.time() + timeout_seconds
    pattern = re.compile(r"https://[-a-z0-9]+\.trycloudflare\.com")
    while time.time() < deadline:
        if process.poll() is not None:
            log = log_path.read_text(encoding="utf-8", errors="replace") if log_path.exists() else ""
            raise RuntimeError(f"cloudflared exited before creating a tunnel.\n\n{log.strip()}")
        if log_path.exists():
            log = log_path.read_text(encoding="utf-8", errors="replace")
            match = pattern.search(log)
            if match:
                return match.group(0)
        time.sleep(1)
    raise TimeoutError(f"Timed out waiting for cloudflared tunnel URL. Check {log_path}.")


def configure_cursor(
    db_path: Path,
    backup_dir: Path,
    base_url: str,
    api_key: str,
    model_ids: list[str],
    default_model: str,
) -> dict[str, Any]:
    backup_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    db_backup = backup_dir / f"state.vscdb.before-agentbridge-{timestamp}.bak"
    state_backup = backup_dir / f"cursor-ai-settings-before-agentbridge-{timestamp}.json"
    shutil.copy2(db_path, db_backup)

    conn = sqlite3.connect(db_path, timeout=30)
    try:
        cursor = conn.cursor()
        row = cursor.execute("select value from ItemTable where key=?", (APPLICATION_USER_KEY,)).fetchone()
        if not row:
            raise RuntimeError("Cursor applicationUser state row not found.")

        blob = _decode_json_blob(row[0])
        ai = blob.setdefault("aiSettings", {})
        if not isinstance(ai, dict):
            ai = {}
            blob["aiSettings"] = ai

        previous = {
            "applicationUserKey": APPLICATION_USER_KEY,
            "openAIBaseUrl": blob.get("openAIBaseUrl"),
            "useOpenAIKey": blob.get("useOpenAIKey"),
            "aiSettings": {
                "userAddedModels": ai.get("userAddedModels"),
                "modelOverrideEnabled": ai.get("modelOverrideEnabled"),
                "modelOverrideDisabled": ai.get("modelOverrideDisabled"),
                "modelConfig": ai.get("modelConfig"),
            },
            "hadPlainOpenAIKeyCell": cursor.execute("select 1 from ItemTable where key=?", (OPENAI_KEY_CELL,)).fetchone()
            is not None,
            "dbBackup": str(db_backup),
        }
        state_backup.write_text(json.dumps(previous, ensure_ascii=False, indent=2), encoding="utf-8")

        blob["openAIBaseUrl"] = base_url
        blob["useOpenAIKey"] = True
        _add_models(ai, model_ids)
        touched_modes = _select_default_model(ai, default_model)
        ai["agentbridgeAddedModels"] = model_ids
        ai["agentbridgeTouchedModes"] = touched_modes
        _touch_model_usage(ai, model_ids)

        compact = json.dumps(blob, ensure_ascii=False, separators=(",", ":"))
        cursor.execute("update ItemTable set value=? where key=?", (compact, APPLICATION_USER_KEY))
        cursor.execute("delete from ItemTable where key=?", (OPENAI_KEY_CELL,))
        cursor.execute("insert into ItemTable(key,value) values(?,?)", (OPENAI_KEY_CELL, api_key))
        conn.commit()
    finally:
        conn.close()

    return {
        "ok": True,
        "dbPath": str(db_path),
        "dbBackup": str(db_backup),
        "settingsBackup": str(state_backup),
        "baseUrl": base_url,
        "models": model_ids,
        "defaultModel": default_model,
    }


def _decode_json_blob(value: Any) -> dict[str, Any]:
    text = value.decode("utf-8", errors="replace") if isinstance(value, bytes) else str(value)
    decoded = json.loads(text)
    if not isinstance(decoded, dict):
        raise RuntimeError("Cursor applicationUser state is not a JSON object.")
    return decoded


def _add_models(ai: dict[str, Any], model_ids: list[str]) -> None:
    user_added = list(ai.get("userAddedModels") or [])
    enabled = list(ai.get("modelOverrideEnabled") or [])
    disabled = list(ai.get("modelOverrideDisabled") or [])

    for model_id in model_ids:
        if model_id not in user_added:
            user_added.append(model_id)
        if model_id not in enabled:
            enabled.append(model_id)
        disabled = [item for item in disabled if item != model_id]

    ai["userAddedModels"] = user_added
    ai["modelOverrideEnabled"] = enabled
    ai["modelOverrideDisabled"] = disabled


def _select_default_model(ai: dict[str, Any], default_model: str) -> list[str]:
    model_config = ai.get("modelConfig") or {}
    touched_modes: list[str] = []
    if not isinstance(model_config, dict):
        ai["modelConfig"] = {}
        return touched_modes

    for mode, config in list(model_config.items()):
        if not isinstance(config, dict):
            continue
        next_config = dict(config)
        next_config["modelName"] = default_model
        next_config["selectedModels"] = [{"modelId": default_model, "parameters": []}]
        model_config[mode] = next_config
        touched_modes.append(mode)

    ai["modelConfig"] = model_config
    return touched_modes


def _touch_model_usage(ai: dict[str, Any], model_ids: list[str]) -> None:
    last_used = ai.get("modelLastUsedAt") or {}
    if not isinstance(last_used, dict):
        return
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    for model_id in model_ids:
        last_used[model_id] = now
    ai["modelLastUsedAt"] = last_used


if __name__ == "__main__":
    raise SystemExit(main())
