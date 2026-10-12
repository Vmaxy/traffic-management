from pathlib import Path

import pytest

from traffic_core.config import PROJECT_ROOT, Settings


def test_reads_defaults_and_normalizes_numeric_video_source(monkeypatch):
    monkeypatch.delenv("TRAFFIC_VIDEO_SOURCE", raising=False)
    settings = Settings.from_env()
    assert settings.video_source == 0
    assert settings.roi_config == PROJECT_ROOT / "config" / "intersection_rois.json"
    assert settings.heartbeat_seconds == 1.0
    assert settings.confidence_threshold == 0.20
    assert settings.min_green_seconds == 3.0
    assert settings.max_green_seconds == 30.0
    assert settings.green_scale_factor == 1.5
    assert settings.max_video_fps == 30.0

    monkeypatch.setenv("TRAFFIC_VIDEO_SOURCE", "3")
    assert Settings.from_env().video_source == 3
    monkeypatch.setenv("TRAFFIC_VIDEO_SOURCE", "http://camera.local/video")
    assert Settings.from_env().video_source == "http://camera.local/video"


def test_resolves_relative_roi_path_against_project(monkeypatch):
    monkeypatch.setenv("TRAFFIC_ROI_CONFIG", "custom/rois.json")
    assert Settings.from_env().roi_config == PROJECT_ROOT / "custom" / "rois.json"
    monkeypatch.setenv("TRAFFIC_ROI_CONFIG", "/tmp/rois.json")
    assert Settings.from_env().roi_config == Path("/tmp/rois.json")


@pytest.mark.parametrize(
    ("variable", "value"),
    [
        ("TRAFFIC_CONFIDENCE", "0"),
        ("TRAFFIC_CONFIDENCE", "1.1"),
        ("TRAFFIC_CONFIDENCE", "nan"),
        ("TRAFFIC_SERIAL_BAUD", "0"),
        ("TRAFFIC_SERIAL_BAUD", "fast"),
        ("TRAFFIC_MIN_GREEN_SECONDS", "-1"),
        ("TRAFFIC_MIN_GREEN_SECONDS", "2.9"),
        ("TRAFFIC_MAX_GREEN_SECONDS", "31"),
        ("TRAFFIC_CAMERA_RETRY_SECONDS", "inf"),
        ("TRAFFIC_HEARTBEAT_SECONDS", "10.0"),
        ("TRAFFIC_LOG_LEVEL", "TRACE"),
    ],
)
def test_rejects_invalid_environment_values(monkeypatch, variable, value):
    monkeypatch.setenv(variable, value)
    with pytest.raises(ValueError):
        Settings.from_env()
