import numpy as np

from traffic_core import camera as camera_module
from traffic_core.camera import CameraStream


class FakeCapture:
    def __init__(self, *_):
        self.frames = [np.zeros((2, 2, 3), dtype=np.uint8), None, np.ones((2, 2, 3), dtype=np.uint8)]
        self.read_index = 0
        self.positions = []
        self.released = False

    def isOpened(self):
        return True

    def set(self, prop, value):
        if prop == camera_module.cv2.CAP_PROP_POS_FRAMES:
            self.positions.append(value)
            self.read_index = 2
        return True

    def get(self, prop):
        return 30.0

    def read(self):
        frame = self.frames[self.read_index]
        self.read_index += 1
        return frame is not None, frame

    def release(self):
        self.released = True


def test_video_file_loops_to_frame_zero_and_uses_source_fps(monkeypatch, tmp_path):
    capture = FakeCapture()
    monkeypatch.setattr(camera_module.cv2, "VideoCapture", lambda _source: capture)
    monkeypatch.setattr(camera_module.time, "sleep", lambda _seconds: None)
    stream = CameraStream(str(tmp_path / "sample.mp4"), max_fps=24.0)

    assert stream.read() is not None
    assert stream.read() is not None
    assert capture.positions == [0]
    assert stream._frame_interval == 1 / 24.0
    stream.release()
    assert capture.released


def test_video_fps_limit_slows_faster_recordings(monkeypatch, tmp_path):
    capture = FakeCapture()
    monkeypatch.setattr(camera_module.cv2, "VideoCapture", lambda _source: capture)
    stream = CameraStream(str(tmp_path / "sample.mp4"), max_fps=15.0)

    assert stream._frame_interval == 1 / 15.0
    stream.release()
