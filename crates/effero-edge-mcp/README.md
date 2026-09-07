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

## ⚠️ Build status: written, not yet compiled

This is the one honest caveat in this scaffold: `rmcp` requires the Rust
2024 edition (rustc/cargo **1.85+**) at every version currently published
— including its earliest release. The sandboxed environment this crate
was authored in only had Rust 1.75 available via `apt`, with no network
path to install a newer toolchain. So unlike `effero-safety-kernel`
(built, tested, and run end-to-end in that same environment), this
crate's code has **not** been compiled.

It was written carefully against `rmcp`'s confirmed, current API and
official example pattern (the `#[tool_router(server_handler)]` macro
combo, `Parameters<T>` extraction, `serve(stdio())`), not guessed from
memory. But "should compile" isn't "compiles" — please verify it before
relying on it:

```bash
cargo build -p effero-edge-mcp
```

If something doesn't line up (macro signatures do shift between `rmcp`
releases), the fix is almost always a small one — check the current
example in the [rmcp README](https://github.com/modelcontextprotocol/rust-sdk)
against `src/main.rs` here. Please open a PR with the fix and delete this
warning once it's confirmed working; that's the natural way for this
note to go away.

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
