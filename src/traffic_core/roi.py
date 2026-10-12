"""Normalized approach polygons and vehicle-to-lane assignment."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Mapping, Sequence

import cv2
import numpy as np


LANES = ("NORTH", "SOUTH", "EAST", "WEST")
Box = Sequence[float]


class ROIManager:
    def __init__(self, config_path: str | Path) -> None:
        self.config_path = Path(config_path)
        try:
            with self.config_path.open("r", encoding="utf-8") as config_file:
                raw_rois = json.load(config_file)
        except OSError as exc:
            raise OSError(f"Unable to read ROI configuration {self.config_path}: {exc}") from exc
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON in ROI configuration {self.config_path}: {exc}") from exc

        if not isinstance(raw_rois, dict):
            raise ValueError("ROI configuration must be a JSON object keyed by lane name")

        self._normalized: dict[str, np.ndarray] = {}
        for lane in LANES:
            points = raw_rois.get(lane)
            if not isinstance(points, list) or len(points) < 3:
                raise ValueError(f"ROI {lane} must contain at least three normalized points")
            try:
                polygon = np.asarray(points, dtype=np.float32)
            except (TypeError, ValueError) as exc:
                raise ValueError(f"ROI {lane} points must be numeric coordinate pairs") from exc
            if polygon.ndim != 2 or polygon.shape[1] != 2:
                raise ValueError(f"ROI {lane} points must each contain exactly two coordinates")
            if not np.isfinite(polygon).all() or ((polygon < 0.0) | (polygon > 1.0)).any():
                raise ValueError(f"ROI {lane} coordinates must be finite and between 0.0 and 1.0")
            self._normalized[lane] = polygon

        self._width = 0
        self._height = 0
        self._scaled: dict[str, np.ndarray] = {}

    def update_resolution(self, width: int, height: int) -> None:
        if width <= 0 or height <= 0:
            raise ValueError("frame width and height must be greater than zero")
        self._width = width
        self._height = height
        self._scaled = {
            lane: np.rint(points * np.array([width - 1, height - 1])).astype(np.int32)
            for lane, points in self._normalized.items()
        }

    @property
    def polygons(self) -> Mapping[str, np.ndarray]:
        return self._scaled.copy()

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
