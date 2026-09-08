"""Concrete reusable stages for Effero pipelines."""

from __future__ import annotations

import asyncio
import inspect
from collections.abc import Awaitable, Callable
from typing import Any, Generic, TypeVar

from effero.pipelines.base import PipelineStage

InputT = TypeVar("InputT")
OutputT = TypeVar("OutputT")
ItemT = TypeVar("ItemT")


class FunctionStage(PipelineStage[InputT, OutputT]):
    """Pipeline stage executing a sync or async function."""

    def __init__(
        self,
        func: Callable[[InputT], OutputT | Awaitable[OutputT]],
        name: str | None = None,
    ) -> None:
        func_name = getattr(func, "__name__", "anonymous_func")
        super().__init__(name=name or func_name)
        self.func = func

    async def process(self, input_data: InputT) -> OutputT:
        res = self.func(input_data)
        if inspect.isawaitable(res):
            return await res  # type: ignore[no-any-return]
        return res  # type: ignore[no-any-return]


class FilterStage(PipelineStage[list[ItemT], list[ItemT]], Generic[ItemT]):
    """Pipeline stage that filters a list of items using a predicate function."""

    def __init__(
        self,
        predicate: Callable[[ItemT], bool | Awaitable[bool]],
        name: str | None = None,
    ) -> None:
        super().__init__(name=name or "FilterStage")
        self.predicate = predicate

    async def process(self, input_data: list[ItemT]) -> list[ItemT]:
        output: list[ItemT] = []
        for item in input_data:
            res = self.predicate(item)
            is_valid = await res if inspect.isawaitable(res) else res
            if is_valid:
                output.append(item)
        return output


class MapStage(PipelineStage[list[InputT], list[OutputT]], Generic[InputT, OutputT]):
    """Pipeline stage applying an item-wise transformation to an input list."""

    def __init__(
        self,
        transform: Callable[[InputT], OutputT | Awaitable[OutputT]],
        name: str | None = None,
    ) -> None:
        super().__init__(name=name or "MapStage")
        self.transform = transform

    async def process(self, input_data: list[InputT]) -> list[OutputT]:
        results: list[OutputT] = []
        for item in input_data:
            res = self.transform(item)
            val = await res if inspect.isawaitable(res) else res
            results.append(val)
        return results


class ParallelBranchStage(PipelineStage[InputT, dict[str, Any]], Generic[InputT]):
    """Executes multiple sub-stages or pipelines concurrently on the same input payload."""

    def __init__(
        self,
        branches: dict[str, PipelineStage[InputT, Any]],
        name: str = "ParallelBranches",
    ) -> None:
        super().__init__(name=name)
        self.branches = branches

    async def process(self, input_data: InputT) -> dict[str, Any]:
        keys = list(self.branches.keys())
        tasks = [self.branches[k].process(input_data) for k in keys]
        raw_results = await asyncio.gather(*tasks, return_exceptions=False)
        return dict(zip(keys, raw_results, strict=True))
