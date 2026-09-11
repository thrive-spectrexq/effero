# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.11] - 2026-09-11

### Added
- **Embodied AI & Agentic Benchmark Suite (`effero.evaluation`)**:
  - Implemented `BenchmarkRunner`, `BenchmarkScenario`, `BenchmarkReport`, `EvaluationMetric`, and `ScenarioResult` for deterministic regression testing and continuous agent evaluation.
  - Added comprehensive benchmark scenarios in `effero.evaluation.scenarios`:
    - `warehouse_pallet_pick_place`: Multi-stage mobile manipulation verifying Cartesian bounds, pick-and-place accuracy, and zero collision violations.
    - `office_waypoint_transit`: Differential drive mobile base navigation and target coordinate convergence.
    - `smart_climate_regulation`: Autonomous telemetry-driven thermostat regulation triggered by room occupancy.
  - Implemented automated report generation with pass rates, execution durations, total estimated token costs, tool call distributions, and Markdown export (`report.to_markdown()`).
- **Frontier LLM Unit Economics & Token Pricing (`core.callbacks.telemetry`)**:
  - Expanded `TelemetryCallback._estimate_cost` to track unit economics across modern frontier models: `gpt-4.5`, `o1-mini`, `o3-mini`, `claude-3-7-sonnet`, and `gemini-2.0-flash`.
  - Continuous calculation of cost-per-scenario and aggregate evaluation spend during benchmark runs.
- **Adaptive Planner Execution Loop & Deliberative Reflection (`core.planner`)**:
  - Added dynamic execution modes in `Planner`:
    - Fast-path execution with automatic temperature reduction during consecutive successful tool invocations.
    - Automatic deliberative self-healing reflection prompt injection upon encountering tool execution errors.
- **Desktop UI Element Inspection & Tree Enumeration (`skills.computer_use.backends`)**:
  - Added `UIElementInfo` dataclass capturing handle, parent handle, window class name, text, and bounding geometry.
  - Added `DesktopBackend.list_elements(hwnd)` with native Win32 child window traversal (`EnumChildWindows`, `GetClassNameW`) and virtual simulation support in `HeadlessDesktopBackend` and `LinuxDesktopBackend`.

### Fixed
- **Eager Skill Loading on Offline Evaluation Agents (`core.agent`)**:
  - Configured `Agent.__init__` to eagerly populate built-in skills into the local registry so evaluation and benchmark agents function offline without requiring full network or daemon startup.
- **Robotics Skill Registry Public Export (`skills.robotics`)**:
  - Added `set_velocity` to `effero.skills.robotics.__all__`, achieving 100% compliance in `scripts/lint_skills.py`.

## [0.1.10] - 2026-09-11

### Added
- **ROS 2 Adapter Live Integration with Robotics Skills (`adapters.ros2`, `skills.robotics`)**:
  - Implemented OMG Common Data Representation (CDR) wire serialization and deserialization for `geometry_msgs/Twist` and `Vector3`.
  - Added `publish_cmd_vel` to `ROS2Bridge` supporting length-prefixed TCP streaming and in-memory CDR packet framing.
  - Wired `ArmController` to automatically publish `trajectory_msgs/JointTrajectory` and `ActuatorCommand` to active ROS 2 bridge.
  - Wired `NavigationController` to automatically publish `geometry_msgs/Twist` cmd_vel during transit, DWA obstacle avoidance, and emergency stops.
  - Added `@skill` entry point `robotics.navigate.set_velocity` for continuous planar velocity control.
  - Added `RoboticsConfig` and `ROS2Config` to `EfferoConfig` with automatic bridge initialization and clean shutdown in `Agent.start()` and `Agent.stop()`.
- **Mobile Manipulator End-to-End Example (`examples/mobile-manipulator/`)**:
  - Created runnable mobile manipulation application coordinating base navigation, visual target localization, and arm pick-and-place with live ROS 2 telemetry.
  - Added `main.py` supporting both autonomous `--scenario` mission execution and interactive natural language REPL.
  - Added architecture documentation and quickstart in `examples/mobile-manipulator/README.md`.
- **Robotics & Agent Performance Benchmark Suite (`benchmarks/`)**:
  - Added `bench_planner.py`: Agent planner step latency with tool dispatch and prompt generation.
  - Added `bench_a_star.py`: A* grid path planning benchmark over 100x100 map with barrier obstacles and line-of-sight smoothing.
  - Added `bench_dwa.py`: Dynamic Window Approach velocity search and candidate obstacle checking.
  - Added `bench_cdr.py`: OMG CDR serialization and deserialization throughput (50-point trajectories, joint states, and twist messages).
  - Added fallback benchmark fixture in `benchmarks/conftest.py` ensuring benchmarks execute reliably across all test runners.
- **Hardware Compatibility Matrix Verification (`docs/compatibility.md`)**:
  - Measured and published verified footprint metrics for Python 3.13 on x86-64 desktop (~1.6s warm start, 45.9 MB idle RAM).

## [0.1.9] - 2026-09-10


### Added
- **Linux & Headless Desktop Automation Backend (`computer_use.desktop`)**:
  - Implemented `LinuxDesktopBackend` leveraging `xdotool` and `wmctrl` for native Linux X11 window management and mouse/keyboard event dispatch.
  - Implemented `HeadlessDesktopBackend` for deterministic virtual testing and headless CI/Docker test execution.
  - Added OS-aware dynamic backend selection (`get_default_desktop_backend()`).
- **Openpilot-Inspired Safety Watchdog & Heartbeat Monitor (`safety.watchdog`)**:
  - Embedded high-frequency daemon watchdog into the Rust Safety Kernel with strict configurable timeout triggers.
  - Added `Watchdog` monitoring, auto-tripping emergency e-stop upon missed agent heartbeat deadlines.
  - Added heartbeat loop in Python `Agent` execution cycle.
- **Isaac Lab-Style Closed-Loop Policy Evaluation Runner (`robotics.policy`)**:
  - Added `PolicyRunner` and `BasePolicy` with fixed step sizes, observation normalization, action clipping, and trajectory recording.
  - Registered `@skill` entry points `robotics.policy.step` and `robotics.policy.run_trajectory`.
- **Deterministic Sensor & Event Replay Harness (`core.replay`)**:
  - Added JSONL-based recording and playback for sensor telemetry and skill interactions.
  - Implemented CLI subcommands `effero record` and `effero replay`.

### Fixed
- **Virtual Key Validation on Non-Windows / Headless Backends**:
  - Enforced canonical virtual key validation across `HeadlessDesktopBackend` and `LinuxDesktopBackend`, ensuring unrecognized key strings consistently raise `ValueError("Unsupported virtual key ...")` across all operating systems.
- **Mypy Static Typing Cleanliness**:
  - Fixed parameter type annotations on `Agent.__init__`, `ReplayRecorder`, and test planners for 100% clean type checks across 164 source files.

## [0.1.8] - 2026-09-09

### Added
- **Safety Kernel Live Telemetry & Environment Facts Wiring**:
  - Connected `Planner._execute_skill()` and `Agent` to feed live robot telemetry (`robot_x`, `robot_y`, `robot_linear_velocity`, `robot_emergency_stopped`), battery levels, nearest person proximity metrics, and invocation parameters into `SafetyClient.check_action()`.
  - Enabled dynamic safety rule enforcement based on actual physical runtime state.
- **REST & WebSocket API Server Authentication**:
  - Implemented token authentication (`Authorization: Bearer <key>` or `X-API-Key: <key>`) across sensitive endpoints (`/v1/chat`, `/v1/skills/invoke`, `/v1/approvals/*`, `/v1/memory/*`, `/v1/tasks/*`, and `/ws/*`).
  - Hardened Human-In-The-Loop approval resolution to prevent unauthorized confirmation of restricted physical/digital actions.
- **Spec-Compliant CORS Hardening**:
  - Enforced CORS specification compliance (disallowed `allow_credentials=True` with wildcard `*` origins; enabled credentialed requests only for explicit configured origins).
- **Shell Command Guardrails (`computer_use.shell`)**:
  - Added pattern detection against destructive system commands (recursive root deletion, fork bombs, disk wiping, reboot/shutdown commands).
  - Added command prefix allowlist filtering via argument and `EFFERO_SHELL_ALLOWLIST` environment variable.
- **IoT MQTT TLS Encryption Support (`adapters.mqtt_matter`)**:
  - Added native `ssl.SSLContext` negotiation, custom CA certificate loading, and mutual TLS certificate support to `MQTTAdapter`.
  - Exposed TLS configuration in `IoTConfig` and `effero.yaml`.
- **Configuration Security Auditing**:
  - Added `EfferoConfig.validate_security()` to audit configurations and log security warnings for missing API keys, plaintext MQTT, or unverified certificates.
  - Enforced `0o600` restrictive file permissions when saving config files.
- **Python 3.13 CI Support**:
  - Added Python 3.13 to the GitHub Actions CI matrix alongside Python 3.11 and 3.12.

### Fixed
- Fixed hanging condition in MQTT connection test under Python 3.11/3.13 by verifying SSL context creation deterministically without orphan background reader tasks.
- Cleaned up formatting and import ordering across the codebase with `ruff format`.

## [0.1.7] - 2026-09-09

### Added
- **Graduated Human-In-The-Loop (HITL) Mode (`safety.approval`)**:
  - Enhanced `AutoApprovalHandler(graduated=True)` to autonomously permit `READ_ONLY` and `ACT_AUTONOMOUS` skills while strictly gating `ACT_WITH_APPROVAL` and `ACT_RESTRICTED` actions for interactive human confirmation.
  - Added async approval resolution support to `Agent` execution cycle.
- **Unified Example Runner Architecture (`examples/runner.py`)**:
  - Consolidated duplicate example launchers (`examples/local-smart-home/main.py` and `examples/desktop-copilot/main.py`) into a reusable `run_agent_loop(config_path)` helper with full CLI argument support.
- **CI Dependency Lock Freshness Enforcement (`scripts/check_lock_freshness.py`)**:
  - Added automated verification in CI ensuring `requirements-dev.lock` stays strictly synchronized with root dependencies in `pyproject.toml`.
- **Rust Edge MCP Toolchain Verification**:
  - Documented and verified Rust 1.85+ toolchain requirement (`rust-version = "1.85"` in `crates/effero-edge-mcp/Cargo.toml`).
- **Test Hardening & Zero-Mock Coverage Expansion (87% total coverage, 370 passing tests)**:
  - Replaced unlisted external mock dependency `respx` with native `httpx.MockTransport` in `tests/test_cloud_api.py`.
  - Added full test coverage for LLM backends (`test_router_anthropic.py`, `test_router_google.py`, `test_router_openai.py`), voice perception, desktop automation, browser skills, IoT sensors/thermostats, and CLI commands.

### Fixed
- Eliminated B904 exception-chaining suppressions and E501 over-length line ignores across codebase (`ignore = []`).
- Cleaned up stale scaffold documentation and comments across safety policies, example configs, and `README.md`.

## [0.1.6] - 2026-09-09

### Added
- **On-Device Inference & Confidence-Based Hybrid Cloud Handoff (Cactus Integration)**:
  - Native `cactus` provider support in `ModelRouter` pointing to local high-performance runtime (`http://127.0.0.1:8080/v1`).
  - Added `min_confidence` and `hybrid_cloud_fallback` options to `ModelConfig` for sub-100ms on-device reasoning with automatic escalation to cloud frontier models (GPT-4o, Claude) when local confidence falls below threshold.
  - Documented INT4/INT8 quantization footprints and latency profiles in `docs/compatibility.md`.
- **Google AI Edge LiteRT-LM In-Process Backend**:
  - In-process `LiteRTLMBackend` executing `.litertlm` container models via `litert-lm-api` with zero daemon overhead.
  - Direct hardware accelerator selection (`device: auto | cpu | gpu | npu`) supporting Raspberry Pi 5 AI HAT (Hailo-8/Coral), Jetson, and mobile edge NPUs.
  - Optional dependency extra: `pip install effero[litert]`.
- **Contract-Compliant Test Infrastructure & Code Quality**:
  - Replaced ad-hoc mock classes and aliases with `ScriptedBackend` supporting sequential responses, dynamic generators, failure modes, and availability tracking.
  - Hardened `MCPClient` protocol handling: catches `isError: True`, preserves JSON-RPC error details on HTTP failures, and avoids leaking pending futures.
  - Dynamic `__version__` propagation in MCP handshake payloads.

## [0.1.5] - 2026-09-08

### Added
- **Documentation & Professional Engineering Suite**:
  - Full MkDocs Material documentation site published to [GitHub Pages](https://thrive-spectrexq.github.io/effero/).
  - Auto-generated Skill Catalog indexing all 45 registered skills across robotics, IoT, perception, and computer use.
  - Public API contract specification ([`VERSIONING.md`](VERSIONING.md)) and Single-Maintainer Transparency & Governance policy ([`GOVERNANCE.md`](GOVERNANCE.md)).
  - AI contribution disclosure rules and human review guidelines ([`AI_POLICY.md`](AI_POLICY.md)).
  - Real-world hardware compatibility matrix ([`docs/compatibility.md`](docs/compatibility.md)) for robotics and edge platforms.
  - Reproducible development environment lockfile (`requirements-dev.lock`) and Dependabot automated updates.
  - Skill Registry validation linter (`scripts/lint_skills.py`) integrated into CI.
  - Real-time robotics benchmarks (`benchmarks/`) covering EKF state estimation and SE(2)/SE(3) transform compounding.
  - Fixed dead ROADMAP documentation references and added CI/coverage/PyPI release badges.

## [0.1.4] - 2026-09-08

### Added
- **Extended Kalman Filter (EKF) Localization (`skills.robotics.localization.ekf`)**:
  - Full $4 \times 4$ covariance propagation fusing kinematic dead-reckoning motion model with sensor observations.
  - Non-linear range and bearing landmark updates with $J_H$ measurement Jacobian and innovation residual processing.
  - Absolute Cartesian position fix fusion (GPS, UWB, or vision fiducials) with dynamic sensor variance weighting.
  - Continuous 2-sigma spatial uncertainty radius computation reported via real-time telemetry.
  - Exposed via `@skill(name="robotics.navigate.localize_predict")`, `@skill(name="robotics.navigate.localize_landmark")`, and `@skill(name="robotics.navigate.localize_position_fix")`.
- **Pandas-Inspired Time-Series Buffers & Rolling Window Analytics (`core.memory.timeseries`)**:
  - `TimeSeriesRingBuffer`: fixed-capacity chronological buffer with linear numeric interpolation.
  - `RollingWindowView`: `.mean()`, `.min()`, `.max()`, `.std()`, and `.rate_of_change()` over configurable trailing time windows.
  - Seamlessly integrated into `WorkingMemory.rolling_metric(name, seconds)`.
- **Keras & PyTorch-Inspired Lifecycle Callbacks (`core.callbacks`)**:
  - `AgentCallback` base class with default no-op hooks and `CallbackList` managing event dispatch with exception isolation.
  - `TelemetryCallback` computing latency distributions, execution counts, and safety approval tallies.
  - `AuditLogCallback` producing an immutable, append-only audit trail of prompts, planning decisions, safety checks, and tool invocations.
  - Integrated directly into `Agent.run()` and `Planner`.
- **Scikit-learn-Inspired Composable Pipelines (`pipelines`)**:
  - Typed `PipelineStage` and `Pipeline` with UNIX-style pipe chaining operator `|` (`pipeline = stage1 | stage2 | stage3`).
  - Pre-built stages: `FunctionStage` (sync/async callables), `FilterStage` (predicate filtering), `MapStage` (item transformations), and `ParallelBranchStage` (concurrent async execution).
- **NumPy Robotics-Inspired Spatial Transformation Algebra (`skills.robotics.transforms`)**:
  - `Transform2D` ($SE(2)$) and `Transform3D` ($SE(3)$) with matrix multiplication `@` composition.
  - Analytical matrix inversion ($R^T, -R^T t$) with zero numerical drift.
  - Bidirectional point transformations, Euclidean distance, angular distance, and unit quaternion conversions.

### Fixed & Optimized
- **ModelRouter Availability Check Latency ([#1](https://github.com/thrive-spectrexq/effero/issues/1))**:
  - Added TTL availability caching (`availability_cache_ttl=300.0s`) in `ModelRouter`, eliminating redundant network health checks on every completion.
- **EventBus History Trimming ([#2](https://github.com/thrive-spectrexq/effero/issues/2))**:
  - Replaced `list.pop(0)` with `collections.deque(maxlen=max_history)` for bounded $O(1)$ auto-eviction without list reallocations.
- **EventBus Subscriber Pattern Dispatch ([#3](https://github.com/thrive-spectrexq/effero/issues/3))**:
  - Separated exact topic subscriptions ($O(1)$ hash table lookup) and pre-compiled wildcard subscriptions (`re.Pattern`), eliminating per-publish `fnmatch()` overhead.
- **SemanticMemory Vector Search ([#4](https://github.com/thrive-spectrexq/effero/issues/4))**:
  - Added spatial inverted dimension indexing to prune orthogonal vectors across large knowledge bases.
  - Replaced $O(N \log N)$ sorting with `heapq.nlargest` for $O(N \log k)$ top-k extraction.
  - Optimized cosine similarity dot product avoiding intermediate `zip()` allocations.
- **EpisodicMemory Load History ([#5](https://github.com/thrive-spectrexq/effero/issues/5))**:
  - Replaced full file `readlines()` with reverse binary chunk reading (`seek(0, 2)` with 8KB buffers) to bound memory footprint to $O(\text{limit})$.
- **WorkingMemory Trimming Allocations ([#6](https://github.com/thrive-spectrexq/effero/issues/6))**:
  - Optimized `_trim()` by reverse-scanning to collect non-system messages up to `num_to_keep`, eliminating 3 intermediate list allocations and applying in-place slice mutation.


## [0.1.3] - 2026-09-08

### Added
- **2D Occupancy Grid Map (`skills.robotics.grid_map`)**:
  - Discrete spatial rasterization supporting points, bounding boxes, circles, and walls via Bresenham line raycasting.
  - Radial obstacle inflation based on robot physical radius for conservative point-mass navigation clearance.
  - Bidirectional continuous-to-grid coordinate transforms and line-of-sight collision checks.
- **A\* 2D Grid Path Planner (`skills.robotics.planning.a_star`)**:
  - 8-connected grid search with Octile distance heuristic and diagonal corner-cutting prevention.
  - Line-of-sight path smoothing shortcutting intermediate stair-step waypoints into direct flight segments.
  - Integrated into `NavigationController` and exposed via `@skill(name="robotics.navigate.plan_path")`.
- **Dynamic Window Approach (DWA) Local Obstacle Avoidance (`skills.robotics.tracking.dwa`)**:
  - Dynamic window evaluation incorporating hardware limits, acceleration constraints, and prediction horizons.
  - Multi-objective scoring combining target goal alignment, cruising velocity reward, and obstacle clearance cost.
  - Integrated into `NavigationController` and exposed via `@skill(name="robotics.navigate.compute_velocity")`.
- **Pure Pursuit Waypoint Tracking (`skills.robotics.tracking.pure_pursuit`)**:
  - Dynamic lookahead distance proportional to vehicle speed with goal arrival deceleration.
  - Curvature-based differential-drive steering computation with angular velocity clamping.
  - Integrated into `NavigationController` and exposed via `@skill(name="robotics.navigate.track_path")`.

## [0.1.2] - 2026-09-08

### Added
- **CLI Configuration Management (`effero config get` / `effero config set`)**:
  - Direct modification and query of `effero.yaml` keys from terminal without manual file editing.
  - Native support for Ollama and local OpenAI-compatible backends (`http://127.0.0.1:11434/v1`).
- **Community System Info Skill (`community.system_info.get_overview`)**:
  - Live OS, CPU cores/usage, RAM, disk capacity, and uptime telemetry via `psutil`.
  - Zero mock dependency — gathers live physical machine metrics.
- **Effero Technical Architecture Guide**:
  - Upgraded `docs/architecture.md` into comprehensive six-layer system documentation.

### Fixed
- **Type Annotations & Clean Code**:
  - Cleaned up loose types and unions in `Planner`, `MCPServer`, `WyomingServer`, `Agent`, `NavigationController`, and `A2ATaskManager`.
  - Added unit test coverage for new CLI commands and community skills (234 tests passing).
- **Rust Safety Kernel Documentation**:
  - Aligned `effero-safety-kerneld` binary documentation with actual TCP socket implementation.

## [0.1.0] - 2026-09-08

### Added
- **Fleet Consensus Integration (`core.fleet`)**:
  - `FleetConfig` model added to `EfferoConfig` (`enabled`, `default_lease_duration`).
  - Opt-in `FleetCoordinator` integration directly in `Agent.__init__`.
  - Task announcement EventBus broadcast (`fleet.cfp.announced`) on `FleetCoordinator.announce_task()`.
  - Failover re-auction history tracking: preservation of `reauction_round`, `previous_bids_count`, and prior metadata.
- **Hardware MCP Server Unit Testing (`crates/effero-edge-mcp`)**:
  - 3 unit tests added for `EdgeDevice`: default pin state verification, digital write/read state validation, and out-of-range bounds error handling.
- **Test Coverage Expansion (Zero-Mock)**:
  - `tests/test_config_env.py`: Verified backend-specific API key loading without environment variable clobbering.
  - `tests/test_fleet_coordinator_integration.py`: End-to-end testing of EventBus CFP broadcasting, lease ID consistency, unrevealed sealed bid rejection, and failover re-auction round tracking.
  - `tests/test_a2a_protocol.py`: Testing `AgentCard` serialization, `TaskMessage` lifecycle, and `A2ATaskManager` execution with both standalone and real Agent instances.
  - `tests/test_cli_commands.py`: Unit tests for `build_parser`, `--version`, `skills`, and project scaffolding `init`.
  - `tests/test_server_websockets.py`: Full WebSocket ping/pong lifecycle, `/v1/approvals` GET/POST resolution, and `/v1/memory` inspection using real production `Agent`.

### Fixed
- **Security / Protocol**:
  - Fixed sealed bid integrity bypass in `SealedBidAuction.close_auction()`: bids with declared commitment hashes that failed to reveal their salt are now strictly rejected.
  - Fixed `TaskLease` ID divergence between `TaskAward` and `LeaseManager.create_lease()`.
  - Fixed `EfferoConfig.from_env()` key clobbering across multiple provider environment variables (`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GOOGLE_API_KEY`).
  - Fixed `EventBus.publish()` and `server.py:handle_approval_request()` crashing synchronous callers with `RuntimeError: no running event loop`.
- **Runtime & Cross-Platform**:
  - Fixed blocking `input()` in interactive CLI REPL (`cli.py:run_repl`) by wrapping in `loop.run_in_executor`.
  - Fixed Windows `connect_read_pipe` incompatibility with ProactorEventLoop in `cli.py:serve_mcp` by using non-blocking executor reads.
  - Fixed `google_backend.py` compatibility with newer `google-genai` SDK (`Part` constructor, union guards, type-annotated tool arguments).
  - Fixed duplicate `module` import symbol in `src/effero/core/router/__init__.py`.
  - Fixed type narrowing on `select_best_node()` in `test_fleet_auction.py`.
  - Resolved all 13 `mypy` static typing errors across the entire codebase.

### Changed
- **Zero-Mock Production Cleanliness**:
  - Removed silent mock API fallback mode in `CloudAPIAdapter` (`adapters/cloud_api/client.py`); now raises explicit `RuntimeError` when unconnected or dependencies are missing.
  - Removed obsolete "mock fallback" docstrings and unused `_is_mock` flag in `BrowserController` (`skills/computer_use/browser.py`).
  - Centralized `BUILTIN_SKILL_MODULES` constant in `effero.sdk` and deduplicated across `Agent`, `cli.list_skills`, and `cli.serve_mcp`.
  - Updated `effero-safety-kernel/README.md` to reflect actual TCP transport (`127.0.0.1:9400`) rather than Unix domain socket.
