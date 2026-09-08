"""Composable pipeline architecture inspired by Scikit-learn and UNIX pipe chaining.

Provides typed PipelineStage abstractions and Pipeline composition with the '|' operator.
"""

from __future__ import annotations

import asyncio
import inspect
import time
from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any, Generic, TypeVar

InputT = TypeVar("InputT")
OutputT = TypeVar("OutputT")


@dataclass
class StageRecord:
    """Execution telemetry record for a single stage within a pipeline run."""

    stage_name: str
    elapsed_seconds: float
    success: bool
    error: str | None = None


@dataclass
class PipelineResult(Generic[OutputT]):
    """Final result of pipeline execution with execution profile metadata."""

    output: OutputT
    records: list[StageRecord] = field(default_factory=list)
    total_elapsed_seconds: float = 0.0

    @property
    def stage_durations(self) -> dict[str, float]:
        """Map of stage name to elapsed execution time in seconds."""
        return {r.stage_name: r.elapsed_seconds for r in self.records}


class PipelineStage(ABC, Generic[InputT, OutputT]):
    """Abstract base class for a composable computational or cognitive pipeline stage."""

    def __init__(self, name: str | None = None) -> None:
        self.name = name or self.__class__.__name__

    @abstractmethod
    async def process(self, input_data: InputT) -> OutputT:
        """Process input data and return stage output."""
        pass

    def __or__(self, other: PipelineStage[OutputT, Any] | Pipeline) -> Pipeline:
        """Chain this stage with another stage or pipeline using the pipe '|' operator."""
        if isinstance(other, Pipeline):
            return Pipeline(steps=[self, *other.stages], name=f"{self.name}_to_{other.name}")
        elif isinstance(other, PipelineStage):
            return Pipeline(steps=[self, other], name=f"{self.name}_to_{other.name}")
        return NotImplemented


class Pipeline:
    """Sequential execution pipeline of composable stages."""

    def __init__(
        self,
        steps: Sequence[PipelineStage[Any, Any] | tuple[str, PipelineStage[Any, Any]]] | None = None,
        name: str = "Pipeline",
    ) -> None:
        self.name = name
        self.stages: list[PipelineStage[Any, Any]] = []
        if steps:
            for step in steps:
                if isinstance(step, tuple):
                    stage_name, stage_obj = step
                    stage_obj.name = stage_name
                    self.stages.append(stage_obj)
                elif isinstance(step, PipelineStage):
                    self.stages.append(step)
                else:
                    raise TypeError(f"Expected PipelineStage or (name, stage) tuple, got {type(step)}")

    def add_stage(self, stage: PipelineStage[Any, Any], name: str | None = None) -> Pipeline:
        """Append a stage to the pipeline."""
        if name:
            stage.name = name
        self.stages.append(stage)
        return self

    @property
    def named_steps(self) -> dict[str, PipelineStage[Any, Any]]:
        """Dictionary of stages keyed by name."""
        return {s.name: s for s in self.stages}

    async def run(self, initial_input: Any) -> PipelineResult[Any]:
        """Execute all stages sequentially, passing output of each stage to the next."""
        current_data = initial_input
        records: list[StageRecord] = []
        t_start = time.perf_counter()

        for stage in self.stages:
            t0 = time.perf_counter()
            try:
                res = stage.process(current_data)
                if inspect.isawaitable(res):
                    current_data = await res
                else:
                    current_data = res
                dt = time.perf_counter() - t0
                records.append(StageRecord(stage_name=stage.name, elapsed_seconds=dt, success=True))
            except Exception as e:
                dt = time.perf_counter() - t0
                records.append(
                    StageRecord(
                        stage_name=stage.name,
                        elapsed_seconds=dt,
                        success=False,
                        error=str(e),
                    )
                )
                raise RuntimeError(f"Pipeline '{self.name}' failed at stage '{stage.name}': {e}") from e

        total_dt = time.perf_counter() - t_start
        return PipelineResult(
            output=current_data,
            records=records,
            total_elapsed_seconds=total_dt,
        )

    def run_sync(self, initial_input: Any) -> PipelineResult[Any]:
        """Synchronous wrapper for executing pipeline within an event loop."""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            import concurrent.futures

            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                return pool.submit(lambda: asyncio.run(self.run(initial_input))).result()
        else:
            return asyncio.run(self.run(initial_input))

    def __or__(self, other: PipelineStage[Any, Any] | Pipeline) -> Pipeline:
        if isinstance(other, Pipeline):
            return Pipeline(steps=[*self.stages, *other.stages], name=f"{self.name}_chained_{other.name}")
        elif isinstance(other, PipelineStage):
            return Pipeline(steps=[*self.stages, other], name=f"{self.name}_chained_{other.name}")
        return NotImplemented

    def __len__(self) -> int:
        return len(self.stages)

    def __getitem__(self, key: int | str | slice) -> Any:
        if isinstance(key, int):
            return self.stages[key]
        elif isinstance(key, str):
            return self.named_steps[key]
        elif isinstance(key, slice):
            return Pipeline(steps=self.stages[key], name=f"{self.name}_slice")
        raise TypeError(f"Invalid key type: {type(key)}")
