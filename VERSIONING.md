# Versioning & Public API Contract

Effero follows [Semantic Versioning 2.0.0](https://semver.org/).

## What counts as the public API

The following modules and symbols are the **stable surface** — the things
community-contributed skills, adapters, and downstream code are expected to
depend on:

| Module | Stable symbols |
|---|---|
| `effero.sdk` | `skill`, `SafetyClass`, `SkillSpec`, `SkillRegistry`, `registry`, `BUILTIN_SKILL_MODULES` |
| `effero.sdk.skill` | Same as above (canonical location) |
| `effero` (top-level) | `Agent`, `EfferoConfig`, `__version__` |
| `effero.adapters.base` | `BaseAdapter` |
| `effero.safety` | `PolicyDecision`, `GuardrailResult`, `SafetyClient`, `ApprovalHandler` and its subclasses |
| `effero.core.router.base` | `LLMBackend`, `ChatMessage`, `ToolCall`, `LLMResponse` |

Everything else — internal module paths, private helpers, the shape of
internal data structures — is **not** part of the public API and may
change without notice in any release.

## SemVer policy

| Version bump | Meaning |
|---|---|
| **Patch** (0.1.x → 0.1.y) | Bug fixes, performance improvements, doc updates. No public API changes. |
| **Minor** (0.x.0 → 0.y.0) | New features, new skills, new adapters. Public API additions only — no removals or breaking changes. |
| **Major** (x.0.0 → y.0.0) | Breaking changes to the public API surface listed above. |

### Pre-1.0 caveat

While Effero is at `0.x.y`, minor-version bumps *may* include breaking
changes to the public API if unavoidable, but they will always be
documented in [CHANGELOG.md](CHANGELOG.md) with migration instructions.
The project will move to `1.0.0` once the public API surface has been
stable across at least two minor releases and has seen real-world use by
external contributors.

## Deprecation policy

Before removing or renaming a public symbol:

1. The old symbol will be kept for at least one minor release with a
   `DeprecationWarning`.
2. The deprecation and its replacement will be documented in the
   CHANGELOG.
3. The removal will happen in the next minor (pre-1.0) or major (post-1.0)
   release.
