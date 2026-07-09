import argparse
import importlib.util
import json
import os
import platform
import shutil
import socket
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from app.config import get_settings
from app.executors.base import command_is_available
from app.tools.configure_cursor import APPLICATION_USER_KEY, cursor_state_db_path


@dataclass(slots=True)
class Check:
    name: str
    ok: bool
    detail: str
    required: bool = True

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "ok": self.ok,
            "detail": self.detail,
            "required": self.required,
        }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run AgentBridge installation and runtime diagnostics.")
    parser.add_argument("--server", action="store_true", help="Also check the configured HTTP server.")
    parser.add_argument("--cursor", action="store_true", help="Also check Cursor CLI, provider state, and MCP registration.")
    parser.add_argument("--base-url", default=None, help="Override server base URL for HTTP checks.")
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of a text report.")
    args = parser.parse_args()

    checks = run_checks(check_server=args.server, check_cursor=args.cursor, base_url=args.base_url)
    if args.json:
        print(json.dumps([check.as_dict() for check in checks], ensure_ascii=False, indent=2))
    else:
        print_report(checks)

    return 0 if all(check.ok or not check.required for check in checks) else 1


def run_checks(check_server: bool = False, check_cursor: bool = False, base_url: str | None = None) -> list[Check]:
    checks: list[Check] = []
    checks.append(_python_version_check())
    checks.extend(_package_checks())

    try:
        settings = get_settings()
        checks.append(Check("config", True, f"loaded config from {settings.config_dir_path}"))
    except Exception as exc:
        checks.append(Check("config", False, str(exc)))
        return checks

    checks.append(Check("project_root", settings.project_root_path.exists(), str(settings.project_root_path)))
    checks.append(
        Check(
            "api_key",
            bool(settings.api_key),
            f"env {settings.server.api_key_env} is {'set' if os.getenv(settings.server.api_key_env) else 'using default'}",
            required=False,
        )
    )
    checks.append(
        Check(
            "grok_command",
            (not settings.agents.grok.enabled) or command_is_available(settings.agents.grok.command),
            settings.agents.grok.command,
            required=False,
        )
    )
    checks.append(
        Check(
            "codex_command",
            (not settings.agents.codex.enabled) or command_is_available(settings.agents.codex.command),
            settings.agents.codex.command,
            required=False,
        )
    )
    checks.append(
        Check(
            "model_presets",
            len(settings.cursor_model_ids()) >= 3,
            f"{len(settings.cursor_model_ids())} cursor-enabled presets",
        )
    )
    checks.append(_port_check(settings.server.host, settings.server.port))
    checks.append(_grok_subagents_check(settings))

    if check_server:
        server_base_url = base_url or f"http://{settings.server.host}:{settings.server.port}"
        checks.extend(_server_checks(server_base_url, settings.api_key))
    if check_cursor:
        checks.extend(_cursor_checks(settings))

    return checks


def _python_version_check() -> Check:
    version = sys.version_info
    ok = version >= (3, 11)
    detail = f"{platform.python_implementation()} {platform.python_version()} on {platform.system()}"
    return Check("python", ok, detail)


def _package_checks() -> list[Check]:
    packages = {
        "fastapi": "fastapi",
        "uvicorn": "uvicorn",
        "pydantic": "pydantic",
        "python-dotenv": "dotenv",
        "pyyaml": "yaml",
    }
    return [
        Check(f"package:{package}", importlib.util.find_spec(module) is not None, module)
        for package, module in packages.items()
    ]


def _port_check(host: str, port: int) -> Check:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.4)
        result = sock.connect_ex((host, port))
    if result == 0:
        return Check("server_port", True, f"{host}:{port} is listening", required=False)
    return Check("server_port", True, f"{host}:{port} is free", required=False)


def _grok_subagents_check(settings: Any) -> Check:
    args = [arg.lower() for arg in settings.agents.grok.args]
    disabled = "--no-subagents" in args
    return Check(
        "grok_subagents",
        not disabled,
        "enabled" if not disabled else "disabled by --no-subagents",
        required=False,
    )


def _server_checks(base_url: str, api_key: str) -> list[Check]:
    base = base_url.rstrip("/")
    headers = {"Authorization": f"Bearer {api_key}"}
    checks: list[Check] = []
    checks.append(_http_check("server:/health", f"{base}/health", headers=None))
    checks.append(_http_check("server:/v1/models", f"{base}/v1/models", headers=headers, expect_key="data"))
    checks.append(_http_check("server:/agentbridge/auto", f"{base}/agentbridge/auto", headers=headers))
    checks.append(_http_check("server:/agentbridge/limits", f"{base}/agentbridge/limits", headers=headers))
    return checks


def _cursor_checks(settings: Any) -> list[Check]:
    checks: list[Check] = []
    cursor_bin = shutil.which("cursor") or shutil.which("cursor.cmd") or shutil.which("Cursor.exe")
    checks.append(Check("cursor:cli", bool(cursor_bin), cursor_bin or "not found", required=False))
    if cursor_bin:
        checks.append(_cursor_help_check(cursor_bin))

    db_path = cursor_state_db_path()
    checks.append(Check("cursor:state_db", db_path.exists(), str(db_path), required=False))
    if db_path.exists():
        checks.extend(_cursor_state_checks(db_path))

    checks.extend(_cursor_mcp_checks(settings))
    return checks


def _cursor_help_check(cursor_bin: str) -> Check:
    import subprocess

    result = subprocess.run([cursor_bin, "--help"], capture_output=True, text=True, check=False, timeout=20)
    text = f"{result.stdout}\n{result.stderr}"
    return Check(
        "cursor:add_mcp",
        "--add-mcp" in text,
        "--add-mcp available" if "--add-mcp" in text else "--add-mcp not shown in cursor --help",
        required=False,
    )


def _cursor_state_checks(db_path: Path) -> list[Check]:
    import sqlite3

    checks: list[Check] = []
    try:
        with sqlite3.connect(f"file:{db_path}?mode=ro", uri=True) as conn:
            row = conn.execute("select value from ItemTable where key=?", (APPLICATION_USER_KEY,)).fetchone()
    except Exception as exc:
        return [Check("cursor:provider_state", False, str(exc), required=False)]

    if not row:
        return [Check("cursor:provider_state", False, "applicationUser state row not found", required=False)]

    try:
        blob = json.loads(row[0] if isinstance(row[0], str) else row[0].decode("utf-8", errors="replace"))
    except json.JSONDecodeError as exc:
        return [Check("cursor:provider_state", False, f"invalid JSON: {exc}", required=False)]

    base_url = str(blob.get("openAIBaseUrl") or "")
    ai_settings = blob.get("aiSettings") if isinstance(blob, dict) else {}
    models = []
    if isinstance(ai_settings, dict):
        models = list(ai_settings.get("agentbridgeAddedModels") or [])
    checks.append(
        Check(
            "cursor:openai_base_url",
            "agentbridge" in base_url.lower() or "/v1" in base_url,
            base_url or "not set",
            required=False,
        )
    )
    checks.append(Check("cursor:agentbridge_models", len(models) >= 3, f"{len(models)} models", required=False))
    return checks


def _cursor_mcp_checks(settings: Any) -> list[Check]:
    paths = [
        settings.config_dir_path / ".cursor" / "mcp.json",
        Path.home() / ".cursor" / "mcp.json",
    ]
    checks: list[Check] = []
    found_agentbridge = False
    existing_paths: list[str] = []
    for path in paths:
        if not path.exists():
            continue
        existing_paths.append(str(path))
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if "agentbridge" in text.lower():
            found_agentbridge = True
    checks.append(
        Check(
            "cursor:mcp_config",
            found_agentbridge,
            ", ".join(existing_paths) if existing_paths else "no .cursor/mcp.json found",
            required=False,
        )
    )
    return checks


def _http_check(
    name: str,
    url: str,
    headers: dict[str, str] | None = None,
    expect_key: str | None = None,
) -> Check:
    request = Request(url, headers=headers or {})
    try:
        with urlopen(request, timeout=8) as response:
            body = response.read().decode("utf-8", errors="replace")
    except HTTPError as exc:
        return Check(name, False, f"HTTP {exc.code}: {url}")
    except URLError as exc:
        return Check(name, False, f"{exc.reason}: {url}")
    except TimeoutError:
        return Check(name, False, f"timeout: {url}")

    if expect_key:
        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            return Check(name, False, "response is not JSON")
        if expect_key not in data:
            return Check(name, False, f"missing JSON key: {expect_key}")

    return Check(name, True, url)


def print_report(checks: list[Check]) -> None:
    for check in checks:
        mark = "OK" if check.ok else "FAIL"
        optional = " optional" if not check.required else ""
        print(f"[{mark}] {check.name}{optional}: {check.detail}")


if __name__ == "__main__":
    raise SystemExit(main())
