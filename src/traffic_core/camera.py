"""Video capture with periodic reconnection attempts."""

from __future__ import annotations

import logging
import time

import cv2
import numpy as np


LOGGER = logging.getLogger(__name__)


class CameraStream:
    def __init__(self, source: int | str, retry_seconds: float = 2.0) -> None:
        if retry_seconds <= 0:
            raise ValueError("retry_seconds must be greater than zero")
        self.source = source
        self.retry_seconds = retry_seconds
        self._capture: cv2.VideoCapture | None = None
        self._next_attempt = 0.0
        self._reported_failure = False
        self._open()

    def _open(self) -> bool:
        capture = cv2.VideoCapture(self.source)
        if capture.isOpened():
            capture.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            self._capture = capture
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
        ok, frame = self._capture.read()
        if ok and frame is not None:
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
