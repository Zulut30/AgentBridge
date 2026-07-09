from pathlib import Path

from app.config import AgentBridgeConfig


class SkillsLoader:
    def __init__(self, settings: AgentBridgeConfig) -> None:
        self.settings = settings

    def load(self) -> str:
        if not self.settings.skills.enabled:
            return ""

        chunks: list[str] = []
        for directory in self._candidate_directories():
            if not directory.exists() or not directory.is_dir():
                continue
            for skill_file in sorted(directory.glob("*.md")):
                content = skill_file.read_text(encoding="utf-8").strip()
                if content:
                    chunks.append(f"<!-- {skill_file} -->\n{content}")

        return "\n\n".join(chunks)

    def _candidate_directories(self) -> list[Path]:
        candidates: list[Path] = []
        seen: set[Path] = set()

        for raw_path in self.settings.skills.paths:
            path = Path(raw_path).expanduser()
            possible_paths = [path] if path.is_absolute() else [
                self.settings.config_dir_path / path,
                self.settings.project_root_path / path,
                Path.cwd() / path,
            ]
            for possible_path in possible_paths:
                resolved = possible_path.resolve()
                if resolved not in seen:
                    seen.add(resolved)
                    candidates.append(resolved)

        return candidates

