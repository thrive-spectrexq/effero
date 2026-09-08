# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
