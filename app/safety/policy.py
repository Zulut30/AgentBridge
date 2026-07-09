from app.config import SafetyConfig


class SafetyPolicy:
    def __init__(self, config: SafetyConfig) -> None:
        self.config = config
        self.forbidden_patterns = [pattern.lower() for pattern in config.forbidden_patterns]

    def ensure_prompt_allowed(self, prompt: str) -> None:
        if not self.config.forbid_dangerous_prompts:
            return
        self._ensure_text_allowed(prompt, "Prompt")

    def ensure_command_allowed(self, command: list[str]) -> None:
        if not self.config.forbid_dangerous_commands:
            return
        self._ensure_text_allowed(" ".join(command), "Command")

    def _ensure_text_allowed(self, text: str, label: str) -> None:
        normalized = text.lower()
        for pattern in self.forbidden_patterns:
            if pattern and pattern in normalized:
                raise ValueError(f"{label} contains forbidden pattern: {pattern}")
