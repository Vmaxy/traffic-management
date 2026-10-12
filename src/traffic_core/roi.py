"""Reference-resolution approach polygons and vehicle-to-lane assignment."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Sequence

import cv2
import numpy as np


LANES = ("NORTH", "SOUTH", "EAST", "WEST")
Box = Sequence[float]


@dataclass(frozen=True)
class LaneOccupancy:
    counts: Mapping[str, int]
    emergency_lanes: frozenset[str]
    assigned_lanes: tuple[str | None, ...]


class ROIManager:
    def __init__(self, config_path: str | Path) -> None:
        self.config_path = Path(config_path)
        try:
            with self.config_path.open("r", encoding="utf-8") as config_file:
                raw_config = json.load(config_file)
        except OSError as exc:
            raise OSError(f"Unable to read ROI configuration {self.config_path}: {exc}") from exc
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON in ROI configuration {self.config_path}: {exc}") from exc

        if not isinstance(raw_config, dict):
            raise ValueError("ROI configuration must be a JSON object")

        # Legacy lane maps use normalized coordinates; the current format stores
        # pixel coordinates together with the dimensions they were drawn against.
        self._normalized_coordinates = "lanes" not in raw_config and "reference_resolution" not in raw_config
        raw_rois = raw_config.get("lanes", raw_config)
        if not isinstance(raw_rois, dict):
            raise ValueError("ROI lanes must be a JSON object keyed by lane name")

        self._reference_width = 1.0
        self._reference_height = 1.0
        if not self._normalized_coordinates:
            resolution = raw_config.get("reference_resolution")
            if not isinstance(resolution, dict):
                raise ValueError("reference_resolution must contain width and height")
            try:
                self._reference_width = float(resolution["width"])
                self._reference_height = float(resolution["height"])
            except (KeyError, TypeError, ValueError) as exc:
                raise ValueError("reference_resolution width and height must be positive numbers") from exc
            if (
                not np.isfinite([self._reference_width, self._reference_height]).all()
                or self._reference_width <= 0
                or self._reference_height <= 0
            ):
                raise ValueError("reference_resolution width and height must be positive numbers")

        self._reference_polygons: dict[str, np.ndarray] = {}
        for lane in LANES:
            points = raw_rois.get(lane)
            if not isinstance(points, list) or len(points) < 3:
                raise ValueError(f"ROI {lane} must contain at least three points")
            try:
                polygon = np.asarray(points, dtype=np.float32)
            except (TypeError, ValueError) as exc:
                raise ValueError(f"ROI {lane} points must be numeric coordinate pairs") from exc
            if polygon.ndim != 2 or polygon.shape[1] != 2:
                raise ValueError(f"ROI {lane} points must each contain exactly two coordinates")
            if not np.isfinite(polygon).all():
                raise ValueError(f"ROI {lane} coordinates must be finite")
            if self._normalized_coordinates and ((polygon < 0.0) | (polygon > 1.0)).any():
                raise ValueError(f"ROI {lane} normalized coordinates must be between 0.0 and 1.0")
            if cv2.contourArea(polygon) == 0:
                raise ValueError(f"ROI {lane} must enclose a non-zero area")
            self._reference_polygons[lane] = polygon

        self._width = 0
        self._height = 0
        self._scaled: dict[str, np.ndarray] = {}

    def update_resolution(self, width: int, height: int) -> None:
        if width <= 0 or height <= 0:
            raise ValueError("frame width and height must be greater than zero")
        self._width = width
        self._height = height
        if self._normalized_coordinates:
            scale = np.array([width - 1, height - 1], dtype=np.float32)
        else:
            scale = np.array(
                [width / self._reference_width, height / self._reference_height],
                dtype=np.float32,
            )
        self._scaled = {
            lane: np.rint(points * scale).astype(np.int32)
            for lane, points in self._reference_polygons.items()
        }

    @property
    def polygons(self) -> Mapping[str, np.ndarray]:
        return {lane: polygon.copy() for lane, polygon in self._scaled.items()}

    @staticmethod
    def anchor_point(box: Box, anchor: str = "bottom_center") -> tuple[float, float]:
        if len(box) != 4:
            raise ValueError("box must contain x1, y1, x2, and y2")
        x1, y1, x2, y2 = (float(value) for value in box)
        if anchor == "bottom_center":
            return (x1 + x2) / 2.0, y2
        if anchor == "center":
            return (x1 + x2) / 2.0, (y1 + y2) / 2.0
        raise ValueError("anchor must be 'bottom_center' or 'center'")

    def assign_box(self, box: Box, anchor: str = "bottom_center") -> str | None:
        if not self._scaled:
            raise RuntimeError("Call update_resolution before assigning detections")
        point = self.anchor_point(box, anchor)
        for lane in LANES:
            if cv2.pointPolygonTest(self._scaled[lane], point, False) >= 0:
                return lane
        return None

    def count_detections(self, detections: Sequence[object]) -> LaneOccupancy:
        """Count vehicles and retain lane assignments plus emergency approaches."""
        counts = {lane: 0 for lane in LANES}
        emergency_lanes: set[str] = set()
        assigned_lanes: list[str | None] = []
        for detection in detections:
            lane = self.assign_box(getattr(detection, "box"))
            assigned_lanes.append(lane)
            if lane is None:
                continue
            counts[lane] += 1
            if bool(getattr(detection, "is_emergency", False)):
                emergency_lanes.add(lane)
        return LaneOccupancy(counts, frozenset(emergency_lanes), tuple(assigned_lanes))
