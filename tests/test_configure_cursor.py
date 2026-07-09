import json
import tempfile
import unittest
from pathlib import Path

from app.config import AgentBridgeConfig, ProjectConfig
from app.tools.configure_cursor import _redact_mcp_definition, write_project_mcp_json


class ConfigureCursorTest(unittest.TestCase):
    def test_write_project_mcp_json_and_redacts_summary(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "agentbridge.yaml").write_text("server: {}\n", encoding="utf-8")
            settings = AgentBridgeConfig(project=ProjectConfig(root=str(root)), config_dir=str(root))

            summary = write_project_mcp_json(
                settings,
                name="agentbridge",
                base_url="http://127.0.0.1:8787",
                api_key="secret-local-key",
            )
            mcp_path = root / ".cursor" / "mcp.json"
            data = json.loads(mcp_path.read_text(encoding="utf-8"))

        self.assertEqual(summary["definition"]["env"]["AGENTBRIDGE_API_KEY"], "<redacted>")
        self.assertEqual(data["mcpServers"]["agentbridge"]["env"]["AGENTBRIDGE_API_KEY"], "secret-local-key")
        self.assertEqual(data["mcpServers"]["agentbridge"]["type"], "stdio")

    def test_redact_mcp_definition_does_not_mutate_original(self) -> None:
        definition = {"env": {"AGENTBRIDGE_API_KEY": "secret"}}

        redacted = _redact_mcp_definition(definition, "AGENTBRIDGE_API_KEY")

        self.assertEqual(redacted["env"]["AGENTBRIDGE_API_KEY"], "<redacted>")
        self.assertEqual(definition["env"]["AGENTBRIDGE_API_KEY"], "secret")


if __name__ == "__main__":
    unittest.main()
