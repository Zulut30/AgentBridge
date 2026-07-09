from app.config import AgentBridgeConfig
from app.executors.base import SubprocessAgentExecutor


class CodexExecutor(SubprocessAgentExecutor):
    def __init__(self, settings: AgentBridgeConfig) -> None:
        super().__init__("codex", settings.agents.codex, settings)

