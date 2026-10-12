"""Run the live AI miniature traffic management application."""

from __future__ import annotations

import logging
import sys
import time
from pathlib import Path

import cv2

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from traffic_core.camera import CameraStream
from traffic_core.config import Settings
from traffic_core.detector import VehicleDetector
from traffic_core.roi import LANES, LaneOccupancy, ROIManager
from traffic_core.safety_fsm import Phase, SafetyFSM
from traffic_core.serial_controller import ArduinoController


LANE_COLORS = {
    "NORTH": (255, 180, 0),
    "SOUTH": (0, 200, 255),
    "EAST": (0, 220, 0),
    "WEST": (220, 0, 220),
}
PHASE_COLORS = {
    Phase.NS_GREEN: (0, 220, 0),
    Phase.EW_GREEN: (0, 220, 0),
    Phase.NS_YELLOW: (0, 220, 255),
    Phase.EW_YELLOW: (0, 220, 255),
    Phase.ALL_RED: (0, 0, 255),
}


def _configure_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def _draw_hud(
    frame,
    roi_manager: ROIManager,
    occupancy: LaneOccupancy,
    detections,
    active_phase: Phase,
    requested_phase: Phase,
    elapsed_seconds: float,
    arduino_status: str,
    acknowledgments: list[str],
) -> None:
    for lane, polygon in roi_manager.polygons.items():
        color = LANE_COLORS[lane]
        cv2.polylines(frame, [polygon], True, color, 2)
        label_point = tuple(int(value) for value in polygon[0])
        cv2.putText(
            frame,
            lane,
            (label_point[0] + 4, label_point[1] + 20),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            color,
            2,
        )

    for detection, lane in zip(detections, occupancy.assigned_lanes):
        x1, y1, x2, y2 = (int(round(value)) for value in detection.box)
        color = (
            (0, 0, 255)
            if detection.is_emergency
            else LANE_COLORS.get(lane, (180, 180, 180))
        )
        kind = "AMBULANCE" if detection.is_emergency else detection.class_name
        label = f"{kind} {detection.confidence:.2f}"
        if lane:
            label += f" | {lane}"
        cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
        cv2.putText(
            frame,
            label,
            (x1, max(18, y1 - 6)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.48,
            color,
            2,
        )

    phase_color = PHASE_COLORS[active_phase]
    emergency_text = ", ".join(sorted(occupancy.emergency_lanes)) or "none"
    lines = [
        "  ".join(f"{lane}: {occupancy.counts[lane]}" for lane in LANES),
        f"EMERGENCY LANE: {emergency_text}",
        f"ACTIVE: {active_phase.value}  |  REQUESTED: {requested_phase.value}  |  {elapsed_seconds:.1f}s",
        f"ARDUINO: {arduino_status}",
        f"ACK: {' | '.join(acknowledgments[-2:]) if acknowledgments else 'none'}",
    ]
    panel_height = 24 * len(lines) + 16
    cv2.rectangle(frame, (8, 8), (min(frame.shape[1] - 8, 770), panel_height), (25, 25, 25), -1)
    for index, text in enumerate(lines):
        color = phase_color if index == 2 else (245, 245, 245)
        cv2.putText(
            frame,
            text,
            (16, 30 + index * 24),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.62,
            color,
            2,
        )


def run() -> None:
    settings = Settings.from_env()
    _configure_logging(settings.log_level)
    logger = logging.getLogger("traffic_system")

    roi_manager = ROIManager(settings.roi_config)
    camera = CameraStream(settings.video_source, settings.camera_retry_seconds)
    controller = ArduinoController(
        port=settings.serial_port,
        baud_rate=settings.serial_baud,
        heartbeat_seconds=settings.heartbeat_seconds,
    )
    fsm = SafetyFSM(
        min_green_seconds=settings.min_green_seconds,
        max_green_seconds=settings.max_green_seconds,
        yellow_seconds=settings.yellow_seconds,
        all_red_seconds=settings.all_red_seconds,
    )
    requested_phase = Phase.NS_GREEN
    fsm.request_phase(requested_phase)
    controller.set_phase(fsm.phase)

    try:
        detector = VehicleDetector(settings.model_path, settings.confidence_threshold)
        logger.info("Loaded YOLO model %s", settings.model_path)
        while True:
            frame = camera.read()
            if frame is None:
                time.sleep(0.02)
                continue

            height, width = frame.shape[:2]
            roi_manager.update_resolution(width, height)
            detections = detector.detect(frame)
            occupancy = roi_manager.count_detections(detections)
            counts = occupancy.counts

            ns_demand = counts["NORTH"] + counts["SOUTH"]
            ew_demand = counts["EAST"] + counts["WEST"]
            emergency_ns = bool({"NORTH", "SOUTH"} & occupancy.emergency_lanes)
            emergency_ew = bool({"EAST", "WEST"} & occupancy.emergency_lanes)

            active_direction = (
                Phase.NS_GREEN
                if fsm.phase in (Phase.NS_GREEN, Phase.NS_YELLOW)
                else Phase.EW_GREEN
                if fsm.phase in (Phase.EW_GREEN, Phase.EW_YELLOW)
                else None
            )
            if active_direction is Phase.NS_GREEN and emergency_ew:
                requested_phase = Phase.EW_GREEN
            elif active_direction is Phase.EW_GREEN and emergency_ns:
                requested_phase = Phase.NS_GREEN
            elif emergency_ns and not emergency_ew:
                requested_phase = Phase.NS_GREEN
            elif emergency_ew and not emergency_ns:
                requested_phase = Phase.EW_GREEN
            elif ns_demand > ew_demand:
                requested_phase = Phase.NS_GREEN
            elif ew_demand > ns_demand:
                requested_phase = Phase.EW_GREEN
            elif active_direction is not None:
                requested_phase = active_direction
            emergency_priority = (
                (requested_phase is Phase.NS_GREEN and emergency_ns and active_direction is Phase.EW_GREEN)
                or (requested_phase is Phase.EW_GREEN and emergency_ew and active_direction is Phase.NS_GREEN)
            )
            fsm.request_phase(requested_phase, emergency=emergency_priority)
            previous_phase = fsm.phase
            active_phase = fsm.tick()
            if active_phase is not previous_phase:
                logger.info("Signal phase changed to %s", active_phase.value)
                controller.set_phase(active_phase)

            acknowledgments = controller.pop_acknowledgments()
            emergency_lanes = ",".join(sorted(occupancy.emergency_lanes)) or "none"
            logger.info(
                "frame counts[N=%d,S=%d,E=%d,W=%d] emergency_lane=%s phase=%s "
                "elapsed=%.2fs arduino_ack=%s",
                counts["NORTH"],
                counts["SOUTH"],
                counts["EAST"],
                counts["WEST"],
                emergency_lanes,
                active_phase.value,
                fsm.elapsed_seconds,
                " | ".join(acknowledgments) if acknowledgments else "none",
            )
            _draw_hud(
                frame,
                roi_manager,
                occupancy,
                detections,
                active_phase,
                requested_phase,
                fsm.elapsed_seconds,
                controller.status,
                acknowledgments,
            )
            cv2.imshow("AI Miniature Traffic Management System", frame)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                break
    finally:
        controller.shutdown()
        camera.release()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    run()
