from main import _parse_args


def test_source_argument_accepts_camera_index_stream_and_video_file(tmp_path):
    video = tmp_path / "traffic_sample.mp4"
    video.write_bytes(b"")

    assert _parse_args(["--source", "1"]).source == 1
    assert _parse_args(["--source", "rtsp://camera.local/live"]).source == "rtsp://camera.local/live"
    assert _parse_args(["--source", str(video)]).source == str(video)


def test_serial_arguments_default_to_simulation_and_support_explicit_settings():
    defaults = _parse_args([])
    assert defaults.port is None
    assert defaults.baudrate == 9600

    configured = _parse_args(["--port", "/dev/ttyACM0", "--baudrate", "115200"])
    assert configured.port == "/dev/ttyACM0"
    assert configured.baudrate == 115200
