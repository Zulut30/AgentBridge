import asyncio
import shutil
import tempfile
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

        if self.agent_config.prompt_via_stdin and self.agent_config.prompt_via_file:
            return self._result(
                start,
                success=False,
                stdout="",
                stderr="executor config cannot use both prompt_via_stdin and prompt_via_file",
                returncode=None,
            )

        try:
            prompt_file = None
            try:
                dynamic_args = self._dynamic_args(target_model, reasoning_effort)
                if self.agent_config.dynamic_args_before_static:
                    command = [self.agent_config.command, *dynamic_args, *self.agent_config.args]
                else:
                    command = [self.agent_config.command, *self.agent_config.args, *dynamic_args]

                if self.agent_config.prompt_via_file:
                    prompt_file = self._write_prompt_file(prompt)
                    if self.agent_config.prompt_file_arg:
                        command.extend([self.agent_config.prompt_file_arg, str(prompt_file)])
                    else:
                        command.append(str(prompt_file))
                elif not self.agent_config.prompt_via_stdin:
                    command.append(prompt)

                try:
                    command_for_safety = command if self._prompt_is_not_command_arg() else command[:-1]
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
                    display_command = self._display_command(command)
                    launch_error = "command not found"
                    if self._command_line_length(command) > 30000:
                        launch_error = (
                            "command line is too long for this platform; "
                            "enable prompt_via_file or prompt_via_stdin for this executor"
                        )
                    return self._result(
                        start,
                        success=False,
                        stdout="",
                        stderr=(
                            f"{launch_error}\n\n"
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
            finally:
                if prompt_file:
                    try:
                        prompt_file.unlink(missing_ok=True)
                    except OSError:
                        pass
        except OSError as exc:
            return self._result(
                start,
                success=False,
                stdout="",
                stderr=str(exc),
                returncode=None,
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

    def _write_prompt_file(self, prompt: str) -> Path:
        prompts_dir = self.settings.config_dir_path / ".agentbridge" / "tmp" / "prompts"
        prompts_dir.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            prefix=f"{self.agent_name}-",
            suffix=".txt",
            dir=prompts_dir,
            delete=False,
        ) as handle:
            handle.write(prompt)
            return Path(handle.name)

    def _prompt_is_not_command_arg(self) -> bool:
        return self.agent_config.prompt_via_stdin or self.agent_config.prompt_via_file

    def _display_command(self, command: list[str]) -> str:
        if self._prompt_is_not_command_arg():
            return " ".join(command)
        return " ".join([*command[:-1], "<prompt>"])

    def _command_line_length(self, command: list[str]) -> int:
        return sum(len(part) for part in command) + max(0, len(command) - 1)
