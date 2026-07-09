import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, BinaryIO
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from app.config import get_settings


PROTOCOL_VERSION = "2024-11-05"


class AgentBridgeMcpServer:
    def __init__(self, base_url: str | None = None, api_key: str | None = None) -> None:
        settings = get_settings()
        self.settings = settings
        self.base_url = (base_url or os.getenv("AGENTBRIDGE_BASE_URL") or self._default_base_url()).rstrip("/")
        self.api_key = api_key or os.getenv(settings.server.api_key_env) or settings.api_key

    def handle_message(self, message: dict[str, Any]) -> dict[str, Any] | None:
        method = message.get("method")
        request_id = message.get("id")

        if method in {"notifications/initialized", "notifications/cancelled"}:
            return None

        try:
            if method == "initialize":
                result = self._initialize(message.get("params") or {})
            elif method == "ping":
                result = {}
            elif method == "tools/list":
                result = {"tools": self._tools()}
            elif method == "tools/call":
                result = self._call_tool(message.get("params") or {})
            elif method in {"resources/list", "prompts/list"}:
                result = {"resources": []} if method == "resources/list" else {"prompts": []}
            else:
                return self._error(request_id, -32601, f"Method not found: {method}")
            if request_id is None:
                return None
            return {"jsonrpc": "2.0", "id": request_id, "result": result}
        except Exception as exc:
            if request_id is None:
                return None
            return self._error(request_id, -32000, str(exc))

    def _initialize(self, params: dict[str, Any]) -> dict[str, Any]:
        protocol_version = params.get("protocolVersion") or PROTOCOL_VERSION
        return {
            "protocolVersion": protocol_version,
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "agentbridge", "version": "0.1.0"},
        }

    def _tools(self) -> list[dict[str, Any]]:
        return [
            {
                "name": "agentbridge_status",
                "description": "Return AgentBridge server, agent, model, auto-routing, and usage status.",
                "inputSchema": self._object_schema({}),
            },
            {
                "name": "agentbridge_limits",
                "description": "Return local AgentBridge request and runtime counters.",
                "inputSchema": self._object_schema({}),
            },
            {
                "name": "agentbridge_models",
                "description": "List Cursor-enabled AgentBridge model ids, optionally filtered by text.",
                "inputSchema": self._object_schema(
                    {
                        "filter": {"type": "string", "description": "Optional case-insensitive model id filter."},
                        "limit": {
                            "type": "integer",
                            "description": "Maximum models to return.",
                            "minimum": 1,
                            "maximum": 300,
                        },
                    }
                ),
            },
            {
                "name": "agentbridge_test_agent",
                "description": "Send a short test prompt through AgentBridge to Grok, Codex, or Auto.",
                "inputSchema": self._object_schema(
                    {
                        "model": {
                            "type": "string",
                            "description": "AgentBridge model id.",
                            "default": "agentbridge-grok",
                        },
                        "prompt": {
                            "type": "string",
                            "description": "Prompt to send.",
                            "default": "Reply with exactly: AGENTBRIDGE_MCP_OK",
                        },
                    }
                ),
            },
            {
                "name": "agentbridge_logs",
                "description": "Read recent AgentBridge local logs.",
                "inputSchema": self._object_schema(
                    {
                        "log": {
                            "type": "string",
                            "description": "Log to read.",
                            "enum": ["server_out", "server_err", "tunnel_err", "usage"],
                            "default": "server_err",
                        },
                        "lines": {
                            "type": "integer",
                            "description": "Number of trailing lines.",
                            "minimum": 1,
                            "maximum": 200,
                            "default": 80,
                        },
                    }
                ),
            },
        ]

    def _call_tool(self, params: dict[str, Any]) -> dict[str, Any]:
        name = str(params.get("name") or "")
        arguments = params.get("arguments") or {}
        if not isinstance(arguments, dict):
            arguments = {}

        try:
            if name == "agentbridge_status":
                payload = self._status()
            elif name == "agentbridge_limits":
                payload = self._request_json("GET", "/agentbridge/limits")
            elif name == "agentbridge_models":
                payload = self._models(arguments)
            elif name == "agentbridge_test_agent":
                payload = self._test_agent(arguments)
            elif name == "agentbridge_logs":
                payload = self._logs(arguments)
            else:
                return self._tool_result(f"Unknown AgentBridge tool: {name}", is_error=True)
        except Exception as exc:
            return self._tool_result(str(exc), is_error=True)

        return self._tool_result(json.dumps(payload, ensure_ascii=False, indent=2))

    def _status(self) -> dict[str, Any]:
        payload = self._request_json("GET", "/agentbridge/status")
        models = payload.pop("models", [])
        payload["model_count"] = len(models) if isinstance(models, list) else 0
        if isinstance(models, list):
            payload["sample_models"] = [
                item.get("id") for item in models[:12] if isinstance(item, dict) and item.get("id")
            ]
        return payload

    def _models(self, arguments: dict[str, Any]) -> dict[str, Any]:
        response = self._request_json("GET", "/v1/models")
        models = [item.get("id") for item in response.get("data", []) if item.get("id")]
        model_filter = str(arguments.get("filter") or "").lower().strip()
        if model_filter:
            models = [model_id for model_id in models if model_filter in model_id.lower()]
        limit = int(arguments.get("limit") or 150)
        return {"count": len(models), "models": models[: max(1, min(limit, 300))]}

    def _test_agent(self, arguments: dict[str, Any]) -> dict[str, Any]:
        model = str(arguments.get("model") or "agentbridge-grok")
        prompt = str(arguments.get("prompt") or "Reply with exactly: AGENTBRIDGE_MCP_OK")
        payload = {"model": model, "messages": [{"role": "user", "content": prompt}]}
        response = self._request_json("POST", "/v1/chat/completions", payload, timeout_seconds=240)
        content = response.get("choices", [{}])[0].get("message", {}).get("content", "")
        return {"model": model, "content": content}

    def _logs(self, arguments: dict[str, Any]) -> dict[str, Any]:
        log_name = str(arguments.get("log") or "server_err")
        lines = max(1, min(int(arguments.get("lines") or 80), 200))
        path = self._log_path(log_name)
        if not path.exists():
            return {"log": log_name, "path": str(path), "exists": False, "text": ""}
        text_lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        return {
            "log": log_name,
            "path": str(path),
            "exists": True,
            "line_count": len(text_lines),
            "text": "\n".join(text_lines[-lines:]),
        }

    def _log_path(self, log_name: str) -> Path:
        root = self.settings.config_dir_path
        paths = {
            "server_out": root / "agentbridge.out.log",
            "server_err": root / "agentbridge.err.log",
            "tunnel_err": root / ".agentbridge" / "tunnel" / "cloudflared.err.log",
            "usage": self.settings.usage_log_path,
        }
        if log_name not in paths:
            raise ValueError(f"unsupported log: {log_name}")
        return paths[log_name]

    def _request_json(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
        timeout_seconds: int = 30,
    ) -> dict[str, Any]:
        data = json.dumps(payload).encode("utf-8") if payload is not None else None
        headers = {"Authorization": f"Bearer {self.api_key}"}
        if data is not None:
            headers["Content-Type"] = "application/json"
        request = Request(f"{self.base_url}{path}", data=data, headers=headers, method=method)
        try:
            with urlopen(request, timeout=timeout_seconds) as response:
                body = response.read().decode("utf-8", errors="replace")
        except HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"AgentBridge HTTP {exc.code} for {path}: {body}") from exc
        except URLError as exc:
            raise RuntimeError(f"AgentBridge is not reachable at {self.base_url}: {exc.reason}") from exc

        try:
            parsed = json.loads(body)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"AgentBridge returned non-JSON response for {path}: {body[:500]}") from exc
        if not isinstance(parsed, dict):
            raise RuntimeError(f"AgentBridge returned unexpected response for {path}")
        return parsed

    def _default_base_url(self) -> str:
        return f"http://{self.settings.server.host}:{self.settings.server.port}"

    def _tool_result(self, text: str, is_error: bool = False) -> dict[str, Any]:
        return {"content": [{"type": "text", "text": text}], "isError": is_error}

    def _object_schema(self, properties: dict[str, Any]) -> dict[str, Any]:
        return {"type": "object", "properties": properties, "additionalProperties": False}

    def _error(self, request_id: Any, code: int, message: str) -> dict[str, Any]:
        return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}


def read_message(stream: BinaryIO) -> dict[str, Any] | None:
    headers: dict[str, str] = {}
    while True:
        line = stream.readline()
        if not line:
            return None
        if line in {b"\r\n", b"\n"}:
            break
        key, _, value = line.decode("ascii", errors="replace").partition(":")
        headers[key.lower().strip()] = value.strip()

    length = int(headers.get("content-length") or "0")
    if length <= 0:
        return None
    body = stream.read(length)
    return json.loads(body.decode("utf-8"))


def write_message(stream: BinaryIO, message: dict[str, Any]) -> None:
    body = json.dumps(message, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    stream.write(f"Content-Length: {len(body)}\r\n\r\n".encode("ascii"))
    stream.write(body)
    stream.flush()


def serve(server: AgentBridgeMcpServer) -> int:
    while True:
        message = read_message(sys.stdin.buffer)
        if message is None:
            return 0
        response = server.handle_message(message)
        if response is not None:
            write_message(sys.stdout.buffer, response)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run AgentBridge MCP stdio server.")
    parser.add_argument("--base-url", default=None, help="AgentBridge server root URL, without /v1.")
    parser.add_argument("--api-key", default=None, help="Bearer token for AgentBridge HTTP endpoints.")
    args = parser.parse_args()

    return serve(AgentBridgeMcpServer(base_url=args.base_url, api_key=args.api_key))


if __name__ == "__main__":
    raise SystemExit(main())
