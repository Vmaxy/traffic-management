"""Video capture with periodic reconnection attempts."""

from __future__ import annotations

import logging
import math
import time

import cv2
import numpy as np


LOGGER = logging.getLogger(__name__)


class CameraStream:
    def __init__(
        self,
        source: int | str,
        retry_seconds: float = 2.0,
        max_fps: float = 30.0,
    ) -> None:
        if retry_seconds <= 0:
            raise ValueError("retry_seconds must be greater than zero")
        if not math.isfinite(max_fps) or max_fps <= 0:
            raise ValueError("max_fps must be greater than zero")
        self.source = source
        self.retry_seconds = retry_seconds
        self.max_fps = max_fps
        self._capture: cv2.VideoCapture | None = None
        self._next_attempt = 0.0
        self._next_frame_at = 0.0
        self._frame_interval = 1.0 / max_fps
        self._is_file = isinstance(source, str) and not source.lower().startswith(
            ("rtsp://", "rtsps://", "http://", "https://")
        )
        self._reported_failure = False
        self._open()

    def _open(self) -> bool:
        capture = cv2.VideoCapture(self.source)
        if capture.isOpened():
            capture.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            self._capture = capture
            if self._is_file:
                source_fps = capture.get(cv2.CAP_PROP_FPS)
                if math.isfinite(source_fps) and source_fps > 0:
                    self._frame_interval = 1.0 / min(source_fps, self.max_fps)
                self._next_frame_at = 0.0
            self._reported_failure = False
            LOGGER.info("Connected to video source %r", self.source)
            return True

        capture.release()
        self._capture = None
        self._next_attempt = time.monotonic() + self.retry_seconds
        if not self._reported_failure:
            LOGGER.warning("Unable to open video source %r; retrying", self.source)
            self._reported_failure = True
        return False

    def read(self) -> np.ndarray | None:
        if self._capture is None:
            if time.monotonic() < self._next_attempt or not self._open():
                return None

        assert self._capture is not None
        if self._is_file:
            now = time.monotonic()
            if self._next_frame_at > now:
                time.sleep(self._next_frame_at - now)
        ok, frame = self._capture.read()
        if not ok and self._is_file:
            LOGGER.info("Video file %r reached its end; restarting from frame 0", self.source)
            self._capture.set(cv2.CAP_PROP_POS_FRAMES, 0)
            ok, frame = self._capture.read()
        if ok and frame is not None:
            if self._is_file:
                self._next_frame_at = time.monotonic() + self._frame_interval
            return frame

        LOGGER.warning("Video source %r stopped returning frames; reconnecting", self.source)
        self._capture.release()
        self._capture = None
        self._next_attempt = time.monotonic() + self.retry_seconds
        self._reported_failure = True
        return None

    def release(self) -> None:
        if self._capture is not None:
            self._capture.release()
            self._capture = None
