# effero-safety-kernel

Effero's runtime guardrail engine, as an independent process.

## Why a separate Rust process, not a Python module

The whole point of this component (see the "Safety & Governance" section of
the top-level project README) is that it checks proposed actions
**independently of the LLM and of the Python orchestrator it's guarding**.
If the guardrail were just another Python module living in the same
process as the agent loop, a sufficiently creative prompt injection could
in principle talk the orchestrator into monkeypatching or skipping it. A
separate OS process, communicating over a narrow protocol, with no LLM
calls anywhere in its dependency graph, is a much more credible hard
boundary — and a small enough one to actually audit.

That's also why this crate deliberately has **no dependency on any
general-purpose expression-evaluation library**: the condition language
(`src/condition.rs`) is a ~150-line hand-rolled recursive-descent parser
over five token types, specifically so the entire evaluation path can be
read and verified in one sitting rather than trusted as a black box.

## What's implemented in this skeleton

- `policy.rs` — the declarative policy schema (rules, glob patterns,
  conditions, actions) and YAML loading.
- `condition.rs` — the safe, dependency-free boolean-expression evaluator
  described above. Supports `&&`, `||`, parentheses, numeric comparisons
  (`<`, `<=`, `>`, `>=`, `==`, `!=`) against named facts, and bare boolean
  facts. Always fails toward `false` (i.e. toward the caller's default /
  require-approval path) on any parse or evaluation error.
- `engine.rs` — matches a skill name against each rule's `applies_to`
  glob patterns (via `globset`), evaluates the first matching rule's
  condition, and returns a `Decision` (allow / require_approval / deny /
  limit). Falls back to `policy.defaults.unknown_skill_action` if nothing
  matches — fail-safe by construction, not by convention.
- `server.rs` + `bin/effero-safety-kerneld.rs` — a small daemon that
  loads a policy file and serves decisions over a **Unix domain socket**
  using a newline-delimited JSON protocol (see below). This has been run
  and exercised end-to-end from a live Python client during development.

## Known simplification vs. the Python-side policy sketch

`src/effero/safety/policies/example.yaml` (Python side) uses dotted
condition expressions like `time.hour >= 23`. This crate's condition
grammar uses **flat** identifiers instead (`time_hour >= 23`), because
supporting dotted member access safely would meaningfully grow the
parser. Unifying the two policy grammars — most likely by having the
Python side flatten facts before sending them across the socket — is
open, tracked work; see the top-level `ROADMAP`.

## Wire protocol

One JSON object per line in, one JSON object per line out, over a Unix
domain socket.

**Request:**
```json
{"skill": "iot.locks.front_door", "facts": {"time_hour": 23.5}}
```

`facts` values may be numbers or booleans. Omit `facts` entirely (or pass
`{}`) if a rule's condition is just `"true"`.

**Response:**
```json
{"decision": "require_approval", "matched_rule": "no-exterior-unlock-at-night", "reason": "Never unlock an exterior door between 23:00 and 06:00 without explicit human approval."}
```

`decision` is one of `"allow"`, `"require_approval"`, `"deny"`, `"limit"`.
A malformed request gets back `{"decision": "require_approval", ...}` —
the server fails safe on bad input too, it never crashes the connection
silently.

## Running it

```bash
cargo build -p effero-safety-kernel
./target/debug/effero-safety-kerneld --policy policies/example.yaml --socket /tmp/effero-safety-kernel.sock
```

Then, from Python (this is the shape the real `effero.safety` module will
wrap once the Python↔Rust bridge lands — see `ROADMAP`):

```python
import socket, json

def ask(skill: str, facts: dict) -> dict:
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.connect("/tmp/effero-safety-kernel.sock")
    s.sendall((json.dumps({"skill": skill, "facts": facts}) + "\n").encode())
    response = json.loads(s.recv(4096).decode())
    s.close()
    return response

ask("iot.locks.front_door", {"time_hour": 23.5})
# {'decision': 'require_approval', 'matched_rule': 'no-exterior-unlock-at-night', ...}
```

## Testing

```bash
cargo test -p effero-safety-kernel
```

11 unit tests cover the condition evaluator (comparisons, `&&`/`||`,
parentheses, bare boolean facts, fail-safe behavior on unknown facts and
malformed conditions) and the engine (glob matching, condition
short-circuiting, default fallback).

## A note on the Rust toolchain

This crate intentionally pins a few transitive dependencies
(`globset = "=0.4.14"`, `indexmap = "=2.2.6"`) to versions that predate
the Rust 2024 edition, and avoids `clap`/`tracing` entirely, so that it
builds on Rust 1.75+ rather than requiring the newest toolchain. If your
environment has a current stable Rust (1.85+), feel free to remove those
pins and re-add richer CLI/logging crates — this was a deliberate
lowest-common-denominator choice for this first skeleton, not a
permanent constraint.

## Roadmap

- Embed this engine in the Python process via `PyO3`, as an alternative
  to the socket protocol, for deployments that want to avoid running a
  second process.
- Unify the condition grammar with the Python-side policy sketch.
- Add a `limit` payload to the response (currently the `limit` values on
  a matched rule are loaded but not yet surfaced over the wire protocol).
- Formal review of the condition parser as part of the v1.0 safety audit
  called for in the top-level `ROADMAP`.
