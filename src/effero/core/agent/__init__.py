"""The Agent — wires together all Effero subsystems."""

from __future__ import annotations

import logging
import time
from typing import Any

from effero.config import EfferoConfig
from effero.core.callbacks.base import AgentCallback, CallbackList
from effero.core.event_bus import EventBus
from effero.core.fleet.coordinator import FleetCoordinator
from effero.core.memory.episodic import EpisodicMemory
from effero.core.memory.semantic import SemanticMemory
from effero.core.memory.working import WorkingMemory
from effero.core.planner.planner import Planner
from effero.core.router.router import ModelRouter
from effero.safety.approval import ApprovalHandler
from effero.safety.client import SafetyClient
from effero.sdk.skill import SkillRegistry
from effero.sdk.skill import registry as global_registry

logger = logging.getLogger(__name__)


class Agent:
    """The top-level Effero agent.

    Wires together: config, event bus, skills, memory, model router,
    safety client, planner, callbacks, and perception pipelines.
    """

    def __init__(
        self,
        config: EfferoConfig | None = None,
        skills: SkillRegistry | None = None,
        approval_handler: ApprovalHandler | None = None,
        fleet: FleetCoordinator | None = None,
        callbacks: list[AgentCallback] | CallbackList | None = None,
    ) -> None:
        self.config = config or EfferoConfig.load()
        self.event_bus = EventBus()
        self.skills = skills or global_registry
        self.working_memory = WorkingMemory()
        self.episodic_memory = EpisodicMemory()
        self.semantic_memory = SemanticMemory()
        self.router = ModelRouter(self.config.agent.model)
        self.callbacks = callbacks if isinstance(callbacks, CallbackList) else CallbackList(callbacks)
        self.safety: SafetyClient | None = None
        self.safety_daemon: Any = None
        if self.config.safety.enabled:
            self.safety = SafetyClient(
                host=self.config.safety.kernel_host,
                port=self.config.safety.kernel_port,
            )
            if self.config.safety.auto_spawn:
                from effero.safety.daemon import SafetyDaemonManager

                self.safety_daemon = SafetyDaemonManager(
                    host=self.config.safety.kernel_host,
                    port=self.config.safety.kernel_port,
                    policy_path=self.config.safety.policy,
                )

        # External MCP clients
        self.mcp_clients: list[Any] = []

        # Fleet coordinator (opt-in)
        if fleet is not None:
            self.fleet: FleetCoordinator | None = fleet
        elif self.config.fleet.enabled:
            self.fleet = FleetCoordinator(
                default_lease_duration=self.config.fleet.default_lease_duration,
                event_bus=self.event_bus,
            )
        else:
            self.fleet = None

        if approval_handler is not None:
            self.approval_handler = approval_handler
        elif self.config.safety.approval_mode == "auto":
            from effero.safety.approval import AutoApprovalHandler

            self.approval_handler = AutoApprovalHandler(approve_all=True)
        else:
            from effero.safety.approval import ConsoleApprovalHandler

            self.approval_handler = ConsoleApprovalHandler()

        self.planner = Planner(
            router=self.router,
            memory=self.working_memory,
            skills=self.skills,
            safety_client=self.safety,
            approval_handler=self.approval_handler,
            callbacks=self.callbacks,
        )

    async def run(self, instruction: str) -> str:
        """Execute an instruction through the planner loop."""
        logger.info(f"Agent '{self.config.agent.name}' processing: {instruction}")
        t0 = time.perf_counter()
        self.callbacks.on_agent_start(instruction)
        try:
            result = await self.planner.run(instruction)
            elapsed = time.perf_counter() - t0
            self.callbacks.on_agent_finish(result, elapsed)
            # Record to episodic memory
            self.episodic_memory.record(
                "interaction",
                {
                    "instruction": instruction,
                    "response": result,
                },
            )
            return result
        except Exception as e:
            self.callbacks.on_agent_error(e)
            raise

    async def chat(self, message: str) -> str:
        """Single-turn chat interface."""
        return await self.run(message)

    async def start(self) -> None:
        """Start background services: Safety daemon, MQTT broker, MCP tools, and builtins."""
        # 1. Start Safety Kernel Daemon if auto-spawn is enabled
        if self.safety_daemon:
            try:
                await self.safety_daemon.ensure_running()
            except Exception as e:
                logger.warning(f"Safety daemon auto-spawn check failed: {e}")

        # 2. Connect SafetyClient
        if self.safety:
            try:
                await self.safety.connect()
                logger.info("Connected to safety kernel")
            except (ConnectionRefusedError, OSError) as e:
                logger.warning(f"Safety kernel not running ({e}) — operating without guardrails")
                self.safety = None
                self.planner.safety = None

        # 3. Initialize & connect IoT MQTT client if configured
        if self.config.iot.enabled and self.config.iot.auto_connect:
            try:
                from effero.adapters.mqtt_matter.client import get_default_client

                mqtt_client = get_default_client()
                mqtt_client.broker_host = self.config.iot.broker_host
                mqtt_client.broker_port = self.config.iot.broker_port
                mqtt_client.username = self.config.iot.username
                mqtt_client.password = self.config.iot.password
                await mqtt_client.connect()
                logger.info(f"Connected to IoT MQTT broker at {mqtt_client.broker_host}:{mqtt_client.broker_port}")
            except Exception as e:
                logger.warning(f"Could not connect to MQTT broker ({e}) — running in local state mode")

        # 4. Load external MCP servers if configured
        if self.config.mcp_servers:
            from effero.protocols.mcp_client import MCPClient

            for mcp_cfg in self.config.mcp_servers:
                try:
                    client = MCPClient(
                        name=mcp_cfg.name,
                        command=mcp_cfg.command,
                        args=mcp_cfg.args,
                        env=mcp_cfg.env,
                        url=mcp_cfg.url,
                        default_safety_class=mcp_cfg.default_safety_class,
                    )
                    await client.connect()
                    await client.list_tools()
                    mounted = client.mount_tools(self.skills)
                    self.mcp_clients.append(client)
                    logger.info(f"Mounted {len(mounted)} tools from external MCP server '{mcp_cfg.name}'")
                except Exception as e:
                    logger.error(f"Failed to mount MCP server '{mcp_cfg.name}': {e}")

        # 5. Load built-in skills
        self._load_builtin_skills()

        logger.info(f"Agent '{self.config.agent.name}' started with {len(self.skills.list())} skills")

    async def stop(self) -> None:
        """Graceful shutdown of safety client, external MCP servers, and background daemons."""
        for client in self.mcp_clients:
            try:
                await client.close()
            except Exception:
                pass
        self.mcp_clients.clear()

        if self.config.iot.enabled:
            try:
                from effero.adapters.mqtt_matter.client import get_default_client

                await get_default_client().disconnect()
            except Exception:
                pass

        if self.safety:
            await self.safety.close()

        if self.safety_daemon:
            await self.safety_daemon.stop()

        logger.info(f"Agent '{self.config.agent.name}' stopped")

    def _load_builtin_skills(self) -> None:
        """Import built-in skill modules to trigger @skill registration."""
        import importlib

        from effero.sdk import BUILTIN_SKILL_MODULES

        for mod_name in BUILTIN_SKILL_MODULES:
            try:
                importlib.import_module(mod_name)
            except ImportError as e:
                logger.debug(f"Could not load skill module {mod_name}: {e}")

    def available_skills(self) -> list[str]:
        """List names of all registered skills."""
        return list(self.skills.list())
