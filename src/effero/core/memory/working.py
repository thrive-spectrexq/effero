"""Working memory module for Effero."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class WorkingMemory:
    max_messages: int = 100
    messages: list[dict[str, Any]] = field(default_factory=list)

    def add_message(self, role: str, content: str, **kwargs: Any) -> None:
        msg = {"role": role, "content": content}
        msg.update(kwargs)
        self.messages.append(msg)
        self._trim()

    def add_tool_result(self, tool_call_id: str, name: str, result: str) -> None:
        msg = {
            "role": "tool",
            "tool_call_id": tool_call_id,
            "name": name,
            "content": result,
        }
        self.messages.append(msg)
        self._trim()

    def get_context(self) -> list[dict[str, Any]]:
        return list(self.messages)

    def clear(self) -> None:
        self.messages.clear()

    def to_dict(self) -> dict[str, Any]:
        return {"messages": self.messages}

    def _trim(self) -> None:
        if len(self.messages) <= self.max_messages:
            return

        system_msgs = [m for m in self.messages if m.get("role") == "system"]
        other_msgs = [m for m in self.messages if m.get("role") != "system"]

        num_to_keep = self.max_messages - len(system_msgs)
        if num_to_keep > 0:
            other_msgs = other_msgs[-num_to_keep:]
        else:
            other_msgs = []

        self.messages = system_msgs + other_msgs
