# Safety Model

Text-alignment guardrails do not protect against unsafe *physical* actions. A model that refuses to describe something harmful in words has been repeatedly shown to still execute an unsafe robot plan unless something *outside the model* stops it.

Effero's guardrail engine is built around that finding.

## Architecture

```
  Planner proposes action
         │
         ▼
  ┌──────────────┐
  │ Safety Class  │ ── READ_ONLY? ──→ Execute immediately
  │   Check       │
  └──────┬───────┘
         │ ACT_*
         ▼
  ┌──────────────┐
  │ Policy Engine │ ── Rust kernel evaluates rules against
  │  (TCP RPC)    │    live device state and facts
  └──────┬───────┘
         │
    ┌────┼────┐
    ▼    ▼    ▼
  ALLOW  DENY  REQUIRE_APPROVAL
    │         │         │
    ▼         ▼         ▼
 Execute   Block   Prompt human
```

## Key principles

- **Policy-as-code**: Declarative rules ("never exceed 0.5 m/s within 1 m of a person") grounded against the *live* world model at runtime.
- **Independent runtime check**: Every action is validated *before* reaching hardware. This check does not go through the LLM and cannot be prompt-injected away.
- **Human-in-the-loop approval**: Skills marked `ACT_WITH_APPROVAL` pause for explicit confirmation before executing.
- **Simulation-first promotion**: Community-contributed skills default to `ACT_RESTRICTED` (dry-run) until a maintainer promotes them.
- **Hardware e-stop hook**: A dedicated kill switch that adapters must implement, independent of the LLM.
- **Full audit log**: Every plan, tool call, guardrail decision, and approval is logged.

## Safety classes

See [Skills Overview](../skills/index.md) for the four safety levels and when to use each.

## Declaring policies

Policies are YAML files in `src/effero/safety/policies/`:

```yaml
rules:
  - name: no-exterior-unlock-at-night
    pattern: "iot.locks.*"
    condition: "time_hour >= 23 || time_hour < 6"
    decision: require_approval
    reason: "Exterior lock actions require approval at night."
```

See [Safety Kernel](rust-kernel.md) for how the Rust daemon evaluates these.
