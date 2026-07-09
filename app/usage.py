import json
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

from app.config import AgentBridgeConfig


class UsageTracker:
    def __init__(self, settings: AgentBridgeConfig) -> None:
        self.settings = settings

    def record(self, event: dict[str, Any]) -> None:
        if not self.settings.usage.enabled:
            return

        path = self.settings.usage_log_path
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            **event,
        }
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n")

    def summary(self) -> dict[str, Any]:
        path = self.settings.usage_log_path
        today = datetime.now(timezone.utc).date().isoformat()
        totals: dict[str, Any] = {
            "today": today,
            "requests_today": 0,
            "seconds_today": 0.0,
            "by_agent": defaultdict(lambda: {"requests": 0, "seconds": 0.0}),
            "by_model": defaultdict(lambda: {"requests": 0, "seconds": 0.0}),
            "limits": {
                "daily_request_limit": self.settings.usage.daily_request_limit,
                "daily_seconds_limit": self.settings.usage.daily_seconds_limit,
            },
            "log_path": str(path),
        }

        if not path.exists():
            totals["by_agent"] = {}
            totals["by_model"] = {}
            totals["remaining"] = self._remaining(totals)
            return totals

        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue
                timestamp = str(event.get("timestamp", ""))
                if not timestamp.startswith(today):
                    continue
                duration = float(event.get("duration_seconds") or 0)
                agent = str(event.get("selected_agent") or "unknown")
                model = str(event.get("requested_model") or "unknown")
                totals["requests_today"] += 1
                totals["seconds_today"] += duration
                totals["by_agent"][agent]["requests"] += 1
                totals["by_agent"][agent]["seconds"] += duration
                totals["by_model"][model]["requests"] += 1
                totals["by_model"][model]["seconds"] += duration

        totals["seconds_today"] = round(totals["seconds_today"], 3)
        totals["by_agent"] = {
            key: {"requests": value["requests"], "seconds": round(value["seconds"], 3)}
            for key, value in sorted(totals["by_agent"].items())
        }
        totals["by_model"] = {
            key: {"requests": value["requests"], "seconds": round(value["seconds"], 3)}
            for key, value in sorted(totals["by_model"].items())
        }
        totals["remaining"] = self._remaining(totals)
        return totals

    def _remaining(self, totals: dict[str, Any]) -> dict[str, int | float | None]:
        request_limit = self.settings.usage.daily_request_limit
        seconds_limit = self.settings.usage.daily_seconds_limit
        return {
            "requests": None if request_limit is None else max(0, request_limit - int(totals["requests_today"])),
            "seconds": None
            if seconds_limit is None
            else max(0.0, round(seconds_limit - float(totals["seconds_today"]), 3)),
        }

