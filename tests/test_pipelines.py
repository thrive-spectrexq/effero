"""Tests for composable pipelines and execution stages."""

import asyncio

import pytest

from effero.pipelines import (
    FilterStage,
    FunctionStage,
    MapStage,
    ParallelBranchStage,
    Pipeline,
)


def test_pipeline_pipe_operator_composition():
    stage1 = FunctionStage(lambda x: x + 1, name="inc")
    stage2 = FunctionStage(lambda x: x * 2, name="double")
    stage3 = FunctionStage(lambda x: f"val={x}", name="format")

    pipeline = stage1 | stage2 | stage3
    assert len(pipeline) == 3
    assert pipeline.stages[0].name == "inc"
    assert pipeline.stages[1].name == "double"
    assert pipeline.stages[2].name == "format"

    result = pipeline.run_sync(5)  # (5 + 1) * 2 = 12 -> "val=12"
    assert result.output == "val=12"
    assert len(result.records) == 3
    assert result.records[0].success is True
    assert result.total_elapsed_seconds >= 0.0


@pytest.mark.asyncio
async def test_async_function_stage():
    async def async_fetch(val: str) -> str:
        await asyncio.sleep(0.01)
        return f"fetched:{val}"

    stage = FunctionStage(async_fetch, name="fetch")
    pipe = Pipeline([stage])

    res = await pipe.run("sample_data")
    assert res.output == "fetched:sample_data"
    assert "fetch" in res.stage_durations


@pytest.mark.asyncio
async def test_map_and_filter_stages():
    numbers = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]

    filter_even = FilterStage(lambda n: n % 2 == 0, name="even_only")
    square_all = MapStage(lambda n: n**2, name="square")

    pipe = filter_even | square_all
    res = await pipe.run(numbers)

    # Evens: [2, 4, 6, 8, 10] -> Squared: [4, 16, 36, 64, 100]
    assert res.output == [4, 16, 36, 64, 100]


@pytest.mark.asyncio
async def test_parallel_branch_stage():
    branch1 = FunctionStage(lambda text: len(text), name="length")
    branch2 = FunctionStage(lambda text: text.upper(), name="uppercase")
    branch3 = FunctionStage(lambda text: text.split(), name="tokens")

    parallel = ParallelBranchStage(
        branches={
            "len": branch1,
            "upper": branch2,
            "words": branch3,
        },
        name="multi_analyzer",
    )

    pipe = Pipeline([parallel])
    res = await pipe.run("Effero Autonomous System")

    assert res.output["len"] == len("Effero Autonomous System")
    assert res.output["upper"] == "EFFERO AUTONOMOUS SYSTEM"
    assert res.output["words"] == ["Effero", "Autonomous", "System"]


def test_pipeline_indexing_and_slicing():
    s1 = FunctionStage(lambda x: x + 1, name="first")
    s2 = FunctionStage(lambda x: x + 2, name="second")
    s3 = FunctionStage(lambda x: x + 3, name="third")

    pipe = s1 | s2 | s3
    assert pipe[0].name == "first"
    assert pipe["second"].name == "second"

    sub_pipe = pipe[1:3]
    assert len(sub_pipe) == 2
    assert sub_pipe[0].name == "second"
    assert sub_pipe[1].name == "third"


def test_pipeline_error_handling():
    def failing_stage(x: int) -> int:
        raise ValueError("Invalid arithmetic input")

    s1 = FunctionStage(lambda x: x + 10, name="valid_stage")
    s2 = FunctionStage(failing_stage, name="bad_stage")

    pipe = s1 | s2
    with pytest.raises(RuntimeError) as exc_info:
        pipe.run_sync(5)

    assert "failed at stage 'bad_stage'" in str(exc_info.value)
