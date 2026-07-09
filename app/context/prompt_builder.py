from app.config import AgentBridgeConfig
from app.context.skills_loader import SkillsLoader


class PromptBuilder:
    def __init__(self, settings: AgentBridgeConfig) -> None:
        self.settings = settings
        self.skills_loader = SkillsLoader(settings)

    def build(self, clean_prompt: str) -> str:
        loaded_skills = self.skills_loader.load()
        skills_content = loaded_skills or "No skills loaded."

        return (
            "# AgentBridge Task\n\n"
            "## User Request\n\n"
            f"{clean_prompt.strip()}\n\n"
            "## Project\n\n"
            f"Root: {self.settings.project_root_path}\n\n"
            "## Rules\n\n"
            "- Make minimal necessary changes.\n"
            "- Do not refactor unrelated code.\n"
            "- Do not delete databases.\n"
            "- Do not run destructive commands.\n"
            "- If changes are needed, explain them clearly.\n"
            "- Prefer producing a patch/diff or step-by-step plan.\n"
            "- If unsure, ask for clarification in the response, but do not modify files blindly.\n\n"
            "## Loaded Skills\n\n"
            f"{skills_content}"
        )

