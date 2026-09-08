# Rust Safety Kernel

The safety kernel (`crates/effero-safety-kernel/`) is a small, dependency-minimal Rust process that runs independently of the Python runtime. This isolation is deliberate: no LLM-side prompt injection can modify the guardrail logic because it runs in a separate OS process.

## Architecture

- **Transport**: Newline-delimited JSON over TCP (`127.0.0.1:9400`)
- **Dependencies**: Minimal — `serde`, `serde_yaml`, `globset`, `tokio`
- **Condition parser**: ~150-line hand-rolled recursive descent parser supporting boolean (`&&`, `||`) and numeric comparisons (`<`, `<=`, `>`, `>=`, `==`, `!=`). Fails safe toward `false` on any parse error.

## Protocol

**Request:**
```json
{"skill": "iot.locks.front_door", "facts": {"time_hour": 23.5}}
```

**Response:**
```json
{"decision": "require_approval", "matched_rule": "no-exterior-unlock-at-night", "reason": "Exterior lock actions require approval at night."}
```

## Building and running

```bash
cd crates
cargo build -p effero-safety-kernel
cargo test -p effero-safety-kernel    # 11 tests

# Run the daemon
cargo run -p effero-safety-kernel --bin effero-safety-kerneld
```

## Python integration

The Python side connects via `SafetyClient` in `src/effero/safety/client.py`:

```python
from effero.safety import SafetyClient

client = SafetyClient(host="127.0.0.1", port=9400)
result = await client.check("iot.locks.front_door", {"time_hour": 23.5})
print(result.decision)  # "require_approval"
```
