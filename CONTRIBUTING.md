# Contributing to Effero

Thanks for considering a contribution — Effero is community-built from day one, and the easiest, highest-leverage contributions are new **skills** and **adapters**, not core-runtime changes. This guide covers both.

By participating in this project you agree to abide by our [Code of Conduct](CODE_OF_CONDUCT.md).

## Ways to contribute

- **New skills** (`src/effero/skills/`) — the easiest entry point. A skill is a small, testable function wrapped in `@skill(...)` (see `src/effero/sdk/skill.py` and the Quickstart in `README.md`).
- **New adapters** (`src/effero/adapters/`) — a new IoT protocol, robot middleware, or microcontroller board.
- **The Rust crates** (`crates/`) — the safety-kernel engine and the embedded MCP server template. See [`crates/README.md`](crates/README.md); `effero-edge-mcp` in particular needs someone to confirm it actually compiles on a modern toolchain (see that crate's README) — a great first Rust contribution.
- **New perception backends** (`src/effero/perception/`) — support for an ASR/TTS/vision/VLA model not yet wired in.
- **Safety policy review** (`src/effero/safety/`) — Effero touches physical hardware; extra scrutiny here is always welcome, even just review comments on a PR.
- **Docs and examples** (`docs/`, `examples/`) — a new worked example is often more valuable than a core-code PR.
- **Bug reports and feature requests** — use the issue templates; see [Reporting issues](#reporting-issues) below.

If you're not sure where something fits, open an issue first and ask — that's a completely valid way to start.

## Development setup

Effero targets Python 3.11+.

```bash
git clone https://github.com/thrive-spectrexq/effero.git
cd effero
python -m venv .venv
source .venv/bin/activate      # .venv\Scripts\activate on Windows
pip install -e ".[dev]"
```

Optional extras (`voice`, `vision`, `ros2`, `iot`) pull in the corresponding heavier dependencies and are only needed if you're touching that subsystem:

```bash
pip install -e ".[dev,voice]"
```

### Rust crates

The `crates/` workspace (safety kernel + edge MCP server) needs Rust
1.85+ (Rust 2024 edition). `rust-toolchain.toml` at the repo root pins
`channel = "stable"`, so `rustup` fetches the right version automatically:

```bash
cargo build --workspace
cargo test --workspace
```

See [`crates/README.md`](crates/README.md) for the status of each crate
before you start — one builds and is tested, the other needs its first
real compile.

### Running checks locally

```bash
pytest                 # tests
ruff check .           # lint
ruff format --check .  # formatting
mypy src/effero        # type checking
```

CI runs the same checks on every pull request (`.github/workflows/ci.yml`) — please make sure they pass locally first.

## Adding a new skill

1. Pick the right subpackage under `src/effero/skills/` (`robotics/`, `iot/`, `computer_use/`, or `community/` for anything that doesn't fit a first-party category yet).
2. Write the skill as a plain, typed Python function and wrap it with `@skill(name=..., description=..., safety_class=...)`.
3. **Choose the safety class deliberately** — see the enum docstring in `src/effero/sdk/skill.py`:
   - `READ_ONLY` for anything that cannot change external state.
   - `ACT_AUTONOMOUS` only for actions you're confident are safe to run unattended.
   - `ACT_WITH_APPROVAL` for anything with real-world consequences you're not fully confident about.
   - `ACT_RESTRICTED` (the default posture for new community skills) — simulation/dry-run only until a maintainer promotes it.
4. Add a unit test under `tests/`.
5. If the skill needs a new declarative safety rule, propose it in `src/effero/safety/policies/` as part of the same PR, and call it out explicitly in the PR description.

## Adding a new adapter

Adapters live in `src/effero/adapters/` and should:

- Keep any heavy/optional dependency (e.g. `rclpy`, `paho-mqtt`) behind an optional extra in `pyproject.toml`, not a hard dependency — see the existing `ros2` and `iot` extras for the pattern.
- Avoid importing the optional dependency at module top-level, so `import effero` keeps working on machines that don't have that hardware stack installed.
- Come with at least one example under `examples/` showing it wired into a real (or simulated) device.

## Pull request checklist

- [ ] Tests added or updated, and `pytest` passes locally.
- [ ] `ruff check .` and `ruff format --check .` pass.
- [ ] New skills declare an explicit, deliberate `safety_class`.
- [ ] Any new hardware/network dependency is behind an optional extra, not a hard dependency.
- [ ] Docs/README/examples updated if behavior or structure changed.
- [ ] Commits are reasonably scoped and the PR description explains *why*, not just *what*.

## Reporting issues

Please use the issue templates (`.github/ISSUE_TEMPLATE/`) for bug reports and feature requests. For anything touching **physical safety** (a skill or adapter that could cause real-world harm if it misbehaves), please say so explicitly in the issue title or first line — those get prioritized.

If you believe you've found a security vulnerability, please follow [`SECURITY.md`](SECURITY.md) instead of opening a public issue.

## Commit and review conventions

- Prefer small, focused PRs over large ones — easier to review, easier to revert if something's wrong.
- Write commit messages that explain intent (`fix: guard against negative celsius in thermostat skill`, not `fix bug`).
- One approving review from a maintainer is required to merge; PRs touching `src/effero/safety/` may require two.

Thank you for helping build this — even a single well-tested skill is a genuinely useful contribution.
