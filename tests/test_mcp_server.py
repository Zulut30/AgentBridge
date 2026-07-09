import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.config import AgentBridgeConfig, ProjectConfig
from app.tools.mcp_server import AgentBridgeMcpServer, read_message, write_message


class McpServerTest(unittest.TestCase):
    def test_initialize_response(self) -> None:
        server = self._server()

        response = server.handle_message(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {"protocolVersion": "2024-11-05"},
            }
        )

        self.assertEqual(response["id"], 1)
        self.assertEqual(response["result"]["serverInfo"]["name"], "agentbridge")
        self.assertIn("tools", response["result"]["capabilities"])

    def test_tools_list_contains_agentbridge_tools(self) -> None:
        server = self._server()

        response = server.handle_message({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        tools = {tool["name"] for tool in response["result"]["tools"]}

        self.assertIn("agentbridge_status", tools)
        self.assertIn("agentbridge_limits", tools)
        self.assertIn("agentbridge_models", tools)
        self.assertIn("agentbridge_test_agent", tools)
        self.assertIn("agentbridge_logs", tools)

    def test_unknown_method_returns_json_rpc_error(self) -> None:
        server = self._server()

        response = server.handle_message({"jsonrpc": "2.0", "id": 3, "method": "missing/method"})

        self.assertEqual(response["error"]["code"], -32601)

    def test_models_tool_filters_results(self) -> None:
        server = self._server()

        with patch.object(
            server,
            "_request_json",
            return_value={
                "data": [
                    {"id": "agentbridge-auto"},
                    {"id": "agentbridge-grok-build-high"},
                    {"id": "agentbridge-codex-gpt-5-high"},
                ]
            },
        ):
            response = server.handle_message(
                {
                    "jsonrpc": "2.0",
                    "id": 4,
                    "method": "tools/call",
                    "params": {"name": "agentbridge_models", "arguments": {"filter": "grok", "limit": 5}},
                }
            )

        text = response["result"]["content"][0]["text"]
        payload = json.loads(text)
        self.assertEqual(payload["models"], ["agentbridge-grok-build-high"])

    def test_status_tool_summarizes_models(self) -> None:
        server = self._server()

        with patch.object(
            server,
            "_request_json",
            return_value={
                "status": "ok",
                "models": [{"id": "agentbridge-auto"}, {"id": "agentbridge-grok"}],
            },
        ):
            response = server.handle_message(
                {
                    "jsonrpc": "2.0",
                    "id": 5,
                    "method": "tools/call",
                    "params": {"name": "agentbridge_status", "arguments": {}},
                }
            )

        text = response["result"]["content"][0]["text"]
        payload = json.loads(text)
        self.assertNotIn("models", payload)
        self.assertEqual(payload["model_count"], 2)
        self.assertEqual(payload["sample_models"], ["agentbridge-auto", "agentbridge-grok"])

    def test_content_length_framing_round_trip(self) -> None:
        buffer = io.BytesIO()
        message = {"jsonrpc": "2.0", "id": 6, "method": "ping"}

        write_message(buffer, message)
        buffer.seek(0)

        self.assertEqual(read_message(buffer), message)

    def _server(self) -> AgentBridgeMcpServer:
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        root = Path(temp_dir.name)
        settings = AgentBridgeConfig(project=ProjectConfig(root=str(root)), config_dir=str(root))
        with patch("app.tools.mcp_server.get_settings", return_value=settings):
            return AgentBridgeMcpServer(base_url="http://127.0.0.1:8787", api_key="test-key")


if __name__ == "__main__":
    unittest.main()
