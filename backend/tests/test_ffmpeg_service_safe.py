"""get_video_duration_safe fallback 测试"""
from unittest.mock import MagicMock, patch

from services.ffmpeg_service import get_video_duration_safe, _parse_duration_from_stderr


def test_parses_hours_minutes_seconds():
    stderr = "  Duration: 01:23:45.67, start: 0.000000\n"
    result = _parse_duration_from_stderr(stderr)
    assert abs(result - 5025.67) < 0.01


def test_parses_minutes_only():
    stderr = "  Duration: 00:05:30.00, start: 0.000000\n"
    result = _parse_duration_from_stderr(stderr)
    assert abs(result - 330.0) < 0.01


def test_parse_no_duration_returns_zero():
    assert _parse_duration_from_stderr("nothing here") == 0.0


def test_returns_float_when_ffprobe_succeeds():
    with patch("services.ffmpeg_service.get_video_duration", return_value=12.5):
        assert get_video_duration_safe("/tmp/fake.mp4") == 12.5


def test_falls_back_to_ffmpeg_when_ffprobe_returns_zero():
    fake_stderr = "  Duration: 00:00:30.50, start: 0.000000\n"
    fake_completed = MagicMock()
    fake_completed.stderr = fake_stderr
    fake_completed.returncode = 1

    with patch("services.ffmpeg_service.get_video_duration", return_value=0.0), \
         patch("services.ffmpeg_service.FFMPEG", "/usr/bin/ffmpeg"), \
         patch("subprocess.run", return_value=fake_completed):
        assert get_video_duration_safe("/tmp/fake.mp4") == 30.5


def test_returns_zero_when_both_fail():
    fake_completed = MagicMock()
    fake_completed.stderr = "no duration line"
    fake_completed.returncode = 1

    with patch("services.ffmpeg_service.get_video_duration", return_value=0.0), \
         patch("services.ffmpeg_service.FFMPEG", "/usr/bin/ffmpeg"), \
         patch("subprocess.run", return_value=fake_completed):
        assert get_video_duration_safe("/tmp/fake.mp4") == 0.0


def test_returns_zero_when_ffmpeg_not_available():
    with patch("services.ffmpeg_service.get_video_duration", return_value=0.0), \
         patch("services.ffmpeg_service.FFMPEG", None):
        assert get_video_duration_safe("/tmp/fake.mp4") == 0.0


def test_ffprobe_exception_triggers_ffmpeg_fallback():
    fake_stderr = "  Duration: 00:01:00.00\n"
    fake_completed = MagicMock(stderr=fake_stderr, returncode=1)

    with patch("services.ffmpeg_service.get_video_duration", side_effect=RuntimeError("ffprobe broken")), \
         patch("services.ffmpeg_service.FFMPEG", "/usr/bin/ffmpeg"), \
         patch("subprocess.run", return_value=fake_completed):
        assert get_video_duration_safe("/tmp/fake.mp4") == 60.0
