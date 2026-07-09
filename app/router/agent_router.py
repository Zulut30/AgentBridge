import asyncio

from app.config import AgentBridgeConfig, get_settings
from app.context.prompt_builder import PromptBuilder
from app.executors.codex_executor import CodexExecutor
from app.executors.grok_executor import GrokExecutor
from app.models import AgentResult
from app.router.command_parser import CommandParser
from app.safety.policy import SafetyPolicy


class AgentRouter:
    def __init__(
        self,
        settings: AgentBridgeConfig,
        grok_executor: GrokExecutor | None = None,
        codex_executor: CodexExecutor | None = None,
    ) -> None:
        self.settings = settings
        self.parser = CommandParser(settings.routing.default_agent)
        self.prompt_builder = PromptBuilder(settings)
        self.safety = SafetyPolicy(settings.safety)
        self.grok_executor = grok_executor or GrokExecutor(settings)
        self.codex_executor = codex_executor or CodexExecutor(settings)

    @classmethod
    def from_settings(cls) -> "AgentRouter":
        return cls(get_settings())

    async def run(self, user_prompt: str) -> str:
        parsed = self.parser.parse(user_prompt)
        self.safety.ensure_prompt_allowed(parsed.clean_prompt)
        prompt = self.prompt_builder.build(parsed.clean_prompt)

        agent = parsed.agent
        if agent == "auto":
            agent = self.settings.routing.default_agent

        if agent == "both":
            grok_result, codex_result = await asyncio.gather(
                self.grok_executor.run(prompt),
                self.codex_executor.run(prompt),
            )
            return self._merge_results(grok_result, codex_result)

        if agent == "grok":
            return self._format_single_result(await self.grok_executor.run(prompt))

        if agent == "codex":
            return self._format_single_result(await self.codex_executor.run(prompt))

        default_agent = self.settings.routing.default_agent
        if default_agent == "grok":
            return self._format_single_result(await self.grok_executor.run(prompt))
        return self._format_single_result(await self.codex_executor.run(prompt))

    def _format_single_result(self, result: AgentResult) -> str:
        if result.success:
            return result.stdout.strip()

        command_name = "Grok Build" if result.agent == "grok" else result.agent.title()
        error = result.stderr or result.stdout or "unknown error"
        return (
            f"AgentBridge could not run {command_name} CLI.\n\n"
            f"Agent: {result.agent}\n"
            f"Return code: {result.returncode}\n"
            f"Duration: {result.duration_seconds:.2f}s\n\n"
            f"Error:\n{error.strip()}\n\n"
            f"Fix:\nInstall and login to {command_name} CLI, then retry."
        )

    def _merge_results(self, grok_result: AgentResult, codex_result: AgentResult) -> str:
        return (
            "# Grok Result\n\n"
            f"{self._format_single_result(grok_result)}\n\n"
            "# Codex Result\n\n"
            f"{self._format_single_result(codex_result)}\n\n"
            "# AgentBridge Summary\n\n"
            "- Grok is usually useful for diagnosis and alternative analysis.\n"
            "- Codex is usually useful for focused implementation work.\n"
            "- Review any proposed diff manually before applying changes."
        )
