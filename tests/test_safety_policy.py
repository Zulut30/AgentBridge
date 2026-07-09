import sys
import tempfile
import unittest
from pathlib import Path

from app.config import AgentBridgeConfig, AgentConfig, ProjectConfig, SafetyConfig
from app.executors.base import SubprocessAgentExecutor
from app.safety.policy import SafetyPolicy


class SafetyPolicyTest(unittest.IsolatedAsyncioTestCase):
    def test_prompt_can_discuss_forbidden_words_by_default(self) -> None:
        policy = SafetyPolicy(SafetyConfig(forbidden_patterns=["TRUNCATE"]))

        policy.ensure_prompt_allowed("Explain why a truncate helper is failing.")

    def test_prompt_scan_can_be_enabled_explicitly(self) -> None:
        policy = SafetyPolicy(
            SafetyConfig(
                forbid_dangerous_prompts=True,
                forbidden_patterns=["TRUNCATE"],
            )
        )

        with self.assertRaisesRegex(ValueError, "forbidden pattern"):
            policy.ensure_prompt_allowed("Run TRUNCATE users.")

    async def test_prompt_arg_is_not_scanned_as_command(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            settings = AgentBridgeConfig(
                project=ProjectConfig(root=str(root)),
                safety=SafetyConfig(forbidden_patterns=["TRUNCATE"]),
                config_dir=str(root),
            )
            executor = SubprocessAgentExecutor(
                "echo-agent",
                AgentConfig(
                    command=sys.executable,
                    args=["-c", "import sys; print(sys.argv[-1])"],
                    prompt_via_stdin=False,
                ),
                settings,
            )

            result = await executor.run("Explain truncate behavior.")

        self.assertTrue(result.success, result.stderr)
        self.assertIn("Explain truncate behavior.", result.stdout)

    async def test_static_dangerous_command_is_still_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            settings = AgentBridgeConfig(
                project=ProjectConfig(root=str(root)),
                safety=SafetyConfig(forbidden_patterns=["dangerous-static-arg"]),
                config_dir=str(root),
            )
            executor = SubprocessAgentExecutor(
                "blocked-agent",
                AgentConfig(
                    command=sys.executable,
                    args=["dangerous-static-arg"],
                    prompt_via_stdin=False,
                ),
                settings,
            )

            result = await executor.run("safe prompt")

        self.assertFalse(result.success)
        self.assertIn("forbidden pattern", result.stderr or "")


if __name__ == "__main__":
    unittest.main()
