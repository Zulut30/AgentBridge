from fastapi import FastAPI

from app.api.openai_compat import router
from app.config import get_settings
from app.executors.base import command_is_available


app = FastAPI(title="AgentBridge", version="0.1.0")
app.include_router(router)


@app.get("/health")
async def health() -> dict:
    settings = get_settings()
    return {
        "status": "ok",
        "project_root": str(settings.project_root_path),
        "agents": {
            "grok": settings.agents.grok.enabled
            and command_is_available(settings.agents.grok.command),
            "codex": settings.agents.codex.enabled
            and command_is_available(settings.agents.codex.command),
        },
    }

