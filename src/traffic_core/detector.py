"""Ultralytics YOLO wrapper for COCO vehicle detections."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
from ultralytics import YOLO


VEHICLE_CLASS_NAMES = {
    2: "car",
    3: "motorcycle",
    5: "bus",
    7: "truck",
}


@dataclass(frozen=True)
class VehicleDetection:
    box: tuple[float, float, float, float]
    confidence: float
    class_name: str


class VehicleDetector:
    def __init__(self, model_path: str = "yolov8n.pt", confidence: float = 0.35) -> None:
        if not 0.0 < confidence <= 1.0:
            raise ValueError("confidence must be greater than 0 and at most 1")
        if not model_path:
            raise ValueError("model_path must not be empty")
        self.model_path = str(Path(model_path).expanduser())
        self.confidence = confidence
        self._model = YOLO(self.model_path)

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
                detections.append(
                    VehicleDetection(
                        box=(float(coords[0]), float(coords[1]), float(coords[2]), float(coords[3])),
                        confidence=float(box.conf.item()),
                        class_name=class_name,
                    )
                )
        return detections
