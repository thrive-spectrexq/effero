"""2D Occupancy Grid Map with obstacle rasterization and radial collision inflation."""

from __future__ import annotations

import math
from typing import Any


class OccupancyGridMap:
    """2D spatial grid map with discrete cell rasterization and obstacle inflation."""

    FREE: int = 0
    OBSTACLE: int = 1
    INFLATED: int = 2

    def __init__(
        self,
        min_x: float = -10.0,
        min_y: float = -10.0,
        max_x: float = 10.0,
        max_y: float = 10.0,
        resolution: float = 0.1,
    ) -> None:
        if max_x <= min_x or max_y <= min_y:
            raise ValueError("Map boundaries must satisfy min < max")
        if resolution <= 0:
            raise ValueError("Resolution must be positive")

        self.min_x = float(min_x)
        self.min_y = float(min_y)
        self.max_x = float(max_x)
        self.max_y = float(max_y)
        self.resolution = float(resolution)

        self.width_cells = int(math.ceil((self.max_x - self.min_x) / self.resolution))
        self.height_cells = int(math.ceil((self.max_y - self.min_y) / self.resolution))

        # Flat bytearray representing cells (row-major: index = gy * width_cells + gx)
        self._cells = bytearray(self.width_cells * self.height_cells)
        self._raw_obstacles: set[tuple[int, int]] = set()

    def world_to_grid(self, x: float, y: float) -> tuple[int, int]:
        """Convert continuous Cartesian world coordinates (meters) to discrete grid indices."""
        gx = int(math.floor((x - self.min_x) / self.resolution))
        gy = int(math.floor((y - self.min_y) / self.resolution))
        return gx, gy

    def grid_to_world(self, gx: int, gy: int) -> tuple[float, float]:
        """Convert discrete grid indices to continuous Cartesian world coordinates (cell center)."""
        x = self.min_x + (gx + 0.5) * self.resolution
        y = self.min_y + (gy + 0.5) * self.resolution
        return round(x, 4), round(y, 4)

    def in_bounds(self, gx: int, gy: int) -> bool:
        """Check if grid coordinates fall within the map boundaries."""
        return 0 <= gx < self.width_cells and 0 <= gy < self.height_cells

    def _get_cell(self, gx: int, gy: int) -> int:
        return self._cells[gy * self.width_cells + gx]

    def _set_cell(self, gx: int, gy: int, value: int) -> None:
        self._cells[gy * self.width_cells + gx] = value

    def is_grid_occupied(self, gx: int, gy: int, include_inflated: bool = True) -> bool:
        """Check if a specific grid cell is occupied by an obstacle or inflation layer."""
        if not self.in_bounds(gx, gy):
            return True  # Out-of-bounds is considered occupied
        val = self._get_cell(gx, gy)
        if include_inflated:
            return val != self.FREE
        return val == self.OBSTACLE

    def is_occupied(self, x: float, y: float, include_inflated: bool = True) -> bool:
        """Check if Cartesian world coordinates fall inside an obstacle or inflation layer."""
        gx, gy = self.world_to_grid(x, y)
        return self.is_grid_occupied(gx, gy, include_inflated=include_inflated)

    def set_obstacle(self, x: float, y: float) -> None:
        """Mark Cartesian world coordinate as an obstacle cell."""
        gx, gy = self.world_to_grid(x, y)
        if self.in_bounds(gx, gy):
            self._set_cell(gx, gy, self.OBSTACLE)
            self._raw_obstacles.add((gx, gy))

    def add_rectangular_obstacle(self, min_x: float, min_y: float, max_x: float, max_y: float) -> None:
        """Rasterize a filled axis-aligned rectangular obstacle."""
        gx0, gy0 = self.world_to_grid(min_x, min_y)
        gx1, gy1 = self.world_to_grid(max_x, max_y)

        min_gx, max_gx = max(0, min(gx0, gx1)), min(self.width_cells - 1, max(gx0, gx1))
        min_gy, max_gy = max(0, min(gy0, gy1)), min(self.height_cells - 1, max(gy0, gy1))

        for gy in range(min_gy, max_gy + 1):
            for gx in range(min_gx, max_gx + 1):
                self._set_cell(gx, gy, self.OBSTACLE)
                self._raw_obstacles.add((gx, gy))

    def add_circular_obstacle(self, center_x: float, center_y: float, radius: float) -> None:
        """Rasterize a filled circular obstacle."""
        cgx, cgy = self.world_to_grid(center_x, center_y)
        r_cells = int(math.ceil(radius / self.resolution))

        min_gx = max(0, cgx - r_cells)
        max_gx = min(self.width_cells - 1, cgx + r_cells)
        min_gy = max(0, cgy - r_cells)
        max_gy = min(self.height_cells - 1, cgy + r_cells)

        r_cells_sq = (radius / self.resolution) ** 2

        for gy in range(min_gy, max_gy + 1):
            for gx in range(min_gx, max_gx + 1):
                dist_sq = (gx - cgx) ** 2 + (gy - cgy) ** 2
                if dist_sq <= r_cells_sq:
                    self._set_cell(gx, gy, self.OBSTACLE)
                    self._raw_obstacles.add((gx, gy))

    def add_line_obstacle(self, x0: float, y0: float, x1: float, y1: float) -> None:
        """Rasterize a wall/line segment using Bresenham's line algorithm."""
        gx0, gy0 = self.world_to_grid(x0, y0)
        gx1, gy1 = self.world_to_grid(x1, y1)

        dx = abs(gx1 - gx0)
        dy = abs(gy1 - gy0)
        sx = 1 if gx0 < gx1 else -1
        sy = 1 if gy0 < gy1 else -1
        err = dx - dy

        curr_x, curr_y = gx0, gy0
        while True:
            if self.in_bounds(curr_x, curr_y):
                self._set_cell(curr_x, curr_y, self.OBSTACLE)
                self._raw_obstacles.add((curr_x, curr_y))

            if curr_x == gx1 and curr_y == gy1:
                break

            e2 = 2 * err
            if e2 > -dy:
                err -= dy
                curr_x += sx
            if e2 < dx:
                err += dx
                curr_y += sy

    def inflate_obstacles(self, robot_radius: float) -> None:
        """Inflate obstacles radially by robot radius to convert robot into a point-mass planner."""
        if robot_radius <= 0:
            return

        r_cells = int(math.ceil(robot_radius / self.resolution))
        r_cells_sq = (robot_radius / self.resolution) ** 2

        # Precompute kernel offsets
        offsets: list[tuple[int, int]] = []
        for dy in range(-r_cells, r_cells + 1):
            for dx in range(-r_cells, r_cells + 1):
                if dx == 0 and dy == 0:
                    continue
                if dx * dx + dy * dy <= r_cells_sq:
                    offsets.append((dx, dy))

        # Clear existing inflation
        for gy in range(self.height_cells):
            for gx in range(self.width_cells):
                if self._get_cell(gx, gy) == self.INFLATED:
                    self._set_cell(gx, gy, self.FREE)

        # Apply inflation around all raw obstacles
        for ogx, ogy in self._raw_obstacles:
            for dx, dy in offsets:
                igx = ogx + dx
                igy = ogy + dy
                if self.in_bounds(igx, igy) and self._get_cell(igx, igy) == self.FREE:
                    self._set_cell(igx, igy, self.INFLATED)

    def is_line_clear(self, x0: float, y0: float, x1: float, y1: float) -> bool:
        """Ray-cast between two continuous coordinates to check for collision-free line of sight."""
        gx0, gy0 = self.world_to_grid(x0, y0)
        gx1, gy1 = self.world_to_grid(x1, y1)

        dx = abs(gx1 - gx0)
        dy = abs(gy1 - gy0)
        sx = 1 if gx0 < gx1 else -1
        sy = 1 if gy0 < gy1 else -1
        err = dx - dy

        curr_x, curr_y = gx0, gy0
        while True:
            if not self.in_bounds(curr_x, curr_y) or self.is_grid_occupied(curr_x, curr_y):
                return False

            if curr_x == gx1 and curr_y == gy1:
                break

            e2 = 2 * err
            if e2 > -dy:
                err -= dy
                curr_x += sx
            if e2 < dx:
                err += dx
                curr_y += sy

        return True

    def to_dict(self) -> dict[str, Any]:
        """Serialize occupancy grid metadata and raw obstacle counts."""
        return {
            "min_x": self.min_x,
            "min_y": self.min_y,
            "max_x": self.max_x,
            "max_y": self.max_y,
            "resolution": self.resolution,
            "width_cells": self.width_cells,
            "height_cells": self.height_cells,
            "obstacle_cells_count": len(self._raw_obstacles),
        }
