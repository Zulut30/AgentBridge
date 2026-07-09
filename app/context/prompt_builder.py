from app.config import AgentBridgeConfig
from app.context.skills_loader import SkillsLoader


class PromptBuilder:
    def __init__(self, settings: AgentBridgeConfig) -> None:
        self.settings = settings
        self.skills_loader = SkillsLoader(settings)

    def build(
        self,
        clean_prompt: str,
        requested_model: str = "agentbridge-auto",
        target_model: str | None = None,
        reasoning_effort: str | None = None,
        selected_agent: str = "auto",
    ) -> str:
        loaded_skills = self.skills_loader.load()
        skills_content = loaded_skills or "No skills loaded."
        target_model_text = target_model or "agent default"
        reasoning_text = reasoning_effort or "agent default"

        return (
            "# AgentBridge Task\n\n"
            "## User Request\n\n"
            f"{clean_prompt.strip()}\n\n"
            "## Cursor Selection\n\n"
            f"Requested model id: {requested_model}\n"
            f"Selected agent: {selected_agent}\n"
            f"Target model: {target_model_text}\n"
            f"Reasoning effort: {reasoning_text}\n\n"
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

    def build_grok(
        self,
        clean_prompt: str,
        requested_model: str = "agentbridge-auto",
        target_model: str | None = None,
        reasoning_effort: str | None = None,
    ) -> str:
        target_model_text = target_model or "agent default"
        reasoning_text = reasoning_effort or "agent default"

        return (
            "Answer the user's exact subject, not a nearby topic. First identify the concrete "
            "subject in the user request, then answer that subject directly. Answer in the same "
            "language as the user unless the user asks otherwise. Use web search and X/x.com "
            "search when the request asks for current, latest, popular, news, meta, or social "
            "information. If the user mentions X/x.com as a source, treat X only as a source; "
            "do not answer with general X trends unless the user explicitly asks for X trends. "
            "For non-English domain words, translate them into search keywords before searching "
            "(examples: `хартстоун` -> `Hearthstone`, `колода` -> `deck`, `мета` -> `meta`). "
            "For game, deck, card, or meta questions, search for the specific game/topic first "
            "and use X only as one of the sources. If the user asks about `deck`, `meta`, "
            "`колода`, or `мета`, start with the concrete deck/meta answer and omit unrelated "
            "general X trend summaries. If sources are available, include concise source links. "
            "Be direct and practical.\n\n"
            f"Requested model id: {requested_model}\n"
            f"Target model: {target_model_text}\n"
            f"Reasoning effort: {reasoning_text}\n\n"
            "User request:\n"
            f"{clean_prompt.strip()}"
        )
