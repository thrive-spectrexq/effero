"""Planner — the plan/act/observe/replan loop."""
from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are Effero, an AI agent that can perceive, reason, and act in both the digital and physical world.

You have access to skills (tools) that let you interact with computers, IoT devices, robots, and sensors.
When the user asks you to do something:
1. Reason about what skills you need
2. Call the appropriate skills using the provided tools
3. Observe the results
4. Report back or continue planning

Always explain your reasoning before acting. If a skill requires human approval, say so.
Be cautious with physical actions — prefer to describe your plan before executing."""


class Planner:
    """LLM-driven plan/act/observe loop."""

    def __init__(self, router, memory, skills, safety_client=None, max_iterations: int = 10) -> None:
        self.router = router  # ModelRouter
        self.memory = memory  # WorkingMemory
        self.skills = skills  # SkillRegistry
        self.safety = safety_client  # SafetyClient or None
        self.max_iterations = max_iterations

    async def run(self, instruction: str) -> str:
        """Execute a plan/act/observe loop for the given instruction."""
        from effero.core.router.base import LLMRequest
        
        self.memory.add_message("system", SYSTEM_PROMPT)
        self.memory.add_message("user", instruction)
        tools = self._get_tools_schema()

        for i in range(self.max_iterations):
            logger.info(f"Planning iteration {i + 1}/{self.max_iterations}")
            
            request = LLMRequest(
                messages=self.memory.get_context(),
                tools=tools if tools else None,
            )
            response = await self.router.complete(request)

            # If LLM responded with text and no tool calls, we're done
            if response.content and not response.tool_calls:
                self.memory.add_message("assistant", response.content)
                return response.content

            if response.tool_calls:
                # Record assistant message with tool calls
                self.memory.add_message(
                    "assistant", 
                    response.content or "",
                    tool_calls=[{"id": tc.id, "type": "function", "function": {"name": tc.name, "arguments": json.dumps(tc.arguments)}} for tc in response.tool_calls]
                )
                # Execute each tool call
                for tc in response.tool_calls:
                    result = await self._execute_skill(tc.name, tc.arguments)
                    self.memory.add_tool_result(tc.id, tc.name, result)
            else:
                return response.content or "(no response)"

        return "(max planning iterations reached)"

    async def _execute_skill(self, name: str, args: dict[str, Any]) -> Any:
        """Execute a skill, checking safety first."""
        # Safety check
        if self.safety and self.safety.connected:
            try:
                decision = await self.safety.check_action(name)
                action = decision.get("decision", "allow")
                if action == "deny":
                    reason = decision.get("reason", "Policy denied this action")
                    return {"error": f"Safety policy denied: {reason}"}
                elif action == "require_approval":
                    reason = decision.get("reason", "Requires approval")
                    logger.warning(f"Skill '{name}' requires approval: {reason}")
                    # In v0.1, log and proceed. v0.2 will add interactive approval.
            except Exception as e:
                logger.warning(f"Safety check failed: {e} — proceeding with caution")

        # Find and execute skill
        try:
            skill_spec = self.skills.get(name)
        except KeyError:
            return {"error": f"Unknown skill: {name}"}
            
        try:
            result = skill_spec(**args)
            if hasattr(result, "__await__"):
                result = await result
            return result
        except Exception as e:
            logger.error(f"Skill {name} failed: {e}")
            return {"error": str(e)}

    def _get_tools_schema(self) -> list[dict]:
        """Build OpenAI-format tool schemas from registered skills."""
        import inspect
        tools = []
        for s_name in self.skills.list():
            s = self.skills.get(s_name)
            properties = {}
            required = []
            for pname, param in s.signature.parameters.items():
                prop: dict[str, Any] = {"type": "string"}
                if param.annotation != inspect.Parameter.empty:
                    ann = param.annotation
                    if ann is str or ann == "str":
                        prop = {"type": "string"}
                    elif ann is int or ann == "int":
                        prop = {"type": "integer"}
                    elif ann is float or ann == "float":
                        prop = {"type": "number"}
                    elif ann is bool or ann == "bool":
                        prop = {"type": "boolean"}
                properties[pname] = prop
                if param.default is inspect.Parameter.empty:
                    required.append(pname)
            
            tools.append({
                "type": "function",
                "function": {
                    "name": s.name,
                    "description": s.description or "",
                    "parameters": {
                        "type": "object",
                        "properties": properties,
                        "required": required,
                    },
                },
            })
        return tools
