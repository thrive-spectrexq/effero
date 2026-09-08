"""Composable pipeline package inspired by Scikit-learn and UNIX pipe chaining."""

from __future__ import annotations

from effero.pipelines.base import Pipeline, PipelineResult, PipelineStage, StageRecord
from effero.pipelines.stages import (
    FilterStage,
    FunctionStage,
    MapStage,
    ParallelBranchStage,
)

__all__ = [
    "Pipeline",
    "PipelineStage",
    "PipelineResult",
    "StageRecord",
    "FunctionStage",
    "FilterStage",
    "MapStage",
    "ParallelBranchStage",
]
