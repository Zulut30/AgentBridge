import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, Field


class ServerConfig(BaseModel):
    host: str = "127.0.0.1"
    port: int = 8787
    api_key_env: str = "AGENTBRIDGE_API_KEY"
    require_api_key: bool = True
    allow_any_bearer: bool = False


class ProjectConfig(BaseModel):
    root: str = "."
    default_branch: str = "main"


class AgentConfig(BaseModel):
    enabled: bool = True
    command: str
    timeout_seconds: int = 1200
    mode: str = "exec"
    args: list[str] = Field(default_factory=list)
    prompt_via_stdin: bool = False
    model_arg: str | None = None
    reasoning_effort_arg: str | None = None
    dynamic_args_before_static: bool = True


class AgentsConfig(BaseModel):
    grok: AgentConfig = Field(
        default_factory=lambda: AgentConfig(
            command="grok",
            mode="headless",
            args=["-p"],
        )
    )
    codex: AgentConfig = Field(
        default_factory=lambda: AgentConfig(
            command="codex",
            mode="exec",
            args=["exec"],
        )
    )


class RoutingConfig(BaseModel):
    default_agent: str = "auto"
    web_search_agent: str = "grok"
    code_agent: str = "codex"
    web_search_keywords: list[str] = Field(
        default_factory=lambda: [
            "x",
            "x.com",
            "twitter",
            "tweet",
            "latest",
            "today",
            "news",
            "search web",
            "web search",
        ]
    )


class ModelPreset(BaseModel):
    id: str
    agent: str = "auto"
    target_model: str | None = None
    reasoning_effort: str | None = None
    label: str | None = None
    description: str | None = None
    cursor_enabled: bool = True


class ModelsConfig(BaseModel):
    presets: list[ModelPreset] = Field(
        default_factory=lambda: [
            ModelPreset(id="agentbridge-auto", agent="auto", label="AgentBridge Auto"),
            ModelPreset(id="agentbridge-grok", agent="grok", label="AgentBridge Grok"),
            ModelPreset(id="agentbridge-codex", agent="codex", label="AgentBridge Codex"),
            ModelPreset(
                id="agentbridge-auto-gpt-5.5-medium",
                agent="auto",
                target_model="gpt-5.5",
                reasoning_effort="medium",
            ),
            ModelPreset(
                id="agentbridge-auto-gpt-5.5-high",
                agent="auto",
                target_model="gpt-5.5",
                reasoning_effort="high",
            ),
            ModelPreset(
                id="agentbridge-auto-gpt-5.6-sol-medium",
                agent="auto",
                target_model="gpt-5.6-sol",
                reasoning_effort="medium",
            ),
            ModelPreset(
                id="agentbridge-auto-gpt-5.6-sol-high",
                agent="auto",
                target_model="gpt-5.6-sol",
                reasoning_effort="high",
            ),
        ]
    )


class UsageConfig(BaseModel):
    enabled: bool = True
    path: str = ".agentbridge/usage.jsonl"
    daily_request_limit: int | None = 200
    daily_seconds_limit: int | None = 7200


class SkillsConfig(BaseModel):
    enabled: bool = True
    paths: list[str] = Field(default_factory=lambda: ["./skills", ".agentbridge/skills"])


class SafetyConfig(BaseModel):
    readonly_by_default: bool = True
    forbid_dangerous_commands: bool = True
    forbidden_patterns: list[str] = Field(
        default_factory=lambda: [
            "rm -rf /",
            "DROP DATABASE",
            "TRUNCATE",
            "DELETE FROM",
            "git push --force",
        ]
    )


class AgentBridgeConfig(BaseModel):
    server: ServerConfig = Field(default_factory=ServerConfig)
    project: ProjectConfig = Field(default_factory=ProjectConfig)
    agents: AgentsConfig = Field(default_factory=AgentsConfig)
    routing: RoutingConfig = Field(default_factory=RoutingConfig)
    models: ModelsConfig = Field(default_factory=ModelsConfig)
    skills: SkillsConfig = Field(default_factory=SkillsConfig)
    safety: SafetyConfig = Field(default_factory=SafetyConfig)
    usage: UsageConfig = Field(default_factory=UsageConfig)
    config_dir: str = "."

    @property
    def api_key(self) -> str:
        return os.getenv(self.server.api_key_env, "local-dev-key")

    @property
    def config_dir_path(self) -> Path:
        return Path(self.config_dir).expanduser().resolve()

    @property
    def project_root_path(self) -> Path:
        root = Path(self.project.root).expanduser()
        if not root.is_absolute():
            root = self.config_dir_path / root
        return root.resolve()

    @property
    def usage_log_path(self) -> Path:
        path = Path(self.usage.path).expanduser()
        if not path.is_absolute():
            path = self.config_dir_path / path
        return path.resolve()

    def model_preset_for(self, model_id: str) -> ModelPreset:
        for preset in self.models.presets:
            if preset.id == model_id:
                return preset

        if model_id.startswith("agentbridge-grok"):
            return ModelPreset(id=model_id, agent="grok")
        if model_id.startswith("agentbridge-codex"):
            return ModelPreset(id=model_id, agent="codex")
        if model_id.startswith("agentbridge-auto"):
            return ModelPreset(id=model_id, agent="auto")

        return ModelPreset(id=model_id, agent="auto", target_model=model_id)

    def cursor_model_ids(self) -> list[str]:
        return [preset.id for preset in self.models.presets if preset.cursor_enabled]


def _model_from_dict(data: dict[str, Any]) -> AgentBridgeConfig:
    if hasattr(AgentBridgeConfig, "model_validate"):
        return AgentBridgeConfig.model_validate(data)
    return AgentBridgeConfig.parse_obj(data)


def load_settings(config_path: str | Path | None = None) -> AgentBridgeConfig:
    load_dotenv()

    requested_path = config_path or os.getenv("AGENTBRIDGE_CONFIG", "agentbridge.yaml")
    path = Path(requested_path).expanduser()
    data: dict[str, Any] = {}

    if path.exists():
        with path.open("r", encoding="utf-8") as handle:
            loaded = yaml.safe_load(handle) or {}
            if not isinstance(loaded, dict):
                raise ValueError(f"Config file {path} must contain a YAML mapping.")
            data.update(loaded)
        data["config_dir"] = str(path.resolve().parent)
    else:
        data["config_dir"] = str(Path.cwd())

    return _model_from_dict(data)


@lru_cache(maxsize=1)
def get_settings() -> AgentBridgeConfig:
    return load_settings()
