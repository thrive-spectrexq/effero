from effero.core.agent import Agent
from effero.sdk.skill import SafetyClass, SkillRegistry, skill


def make_registry() -> SkillRegistry:
    """A fresh, isolated registry per test so tests can't clash with
    each other or with skills registered elsewhere in the process.
    """
    return SkillRegistry()


def test_skill_registration_and_direct_call() -> None:
    @skill(
        name="test.echo",
        description="Echo a value back. Used only in tests.",
        safety_class=SafetyClass.READ_ONLY,
    )
    def _echo(value: str) -> str:
        return value

    # The decorator registers against the module-level default registry
    # by design (see effero.sdk.skill.registry); this test just checks
    # the resulting SkillSpec behaves correctly when called directly.
    assert _echo("hello") == "hello"
    assert _echo.name == "test.echo"
    assert _echo.safety_class is SafetyClass.READ_ONLY


def test_duplicate_registration_raises() -> None:
    reg = make_registry()

    @reg_skill(reg, "test.dup", SafetyClass.READ_ONLY)
    def _first() -> int:
        return 1

    try:

        @reg_skill(reg, "test.dup", SafetyClass.READ_ONLY)
        def _second() -> int:
            return 2

    except ValueError as exc:
        assert "already registered" in str(exc)
    else:
        raise AssertionError("Expected ValueError for a duplicate skill name")


def test_agent_can_list_and_invoke_registered_skills() -> None:
    from effero.sdk.skill import registry as default_registry

    default_registry.clear()

    @skill(
        name="test.add",
        description="Add two numbers. Used only in tests.",
        safety_class=SafetyClass.READ_ONLY,
    )
    def _add(a: int, b: int) -> int:
        return a + b

    agent = Agent(name="test-agent")

    assert "test.add" in agent.available_skills()
    assert agent.invoke_skill("test.add", a=2, b=3) == 5
    assert agent.history[-1].skill_name == "test.add"
    assert agent.history[-1].result == 5


def reg_skill(reg: SkillRegistry, name: str, safety_class: SafetyClass):
    """Helper: register directly against a specific SkillRegistry instance
    rather than the module-level default (used to test duplicate-name
    handling in isolation).
    """
    import functools
    import inspect

    from effero.sdk.skill import SkillSpec

    def decorator(func):
        spec = SkillSpec(
            name=name,
            description="test helper skill",
            safety_class=safety_class,
            func=func,
            signature=inspect.signature(func),
        )
        functools.update_wrapper(spec, func)
        reg.register(spec)
        return spec

    return decorator
