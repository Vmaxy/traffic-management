from main import _parse_args


def test_source_argument_accepts_camera_index_stream_and_video_file(tmp_path):
    video = tmp_path / "traffic_sample.mp4"
    video.write_bytes(b"")

    assert _parse_args(["--source", "1"]).source == 1
    assert _parse_args(["--source", "rtsp://camera.local/live"]).source == "rtsp://camera.local/live"
    assert _parse_args(["--source", str(video)]).source == str(video)
