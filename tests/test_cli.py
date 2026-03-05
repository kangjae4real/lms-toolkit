"""cli.py 순수 함수 단위 테스트"""

from src.auto_watch.cli import _format_duration, _is_target_video_url, _safe_filename


class TestFormatDuration:
    def test_seconds_only(self):
        assert _format_duration(45) == "0:45"

    def test_minutes_and_seconds(self):
        assert _format_duration(125) == "2:05"

    def test_hours(self):
        assert _format_duration(3661) == "1:01:01"

    def test_zero(self):
        assert _format_duration(0) == "0:00"

    def test_exact_hour(self):
        assert _format_duration(3600) == "1:00:00"


class TestIsTargetVideoUrl:
    def test_valid_commons_url(self):
        url = "https://commons.ssu.ac.kr/em/media_files/abc123/media.mp4"
        assert _is_target_video_url(url) is True

    def test_valid_cdn_url(self):
        url = "https://some.commonscdn.com/em/media_files/abc123/video.mp4"
        assert _is_target_video_url(url) is True

    def test_reject_intro(self):
        url = "https://commons.ssu.ac.kr/em/media_files/abc123/intro.mp4"
        assert _is_target_video_url(url) is False

    def test_reject_non_mp4(self):
        url = "https://commons.ssu.ac.kr/em/media_files/abc123/video.m3u8"
        assert _is_target_video_url(url) is False

    def test_reject_no_media_files(self):
        url = "https://commons.ssu.ac.kr/em/other_path/abc123/video.mp4"
        assert _is_target_video_url(url) is False

    def test_reject_other_domain(self):
        url = "https://example.com/media_files/abc123/video.mp4"
        assert _is_target_video_url(url) is False


class TestSafeFilename:
    def test_special_chars(self):
        assert _safe_filename('test:file/name*"bad') == "test_file_name__bad"

    def test_normal_name(self):
        assert _safe_filename("정상적인 파일명") == "정상적인 파일명"

    def test_strips_whitespace(self):
        assert _safe_filename("  file  ") == "file"
