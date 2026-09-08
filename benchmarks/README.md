# Benchmarks

Performance benchmarks for Effero's real-time-sensitive components.

## Running

```bash
pip install pytest-benchmark
pytest benchmarks/ --benchmark-only -v
```

## What's benchmarked

- **A* path planning** — 50×50 grid with obstacles
- **EKF localization** — predict + landmark update cycle
- **Transform composition** — SE(2) and SE(3) matrix chains
- **Planner loop** — single plan-act-observe iteration

These components are real-time-sensitive: they run inside physical
control loops where latency directly affects safety and performance.

## CI integration

Benchmarks run as a non-blocking CI job. Results are not gating but
are available for manual review on PRs that touch performance-critical
code paths.
