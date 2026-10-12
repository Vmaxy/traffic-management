"""Environment-backed application configuration."""

from __future__ import annotations

import math
import os
from dataclasses import dataclass
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _positive_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    try:
        value = default if raw is None else float(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be a number, got {raw!r}") from exc
    if not math.isfinite(value) or value <= 0:
        raise ValueError(f"{name} must be greater than zero")
    return value


def _source_value(raw: str) -> int | str:
    value = raw.strip()
    if not value:
        return 0
    if value.isdecimal():
        return int(value)
    return value


@dataclass(frozen=True)
class Settings:
    video_source: int | str = 0
    roi_config: Path = PROJECT_ROOT / "config" / "intersection_rois.json"
    model_path: str = "yolov8n.pt"
    confidence_threshold: float = 0.20
    serial_port: str | None = None
    serial_baud: int = 9600
    camera_retry_seconds: float = 2.0
    min_green_seconds: float = 3.0
    max_green_seconds: float = 30.0
    green_scale_factor: float = 1.5
    max_video_fps: float = 30.0
    yellow_seconds: float = 3.0
    all_red_seconds: float = 1.5
    heartbeat_seconds: float = 1.0
    log_level: str = "INFO"

    @classmethod
    def from_env(cls) -> Settings:
        source = _source_value(os.getenv("TRAFFIC_VIDEO_SOURCE", "0"))
        roi_path = Path(
            os.getenv("TRAFFIC_ROI_CONFIG", str(PROJECT_ROOT / "config" / "intersection_rois.json"))
        ).expanduser()
        if not roi_path.is_absolute():
            roi_path = PROJECT_ROOT / roi_path

        confidence_raw = os.getenv("TRAFFIC_CONFIDENCE", "0.20")
        try:
            confidence = float(confidence_raw)
        except ValueError as exc:
            raise ValueError("TRAFFIC_CONFIDENCE must be a number") from exc
        if not math.isfinite(confidence) or not 0.0 < confidence <= 1.0:
            raise ValueError("TRAFFIC_CONFIDENCE must be greater than 0 and at most 1")

        baud_raw = os.getenv("TRAFFIC_SERIAL_BAUD", "9600")
        try:
            baud = int(baud_raw)
        except ValueError as exc:
            raise ValueError("TRAFFIC_SERIAL_BAUD must be an integer") from exc
        if baud <= 0:
            raise ValueError("TRAFFIC_SERIAL_BAUD must be greater than zero")

        heartbeat = _positive_float("TRAFFIC_HEARTBEAT_SECONDS", 1.0)
        if heartbeat >= 10.0:
            raise ValueError(
                "TRAFFIC_HEARTBEAT_SECONDS must be less than the 10-second Arduino watchdog"
            )

        min_green = _positive_float("TRAFFIC_MIN_GREEN_SECONDS", 3.0)
        max_green = _positive_float("TRAFFIC_MAX_GREEN_SECONDS", 30.0)
        if min_green < 3.0:
            raise ValueError("TRAFFIC_MIN_GREEN_SECONDS must be at least 3 seconds")
        if max_green > 30.0:
            raise ValueError("TRAFFIC_MAX_GREEN_SECONDS must be at most 30 seconds")
        if max_green < min_green:
            raise ValueError("TRAFFIC_MAX_GREEN_SECONDS must be at least TRAFFIC_MIN_GREEN_SECONDS")
        green_scale_factor = _positive_float("TRAFFIC_GREEN_SCALE_FACTOR", 1.5)

        serial_port = os.getenv("TRAFFIC_SERIAL_PORT", "").strip() or None
        log_level = os.getenv("TRAFFIC_LOG_LEVEL", "INFO").upper()
        if log_level not in {"CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"}:
            raise ValueError("TRAFFIC_LOG_LEVEL must be CRITICAL, ERROR, WARNING, INFO, or DEBUG")

        return cls(
            video_source=source,
            roi_config=roi_path,
            model_path=os.getenv("TRAFFIC_MODEL", "yolov8n.pt"),
            confidence_threshold=confidence,
            serial_port=serial_port,
            serial_baud=baud,
            camera_retry_seconds=_positive_float("TRAFFIC_CAMERA_RETRY_SECONDS", 2.0),
            min_green_seconds=min_green,
            max_green_seconds=max_green,
            green_scale_factor=green_scale_factor,
            max_video_fps=_positive_float("TRAFFIC_MAX_VIDEO_FPS", 30.0),
            yellow_seconds=_positive_float("TRAFFIC_YELLOW_SECONDS", 3.0),
            all_red_seconds=_positive_float("TRAFFIC_ALL_RED_SECONDS", 1.5),
            heartbeat_seconds=heartbeat,
            log_level=log_level,
        )
