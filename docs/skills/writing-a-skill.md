# Writing a Skill

Skills are the easiest and most impactful contribution to Effero. A skill is a plain Python function wrapped with the `@skill` decorator.

## Step-by-step

### 1. Pick the right subpackage

- `src/effero/skills/robotics/` — robot motion, navigation, manipulation
- `src/effero/skills/iot/` — smart home, sensors, actuators
- `src/effero/skills/computer_use/` — shell, browser, file operations
- `src/effero/skills/community/` — anything that doesn't fit above

### 2. Write the skill

```python
from effero.sdk import skill, SafetyClass

@skill(
    name="community.weather.get_forecast",
    description="Get the weather forecast for a given city.",
    safety_class=SafetyClass.READ_ONLY,
)
def get_forecast(city: str, days: int = 3) -> dict:
    """Fetch weather forecast from a public API."""
    # Your implementation here
    return {"city": city, "days": days, "forecast": "sunny"}
```

### 3. Choose the safety class deliberately

- **`READ_ONLY`** — for anything that cannot change external state.
- **`ACT_AUTONOMOUS`** — only for actions you're confident are safe unattended.
- **`ACT_WITH_APPROVAL`** — for anything with real-world consequences.
- **`ACT_RESTRICTED`** — the default for new community skills (simulation-only until promoted).

### 4. Add a test

Create a test file under `tests/`:

```python
def test_get_forecast():
    from effero.skills.community.weather import get_forecast
    result = get_forecast("London", days=1)
    assert result["city"] == "London"
    assert "forecast" in result
```

### 5. Submit your PR

See [Contributing](../contributing.md) for the full PR checklist.
