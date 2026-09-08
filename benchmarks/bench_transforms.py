"""Benchmark SE(2) and SE(3) transform composition."""

import math

import pytest

from effero.skills.robotics.transforms import Transform2D, Transform3D


@pytest.fixture
def chain_2d():
    """A list of 100 SE(2) transforms to compose."""
    return [
        Transform2D(x=0.1 * i, y=0.05 * i, theta=math.radians(3.6 * i))
        for i in range(100)
    ]


@pytest.fixture
def chain_3d():
    """A list of 50 SE(3) transforms to compose."""
    return [
        Transform3D.from_euler(
            x=0.1 * i, y=0.05 * i, z=0.02 * i,
            roll=math.radians(1.0 * i),
            pitch=math.radians(0.5 * i),
            yaw=math.radians(2.0 * i),
        )
        for i in range(50)
    ]


def test_compose_2d_chain(benchmark, chain_2d):
    """Benchmark composing 100 SE(2) transforms via @ operator."""
    def compose():
        result = chain_2d[0]
        for t in chain_2d[1:]:
            result = result @ t
        return result

    benchmark(compose)


def test_compose_3d_chain(benchmark, chain_3d):
    """Benchmark composing 50 SE(3) transforms via @ operator."""
    def compose():
        result = chain_3d[0]
        for t in chain_3d[1:]:
            result = result @ t
        return result

    benchmark(compose)


def test_inverse_2d(benchmark):
    """Benchmark SE(2) analytical inversion."""
    t = Transform2D(x=1.0, y=2.0, theta=math.radians(45))
    benchmark(t.inverse)
