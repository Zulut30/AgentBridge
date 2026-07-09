import asyncio
import shutil
import time
from abc import ABC, abstractmethod
from pathlib import Path

from app.config import AgentBridgeConfig, AgentConfig
from app.models import AgentResult
from app.safety.policy import SafetyPolicy


def command_is_available(command: str) -> bool:
    if not command:
        return False
    command_path = Path(command).expanduser()
    if command_path.exists():
        return True
    return shutil.which(command) is not None


class AgentExecutor(ABC):
    @abstractmethod
    async def run(
        self,
        prompt: str,
        target_model: str | None = None,
        reasoning_effort: str | None = None,
    ) -> AgentResult:
        raise NotImplementedError


class SubprocessAgentExecutor(AgentExecutor):
    def __init__(
        self,
        agent_name: str,
        agent_config: AgentConfig,
        settings: AgentBridgeConfig,
    ) -> None:
        self.agent_name = agent_name
        self.agent_config = agent_config
        self.settings = settings
        self.safety = SafetyPolicy(settings.safety)

    async def run(
        self,
        prompt: str,
        target_model: str | None = None,
        reasoning_effort: str | None = None,
    ) -> AgentResult:
        start = time.perf_counter()

        if not self.agent_config.enabled:
            return self._result(
                start,
                success=False,
                stdout="",
                stderr=f"{self.agent_name} executor is disabled in config.",
                returncode=None,
            )

        dynamic_args = self._dynamic_args(target_model, reasoning_effort)
        if self.agent_config.dynamic_args_before_static:
            command = [self.agent_config.command, *dynamic_args, *self.agent_config.args]
        else:
            command = [self.agent_config.command, *self.agent_config.args, *dynamic_args]
        if not self.agent_config.prompt_via_stdin:
            command.append(prompt)

        try:
            command_for_safety = command if self.agent_config.prompt_via_stdin else command[:-1]
            self.safety.ensure_command_allowed(command_for_safety)
        except ValueError as exc:
            return self._result(
                start,
                success=False,
                stdout="",
                stderr=str(exc),
                returncode=None,
            )

        try:
            process = await asyncio.create_subprocess_exec(
                *command,
                cwd=str(self.settings.project_root_path),
                stdin=asyncio.subprocess.PIPE if self.agent_config.prompt_via_stdin else None,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except FileNotFoundError:
            display_command = " ".join([self.agent_config.command, *self.agent_config.args, "<prompt>"])
            return self._result(
                start,
                success=False,
                stdout="",
                stderr=(
                    f"command not found\n\n"
                    f"Command:\n{display_command}\n"
                ),
                returncode=None,
            )
        except OSError as exc:
            return self._result(
                start,
                success=False,
                stdout="",
                stderr=str(exc),
                returncode=None,
            )

        try:
            prompt_input = prompt.encode("utf-8") if self.agent_config.prompt_via_stdin else None
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                process.communicate(input=prompt_input),
                timeout=self.agent_config.timeout_seconds,
            )
        except TimeoutError:
            process.kill()
            await process.wait()
            return self._result(
                start,
                success=False,
                stdout="",
                stderr=f"command timed out after {self.agent_config.timeout_seconds}s",
                returncode=process.returncode,
            )

        stdout = stdout_bytes.decode("utf-8", errors="replace")
        stderr = stderr_bytes.decode("utf-8", errors="replace") or None
        return self._result(
            start,
            success=process.returncode == 0,
            stdout=stdout,
            stderr=stderr,
            returncode=process.returncode,
        )

    def _result(
        self,
        start: float,
        success: bool,
        stdout: str,
        stderr: str | None,
        returncode: int | None,
    ) -> AgentResult:
        return AgentResult(
            agent=self.agent_name,
            success=success,
            stdout=stdout,
            stderr=stderr,
            duration_seconds=time.perf_counter() - start,
            returncode=returncode,
        )

    def _dynamic_args(
        self,
        target_model: str | None,
        reasoning_effort: str | None,
    ) -> list[str]:
        args: list[str] = []
        if target_model and self.agent_config.model_arg:
            args.extend([self.agent_config.model_arg, target_model])
        if reasoning_effort and self.agent_config.reasoning_effort_arg:
            args.extend([self.agent_config.reasoning_effort_arg, reasoning_effort])
        return args
