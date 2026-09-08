# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
