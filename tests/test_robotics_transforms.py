"""Tests for SE(2) and SE(3) spatial transformations."""

import math

import pytest

from effero.skills.robotics.transforms import Transform2D, Transform3D, wrap_angle


def test_wrap_angle():
    assert wrap_angle(0.0) == 0.0
    assert wrap_angle(math.pi) == pytest.approx(math.pi)
    assert wrap_angle(3.0 * math.pi) == pytest.approx(math.pi)
    assert wrap_angle(-3.0 * math.pi) == pytest.approx(math.pi)
    assert wrap_angle(math.pi / 2.0) == pytest.approx(math.pi / 2.0)


def test_transform2d_composition_and_inverse():
    # Robot starts at (0, 0, 0)
    # Move forward 2 meters along x, turn +90 degrees (pi/2)
    t1 = Transform2D(x=2.0, y=0.0, theta=math.pi / 2.0)
    # Move forward 1 meter in the new heading (which points along global y)
    t2 = Transform2D(x=1.0, y=0.0, theta=0.0)

    # Compose via @ operator
    t_combined = t1 @ t2
    assert t_combined.x == pytest.approx(2.0)
    assert t_combined.y == pytest.approx(1.0)
    assert t_combined.theta == pytest.approx(math.pi / 2.0)

    # Test exact inverse
    inv = t_combined.inverse()
    identity = t_combined @ inv
    assert identity.x == pytest.approx(0.0, abs=1e-7)
    assert identity.y == pytest.approx(0.0, abs=1e-7)
    assert identity.theta == pytest.approx(0.0, abs=1e-7)


def test_transform2d_point_transform():
    # Frame at (10, 5) rotated 90 degrees
    tf = Transform2D(x=10.0, y=5.0, theta=math.pi / 2.0)

    # Point at (2, 0) in local frame should be at (10, 7) in global frame
    gx, gy = tf.transform_point(2.0, 0.0)
    assert gx == pytest.approx(10.0)
    assert gy == pytest.approx(7.0)

    # Inverse point transform back to local frame
    lx, ly = tf.inverse_transform_point(gx, gy)
    assert lx == pytest.approx(2.0)
    assert ly == pytest.approx(0.0)


def test_transform2d_distances():
    t1 = Transform2D(x=0.0, y=0.0, theta=0.0)
    t2 = Transform2D(x=3.0, y=4.0, theta=math.pi / 4.0)

    assert t1.distance_to(t2) == pytest.approx(5.0)
    assert t1.angular_distance_to(t2) == pytest.approx(math.pi / 4.0)


def test_transform3d_composition_and_inverse():
    t1 = Transform3D(x=1.0, y=2.0, z=3.0, roll=0.0, pitch=0.0, yaw=math.pi / 2.0)
    t2 = Transform3D(x=0.0, y=1.0, z=0.0, roll=0.0, pitch=0.0, yaw=0.0)

    t_res = t1 @ t2
    # In local frame of t1, forward along x rotated 90 deg -> points along y
    # Here t2 is (0, 1, 0), rotated 90 deg yaw -> (-1, 0, 0)
    assert t_res.x == pytest.approx(0.0, abs=1e-7)
    assert t_res.y == pytest.approx(2.0, abs=1e-7)
    assert t_res.z == pytest.approx(3.0, abs=1e-7)

    inv = t1.inverse()
    ident = t1 @ inv
    assert ident.x == pytest.approx(0.0, abs=1e-7)
    assert ident.y == pytest.approx(0.0, abs=1e-7)
    assert ident.z == pytest.approx(0.0, abs=1e-7)
    assert ident.roll == pytest.approx(0.0, abs=1e-7)
    assert ident.pitch == pytest.approx(0.0, abs=1e-7)
    assert ident.yaw == pytest.approx(0.0, abs=1e-7)


def test_transform3d_point_transform():
    t = Transform3D(x=5.0, y=5.0, z=5.0, roll=0.0, pitch=0.0, yaw=0.0)
    px, py, pz = t.transform_point(1.0, 2.0, 3.0)
    assert px == pytest.approx(6.0)
    assert py == pytest.approx(7.0)
    assert pz == pytest.approx(8.0)


def test_transform3d_quaternion_roundtrip():
    t_orig = Transform3D(
        x=1.5,
        y=-2.0,
        z=3.5,
        roll=0.2,
        pitch=-0.3,
        yaw=1.1,
    )
    qx, qy, qz, qw = t_orig.quaternion

    t_recovered = Transform3D.from_quaternion(
        x=t_orig.x,
        y=t_orig.y,
        z=t_orig.z,
        qx=qx,
        qy=qy,
        qz=qz,
        qw=qw,
    )

    assert t_recovered.x == pytest.approx(t_orig.x)
    assert t_recovered.y == pytest.approx(t_orig.y)
    assert t_recovered.z == pytest.approx(t_orig.z)
    assert t_recovered.roll == pytest.approx(t_orig.roll, abs=1e-5)
    assert t_recovered.pitch == pytest.approx(t_orig.pitch, abs=1e-5)
    assert t_recovered.yaw == pytest.approx(t_orig.yaw, abs=1e-5)
