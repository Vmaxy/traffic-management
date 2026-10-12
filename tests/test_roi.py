import json

import pytest

from traffic_core.roi import LANES, ROIManager


@pytest.fixture
def roi_manager(tmp_path):
    config = {
        "NORTH": [[0.4, 0.0], [0.6, 0.0], [0.6, 0.4], [0.4, 0.4]],
        "SOUTH": [[0.4, 0.6], [0.6, 0.6], [0.6, 1.0], [0.4, 1.0]],
        "EAST": [[0.6, 0.4], [1.0, 0.4], [1.0, 0.6], [0.6, 0.6]],
        "WEST": [[0.0, 0.4], [0.4, 0.4], [0.4, 0.6], [0.0, 0.6]],
    }
    path = tmp_path / "rois.json"
    path.write_text(json.dumps(config), encoding="utf-8")
    manager = ROIManager(path)
    manager.update_resolution(1000, 1000)
    return manager


@pytest.mark.parametrize(
    ("box", "expected_lane"),
    [
        ((480, 100, 520, 200), "NORTH"),
        ((480, 800, 520, 900), "SOUTH"),
        ((800, 480, 900, 520), "EAST"),
        ((100, 480, 200, 520), "WEST"),
    ],
)
def test_assigns_bottom_center_to_each_approach(roi_manager, box, expected_lane):
    assert roi_manager.assign_box(box) == expected_lane


def test_junction_is_neutral(roi_manager):
    assert roi_manager.assign_box((450, 450, 550, 550)) is None


def test_can_use_center_anchor(roi_manager):
    assert roi_manager.assign_box((450, 100, 550, 350), anchor="center") == "NORTH"


def test_scaled_rois_cover_all_four_lanes(roi_manager):
    assert set(roi_manager.polygons) == set(LANES)
    assert roi_manager.polygons["NORTH"].max() == 599


def test_invalid_resolution_is_rejected(roi_manager):
    with pytest.raises(ValueError, match="greater than zero"):
        roi_manager.update_resolution(0, 480)
