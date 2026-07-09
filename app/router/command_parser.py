import re

from app.models import ParsedCommand


COMMAND_RE = re.compile(r"^\s*@(grok|codex|both|auto)\b\s*", re.IGNORECASE)


class CommandParser:
    def __init__(self, default_agent: str = "codex") -> None:
        self.default_agent = default_agent

    def parse(self, text: str) -> ParsedCommand:
        raw_text = text or ""
        match = COMMAND_RE.match(raw_text)
        if not match:
            return ParsedCommand(
                agent=self.default_agent,
                mode="default",
                clean_prompt=raw_text.strip(),
            )

        command = match.group(1).lower()
        clean_prompt = raw_text[match.end() :].strip()

        if command == "auto":
            return ParsedCommand(
                agent="auto",
                mode="auto",
                clean_prompt=clean_prompt,
            )

        return ParsedCommand(
            agent=command,
            mode="normal",
            clean_prompt=clean_prompt,
        )

