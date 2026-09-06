## Summary

<!-- What does this PR do, and why? -->

## Type of change

- [ ] New skill
- [ ] New adapter
- [ ] New perception backend
- [ ] Core runtime (orchestrator / memory / router)
- [ ] Safety / guardrail policy
- [ ] Docs / examples
- [ ] Other (describe above)

## Checklist

- [ ] Tests added or updated, and `pytest` passes locally
- [ ] `ruff check .` and `ruff format --check .` pass
- [ ] New skills declare an explicit, deliberate `safety_class` (see `CONTRIBUTING.md`)
- [ ] Any new hardware/network dependency is behind an optional extra in `pyproject.toml`, not a hard dependency
- [ ] Docs/README/examples updated if behavior or structure changed

## Safety impact

<!--
If this PR adds or changes anything that can act on physical hardware
(a skill, an adapter, a safety policy), describe the safety implications
here explicitly, even if you believe they're minor.
-->

## Related issues

<!-- e.g. Closes #123 -->
