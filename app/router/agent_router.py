import asyncio
import re
import time
from typing import Any

from app.config import AgentBridgeConfig, ModelPreset, get_settings
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

        codex_prompt = self.prompt_builder.build(
            parsed.clean_prompt,
            requested_model=requested_model,
            target_model=preset.target_model,
            reasoning_effort=preset.reasoning_effort,
            selected_agent=agent,
        )
        grok_prompt = self.prompt_builder.build_grok(
            parsed.clean_prompt,
            requested_model=requested_model,
            target_model=preset.target_model,
            reasoning_effort=preset.reasoning_effort,
        )

        if agent == "both":
            grok_target, grok_reasoning = self._executor_args_for("grok", preset)
            codex_target, codex_reasoning = self._executor_args_for("codex", preset)
            grok_result, codex_result = await asyncio.gather(
                self._run_with_model_fallback(self.grok_executor, grok_prompt, grok_target, grok_reasoning),
                self._run_with_model_fallback(self.codex_executor, codex_prompt, codex_target, codex_reasoning),
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
            executor_target, executor_reasoning = self._executor_args_for("grok", preset)
            result = await self._run_with_model_fallback(
                self.grok_executor,
                grok_prompt,
                executor_target,
                executor_reasoning,
            )
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
            executor_target, executor_reasoning = self._executor_args_for("codex", preset)
            result = await self._run_with_model_fallback(
                self.codex_executor,
                codex_prompt,
                executor_target,
                executor_reasoning,
            )
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
            executor_target, executor_reasoning = self._executor_args_for("grok", preset)
            result = await self._run_with_model_fallback(
                self.grok_executor,
                grok_prompt,
                executor_target,
                executor_reasoning,
            )
            selected_agent = "grok"
        else:
            executor_target, executor_reasoning = self._executor_args_for("codex", preset)
            result = await self._run_with_model_fallback(
                self.codex_executor,
                codex_prompt,
                executor_target,
                executor_reasoning,
            )
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

    def _executor_args_for(self, selected_agent: str, preset: ModelPreset) -> tuple[str | None, str | None]:
        target_model = preset.target_model
        reasoning_effort = preset.reasoning_effort

        if selected_agent == "grok":
            if target_model and not target_model.startswith("grok"):
                target_model = None
            if reasoning_effort not in {None, "low", "medium", "high"}:
                reasoning_effort = None

        if selected_agent == "codex" and target_model:
            is_codex_compatible = target_model.startswith("gpt-") or "codex" in target_model
            if not is_codex_compatible:
                target_model = None

        return target_model, reasoning_effort

    async def _run_with_model_fallback(
        self,
        executor: Any,
        prompt: str,
        target_model: str | None,
        reasoning_effort: str | None,
    ) -> AgentResult:
        result = await executor.run(prompt, target_model, reasoning_effort)
        result = self._empty_success_as_failure(result)
        if not target_model or result.success or not self._looks_like_model_rejection(result):
            return result

        fallback = await executor.run(prompt, None, reasoning_effort)
        fallback = self._empty_success_as_failure(fallback)
        fallback.duration_seconds += result.duration_seconds
        if fallback.success:
            fallback.stdout = (
                f"AgentBridge model fallback: `{target_model}` was rejected by {result.agent} CLI, "
                "so the request was retried with that CLI's default model.\n\n"
                f"{fallback.stdout}"
            )
            return fallback

        original_error = (result.stderr or result.stdout or "").strip()
        fallback_error = (fallback.stderr or fallback.stdout or "").strip()
        fallback.stderr = (
            f"Original model `{target_model}` was rejected by {result.agent} CLI:\n"
            f"{original_error}\n\n"
            "Fallback without an explicit model also failed:\n"
            f"{fallback_error}"
        )
        return fallback

    def _empty_success_as_failure(self, result: AgentResult) -> AgentResult:
        if not result.success or result.stdout.strip():
            return result
        return AgentResult(
            agent=result.agent,
            success=False,
            stdout=result.stdout,
            stderr="agent returned empty output",
            duration_seconds=result.duration_seconds,
            returncode=result.returncode,
        )

    def _looks_like_model_rejection(self, result: AgentResult) -> bool:
        output = f"{result.stderr or ''}\n{result.stdout or ''}".lower()
        markers = [
            "model is not supported",
            "unknown model",
            "unsupported model",
            "model_not_found",
            "invalid model",
        ]
        return any(marker in output for marker in markers)

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
