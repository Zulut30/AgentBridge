import tempfile
import unittest
from pathlib import Path

from app.config import AgentBridgeConfig, ProjectConfig, SkillsConfig
from app.context.prompt_builder import PromptBuilder


class PromptBuilderTest(unittest.TestCase):
    def test_prompt_includes_request_project_rules_and_skills(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            skills_dir = root / "skills"
            skills_dir.mkdir()
            (skills_dir / "minimal.md").write_text("# Test Skill\n\n- Keep it small.", encoding="utf-8")

            settings = AgentBridgeConfig(
                project=ProjectConfig(root=str(root)),
                skills=SkillsConfig(paths=[str(skills_dir)]),
                config_dir=str(root),
            )

            prompt = PromptBuilder(settings).build("fix the auth bug")

        self.assertIn("# AgentBridge Task", prompt)
        self.assertIn("fix the auth bug", prompt)
        self.assertIn(f"Root: {root.resolve()}", prompt)
        self.assertIn("- Make minimal necessary changes.", prompt)
        self.assertIn("# Test Skill", prompt)

    def test_prompt_handles_no_skills(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            settings = AgentBridgeConfig(
                project=ProjectConfig(root=str(root)),
                skills=SkillsConfig(enabled=False),
                config_dir=str(root),
            )

            prompt = PromptBuilder(settings).build("explain project")

        self.assertIn("No skills loaded.", prompt)

    def test_grok_prompt_is_search_focused_and_compact(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            settings = AgentBridgeConfig(
                project=ProjectConfig(root=str(root)),
                skills=SkillsConfig(enabled=False),
                config_dir=str(root),
            )

            prompt = PromptBuilder(settings).build_grok(
                "какая колода в Hearthstone сейчас популярная в X",
                requested_model="agentbridge-auto",
            )

        self.assertIn("Use web search and X/x.com search", prompt)
        self.assertIn("Answer in the same language", prompt)
        self.assertIn("хартстоун", prompt)
        self.assertIn("Hearthstone", prompt)
        self.assertIn("Answer the user's exact subject", prompt)
        self.assertIn("omit unrelated general X trend summaries", prompt)
        self.assertIn("какая колода", prompt)
        self.assertNotIn("# AgentBridge Task", prompt)
        self.assertNotIn("No skills loaded.", prompt)


if __name__ == "__main__":
    unittest.main()
