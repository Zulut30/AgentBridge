from app.config import AgentBridgeConfig
from app.executors.base import SubprocessAgentExecutor


class GrokExecutor(SubprocessAgentExecutor):
    def __init__(self, settings: AgentBridgeConfig) -> None:
        super().__init__("grok", settings.agents.grok, settings)

