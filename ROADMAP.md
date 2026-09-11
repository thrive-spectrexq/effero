# Roadmap

> This is a living document. Items are roughly ordered by expected delivery.
> For completed milestones, see [CHANGELOG.md](CHANGELOG.md).

## Near-term (v0.2.x)

- [x] Python ↔ Rust safety-kernel bridge & daemon manager (`src/effero/safety/` → `crates/effero-safety-kernel` TCP RPC & auto-spawn)
- [x] MCP client wiring in `src/effero/protocols/` for external MCP servers (including `effero-edge-mcp`)
- [x] `effero run --voice` & `effero voice` end-to-end voice loop (wake-word → ASR → LLM → skill → TTS)
- [x] MQTT/Matter adapter live integration with `iot.*` skills

## Mid-term (v0.3.x)

- [x] ROS 2 adapter live integration with `robotics.*` skills
- [x] `mobile-manipulator` example (VLA + ROS 2 + navigation)
- [x] Hardware compatibility matrix with measured footprint numbers
- [x] Versioned documentation site (mkdocs-material + GitHub Pages)

## Longer-term

- [ ] `industrial-monitor` and `multi-robot-swarm` examples
- [x] Performance benchmark suite (planner loop, EKF, A*, DWA, CDR, transforms)
- [ ] Community skill marketplace / browsable catalog
- [ ] Plugin-based adapter discovery

## How to propose changes

Open an issue or PR — the roadmap is as much a community document as the code.
