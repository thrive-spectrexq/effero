"""Planner — the plan/act/observe/replan loop."""

from __future__ import annotations

import json
import logging
import time
from typing import TYPE_CHECKING, Any

from effero.core.callbacks.base import CallbackList

if TYPE_CHECKING:
    from effero.core.memory.working import WorkingMemory
    from effero.core.router.base import LLMBackend
    from effero.core.router.router import ModelRouter
    from effero.safety.approval import ApprovalHandler
    from effero.safety.client import SafetyClient
    from effero.sdk.skill import SkillRegistry

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are Effero, an AI agent that can perceive, reason, and act
in both the digital and physical world.

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

    def __init__(
        self,
        router: ModelRouter | LLMBackend,
        memory: WorkingMemory,
        skills: SkillRegistry,
        safety_client: SafetyClient | None = None,
        approval_handler: ApprovalHandler | None = None,
        callbacks: CallbackList | None = None,
        require_approval_for: list[str] | None = None,
        max_iterations: int = 10,
    ) -> None:
        self.router = router
        self.memory = memory
        self.skills = skills
        self.safety = safety_client  # SafetyClient or None
        self.approval_handler = approval_handler  # ApprovalHandler or None
        self.callbacks = callbacks or CallbackList()
        self.require_approval_for = require_approval_for or []
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
            self.callbacks.on_llm_response(response)
            self.callbacks.on_plan_generated(response)

            # If LLM responded with text and no tool calls, we're done
            if response.content and not response.tool_calls:
                self.memory.add_message("assistant", response.content)
                return response.content

            if response.tool_calls:
                # Record assistant message with tool calls
                self.memory.add_message(
                    "assistant",
                    response.content or "",
                    tool_calls=[
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {"name": tc.name, "arguments": json.dumps(tc.arguments)},
                        }
                        for tc in response.tool_calls
                    ],
                )
                # Execute each tool call
                for tc in response.tool_calls:
                    result = await self._execute_skill(tc.name, tc.arguments)
                    self.memory.add_tool_result(tc.id, tc.name, result)
            else:
                return response.content or "(no response)"

        return "(max planning iterations reached)"

    async def _execute_skill(self, name: str, args: dict[str, Any]) -> Any:
        """Execute a skill, checking safety and human approval first."""
        from effero.sdk.skill import SafetyClass

        # Find skill spec
        try:
            skill_spec = self.skills.get(name)
        except KeyError:
            return {"error": f"Unknown skill: {name}"}

        needs_approval = (
            getattr(skill_spec, "safety_class", None) == SafetyClass.ACT_WITH_APPROVAL
            or getattr(skill_spec, "safety_class", None) == "act_with_approval"
        )
        approval_reason = f"Skill '{name}' has declared safety class {getattr(skill_spec, 'safety_class', 'unknown')}"

        if not needs_approval and self.require_approval_for:
            import fnmatch

            for pattern in self.require_approval_for:
                if fnmatch.fnmatch(name, pattern) or name.startswith(pattern.rstrip("*")):
                    needs_approval = True
                    approval_reason = f"Skill '{name}' matches require_approval_for pattern '{pattern}'"
                    break

        # Safety kernel check
        if self.safety and self.safety.connected:
            try:
                decision = await self.safety.check_action(name)
                action = decision.get("decision", "allow")
                if action == "deny":
                    reason = decision.get("reason", "Policy denied this action")
                    self.callbacks.on_safety_check(name, args, approved=False, reason=reason)
                    return {"error": f"Safety policy denied: {reason}"}
                elif action == "require_approval":
                    needs_approval = True
                    approval_reason = decision.get("reason", approval_reason)
            except Exception as e:
                logger.warning(f"Safety check failed: {e} — proceeding with caution")

        # Interactive Human-In-The-Loop Approval check
        if needs_approval and self.approval_handler:
            from effero.safety.approval import ApprovalRequest

            approval_req = ApprovalRequest(
                skill_name=name,
                arguments=args,
                reason=approval_reason,
                safety_class=str(getattr(skill_spec, "safety_class", "act_with_approval")),
            )
            approval_res = await self.approval_handler.request_approval(approval_req)
            if not approval_res.approved:
                logger.warning(f"Skill execution denied by operator: {name}")
                reason = approval_res.comment or "Permission denied by operator"
                self.callbacks.on_safety_check(name, args, approved=False, reason=reason)
                return {"error": f"Action unauthorized by human operator: {reason}"}

        self.callbacks.on_safety_check(name, args, approved=True, reason=None)
        self.callbacks.on_skill_before_execute(name, args)
        t0 = time.perf_counter()
        try:
            result = skill_spec(**args)
            if hasattr(result, "__await__"):
                result = await result
            elapsed = time.perf_counter() - t0
            self.callbacks.on_skill_after_execute(name, result, elapsed)
            return result
        except Exception as e:
            elapsed = time.perf_counter() - t0
            self.callbacks.on_skill_after_execute(name, {"error": str(e)}, elapsed)
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

            tools.append(
                {
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
                }
            )
        return tools
