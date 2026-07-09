import json
import time
import uuid
from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.responses import StreamingResponse

from app.config import AgentBridgeConfig, get_settings
from app.models import ChatCompletionRequest, ChatMessage, ResponsesRequest
from app.router.agent_router import AgentRouter
from app.executors.base import command_is_available
from app.usage import UsageTracker


router = APIRouter()


def require_bearer_token(
    authorization: str | None = Header(default=None),
    settings: AgentBridgeConfig = Depends(get_settings),
) -> None:
    if not settings.server.require_api_key:
        return
    if settings.server.allow_any_bearer and authorization and authorization.startswith("Bearer "):
        return
    expected = f"Bearer {settings.api_key}"
    if authorization != expected:
        raise HTTPException(status_code=401, detail="Unauthorized")


@router.get("/v1/models", dependencies=[Depends(require_bearer_token)])
async def list_models(settings: AgentBridgeConfig = Depends(get_settings)) -> dict[str, Any]:
    return {
        "object": "list",
        "data": [
            {
                "id": preset.id,
                "object": "model",
                "owned_by": "agentbridge",
            }
            for preset in settings.models.presets
            if preset.cursor_enabled
        ],
    }


@router.get("/agentbridge/status", dependencies=[Depends(require_bearer_token)])
async def agentbridge_status(settings: AgentBridgeConfig = Depends(get_settings)) -> dict[str, Any]:
    router_instance = AgentRouter(settings)
    return {
        "status": "ok",
        "project_root": str(settings.project_root_path),
        "agents": {
            "grok": {
                "enabled": settings.agents.grok.enabled,
                "command": settings.agents.grok.command,
                "available": settings.agents.grok.enabled and command_is_available(settings.agents.grok.command),
                "subagents_enabled": "--no-subagents" not in [arg.lower() for arg in settings.agents.grok.args],
            },
            "codex": {
                "enabled": settings.agents.codex.enabled,
                "command": settings.agents.codex.command,
                "available": settings.agents.codex.enabled and command_is_available(settings.agents.codex.command),
            },
        },
        "models": [preset.model_dump() if hasattr(preset, "model_dump") else preset.dict() for preset in settings.models.presets],
        "auto": router_instance.describe_auto(),
        "usage": UsageTracker(settings).summary(),
    }


@router.get("/agentbridge/limits", dependencies=[Depends(require_bearer_token)])
async def agentbridge_limits(settings: AgentBridgeConfig = Depends(get_settings)) -> dict[str, Any]:
    return UsageTracker(settings).summary()


@router.get("/agentbridge/auto", dependencies=[Depends(require_bearer_token)])
async def agentbridge_auto(settings: AgentBridgeConfig = Depends(get_settings)) -> dict[str, Any]:
    return AgentRouter(settings).describe_auto()


@router.post("/v1/chat/completions", dependencies=[Depends(require_bearer_token)])
async def chat_completions(request: ChatCompletionRequest) -> Any:
    prompt = _messages_to_prompt(request.messages)
    try:
        route_result = await AgentRouter.from_settings().run(prompt, request.model)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    content = route_result.content
    _record_usage("chat.completions", prompt, content, route_result)

    if request.stream:
        return StreamingResponse(
            _chat_completion_stream(request.model, content),
            media_type="text/event-stream",
        )

    return _chat_completion_response(request.model, content)


@router.post("/v1/responses", dependencies=[Depends(require_bearer_token)])
async def responses(request: ResponsesRequest) -> Any:
    prompt = _responses_input_to_prompt(request.input)
    try:
        route_result = await AgentRouter.from_settings().run(prompt, request.model)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    content = route_result.content
    _record_usage("responses", prompt, content, route_result)

    if request.stream:
        return StreamingResponse(
            _responses_stream(request.model, content),
            media_type="text/event-stream",
        )

    return _responses_response(request.model, content)


def _messages_to_prompt(messages: list[ChatMessage]) -> str:
    parts: list[str] = []
    for message in messages:
        text = _content_to_text(message.content)
        if not text:
            continue
        if message.role == "user":
            parts.append(text)
        else:
            parts.append(f"{message.role}: {text}")
    return "\n\n".join(parts).strip()


def _responses_input_to_prompt(input_value: Any) -> str:
    if isinstance(input_value, str):
        return input_value.strip()

    if isinstance(input_value, list):
        parts: list[str] = []
        for item in input_value:
            if isinstance(item, dict):
                role = item.get("role")
                content = _content_to_text(item.get("content", item))
                parts.append(f"{role}: {content}" if role else content)
            else:
                parts.append(_content_to_text(item))
        return "\n\n".join(part for part in parts if part).strip()

    if isinstance(input_value, dict):
        return _content_to_text(input_value)

    return str(input_value).strip()


def _content_to_text(content: Any) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict):
                if "text" in item:
                    parts.append(str(item["text"]))
                elif item.get("type") == "input_text" and "content" in item:
                    parts.append(str(item["content"]))
                else:
                    parts.append(json.dumps(item, ensure_ascii=False))
            else:
                parts.append(str(item))
        return "\n".join(parts)
    if isinstance(content, dict):
        if "text" in content:
            return str(content["text"])
        if "content" in content:
            return _content_to_text(content["content"])
        return json.dumps(content, ensure_ascii=False)
    return str(content)


def _record_usage(endpoint: str, prompt: str, content: str, route_result: Any) -> None:
    settings = get_settings()
    UsageTracker(settings).record(
        {
            "endpoint": endpoint,
            "requested_model": route_result.requested_model,
            "preset_id": route_result.preset_id,
            "selected_agent": route_result.selected_agent,
            "target_model": route_result.target_model,
            "reasoning_effort": route_result.reasoning_effort,
            "duration_seconds": round(route_result.duration_seconds, 3),
            "success": route_result.success,
            "input_chars": len(prompt),
            "output_chars": len(content),
        }
    )


def _chat_completion_response(model: str, content: str) -> dict[str, Any]:
    return {
        "id": f"chatcmpl-{uuid.uuid4().hex}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": content,
                },
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
        },
    }


async def _chat_completion_stream(model: str, content: str) -> AsyncIterator[str]:
    chunk = {
        "id": f"chatcmpl-{uuid.uuid4().hex}",
        "object": "chat.completion.chunk",
        "created": int(time.time()),
        "model": model,
        "choices": [
            {
                "index": 0,
                "delta": {
                    "role": "assistant",
                    "content": content,
                },
                "finish_reason": "stop",
            }
        ],
    }
    yield f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"
    yield "data: [DONE]\n\n"


def _responses_response(model: str, content: str) -> dict[str, Any]:
    response_id = f"resp_{uuid.uuid4().hex}"
    return {
        "id": response_id,
        "object": "response",
        "created_at": int(time.time()),
        "status": "completed",
        "model": model,
        "output": [
            {
                "id": f"msg_{uuid.uuid4().hex}",
                "type": "message",
                "status": "completed",
                "role": "assistant",
                "content": [
                    {
                        "type": "output_text",
                        "text": content,
                    }
                ],
            }
        ],
        "output_text": content,
        "usage": {
            "input_tokens": 0,
            "output_tokens": 0,
            "total_tokens": 0,
        },
    }


async def _responses_stream(model: str, content: str) -> AsyncIterator[str]:
    response_id = f"resp_{uuid.uuid4().hex}"
    events = [
        {
            "type": "response.created",
            "response": {
                "id": response_id,
                "object": "response",
                "created_at": int(time.time()),
                "status": "in_progress",
                "model": model,
            },
        },
        {
            "type": "response.output_text.delta",
            "item_id": f"msg_{uuid.uuid4().hex}",
            "output_index": 0,
            "content_index": 0,
            "delta": content,
        },
        {
            "type": "response.completed",
            "response": {
                "id": response_id,
                "object": "response",
                "created_at": int(time.time()),
                "status": "completed",
                "model": model,
                "output_text": content,
            },
        },
    ]
    for event in events:
        yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
    yield "data: [DONE]\n\n"
