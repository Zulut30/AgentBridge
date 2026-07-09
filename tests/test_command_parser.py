import unittest

from app.router.command_parser import CommandParser


class CommandParserTest(unittest.TestCase):
    def test_grok_command(self) -> None:
        parsed = CommandParser(default_agent="codex").parse("@grok analyze auth")

        self.assertEqual(parsed.agent, "grok")
        self.assertEqual(parsed.mode, "normal")
        self.assertEqual(parsed.clean_prompt, "analyze auth")

    def test_codex_command(self) -> None:
        parsed = CommandParser(default_agent="grok").parse("  @codex fix bug")

        self.assertEqual(parsed.agent, "codex")
        self.assertEqual(parsed.clean_prompt, "fix bug")

    def test_both_command(self) -> None:
        parsed = CommandParser(default_agent="codex").parse("@both compare outputs")

        self.assertEqual(parsed.agent, "both")
        self.assertEqual(parsed.clean_prompt, "compare outputs")

    def test_auto_command(self) -> None:
        parsed = CommandParser(default_agent="codex").parse("@auto route this")

        self.assertEqual(parsed.agent, "auto")
        self.assertEqual(parsed.mode, "auto")
        self.assertEqual(parsed.clean_prompt, "route this")

    def test_no_command_uses_default_agent(self) -> None:
        parsed = CommandParser(default_agent="codex").parse("plain request")

        self.assertEqual(parsed.agent, "codex")
        self.assertEqual(parsed.mode, "default")
        self.assertEqual(parsed.clean_prompt, "plain request")


if __name__ == "__main__":
    unittest.main()

