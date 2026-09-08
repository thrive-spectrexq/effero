# Effero's Rust workspace

Effero's core (orchestrator, planner, memory, skills, adapters) is Python
— see the top-level README's "Why Rust doesn't help" note in the
Architecture discussion. This workspace exists for the two places where
Rust specifically earns its complexity:

| Crate | Purpose | Status |
|---|---|---|
| [`effero-safety-kernel`](effero-safety-kernel/) | The runtime guardrail engine, run as an independent process so no LLM-side prompt injection can bypass it. | **Builds, tests, and runs end-to-end** (verified: `cargo build`, `cargo test` — 11/11 passing — and a live Unix-socket round trip from a Python client). |
| [`effero-edge-mcp`](effero-edge-mcp/) | A template MCP server for constrained/embedded devices, using Anthropic's official `rmcp` SDK. | **Written against the confirmed current `rmcp` API, not yet compiled** — see that crate's README for why, and what to run to verify it yourself. |

## Requirements

```
rustc/cargo 1.85+   (Rust 2024 edition)
```

A `rust-toolchain.toml` at the repo root pins `channel = "stable"`, so
`rustup` will fetch the right version automatically the first time you
build here.

## Building

```bash
cargo build --workspace
cargo test --workspace
```

## Why two crates with different histories

`effero-safety-kernel` was built and verified inside a sandboxed dev
environment that only had Rust 1.75 available (no path to a newer
toolchain on that machine's network). Rather than block on that, it was
deliberately written with a minimal, conservative dependency set — which
turned out to double as a genuinely good property for a safety-critical
component anyway (smaller audit surface). It happens to build on 1.75+,
though the workspace as a whole targets 1.85+ because of the crate below.

`effero-edge-mcp` depends on `rmcp`, the official MCP Rust SDK, which
requires the Rust 2024 edition (1.85+) at every published version as of
this writing. That same sandboxed environment couldn't build it, so this
crate has **not** been compiled or run yet — only written carefully
against `rmcp`'s confirmed current API and examples. Treat it as a
starting point to verify (`cargo build -p effero-edge-mcp`) rather than
as tested code, until someone does that on a real toolchain and this note
gets deleted.

## Talking to Python

Neither crate is wired into the Python core yet:

- `effero-safety-kernel` exposes a Unix-socket JSON protocol (documented
  in its README) that `src/effero/safety/__init__.py` will eventually
  call into.
- `effero-edge-mcp` is a standalone MCP server; it plugs into Effero's
  skill layer the same way any MCP server does, once the Python-side MCP
  client wiring in `src/effero/protocols/` lands.

Both integration points are open work — see the top-level [ROADMAP](../ROADMAP.md).
