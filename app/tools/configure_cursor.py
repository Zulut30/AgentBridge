import argparse
import json
import os
import shutil
import sqlite3
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.config import get_settings


APPLICATION_USER_KEY = "src.vs.platform.reactivestorage.browser.reactiveStorageServiceImpl.persistentStorage.applicationUser"
OPENAI_KEY_CELL = "cursorAuth/openAIKey"


def main() -> int:
    parser = argparse.ArgumentParser(description="Configure Cursor to use AgentBridge.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8787/v1")
    parser.add_argument("--api-key", default=None)
    parser.add_argument("--default-model", default="agentbridge-auto")
    parser.add_argument("--db-path", default=None)
    parser.add_argument("--backup-dir", default=None)
    parser.add_argument("--force", action="store_true", help="Write even when Cursor appears to be running.")
    parser.add_argument("--open", action="store_true", help="Open Cursor on the configured project after writing.")
    args = parser.parse_args()

    settings = get_settings()
    db_path = Path(args.db_path).expanduser().resolve() if args.db_path else cursor_state_db_path()
    backup_dir = Path(args.backup_dir).expanduser().resolve() if args.backup_dir else settings.config_dir_path / ".agentbridge" / "cursor-backups"
    api_key = args.api_key or settings.api_key

    if not db_path.exists():
        raise SystemExit(f"Cursor state database not found: {db_path}")
    if is_cursor_running() and not args.force:
        raise SystemExit("Cursor is running. Quit Cursor first or pass --force.")

    summary = configure_cursor(
        db_path=db_path,
        backup_dir=backup_dir,
        base_url=args.base_url,
        api_key=api_key,
        model_ids=settings.cursor_model_ids(),
        default_model=args.default_model,
    )

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
    if not cursor_bin:
        raise RuntimeError("Could not find Cursor launcher on PATH.")
    subprocess.Popen([cursor_bin, "--reuse-window", str(project_root)], close_fds=True)


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
