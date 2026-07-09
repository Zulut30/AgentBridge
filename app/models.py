from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, Field


class ChatMessage(BaseModel):
    role: str
    content: Any


class ChatCompletionRequest(BaseModel):
    model: str = "agentbridge-auto"
    messages: list[ChatMessage]
    stream: bool = False


class ResponsesRequest(BaseModel):
    model: str = "agentbridge-auto"
    input: Any
    stream: bool = False


@dataclass(slots=True)
class ParsedCommand:
    agent: str
    mode: str
    clean_prompt: str


@dataclass(slots=True)
class AgentResult:
    agent: str
    success: bool
    stdout: str
    stderr: str | None
    duration_seconds: float
    returncode: int | None


@dataclass(slots=True)
class RouteResult:
    content: str
    requested_model: str
    preset_id: str
    selected_agent: str
    target_model: str | None
    reasoning_effort: str | None
    duration_seconds: float
    success: bool


class ErrorResponse(BaseModel):
    detail: str = Field(..., examples=["Unauthorized"])
