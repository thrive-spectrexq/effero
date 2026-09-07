"""Comprehensive test suite for robotics trajectory interpolation and workspace collision validation."""

from __future__ import annotations

import math

import pytest

from effero.skills.robotics.arm import ArmController, JointConfiguration
from effero.skills.robotics.collision import (
    ArmCollisionValidator,
    BoxObstacle,
    CylinderObstacle,
    SphereObstacle,
    WorkspaceBounds,
)
from effero.skills.robotics.trajectory import (
    MinimumJerkTrajectory,
    MultiSegmentTrajectoryPlanner,
    QuinticPolynomial,
)


def test_quintic_polynomial_boundary_conditions() -> None:
    """Verify that quintic polynomial strictly satisfies all 6 boundary conditions."""
    q0, v0, a0 = 0.5, 0.1, -0.2
    q1, v1, a1 = 2.0, -0.15, 0.05
    duration = 2.5

    poly = QuinticPolynomial(q0, v0, a0, q1, v1, a1, duration)

    # Initial boundary conditions at t = 0
    assert math.isclose(poly.position(0.0), q0, abs_tol=1e-7)
    assert math.isclose(poly.velocity(0.0), v0, abs_tol=1e-7)
    assert math.isclose(poly.acceleration(0.0), a0, abs_tol=1e-7)

    # Final boundary conditions at t = duration
    assert math.isclose(poly.position(duration), q1, abs_tol=1e-7)
    assert math.isclose(poly.velocity(duration), v1, abs_tol=1e-7)
    assert math.isclose(poly.acceleration(duration), a1, abs_tol=1e-7)


def test_quintic_polynomial_derivatives_consistency() -> None:
    """Verify that analytical derivatives match numerical finite differences."""
    poly = QuinticPolynomial(
        q0=0.0,
        v0=0.0,
        a0=0.0,
        q1=1.5,
        v1=0.0,
        a1=0.0,
        duration=3.0,
    )

    dt = 1e-5
    for t_test in [0.5, 1.0, 1.5, 2.0]:
        # Velocity check: (q(t+dt) - q(t-dt)) / (2*dt)
        num_vel = (poly.position(t_test + dt) - poly.position(t_test - dt)) / (2 * dt)
        assert math.isclose(poly.velocity(t_test), num_vel, rel_tol=1e-4)

        # Acceleration check: (v(t+dt) - v(t-dt)) / (2*dt)
        num_acc = (poly.velocity(t_test + dt) - poly.velocity(t_test - dt)) / (2 * dt)
        assert math.isclose(poly.acceleration(t_test), num_acc, rel_tol=1e-4)

        # Jerk check: (a(t+dt) - a(t-dt)) / (2*dt)
        num_jerk = (poly.acceleration(t_test + dt) - poly.acceleration(t_test - dt)) / (2 * dt)
        assert math.isclose(poly.jerk(t_test), num_jerk, rel_tol=1e-4)


def test_quintic_polynomial_invalid_duration() -> None:
    with pytest.raises(ValueError, match="must be positive"):
        QuinticPolynomial(0, 0, 0, 1, 0, 0, duration=0.0)
    with pytest.raises(ValueError, match="must be positive"):
        QuinticPolynomial(0, 0, 0, 1, 0, 0, duration=-1.0)


def test_minimum_jerk_trajectory_endpoints_rest_to_rest() -> None:
    """Verify rest-to-rest 4-DOF arm trajectory begins and ends at zero velocity and acceleration."""
    start = [0.0, 0.5, -1.0, 0.5]
    target = [1.2, -0.2, 0.8, -0.4]
    duration = 2.0

    traj = MinimumJerkTrajectory(start, target, duration=duration)
    pt_start = traj.evaluate(0.0)
    pt_end = traj.evaluate(duration)

    for i in range(4):
        assert math.isclose(pt_start.positions[i], start[i], abs_tol=1e-6)
        assert math.isclose(pt_start.velocities[i], 0.0, abs_tol=1e-6)
        assert math.isclose(pt_start.accelerations[i], 0.0, abs_tol=1e-6)

        assert math.isclose(pt_end.positions[i], target[i], abs_tol=1e-6)
        assert math.isclose(pt_end.velocities[i], 0.0, abs_tol=1e-6)
        assert math.isclose(pt_end.accelerations[i], 0.0, abs_tol=1e-6)


def test_minimum_jerk_velocity_symmetry() -> None:
    """Verify that rest-to-rest minimum jerk trajectory exhibits velocity symmetry and peak at t=T/2."""
    traj = MinimumJerkTrajectory([0.0], [2.0], duration=4.0)

    # Midpoint should have maximum velocity
    v_mid = traj.evaluate(2.0).velocities[0]
    # For rest-to-rest minimum jerk, v_max = 1.875 * (q1 - q0) / T = 1.875 * 2.0 / 4.0 = 0.9375
    assert math.isclose(v_mid, 0.9375, abs_tol=1e-5)

    # Velocity at symmetric times should match
    v_1 = traj.evaluate(1.0).velocities[0]
    v_3 = traj.evaluate(3.0).velocities[0]
    assert math.isclose(v_1, v_3, abs_tol=1e-6)

    # Acceleration at midpoint should cross zero
    a_mid = traj.evaluate(2.0).accelerations[0]
    assert math.isclose(a_mid, 0.0, abs_tol=1e-6)


def test_minimum_jerk_uniform_sampling() -> None:
    traj = MinimumJerkTrajectory([0.0, 0.0], [1.0, 2.0], duration=1.0)
    samples = traj.sample(dt=0.1)

    assert len(samples) == 11
    assert math.isclose(samples[0].time, 0.0, abs_tol=1e-6)
    assert math.isclose(samples[-1].time, 1.0, abs_tol=1e-6)

    for i in range(len(samples) - 1):
        dt = samples[i + 1].time - samples[i].time
        assert math.isclose(dt, 0.1, abs_tol=1e-6)


def test_minimum_jerk_dimension_mismatch() -> None:
    with pytest.raises(ValueError, match="Dimension mismatch"):
        MinimumJerkTrajectory([0.0, 1.0], [0.0], duration=1.0)


def test_multi_segment_trajectory_c2_continuity() -> None:
    """Verify position, velocity, and acceleration continuity across waypoint transitions."""
    planner = MultiSegmentTrajectoryPlanner(max_velocity=2.0, max_acceleration=5.0)
    waypoints = [
        [0.0, 0.0, 0.0],
        [0.5, 0.8, -0.4],
        [1.2, 0.2, 0.6],
        [0.8, -0.5, 0.1],
    ]
    planner.plan(waypoints, durations=[1.5, 1.5, 1.5])

    # Check continuity at transition times t = 1.5 and t = 3.0
    eps = 1e-5
    for transition_t in [1.5, 3.0]:
        pt_before = planner.evaluate(transition_t - eps)
        pt_after = planner.evaluate(transition_t + eps)

        for j in range(3):
            assert math.isclose(pt_before.positions[j], pt_after.positions[j], abs_tol=1e-3)
            assert math.isclose(pt_before.velocities[j], pt_after.velocities[j], abs_tol=1e-2)
            assert math.isclose(pt_before.accelerations[j], pt_after.accelerations[j], abs_tol=1e-1)


def test_multi_segment_trajectory_velocity_limits() -> None:
    """Verify that multi-segment planner limits velocity across waypoints."""
    v_limit = 1.0
    planner = MultiSegmentTrajectoryPlanner(max_velocity=v_limit, max_acceleration=2.0)
    waypoints = [
        [0.0, 0.0],
        [1.0, 2.0],
        [2.0, 0.0],
    ]
    planner.plan(waypoints)  # Automatic duration allocation

    samples = planner.sample(dt=0.02)
    assert len(samples) > 20

    for pt in samples:
        for v in pt.velocities:
            # Allow small margin due to polynomial curvature between via-points
            assert abs(v) <= v_limit * 1.05


def test_workspace_bounds_containment() -> None:
    bounds = WorkspaceBounds(
        min_x=-0.5,
        max_x=0.5,
        min_y=-0.5,
        max_y=0.5,
        min_z=0.0,
        max_z=0.6,
        min_table_z=0.0,
    )

    # Interior point
    assert bounds.contains_point((0.2, -0.1, 0.3)) is True

    # Outside X boundary
    assert bounds.contains_point((0.55, 0.0, 0.3)) is False

    # Below table height
    assert bounds.contains_point((0.2, 0.1, -0.05)) is False

    # Above max Z
    assert bounds.contains_point((0.0, 0.0, 0.65)) is False


def test_box_obstacle_signed_distance() -> None:
    box = BoxObstacle(center=(0.3, 0.0, 0.2), size=(0.1, 0.1, 0.1))

    # Center is inside: distance should be -0.05
    dist_center = box.signed_distance_point((0.3, 0.0, 0.2))
    assert math.isclose(dist_center, -0.05, abs_tol=1e-6)

    # Point on face boundary: distance should be 0.0
    dist_face = box.signed_distance_point((0.35, 0.0, 0.2))
    assert math.isclose(dist_face, 0.0, abs_tol=1e-6)

    # Point outside: 0.1m away along X
    dist_outside = box.signed_distance_point((0.45, 0.0, 0.2))
    assert math.isclose(dist_outside, 0.1, abs_tol=1e-6)
    assert box.contains_point((0.32, 0.0, 0.2)) is True
    assert box.contains_point((0.45, 0.0, 0.2)) is False


def test_sphere_obstacle_signed_distance_and_segment() -> None:
    sphere = SphereObstacle(center=(0.2, 0.2, 0.2), radius=0.05)

    # Point at center
    assert math.isclose(sphere.signed_distance_point((0.2, 0.2, 0.2)), -0.05, abs_tol=1e-6)

    # Point 0.1m from center (0.05m outside)
    assert math.isclose(sphere.signed_distance_point((0.3, 0.2, 0.2)), 0.05, abs_tol=1e-6)

    # Segment passing through sphere center
    seg_p1 = (0.0, 0.2, 0.2)
    seg_p2 = (0.4, 0.2, 0.2)
    dist_seg = sphere.distance_to_segment(seg_p1, seg_p2)
    assert dist_seg <= -0.049  # Passes directly through center

    # Segment far away
    seg_far1 = (0.0, -0.5, 0.2)
    seg_far2 = (0.4, -0.5, 0.2)
    dist_far = sphere.distance_to_segment(seg_far1, seg_far2)
    assert dist_far > 0.5


def test_cylinder_obstacle_signed_distance() -> None:
    cyl = CylinderObstacle(center=(0.0, 0.0, 0.5), radius=0.1, height=0.4)

    # Point at center
    dist_center = cyl.signed_distance_point((0.0, 0.0, 0.5))
    assert math.isclose(dist_center, -0.1, abs_tol=1e-6)

    # Point outside radially
    dist_radial = cyl.signed_distance_point((0.2, 0.0, 0.5))
    assert math.isclose(dist_radial, 0.1, abs_tol=1e-6)

    # Point outside axially (z=0.8, top is at 0.7)
    dist_axial = cyl.signed_distance_point((0.0, 0.0, 0.8))
    assert math.isclose(dist_axial, 0.1, abs_tol=1e-6)


def test_arm_collision_validator_link_forward_kinematics() -> None:
    validator = ArmCollisionValidator(l0=0.15, l1=0.25, l2=0.22, l3=0.08)
    # Upright pose
    joints = JointConfiguration(base=0.0, shoulder=math.pi / 2, elbow=0.0, wrist=0.0)
    pts = validator.get_joint_positions(joints)

    assert math.isclose(pts[0][2], 0.0, abs_tol=1e-4)
    assert math.isclose(pts[1][2], 0.15, abs_tol=1e-4)
    assert math.isclose(pts[2][2], 0.15 + 0.25, abs_tol=1e-4)
    assert math.isclose(pts[3][2], 0.15 + 0.25 + 0.22, abs_tol=1e-4)
    assert math.isclose(pts[4][2], 0.15 + 0.25 + 0.22 + 0.08, abs_tol=1e-4)


def test_arm_collision_validator_table_penetration() -> None:
    validator = ArmCollisionValidator(l0=0.15, l1=0.25, l2=0.22, l3=0.08, link_radius=0.03)
    # Severe pitch-down pointing links below tabletop z=0.0
    colliding_joints = JointConfiguration(
        base=0.0,
        shoulder=math.radians(-45.0),
        elbow=math.radians(-45.0),
        wrist=0.0,
    )
    is_valid, reason = validator.validate_configuration(colliding_joints)
    assert is_valid is False
    assert "penetrates tabletop" in str(reason) or "violates workspace bounds" in str(reason)


def test_arm_collision_validator_obstacle_collision() -> None:
    validator = ArmCollisionValidator(l0=0.15, l1=0.25, l2=0.22, l3=0.08, link_radius=0.03)
    # Normal ready pose
    ready_pose = JointConfiguration(
        base=0.0,
        shoulder=math.radians(45.0),
        elbow=math.radians(-90.0),
        wrist=math.radians(45.0),
    )
    # Initially clear
    is_valid, _ = validator.validate_configuration(ready_pose)
    assert is_valid is True

    # Place an obstacle directly at the end-effector position
    ee_pos = validator.get_joint_positions(ready_pose)[4]
    obstacle = SphereObstacle(center=ee_pos, radius=0.05)
    validator.add_obstacle(obstacle)

    # Now configuration must collide
    collides, reason = validator.validate_configuration(ready_pose)
    assert collides is False
    assert "collides with obstacle" in str(reason)

    # Remove obstacle and verify it clears
    validator.remove_obstacle(obstacle)
    is_valid_again, _ = validator.validate_configuration(ready_pose)
    assert is_valid_again is True


def test_arm_trajectory_collision_validation() -> None:
    validator = ArmCollisionValidator(l0=0.15, l1=0.25, l2=0.22, l3=0.08, link_radius=0.03)
    # Define trajectory between two collision-free states
    q_start = [0.0, math.radians(45.0), math.radians(-90.0), math.radians(45.0)]
    q_end = [math.radians(90.0), math.radians(45.0), math.radians(-90.0), math.radians(45.0)]

    traj = MinimumJerkTrajectory(q_start, q_end, duration=1.0)
    samples = traj.sample(dt=0.05)

    # Path should be valid initially
    valid, _ = validator.validate_trajectory(samples)
    assert valid is True

    # Place an obstacle directly in the midpoint of the base rotation path (base=45 deg)
    mid_joints = traj.evaluate(0.5).positions
    mid_ee = validator.get_joint_positions(mid_joints)[4]
    validator.add_obstacle(BoxObstacle(center=mid_ee, size=(0.08, 0.08, 0.08)))

    # Trajectory validation must catch the collision along the path
    valid_mid, reason_mid = validator.validate_trajectory(samples)
    assert valid_mid is False
    assert "Collision at step" in str(reason_mid)


def test_arm_controller_integration_with_collision_avoidance() -> None:
    """Verify ArmController uses collision validation and rejects collision movements."""
    ctrl = ArmController()

    # Move to safe valid position
    res = ctrl.move_to_cartesian(0.25, 0.10, 0.20)
    assert res["status"] == "success"
    assert res["trajectory_points_count"] > 0

    # Add obstacle at (0.30, 0.0, 0.20)
    obstacle = SphereObstacle(center=(0.30, 0.0, 0.20), radius=0.06)
    ctrl.collision_validator.add_obstacle(obstacle)

    # Attempting to move into the obstacle must raise ValueError
    with pytest.raises(ValueError, match="violates collision constraints|outside Cartesian"):
        ctrl.move_to_cartesian(0.30, 0.0, 0.20)
