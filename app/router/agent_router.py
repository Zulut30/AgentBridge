import asyncio
import re
import time

from app.config import AgentBridgeConfig, get_settings
from app.context.prompt_builder import PromptBuilder
from app.executors.codex_executor import CodexExecutor
from app.executors.grok_executor import GrokExecutor
from app.models import AgentResult, RouteResult
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

    async def run(self, user_prompt: str, requested_model: str = "agentbridge-auto") -> RouteResult:
        start = time.perf_counter()
        preset = self.settings.model_preset_for(requested_model)
        parsed = self.parser.parse(user_prompt)
        self.safety.ensure_prompt_allowed(parsed.clean_prompt)

        agent = parsed.agent if parsed.mode != "default" else preset.agent
        if agent == "auto":
            agent = self._resolve_auto_agent(parsed.clean_prompt)

        prompt = self.prompt_builder.build(
            parsed.clean_prompt,
            requested_model=requested_model,
            target_model=preset.target_model,
            reasoning_effort=preset.reasoning_effort,
            selected_agent=agent,
        )

        if agent == "both":
            grok_result, codex_result = await asyncio.gather(
                self.grok_executor.run(prompt, preset.target_model, preset.reasoning_effort),
                self.codex_executor.run(prompt, preset.target_model, preset.reasoning_effort),
            )
            content = self._merge_results(grok_result, codex_result)
            return self._route_result(
                content,
                requested_model,
                preset.id,
                agent,
                preset.target_model,
                preset.reasoning_effort,
                time.perf_counter() - start,
                grok_result.success and codex_result.success,
            )

        if agent == "grok":
            result = await self.grok_executor.run(prompt, preset.target_model, preset.reasoning_effort)
            return self._route_result(
                self._format_single_result(result),
                requested_model,
                preset.id,
                agent,
                preset.target_model,
                preset.reasoning_effort,
                time.perf_counter() - start,
                result.success,
            )

        if agent == "codex":
            result = await self.codex_executor.run(prompt, preset.target_model, preset.reasoning_effort)
            return self._route_result(
                self._format_single_result(result),
                requested_model,
                preset.id,
                agent,
                preset.target_model,
                preset.reasoning_effort,
                time.perf_counter() - start,
                result.success,
            )

        default_agent = self.settings.routing.default_agent
        if default_agent == "grok":
            result = await self.grok_executor.run(prompt, preset.target_model, preset.reasoning_effort)
            selected_agent = "grok"
        else:
            result = await self.codex_executor.run(prompt, preset.target_model, preset.reasoning_effort)
            selected_agent = "codex"
        return self._route_result(
            self._format_single_result(result),
            requested_model,
            preset.id,
            selected_agent,
            preset.target_model,
            preset.reasoning_effort,
            time.perf_counter() - start,
            result.success,
        )

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

    def _resolve_auto_agent(self, prompt: str) -> str:
        normalized = prompt.lower()
        for keyword in self.settings.routing.web_search_keywords:
            if self._keyword_matches(normalized, keyword.lower()):
                return self.settings.routing.web_search_agent
        return self.settings.routing.code_agent

    def _keyword_matches(self, normalized_prompt: str, keyword: str) -> bool:
        if keyword == "x":
            return re.search(r"\bx\b", normalized_prompt) is not None
        if " " in keyword:
            return keyword in normalized_prompt
        return re.search(rf"\b{re.escape(keyword)}\b", normalized_prompt) is not None

    def describe_auto(self) -> dict[str, object]:
        return {
            "default": "code_agent unless a web/search/X keyword is present",
            "code_agent": self.settings.routing.code_agent,
            "web_search_agent": self.settings.routing.web_search_agent,
            "web_search_keywords": self.settings.routing.web_search_keywords,
            "explicit_commands": {
                "@grok": "force Grok Build CLI",
                "@codex": "force Codex CLI",
                "@both": "run both CLIs in parallel",
                "@auto": "use AgentBridge auto routing rules",
            },
        }

    def _route_result(
        self,
        content: str,
        requested_model: str,
        preset_id: str,
        selected_agent: str,
        target_model: str | None,
        reasoning_effort: str | None,
        duration_seconds: float,
        success: bool,
    ) -> RouteResult:
        return RouteResult(
            content=content,
            requested_model=requested_model,
            preset_id=preset_id,
            selected_agent=selected_agent,
            target_model=target_model,
            reasoning_effort=reasoning_effort,
            duration_seconds=duration_seconds,
            success=success,
        )
