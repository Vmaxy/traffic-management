# AI Miniature Traffic Management System

The Python application reads an overhead camera, video file, IP/RTSP stream, or USB webcam; detects COCO car, bus, and truck classes with Ultralytics YOLO; and counts detections in four approach regions. Lane green times use `clamp(MIN_GREEN + vehicle_count * SCALE_FACTOR, MIN_GREEN, MAX_GREEN)` over a 15-frame moving average. Normal phase choices are latched at phase boundaries, while detected emergency vehicles retain priority after minimum green. Video files loop at end-of-file and are throttled to their recorded frame rate (up to the configured FPS limit).

An Arduino Uno/Nano drives 12 signal LEDs on digital pins 2-13; pins 0 (RX) and 1 (TX) remain available for USB serial. Its non-blocking `millis()` state machine enforces Green → Yellow (3 seconds) → All-Red clearance (1.5 seconds) → next Green. The serial protocol accepts `SET:<lane>:<green_seconds>` (`N`, `S`, `E`, or `W`), plus `NEXT:NS` / `NEXT:EW` to request the next direction. Opposing approaches share a phase, and that phase uses the larger duration of its two lane settings. Valid commands receive `ACK:` responses. If valid serial input is lost for 10 seconds, the firmware forces all-red.

## Setup

Use Python 3.10 or newer. From this directory, install dependencies:

```bash
python -m pip install -r requirements.txt
```

Upload `firmware/traffic_signal_controller/traffic_signal_controller.ino` to an Uno/Nano. Connect each lane's red, yellow, and green LED to the pins documented in the sketch, with a 220-330 ohm resistor in series and a common ground. D13 is also the Uno's built-in LED pin.

Run `python main.py` for the configured source (webcam `0` by default), or pass `--source traffic_sample.mp4`, `--source rtsp://...`, or `--source 1` for another webcam. Press `q` in the video window to shut down. The first YOLO run may download the configured model if it is not present locally.

## Configuration

All settings are optional environment variables:

| Variable | Default | Purpose |
| --- | --- | --- |
| `TRAFFIC_VIDEO_SOURCE` | `0` | Webcam index or camera stream URL, such as an HTTP/MJPEG URL |
| `TRAFFIC_MAX_VIDEO_FPS` | `30.0` | Maximum playback rate for recorded video; playback is also capped to the video's reported FPS |
| `TRAFFIC_ROI_CONFIG` | `config/intersection_rois.json` | Path to lane polygons in the file's reference resolution |
| `TRAFFIC_MODEL` | `yolov8n.pt` | Ultralytics model path/name |
| `TRAFFIC_CONFIDENCE` | `0.20` | Detection confidence threshold, greater than 0 and at most 1 |
| `TRAFFIC_SERIAL_PORT` | auto-detect | Arduino serial port; set explicitly if multiple USB serial devices are attached |
| `TRAFFIC_SERIAL_BAUD` | `9600` | Serial baud rate (must match the firmware) |
| `TRAFFIC_MIN_GREEN_SECONDS` | `3.0` | Minimum green duration (3-30 seconds, including emergency priority clearance) |
| `TRAFFIC_MAX_GREEN_SECONDS` | `30.0` | Maximum green duration (up to 30 seconds) before fair handoff to the opposing approach |
| `TRAFFIC_GREEN_SCALE_FACTOR` | `1.5` | Additional green seconds per smoothed vehicle count |
| `TRAFFIC_YELLOW_SECONDS` | `3.0` | Yellow clearance duration |
| `TRAFFIC_ALL_RED_SECONDS` | `1.5` | All-red clearance duration |
| `TRAFFIC_HEARTBEAT_SECONDS` | `1.0` | Signal-plan resend interval; must remain below the Arduino's 10-second watchdog |
| `TRAFFIC_CAMERA_RETRY_SECONDS` | `2.0` | Delay between camera reconnection attempts |
| `TRAFFIC_LOG_LEVEL` | `INFO` | Python log level |

For example, set `TRAFFIC_VIDEO_SOURCE` to the local stream URL and `TRAFFIC_SERIAL_PORT` to the port shown by your operating system before running the application. If the Arduino is unavailable, the application logs signal commands in simulation mode and continues processing video.

## Camera ROI calibration

The included `config/intersection_rois.json` contains **example** polygons, not camera-calibrated measurements. Polygons are pixel coordinates inside `lanes`, drawn at the `reference_resolution` width and height; the application scales them independently to each camera frame. Edit all four polygons to cover the corresponding approaches in your camera view. Keep them outside the central junction; vehicle detections are assigned using the bounding-box bottom-center, and detections outside every polygon are unassigned. The example assumes NORTH is at the top of the displayed frame, SOUTH at the bottom, EAST on the right, and WEST on the left. Verify the lane labels and counts against the physical model before connecting live signals.

Counts are the number of vehicle detections assigned to each ROI in the current frame, not cumulative trip counts or tracked identities.
