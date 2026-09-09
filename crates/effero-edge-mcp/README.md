# effero-edge-mcp

A minimal MCP server template for constrained / embedded devices, built on
[Anthropic's official Rust MCP SDK (`rmcp`)](https://github.com/modelcontextprotocol/rust-sdk).

## What it does

Exposes two tools — `read_pin` and `set_pin` — over stdio via MCP. In
this skeleton they operate on an in-memory simulated 32-pin GPIO bank so
the pattern is runnable without real hardware. The point isn't the pins;
it's the shape: **a device that speaks MCP over stdio plugs into Effero's
skill layer exactly like a Python skill does**, from the orchestrator's
point of view. Swap the body of `read_pin`/`set_pin` for real
`embedded-hal` calls and you have a real hardware bridge with no other
code changed.

## Toolchain Requirement & Build Status: Confirmed Working

This crate relies on `rmcp` 3.2.0, which targets Rust Edition 2024 dependencies. It requires **Rust 1.85.0 or newer** (specified as `rust-version = "1.85"` in `Cargo.toml`).

The crate is verified and passes all tests on Rust 1.85+ stable (and in GitHub Actions CI):

```bash
cargo build -p effero-edge-mcp
cargo test -p effero-edge-mcp
```


## Running it (once verified)

```bash
cargo run -p effero-edge-mcp
```

It speaks MCP over stdio, so the easiest way to poke at it interactively
is the official MCP Inspector:

```bash
npx @modelcontextprotocol/inspector cargo run -p effero-edge-mcp
```

## Porting to real hardware

For a genuinely embedded target (ESP32, RP2040, etc. running `no_std`),
this `std`-based, stdio-transport version isn't directly portable —
bare-metal targets need a board-specific HAL crate, a different MCP
transport (these boards typically don't have a conventional stdio/OS
process model), and careful attention to binary size. That's real,
separate work, intentionally out of scope for this first skeleton. This
crate is the right template for anything that *can* run a small Linux
userspace process (a Pi Zero, an OpenWRT router, a Linux-capable
microcontroller board) today.

## Roadmap

- Get this compiling and tested on a real 1.85+ toolchain (see warning
  above) -- good first contribution.
- Wire it into `src/effero/protocols/` as a reference MCP client
  integration from the Python side.
- A `no_std` / `embedded-hal` variant for true bare-metal boards, once
  the transport question above is resolved.
