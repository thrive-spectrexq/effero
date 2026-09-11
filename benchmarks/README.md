# Benchmarks

Performance benchmarks for Effero's real-time-sensitive components.

## Running

```bash
# Run all benchmarks directly
pytest benchmarks/ -o python_files="bench_*.py" -v

# Run with pytest-benchmark statistical profiling (if installed)
pytest benchmarks/ -o python_files="bench_*.py" --benchmark-only -v
```

## What's benchmarked

- **A* Path Planning** (`bench_a_star.py`) — 100×100 grid search with barrier obstacles and line-of-sight smoothing.
- **Dynamic Window Approach** (`bench_dwa.py`) — Local collision-avoiding command velocity generation across obstacle clusters.
- **Extended Kalman Filter** (`bench_ekf.py`) — Predict step, landmark range/bearing update, and full state propagation cycles.
- **Spatial Transforms** (`bench_transforms.py`) — SE(2) and SE(3) matrix chain composition and analytical inversions.
- **OMG CDR Serializer** (`bench_cdr.py`) — Real-time binary wire encoding/decoding throughput for `JointTrajectory` (50 points), `JointState`, and `geometry_msgs/Twist`.
- **Agent Planner Loop** (`bench_planner.py`) — Full plan-act-observe cycle: prompt rendering, tool selection, skill execution, and LLM summary.

These components are real-time-sensitive: they run inside physical control loops where latency directly affects safety, stability, and throughput.

## CI integration

Benchmarks run in CI to catch regression bottlenecks across releases.
