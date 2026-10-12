"""Ultralytics YOLO wrapper for COCO vehicle detections."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
from ultralytics import YOLO


VEHICLE_CLASS_NAMES = {
    2: "car",
    5: "bus",
    7: "truck",
}
AMBULANCE_CLASS_CONFIDENCE = 0.65


@dataclass(frozen=True)
class VehicleDetection:
    box: tuple[float, float, float, float]
    confidence: float
    class_name: str
    is_emergency: bool = False


class VehicleDetector:
    def __init__(self, model_path: str = "yolov8n.pt", confidence: float = 0.20) -> None:
        if not 0.0 < confidence <= 1.0:
            raise ValueError("confidence must be greater than 0 and at most 1")
        if not model_path:
            raise ValueError("model_path must not be empty")
        self.model_path = str(Path(model_path).expanduser())
        self.confidence = confidence
        self._model = YOLO(self.model_path)

    @staticmethod
    def _has_ambulance_colors(frame: np.ndarray, box: tuple[float, float, float, float]) -> bool:
        """Recognize a red-and-white toy ambulance even when COCO labels it as a car."""
        height, width = frame.shape[:2]
        x1, y1, x2, y2 = (int(round(value)) for value in box)
        x1, x2 = max(0, x1), min(width, x2)
        y1, y2 = max(0, y1), min(height, y2)
        crop = frame[y1:y2, x1:x2]
        if crop.size == 0:
            return False

        hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
        hue, saturation, value = cv2.split(hsv)
        red = (((hue <= 10) | (hue >= 170)) & (saturation >= 90) & (value >= 60))
        white = (saturation <= 70) & (value >= 175)
        pixel_count = float(crop.shape[0] * crop.shape[1])
        return (
            float(np.count_nonzero(red)) / pixel_count >= 0.06
            and float(np.count_nonzero(white)) / pixel_count >= 0.12
        )

    def detect(self, frame: np.ndarray) -> list[VehicleDetection]:
        results = self._model.predict(
            source=frame,
            classes=list(VEHICLE_CLASS_NAMES),
            conf=self.confidence,
            verbose=False,
        )
        detections: list[VehicleDetection] = []
        for result in results:
            if result.boxes is None:
                continue
            for box in result.boxes:
                class_id = int(box.cls.item())
                class_name = VEHICLE_CLASS_NAMES.get(class_id)
                if class_name is None:
                    continue
                coords = box.xyxy[0].tolist()
                bounds = (float(coords[0]), float(coords[1]), float(coords[2]), float(coords[3]))
                confidence = float(box.conf.item())
                detections.append(
                    VehicleDetection(
                        box=bounds,
                        confidence=confidence,
                        class_name=class_name,
                        is_emergency=(
                            (class_name in {"bus", "truck"} and confidence >= AMBULANCE_CLASS_CONFIDENCE)
                            or self._has_ambulance_colors(frame, bounds)
                        ),
                    )
                )
        return detections
