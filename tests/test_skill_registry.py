"""Tests for skill registration, lookup, and the @skill decorator."""
from __future__ import annotations

import functools
import inspect

from effero.sdk.skill import SafetyClass, SkillRegistry, SkillSpec, skill
from effero.sdk.skill import registry as default_registry


def make_registry() -> SkillRegistry:
    """A fresh, isolated registry per test so tests can't clash."""
    return SkillRegistry()


def test_skill_registration_and_direct_call() -> None:
    reg = make_registry()
    
    def echo_fn(value: str) -> str:
        return value
    
    spec = SkillSpec(
        name="test.echo",
        description="Echo a value back.",
        safety_class=SafetyClass.READ_ONLY,
        func=echo_fn,
        signature=inspect.signature(echo_fn),
    )
    functools.update_wrapper(spec, echo_fn)
    reg.register(spec)

    assert spec("hello") == "hello"
    assert spec.name == "test.echo"
    assert spec.safety_class is SafetyClass.READ_ONLY


def test_registry_get_and_list() -> None:
    reg = make_registry()

    def add_fn(a: int, b: int) -> int:
        return a + b

    spec = SkillSpec(
        name="test.add",
        description="Add two numbers.",
        safety_class=SafetyClass.READ_ONLY,
        func=add_fn,
        signature=inspect.signature(add_fn),
    )
    reg.register(spec)

    assert "test.add" in reg.list()
    retrieved = reg.get("test.add")
    assert retrieved.name == "test.add"
    assert retrieved(2, 3) == 5


def test_duplicate_registration_raises() -> None:
    reg = make_registry()

    def first_fn() -> int:
        return 1

    spec1 = SkillSpec(
        name="test.dup",
        description="First",
        safety_class=SafetyClass.READ_ONLY,
        func=first_fn,
        signature=inspect.signature(first_fn),
    )
    reg.register(spec1)

    def second_fn() -> int:
        return 2

    spec2 = SkillSpec(
        name="test.dup",
        description="Second",
        safety_class=SafetyClass.READ_ONLY,
        func=second_fn,
        signature=inspect.signature(second_fn),
    )

    try:
        reg.register(spec2)
    except ValueError as exc:
        assert "already registered" in str(exc)
    else:
        raise AssertionError("Expected ValueError for a duplicate skill name")


def test_clear_removes_all_skills() -> None:
    reg = make_registry()

    spec = SkillSpec(
        name="test.clear_me",
        description="Temp",
        safety_class=SafetyClass.READ_ONLY,
        func=lambda: None,
        signature=inspect.signature(lambda: None),
    )
    reg.register(spec)
    assert len(reg.list()) == 1

    reg.clear()
    assert len(reg.list()) == 0


def test_skill_decorator_registers_to_global_registry() -> None:
    default_registry.clear()

    @skill(
        name="test.decorated",
        description="A decorated skill.",
        safety_class=SafetyClass.READ_ONLY,
    )
    def decorated_fn(x: int) -> int:
        return x * 2

    assert "test.decorated" in default_registry.list()
    assert decorated_fn(5) == 10
    assert decorated_fn.name == "test.decorated"

    default_registry.clear()
