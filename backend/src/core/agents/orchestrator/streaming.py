"""Compatibility adapter from graph events to the existing NDJSON API contract."""

from __future__ import annotations

from typing import Any

from core.models.run_state import ClaimAnalysisRunState


class StreamingProgressCompatibilityAdapter:
    def __init__(self) -> None:
        self._index = 0
        self._total = 0

    def adapt(self, event: dict[str, Any], state: ClaimAnalysisRunState) -> list[dict[str, Any]]:
        kind = event["kind"]
        if kind == "plan_completed":
            self._total = len(event["tasks"]) + 1
            response = event["responses"][0]
            return [
                {
                    "event": "analysis_started",
                    "total_agents": self._total,
                    "message": "Bounded agent analysis started.",
                    "agent_response": response.model_dump(mode="json"),
                    "planned_agents": event["planned_agents"],
                },
                self._completed(response, message=f"{response.agent_name} completed."),
            ]
        if kind == "task_started":
            task = event["task"]
            if task.task_type.value == "plan":
                return []
            self._index += 1
            return [
                {
                    "event": "agent_started",
                    "agent_name": task.agent_name,
                    "index": self._index,
                    "total_agents": self._total,
                    "message": f"{task.agent_name} started.",
                    "task_id": task.task_id,
                    "selection_reason": task.selection_reason,
                }
            ]
        if kind == "task_completed":
            return [
                self._completed(
                    response,
                    message=f"{response.agent_name} completed task {event['task'].task_id}.",
                )
                for response in event["responses"]
            ]
        if kind == "stopped":
            # Stop metadata is carried on the compatible analysis_completed result.
            return []
        if kind == "failed":
            return []
        return []

    def _completed(self, response, *, message: str) -> dict[str, Any]:
        return {
            "event": "agent_completed",
            "agent_name": response.agent_name,
            "index": self._index,
            "total_agents": self._total,
            "message": message,
            "agent_response": response.model_dump(mode="json"),
        }


__all__ = ["StreamingProgressCompatibilityAdapter"]
