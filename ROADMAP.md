# Roadmap

> This is a living document. Items are roughly ordered by expected delivery.
> For completed milestones, see [CHANGELOG.md](CHANGELOG.md).

## Near-term (v0.2.x)

- [ ] Python ↔ Rust safety-kernel bridge (`src/effero/safety/` → `crates/effero-safety-kernel` TCP RPC)
- [ ] MCP client wiring in `src/effero/protocols/` for external MCP servers (including `effero-edge-mcp`)
- [ ] `effero run` end-to-end voice loop (wake-word → ASR → LLM → skill → TTS)
- [ ] MQTT/Matter adapter live integration with `iot.*` skills

## Mid-term (v0.3.x)

- [ ] ROS 2 adapter live integration with `robotics.*` skills
- [ ] `mobile-manipulator` example (VLA + ROS 2 + navigation)
- [ ] Hardware compatibility matrix with measured footprint numbers
- [ ] Versioned documentation site (mkdocs-material + GitHub Pages)

## Longer-term

- [ ] `industrial-monitor` and `multi-robot-swarm` examples
- [ ] Performance benchmark suite (planner loop, EKF, A*, DWA)
- [ ] Community skill marketplace / browsable catalog
- [ ] Plugin-based adapter discovery

## How to propose changes

Open an issue or PR — the roadmap is as much a community document as the code.
