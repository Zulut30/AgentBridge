import tempfile
import unittest
from pathlib import Path

from app.config import AgentBridgeConfig, ProjectConfig, SkillsConfig
from app.models import AgentResult
from app.router.agent_router import AgentRouter


class FakeExecutor:
    def __init__(self, agent: str) -> None:
        self.agent = agent
        self.calls: list[tuple[str | None, str | None]] = []
        self.results: list[AgentResult] = []

    async def run(
        self,
        prompt: str,
        target_model: str | None = None,
        reasoning_effort: str | None = None,
    ) -> AgentResult:
        self.calls.append((target_model, reasoning_effort))
        if self.results:
            return self.results.pop(0)
        return AgentResult(
            agent=self.agent,
            success=True,
            stdout=f"{self.agent} ok",
            stderr=None,
            duration_seconds=0.01,
            returncode=0,
        )


class AgentRouterTest(unittest.IsolatedAsyncioTestCase):
    async def test_auto_routes_web_search_keywords_to_grok(self) -> None:
        router, grok, codex = self._router()

        result = await router.run("search X for current news", "agentbridge-auto")

        self.assertEqual(result.selected_agent, "grok")
        self.assertEqual(result.content, "grok ok")
        self.assertEqual(len(grok.calls), 1)
        self.assertEqual(len(codex.calls), 0)

    async def test_auto_routes_code_tasks_to_codex(self) -> None:
        router, grok, codex = self._router()

        result = await router.run("fix this Python bug", "agentbridge-auto")

        self.assertEqual(result.selected_agent, "codex")
        self.assertEqual(result.content, "codex ok")
        self.assertEqual(len(grok.calls), 0)
        self.assertEqual(len(codex.calls), 1)

    async def test_model_preset_passes_target_model_and_reasoning(self) -> None:
        router, _grok, codex = self._router()

        result = await router.run("fix this bug", "agentbridge-auto-gpt-5.5-high")

        self.assertEqual(result.target_model, "gpt-5.5")
        self.assertEqual(result.reasoning_effort, "high")
        self.assertEqual(codex.calls, [("gpt-5.5", "high")])

    async def test_web_route_does_not_pass_openai_model_to_grok(self) -> None:
        router, grok, _codex = self._router()

        result = await router.run("search X for current news", "agentbridge-auto-gpt-5.5-high")

        self.assertEqual(result.selected_agent, "grok")
        self.assertEqual(result.target_model, "gpt-5.5")
        self.assertEqual(result.reasoning_effort, "high")
        self.assertEqual(grok.calls, [(None, "high")])

    async def test_unknown_agentbridge_model_id_is_parsed(self) -> None:
        router, _grok, codex = self._router()

        result = await router.run("fix this bug", "agentbridge-auto-gpt-5.6-sol-xhigh-fast")

        self.assertEqual(result.target_model, "gpt-5.6-sol")
        self.assertEqual(result.reasoning_effort, "xhigh")
        self.assertEqual(codex.calls, [("gpt-5.6-sol", "xhigh")])

    async def test_unsupported_target_model_falls_back_to_default_cli_model(self) -> None:
        router, _grok, codex = self._router()
        codex.results = [
            AgentResult("codex", False, "", "model is not supported", 0.01, 1),
            AgentResult("codex", True, "fallback ok", None, 0.02, 0),
        ]

        result = await router.run("fix this bug", "agentbridge-auto-gpt-5.6-sol-high")

        self.assertTrue(result.success)
        self.assertIn("AgentBridge model fallback", result.content)
        self.assertIn("fallback ok", result.content)
        self.assertEqual(codex.calls, [("gpt-5.6-sol", "high"), (None, "high")])

    def _router(self) -> tuple[AgentRouter, FakeExecutor, FakeExecutor]:
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        root = Path(temp_dir.name)
        settings = AgentBridgeConfig(
            project=ProjectConfig(root=str(root)),
            skills=SkillsConfig(enabled=False),
            config_dir=str(root),
        )
        grok = FakeExecutor("grok")
        codex = FakeExecutor("codex")
        return AgentRouter(settings, grok_executor=grok, codex_executor=codex), grok, codex


if __name__ == "__main__":
    unittest.main()
