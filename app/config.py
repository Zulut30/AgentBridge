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
    default_agent: str = "codex"


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
    skills: SkillsConfig = Field(default_factory=SkillsConfig)
    safety: SafetyConfig = Field(default_factory=SafetyConfig)
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
