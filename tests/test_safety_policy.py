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

    async def test_prompt_file_mode_handles_long_prompts_and_cleans_up(self) -> None:
        prompt = "Long Cursor prompt. " * 3000
        reader = (
            "import pathlib, sys; "
            "path = pathlib.Path(sys.argv[sys.argv.index('--prompt-file') + 1]); "
            "print(path.read_text(encoding='utf-8')[:18]); "
            "print(len(path.read_text(encoding='utf-8')))"
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            settings = AgentBridgeConfig(
                project=ProjectConfig(root=str(root)),
                config_dir=str(root),
            )
            executor = SubprocessAgentExecutor(
                "file-agent",
                AgentConfig(
                    command=sys.executable,
                    args=["-c", reader],
                    prompt_via_file=True,
                    prompt_file_arg="--prompt-file",
                ),
                settings,
            )

            result = await executor.run(prompt)
            prompt_dir = root / ".agentbridge" / "tmp" / "prompts"
            leftovers = list(prompt_dir.glob("file-agent-*.txt")) if prompt_dir.exists() else []

        self.assertTrue(result.success, result.stderr)
        self.assertIn("Long Cursor prompt", result.stdout)
        self.assertIn(str(len(prompt)), result.stdout)
        self.assertEqual(leftovers, [])

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
