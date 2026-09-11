"""The Agent — wires together all Effero subsystems."""

from __future__ import annotations

import asyncio
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
        self._heartbeat_task: asyncio.Task | None = None
        self.server_api_key: str | None = None
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
        self.ros2_bridge: Any | None = None

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

        def _agent_facts_provider(skill_name: str, args: dict[str, Any]) -> dict[str, Any]:
            facts: dict[str, Any] = {}
            if hasattr(self, "working_memory") and self.working_memory.telemetry_streams:
                for m in self.working_memory.telemetry_streams:
                    v = self.working_memory.get_latest_metric(m)
                    if isinstance(v, (int, float, bool)):
                        facts[m] = v
            try:
                from effero.skills.robotics.navigate import _nav_controller

                facts["robot_x"] = _nav_controller.pose.x
                facts["robot_y"] = _nav_controller.pose.y
                facts["robot_linear_velocity"] = _nav_controller.linear_velocity_mps
                facts["robot_emergency_stopped"] = _nav_controller.emergency_stopped
            except (ImportError, AttributeError):
                pass
            return facts

        self.planner = Planner(
            router=self.router,
            memory=self.working_memory,
            skills=self.skills,
            safety_client=self.safety,
            approval_handler=self.approval_handler,
            callbacks=self.callbacks,
            require_approval_for=self.config.safety.require_approval_for,
            facts_provider=_agent_facts_provider,
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

        # 2. Connect SafetyClient and spawn heartbeat task
        if self.safety:
            try:
                await self.safety.connect()
                logger.info("Connected to safety kernel")
                if self.config.safety.heartbeat_enabled:
                    self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())
            except (ConnectionRefusedError, OSError) as e:
                logger.warning(f"Safety kernel not running ({e}) — operating without guardrails")
                self.safety = None
                self.planner.safety = None

        # 3. Initialize & connect IoT MQTT client if configured
        if self.config.iot.enabled and self.config.iot.auto_connect:
            try:
                from effero.adapters.mqtt_matter.client import get_default_client

                mqtt_client = get_default_client(self.config.iot)
                mqtt_client.broker_host = self.config.iot.broker_host
                mqtt_client.broker_port = self.config.iot.broker_port
                mqtt_client.username = self.config.iot.username
                mqtt_client.password = self.config.iot.password
                mqtt_client.use_tls = self.config.iot.use_tls
                mqtt_client.ca_certs = self.config.iot.ca_certs
                mqtt_client.certfile = self.config.iot.certfile
                mqtt_client.keyfile = self.config.iot.keyfile
                mqtt_client.tls_insecure = self.config.iot.tls_insecure
                await mqtt_client.connect()
                logger.info(f"Connected to IoT MQTT broker at {mqtt_client.broker_host}:{mqtt_client.broker_port}")
            except Exception as e:
                logger.warning(f"Could not connect to MQTT broker ({e}) — running in local state mode")

        # 4. Initialize ROS 2 bridge if configured
        if self.config.robotics.ros2.enabled:
            try:
                from effero.adapters.ros2.bridge import ROS2Bridge
                from effero.skills.robotics.arm import _arm_controller
                from effero.skills.robotics.navigate import _nav_controller

                self.ros2_bridge = ROS2Bridge(node_name=self.config.robotics.ros2.node_name)
                try:
                    await self.ros2_bridge.connect(
                        host=self.config.robotics.ros2.transport_host,
                        port=self.config.robotics.ros2.transport_port,
                    )
                except Exception as e:
                    logger.info(f"ROS 2 socket bridge offline ({e}) — operating in in-memory CDR mode")

                if self.config.robotics.ros2.auto_publish_arm_trajectory:
                    _arm_controller.attach_ros2_bridge(self.ros2_bridge)
                if self.config.robotics.ros2.auto_publish_nav_cmd_vel:
                    _nav_controller.attach_ros2_bridge(self.ros2_bridge)
                logger.info("Initialized ROS 2 bridge integration with robotics skills")
            except Exception as e:
                logger.warning(f"Failed to initialize ROS 2 bridge: {e}")

        # 5. Load external MCP servers if configured
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

        # 6. Load built-in skills
        self._load_builtin_skills()

        # 7. Apply skill configuration filtering if specified in effero.yaml
        if self.config.skills:
            import fnmatch

            filtered_reg = SkillRegistry()
            all_names = list(self.skills.list())
            for pattern in self.config.skills:
                matches = 0
                for skill_name in all_names:
                    if fnmatch.fnmatch(skill_name, pattern) or skill_name.startswith(pattern.rstrip("*")):
                        filtered_reg.register(self.skills.get(skill_name))
                        matches += 1
                if matches == 0:
                    logger.warning(f"Configured skill pattern '{pattern}' matched 0 registered skills.")
            self.skills = filtered_reg
            self.planner.skills = filtered_reg

        logger.info(f"Agent '{self.config.agent.name}' started with {len(self.skills.list())} skills")

    async def stop(self) -> None:
        """Graceful shutdown of safety client, external MCP servers, and background daemons."""
        for client in self.mcp_clients:
            try:
                await client.close()
            except Exception:
                pass
        self.mcp_clients.clear()

        if self.ros2_bridge:
            try:
                await self.ros2_bridge.disconnect()
            except Exception:
                pass
            self.ros2_bridge = None
            try:
                from effero.skills.robotics.arm import _arm_controller
                from effero.skills.robotics.navigate import _nav_controller

                _arm_controller.attach_ros2_bridge(None)
                _nav_controller.attach_ros2_bridge(None)
            except Exception:
                pass

        if self.config.iot.enabled:
            try:
                from effero.adapters.mqtt_matter.client import get_default_client

                await get_default_client().disconnect()
            except Exception:
                pass

        if self._heartbeat_task:
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass
            self._heartbeat_task = None

        if self.safety:
            await self.safety.close()

        if self.safety_daemon:
            await self.safety_daemon.stop()

        logger.info(f"Agent '{self.config.agent.name}' stopped")

    async def _heartbeat_loop(self) -> None:
        """Background task emitting heartbeats to safety kernel to keep deadman watchdog alive."""
        interval = max(0.05, self.config.safety.heartbeat_interval)
        while True:
            try:
                await asyncio.sleep(interval)
                if self.safety and self.safety.connected:
                    await self.safety.send_heartbeat()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.debug(f"Heartbeat error: {e}")

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
