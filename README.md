# AI Miniature Traffic Management System

The Python application reads an overhead camera stream, detects COCO vehicle classes with Ultralytics YOLO, counts detections in four approach regions, and selects conflict-free traffic phases. An Arduino Uno/Nano drives the 12 signal LEDs. The Python FSM enforces minimum green, yellow, and all-red clearance; the Arduino independently returns to all-red if it receives no command for 2.5 seconds.

## Setup

Use Python 3.10 or newer. From this directory, install dependencies:

```bash
python -m pip install -r requirements.txt
```

Upload `firmware/traffic_signal_controller/traffic_signal_controller.ino` to an Uno/Nano. Connect each lane's red, yellow, and green LED to the pins documented in the sketch, with a 220-330 ohm resistor in series and a common ground. D13 is also the Uno's built-in LED pin.

Run `python main.py`. By default, video comes from webcam index `0`; press `q` in the video window to shut down. The first YOLO run may download the configured model if it is not present locally.

## Configuration

All settings are optional environment variables:

| Variable | Default | Purpose |
| --- | --- | --- |
| `TRAFFIC_VIDEO_SOURCE` | `0` | Webcam index or camera stream URL, such as an HTTP/MJPEG URL |
| `TRAFFIC_ROI_CONFIG` | `config/intersection_rois.json` | Path to normalized lane polygons |
| `TRAFFIC_MODEL` | `yolov8n.pt` | Ultralytics model path/name |
| `TRAFFIC_CONFIDENCE` | `0.35` | Detection confidence threshold, greater than 0 and at most 1 |
| `TRAFFIC_SERIAL_PORT` | auto-detect | Arduino serial port; set explicitly if multiple USB serial devices are attached |
| `TRAFFIC_SERIAL_BAUD` | `9600` | Serial baud rate (must match the firmware) |
| `TRAFFIC_MIN_GREEN_SECONDS` | `4.0` | Minimum green duration |
| `TRAFFIC_YELLOW_SECONDS` | `2.0` | Yellow clearance duration |
| `TRAFFIC_ALL_RED_SECONDS` | `1.0` | All-red clearance duration |
| `TRAFFIC_HEARTBEAT_SECONDS` | `1.0` | Current-phase resend interval; must remain below the Arduino's 2.5-second watchdog |
| `TRAFFIC_CAMERA_RETRY_SECONDS` | `2.0` | Delay between camera reconnection attempts |
| `TRAFFIC_LOG_LEVEL` | `INFO` | Python log level |

For example, set `TRAFFIC_VIDEO_SOURCE` to the local stream URL and `TRAFFIC_SERIAL_PORT` to the port shown by your operating system before running the application. If the Arduino is unavailable, the application logs signal commands in simulation mode and continues processing video.

## Camera ROI calibration

The included `config/intersection_rois.json` contains normalized **example** polygons, not camera-calibrated measurements. Image coordinates use `(0, 0)` at the top-left and `(1, 1)` at the bottom-right. Edit all four polygons to cover the corresponding approaches in your camera view. Keep them outside the central junction; vehicle detections whose bottom-center falls outside every polygon are unassigned. The example assumes NORTH is at the top of the displayed frame, SOUTH at the bottom, EAST on the right, and WEST on the left. Verify the lane labels and counts against the physical model before connecting live signals.

Counts are the number of vehicle detections assigned to each ROI in the current frame, not cumulative trip counts or tracked identities.
