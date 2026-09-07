"""Trajectory generation and interpolation for multi-DOF robotics systems."""

from __future__ import annotations

import math
from dataclasses import dataclass, field


@dataclass
class TrajectoryPoint:
    """A sampled point along a continuous multi-joint trajectory."""

    time: float
    positions: list[float]
    velocities: list[float] = field(default_factory=list)
    accelerations: list[float] = field(default_factory=list)
    jerks: list[float] = field(default_factory=list)

    def __post_init__(self) -> None:
        n = len(self.positions)
        if not self.velocities:
            self.velocities = [0.0] * n
        if not self.accelerations:
            self.accelerations = [0.0] * n
        if not self.jerks:
            self.jerks = [0.0] * n


class QuinticPolynomial:
    """Analytical 5th-order (quintic) polynomial trajectory segment for a single DOF.

    Solves:
        q(t) = c0 + c1*t + c2*t^2 + c3*t^3 + c4*t^4 + c5*t^5
    satisfying boundary conditions:
        q(0) = q0, q'(0) = v0, q''(0) = a0
        q(T) = q1, q'(T) = v1, q''(T) = a1
    """

    def __init__(
        self,
        q0: float,
        v0: float,
        a0: float,
        q1: float,
        v1: float,
        a1: float,
        duration: float,
    ) -> None:
        if duration <= 0.0:
            raise ValueError(f"Trajectory duration must be positive, got {duration}")

        self.q0 = q0
        self.v0 = v0
        self.a0 = a0
        self.q1 = q1
        self.v1 = v1
        self.a1 = a1
        self.duration = duration

        # Analytical solution for polynomial coefficients
        t = duration
        t2 = t * t
        t3 = t2 * t
        t4 = t3 * t
        t5 = t4 * t

        self.c0 = q0
        self.c1 = v0
        self.c2 = 0.5 * a0
        self.c3 = (20.0 * (q1 - q0) - (8.0 * v1 + 12.0 * v0) * t - (3.0 * a0 - a1) * t2) / (2.0 * t3)
        self.c4 = (30.0 * (q0 - q1) + (14.0 * v1 + 16.0 * v0) * t + (3.0 * a0 - 2.0 * a1) * t2) / (2.0 * t4)
        self.c5 = (12.0 * (q1 - q0) - 6.0 * (v1 + v0) * t + (a1 - a0) * t2) / (2.0 * t5)

    def position(self, t: float) -> float:
        """Evaluate position at time t."""
        t_clamped = max(0.0, min(self.duration, t))
        return (
            self.c0
            + self.c1 * t_clamped
            + self.c2 * (t_clamped**2)
            + self.c3 * (t_clamped**3)
            + self.c4 * (t_clamped**4)
            + self.c5 * (t_clamped**5)
        )

    def velocity(self, t: float) -> float:
        """Evaluate velocity at time t."""
        t_clamped = max(0.0, min(self.duration, t))
        return (
            self.c1
            + 2.0 * self.c2 * t_clamped
            + 3.0 * self.c3 * (t_clamped**2)
            + 4.0 * self.c4 * (t_clamped**3)
            + 5.0 * self.c5 * (t_clamped**4)
        )

    def acceleration(self, t: float) -> float:
        """Evaluate acceleration at time t."""
        t_clamped = max(0.0, min(self.duration, t))
        return (
            2.0 * self.c2
            + 6.0 * self.c3 * t_clamped
            + 12.0 * self.c4 * (t_clamped**2)
            + 20.0 * self.c5 * (t_clamped**3)
        )

    def jerk(self, t: float) -> float:
        """Evaluate jerk at time t."""
        t_clamped = max(0.0, min(self.duration, t))
        return 6.0 * self.c3 + 24.0 * self.c4 * t_clamped + 60.0 * self.c5 * (t_clamped**2)

    def evaluate(self, t: float) -> tuple[float, float, float, float]:
        """Evaluate (position, velocity, acceleration, jerk) at time t."""
        return (
            self.position(t),
            self.velocity(t),
            self.acceleration(t),
            self.jerk(t),
        )


class MinimumJerkTrajectory:
    """Multi-DOF minimum jerk trajectory generator.

    Minimizes the cost function integral_0^T (d3q/dt3)^2 dt between specified
    boundary conditions across all joint dimensions.
    """

    def __init__(
        self,
        start_positions: list[float],
        target_positions: list[float],
        duration: float,
        start_velocities: list[float] | None = None,
        target_velocities: list[float] | None = None,
        start_accelerations: list[float] | None = None,
        target_accelerations: list[float] | None = None,
    ) -> None:
        if len(start_positions) != len(target_positions):
            raise ValueError(f"Dimension mismatch: start ({len(start_positions)}) vs target ({len(target_positions)})")
        if duration <= 0.0:
            raise ValueError(f"Duration must be positive, got {duration}")

        self.num_dof = len(start_positions)
        self.duration = duration
        self.start_positions = list(start_positions)
        self.target_positions = list(target_positions)

        v0 = start_velocities or [0.0] * self.num_dof
        v1 = target_velocities or [0.0] * self.num_dof
        a0 = start_accelerations or [0.0] * self.num_dof
        a1 = target_accelerations or [0.0] * self.num_dof

        self.polynomials: list[QuinticPolynomial] = [
            QuinticPolynomial(
                q0=start_positions[i],
                v0=v0[i],
                a0=a0[i],
                q1=target_positions[i],
                v1=v1[i],
                a1=a1[i],
                duration=duration,
            )
            for i in range(self.num_dof)
        ]

    def evaluate(self, t: float) -> TrajectoryPoint:
        """Sample all DOF at absolute time t within [0, duration]."""
        pos: list[float] = []
        vel: list[float] = []
        acc: list[float] = []
        jrk: list[float] = []

        for poly in self.polynomials:
            p, v, a, j = poly.evaluate(t)
            pos.append(p)
            vel.append(v)
            acc.append(a)
            jrk.append(j)

        return TrajectoryPoint(
            time=t,
            positions=pos,
            velocities=vel,
            accelerations=acc,
            jerks=jrk,
        )

    def sample(self, dt: float = 0.02) -> list[TrajectoryPoint]:
        """Generate uniform time-sampled trajectory points at rate dt."""
        if dt <= 0.0:
            raise ValueError(f"Time step dt must be positive, got {dt}")

        num_steps = max(2, int(math.ceil(self.duration / dt)) + 1)
        points: list[TrajectoryPoint] = []
        for step in range(num_steps):
            t = min(self.duration, step * dt)
            points.append(self.evaluate(t))
        return points


class MultiSegmentTrajectoryPlanner:
    """Plans multi-waypoint trajectories with C^2 continuity through N joint configurations.

    Enforces joint limits for velocity, acceleration, and jerk, and generates
    continuous transitions across all via-points.
    """

    def __init__(
        self,
        max_velocity: float | list[float] = 1.5,
        max_acceleration: float | list[float] = 3.0,
        max_jerk: float | list[float] = 15.0,
    ) -> None:
        self.max_velocity = max_velocity
        self.max_acceleration = max_acceleration
        self.max_jerk = max_jerk

        self.segments: list[MinimumJerkTrajectory] = []
        self.segment_durations: list[float] = []
        self.segment_start_times: list[float] = []
        self.total_duration: float = 0.0
        self.waypoints: list[list[float]] = []

    def _get_limit(self, limit: float | list[float], dof_index: int) -> float:
        if isinstance(limit, (list, tuple)):
            return float(limit[dof_index])
        return float(limit)

    def plan(
        self,
        waypoints: list[list[float]],
        durations: list[float] | None = None,
    ) -> list[MinimumJerkTrajectory]:
        """Plan trajectory across waypoints.

        Args:
            waypoints: List of joint configurations [q0, q1, ..., q_{N-1}].
            durations: Optional explicit list of segment durations (length N-1).
        """
        if len(waypoints) < 2:
            raise ValueError(f"At least 2 waypoints required for trajectory, got {len(waypoints)}")

        num_dof = len(waypoints[0])
        for i, wp in enumerate(waypoints):
            if len(wp) != num_dof:
                raise ValueError(f"Waypoint {i} dimension {len(wp)} does not match expected {num_dof}")

        self.waypoints = [list(wp) for wp in waypoints]
        num_segments = len(waypoints) - 1

        # 1. Determine segment durations if not provided
        if durations is not None:
            if len(durations) != num_segments:
                raise ValueError(f"Expected {num_segments} durations, got {len(durations)}")
            seg_durations = [max(0.01, float(d)) for d in durations]
        else:
            seg_durations = []
            for k in range(num_segments):
                seg_dur = 0.1  # minimum duration
                q_curr = waypoints[k]
                q_next = waypoints[k + 1]
                for j in range(num_dof):
                    dq = abs(q_next[j] - q_curr[j])
                    v_lim = self._get_limit(self.max_velocity, j)
                    a_lim = self._get_limit(self.max_acceleration, j)
                    j_lim = self._get_limit(self.max_jerk, j)

                    t_vel = 2.2 * (dq / v_lim) if v_lim > 0 else 0.1
                    t_acc = math.sqrt((10.0 / math.sqrt(3)) * dq / a_lim) if a_lim > 0 else 0.1
                    t_jrk = ((60.0 * dq) / j_lim) ** (1.0 / 3.0) if j_lim > 0 else 0.1

                    seg_dur = max(seg_dur, t_vel, t_acc, t_jrk)
                seg_durations.append(round(seg_dur, 4))

        # 2. Estimate intermediate boundary velocities (C^1 continuity)
        # Endpoints are zero velocity
        velocities: list[list[float]] = [[0.0] * num_dof for _ in range(len(waypoints))]
        for k in range(1, len(waypoints) - 1):
            dt_prev = seg_durations[k - 1]
            dt_next = seg_durations[k]
            for j in range(num_dof):
                # Central difference based on segment times
                v = (waypoints[k + 1][j] - waypoints[k - 1][j]) / (dt_prev + dt_next)
                v_lim = self._get_limit(self.max_velocity, j)
                v_clamped = max(-v_lim, min(v_lim, v))
                velocities[k][j] = v_clamped

        # 3. Estimate intermediate boundary accelerations (C^2 continuity)
        accelerations: list[list[float]] = [[0.0] * num_dof for _ in range(len(waypoints))]
        for k in range(1, len(waypoints) - 1):
            dt_prev = seg_durations[k - 1]
            dt_next = seg_durations[k]
            for j in range(num_dof):
                a = 2.0 * (velocities[k][j] - velocities[k - 1][j]) / dt_prev
                a_lim = self._get_limit(self.max_acceleration, j)
                a_clamped = max(-a_lim, min(a_lim, a))
                accelerations[k][j] = a_clamped

        # 4. Construct trajectory segments
        self.segments = []
        self.segment_durations = seg_durations
        self.segment_start_times = []
        current_time = 0.0

        for k in range(num_segments):
            self.segment_start_times.append(current_time)
            traj = MinimumJerkTrajectory(
                start_positions=waypoints[k],
                target_positions=waypoints[k + 1],
                duration=seg_durations[k],
                start_velocities=velocities[k],
                target_velocities=velocities[k + 1],
                start_accelerations=accelerations[k],
                target_accelerations=accelerations[k + 1],
            )
            self.segments.append(traj)
            current_time += seg_durations[k]

        self.total_duration = current_time
        return self.segments

    def evaluate(self, t: float) -> TrajectoryPoint:
        """Evaluate trajectory point at global time t."""
        if not self.segments:
            raise RuntimeError("Trajectory planner has not planned any waypoints yet")

        t_clamped = max(0.0, min(self.total_duration, t))

        # Find segment
        seg_idx = 0
        for i, start_t in enumerate(self.segment_start_times):
            if t_clamped >= start_t:
                seg_idx = i
            else:
                break

        local_t = t_clamped - self.segment_start_times[seg_idx]
        point = self.segments[seg_idx].evaluate(local_t)
        point.time = t_clamped
        return point

    def sample(self, dt: float = 0.02) -> list[TrajectoryPoint]:
        """Sample entire multi-segment trajectory uniformly at interval dt."""
        if not self.segments:
            raise RuntimeError("Trajectory planner has not planned any waypoints yet")
        if dt <= 0.0:
            raise ValueError(f"Sample interval dt must be positive, got {dt}")

        num_steps = max(2, int(math.ceil(self.total_duration / dt)) + 1)
        points: list[TrajectoryPoint] = []
        for step in range(num_steps):
            t = min(self.total_duration, step * dt)
            points.append(self.evaluate(t))
        return points
