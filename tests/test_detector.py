from types import SimpleNamespace

import numpy as np

from traffic_core.detector import VehicleDetector


class FakeBox:
    def __init__(self, class_id, confidence, coordinates):
        self.cls = SimpleNamespace(item=lambda: class_id)
        self.conf = SimpleNamespace(item=lambda: confidence)
        self.xyxy = [SimpleNamespace(tolist=lambda: coordinates)]


def test_uses_lower_vehicle_threshold_and_flags_toy_ambulance(monkeypatch):
    class FakeYOLO:
        def __init__(self, model_path):
            self.model_path = model_path

        def predict(self, **kwargs):
            self.predict_args = kwargs
            return [
                SimpleNamespace(
                    boxes=[
                        FakeBox(2, 0.24, [0, 0, 20, 20]),
                        FakeBox(7, 0.80, [20, 0, 40, 20]),
                        FakeBox(3, 0.99, [40, 0, 60, 20]),
                    ]
                )
            ]

    monkeypatch.setattr("traffic_core.detector.YOLO", FakeYOLO)
    detector = VehicleDetector("toy-model.pt")
    frame = np.zeros((20, 60, 3), dtype=np.uint8)
    frame[:, :10] = (0, 0, 255)
    frame[:, 10:20] = (255, 255, 255)

    detections = detector.detect(frame)

    assert detector.confidence == 0.20
    assert detector._model.predict_args["conf"] == 0.20
    assert detector._model.predict_args["classes"] == [2, 5, 7]
    assert len(detections) == 2
    assert detections[0].class_name == "car"
    assert detections[0].is_emergency  # red-and-white livery, despite a car label
    assert detections[1].class_name == "truck"
    assert detections[1].is_emergency  # high-confidence bus/truck fallback
