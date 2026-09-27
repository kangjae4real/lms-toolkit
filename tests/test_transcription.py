"""transcription.py 다운로드 견고성 테스트"""

import pytest
import requests

from src.auto_watch import transcription


class _FakeResp:
    def __init__(self, chunks, fail_after=None, status=200, content_length=None):
        self.status_code = status
        length = sum(len(c) for c in chunks) if content_length is None else content_length
        self.headers = {"Content-Length": str(length)}
        self._chunks = chunks
        self._fail_after = fail_after

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}")

    def iter_content(self, chunk_size):
        for i, c in enumerate(self._chunks):
            if self._fail_after is not None and i >= self._fail_after:
                raise requests.ConnectionError("끊김")
            yield c


@pytest.fixture
def no_backoff(monkeypatch):
    monkeypatch.setattr(transcription, "DOWNLOAD_RETRY_BACKOFF_SEC", 0)


class TestDownloadMp4:
    def test_timeout_is_set(self, tmp_path, monkeypatch):
        seen = {}

        def fake_get(url, **kw):
            seen.update(kw)
            return _FakeResp([b"abc"])

        monkeypatch.setattr(transcription.req_lib, "get", fake_get)
        transcription._download_mp4("http://x", tmp_path / "a.part.mp4", "", "t")
        assert seen.get("timeout")

    def test_resumes_from_part_with_range(self, tmp_path, monkeypatch):
        part = tmp_path / "a.part.mp4"
        part.write_bytes(b"ab")
        seen = {}

        def fake_get(url, **kw):
            seen.update(kw)
            return _FakeResp([b"cd"], status=206)

        monkeypatch.setattr(transcription.req_lib, "get", fake_get)
        transcription._download_mp4("http://x", part, "", "t")

        assert seen["headers"]["Range"] == "bytes=2-"
        assert part.read_bytes() == b"abcd"

    def test_restarts_when_server_ignores_range(self, tmp_path, monkeypatch):
        part = tmp_path / "a.part.mp4"
        part.write_bytes(b"stale")
        monkeypatch.setattr(transcription.req_lib, "get", lambda url, **kw: _FakeResp([b"full"]))

        transcription._download_mp4("http://x", part, "", "t")

        assert part.read_bytes() == b"full"

    def test_short_body_raises(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            transcription.req_lib,
            "get",
            lambda url, **kw: _FakeResp([b"abc"], content_length=10),
        )
        with pytest.raises(OSError):
            transcription._download_mp4("http://x", tmp_path / "a.part.mp4", "", "t")

    def test_client_error_is_not_retryable(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            transcription.req_lib, "get", lambda url, **kw: _FakeResp([], status=403)
        )
        with pytest.raises(transcription._NonRetryableError):
            transcription._download_mp4("http://x", tmp_path / "a.part.mp4", "", "t")


class TestDownloadWithRetry:
    async def test_interrupted_download_resumes_on_retry(self, tmp_path, monkeypatch, no_backoff):
        responses = iter([_FakeResp([b"ab", b"cd"], fail_after=1), _FakeResp([b"cd"], status=206)])
        ranges = []

        def fake_get(url, **kw):
            ranges.append(kw["headers"].get("Range"))
            return next(responses)

        monkeypatch.setattr(transcription.req_lib, "get", fake_get)
        out = tmp_path / "a.mp4"
        await transcription._download_with_retry("http://x", out, "t", "", hls=False)

        assert ranges == [None, "bytes=2-"]
        assert out.read_bytes() == b"abcd"
        assert [p.name for p in tmp_path.iterdir()] == ["a.mp4"]

    async def test_gives_up_but_keeps_part_for_next_run(self, tmp_path, monkeypatch, no_backoff):
        calls = []

        def fake_get(url, **kw):
            calls.append(1)
            return _FakeResp([b"ab", b"cd"], fail_after=1 if len(calls) == 1 else 0)

        monkeypatch.setattr(transcription.req_lib, "get", fake_get)
        with pytest.raises(requests.ConnectionError):
            await transcription._download_with_retry(
                "http://x", tmp_path / "a.mp4", "t", "", hls=False
            )

        assert len(calls) == transcription.DOWNLOAD_MAX_ATTEMPTS
        assert [p.name for p in tmp_path.iterdir()] == ["a.part.mp4"]

    async def test_client_error_fails_without_retry(self, tmp_path, monkeypatch, no_backoff):
        calls = []

        def fake_get(url, **kw):
            calls.append(1)
            return _FakeResp([], status=404)

        monkeypatch.setattr(transcription.req_lib, "get", fake_get)
        with pytest.raises(transcription._NonRetryableError):
            await transcription._download_with_retry(
                "http://x", tmp_path / "a.mp4", "t", "", hls=False
            )
        assert len(calls) == 1


class TestSkipExisting:
    @pytest.fixture
    def course(self, tmp_path, monkeypatch):
        monkeypatch.setattr(transcription, "OUTPUT_DIR", tmp_path)
        monkeypatch.setattr(transcription, "PROJECT_DIR", tmp_path)
        course = tmp_path / "과목"
        course.mkdir()
        return course

    @staticmethod
    def _boom(*a, **kw):
        raise AssertionError("다시 하면 안 됨")

    async def test_existing_mp4_and_txt_are_not_redone(self, course, monkeypatch):
        (course / "강의.mp4").write_bytes(b"x")
        (course / "강의.txt").write_text("done", encoding="utf-8")
        monkeypatch.setattr(transcription, "_download_with_retry", self._boom)
        monkeypatch.setattr(transcription, "_get_whisper", self._boom)

        result = await transcription.download_and_transcribe("http://x", "과목", "강의")

        assert result["mp4"] == str(course / "강의.mp4")
        assert result["txt"] == str(course / "강의.txt")
        assert result["skipped"] is True
        assert transcription.transcript_exists("과목", "강의")

    async def test_existing_mp4_only_transcribes(self, course, monkeypatch):
        (course / "강의.mp4").write_bytes(b"x")
        monkeypatch.setattr(transcription, "_download_with_retry", self._boom)

        class _FakeWhisper:
            def transcribe(self, audio_path, txt_path):
                with open(txt_path, "w", encoding="utf-8") as f:
                    f.write("전사")

        monkeypatch.setattr(transcription, "_get_whisper", _FakeWhisper)

        result = await transcription.download_and_transcribe("http://x", "과목", "강의")

        assert result["txt"] == str(course / "강의.txt")
        assert result["skipped"] is False
        assert sorted(p.name for p in course.iterdir()) == ["강의.mp4", "강의.txt"]
