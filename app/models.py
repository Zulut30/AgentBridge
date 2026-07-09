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


class ErrorResponse(BaseModel):
    detail: str = Field(..., examples=["Unauthorized"])

