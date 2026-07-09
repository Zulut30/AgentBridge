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


def _default_model_presets() -> list[ModelPreset]:
    presets: list[ModelPreset] = [
        ModelPreset(id="agentbridge-auto", agent="auto", label="AgentBridge Auto"),
        ModelPreset(id="agentbridge-grok", agent="grok", label="AgentBridge Grok"),
        ModelPreset(id="agentbridge-codex", agent="codex", label="AgentBridge Codex"),
    ]

    _add_variant_presets(
        presets,
        agent="auto",
        bases=[
            "gpt-5.6-sol",
            "gpt-5.5",
            "gpt-5.4",
        ],
        efforts=["none", "low", "medium", "high", "xhigh"],
        include_fast=True,
    )
    _add_variant_presets(
        presets,
        agent="auto",
        bases=[
            "gpt-5.4-mini",
            "gpt-5.4-nano",
        ],
        efforts=["none", "low", "medium", "high", "xhigh"],
    )
    _add_variant_presets(
        presets,
        agent="auto",
        bases=[
            "gpt-5.3-codex",
            "gpt-5.2-codex",
            "gpt-5.2",
        ],
        efforts=["low", "high", "xhigh"],
        include_fast=True,
    )
    _add_variant_presets(
        presets,
        agent="auto",
        bases=[
            "gpt-5.1-codex-max",
        ],
        efforts=["low", "medium", "high", "xhigh"],
        include_fast=True,
    )
    _add_variant_presets(
        presets,
        agent="auto",
        bases=[
            "gpt-5.1",
            "gpt-5.1-codex-mini",
        ],
        efforts=["low", "high"],
    )
    _add_variant_presets(
        presets,
        agent="auto",
        bases=[
            "gpt-5-codex",
            "gpt-5",
            "gpt-5-mini",
            "gpt-5-nano",
        ],
        efforts=["low", "medium", "high"],
    )

    _add_variant_presets(
        presets,
        agent="codex",
        bases=[
            "gpt-5.3-codex",
            "gpt-5.2-codex",
            "gpt-5.1-codex-max",
            "gpt-5.1-codex-mini",
            "gpt-5-codex",
        ],
        efforts=["low", "medium", "high", "xhigh"],
        include_fast=True,
    )

    presets.extend(
        [
            ModelPreset(id="agentbridge-grok-build", agent="grok", target_model="grok-build"),
            ModelPreset(
                id="agentbridge-grok-build-low",
                agent="grok",
                target_model="grok-build",
                reasoning_effort="low",
            ),
            ModelPreset(
                id="agentbridge-grok-build-medium",
                agent="grok",
                target_model="grok-build",
                reasoning_effort="medium",
            ),
            ModelPreset(
                id="agentbridge-grok-build-high",
                agent="grok",
                target_model="grok-build",
                reasoning_effort="high",
            ),
            ModelPreset(
                id="agentbridge-grok-composer-2.5-fast",
                agent="grok",
                target_model="grok-composer-2.5-fast",
            ),
        ]
    )

    return _dedupe_presets(presets)


def _add_variant_presets(
    presets: list[ModelPreset],
    *,
    agent: str,
    bases: list[str],
    efforts: list[str],
    include_fast: bool = False,
) -> None:
    for base in bases:
        presets.append(ModelPreset(id=f"agentbridge-{agent}-{base}", agent=agent, target_model=base))
        for effort in efforts:
            reasoning = _reasoning_from_suffix(effort)
            presets.append(
                ModelPreset(
                    id=f"agentbridge-{agent}-{base}-{effort}",
                    agent=agent,
                    target_model=base,
                    reasoning_effort=reasoning,
                )
            )
            if include_fast:
                presets.append(
                    ModelPreset(
                        id=f"agentbridge-{agent}-{base}-{effort}-fast",
                        agent=agent,
                        target_model=base,
                        reasoning_effort=reasoning,
                        description="Fast variant requested by Cursor; CLI support depends on the selected backend.",
                    )
                )


def _dedupe_presets(presets: list[ModelPreset]) -> list[ModelPreset]:
    seen: set[str] = set()
    deduped: list[ModelPreset] = []
    for preset in presets:
        if preset.id in seen:
            continue
        seen.add(preset.id)
        deduped.append(preset)
    return deduped


def _reasoning_from_suffix(suffix: str | None) -> str | None:
    if suffix in {None, "", "default", "none"}:
        return None
    if suffix == "extra-high":
        return "xhigh"
    return suffix


def _infer_agentbridge_preset(model_id: str) -> ModelPreset | None:
    prefixes = {
        "agentbridge-auto-": "auto",
        "agentbridge-codex-": "codex",
        "agentbridge-grok-": "grok",
    }
    for prefix, agent in prefixes.items():
        if not model_id.startswith(prefix):
            continue
        target_model, reasoning_effort = _parse_agentbridge_target(model_id[len(prefix) :], agent)
        return ModelPreset(
            id=model_id,
            agent=agent,
            target_model=target_model,
            reasoning_effort=reasoning_effort,
        )
    return None


def _parse_agentbridge_target(raw_target: str, agent: str) -> tuple[str | None, str | None]:
    target = raw_target.strip("-")
    if not target:
        return None, None

    if agent != "grok" and target.endswith("-fast"):
        target = target[: -len("-fast")]

    for suffix in ["extra-high", "xhigh", "medium", "high", "low", "none", "max"]:
        marker = f"-{suffix}"
        if target.endswith(marker):
            return target[: -len(marker)] or None, _reasoning_from_suffix(suffix)

    return target, None


class ModelsConfig(BaseModel):
    presets: list[ModelPreset] = Field(default_factory=_default_model_presets)


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
    forbid_dangerous_prompts: bool = False
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

        inferred = _infer_agentbridge_preset(model_id)
        if inferred:
            return inferred

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
