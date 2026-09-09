# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
