"""영상 다운로드 및 음성-텍스트 전사"""

from __future__ import annotations

import asyncio
import logging
import re
import time
from pathlib import Path
from typing import TYPE_CHECKING

import requests as req_lib

from .cli import _safe_filename
from .config import (
    DOWNLOAD_CHUNK_SIZE,
    DOWNLOAD_MAX_ATTEMPTS,
    DOWNLOAD_REPORT_INTERVAL,
    DOWNLOAD_RETRY_BACKOFF_SEC,
    DOWNLOAD_TIMEOUT,
    OUTPUT_DIR,
    PROJECT_DIR,
    USER_AGENT,
)
from .types import TranscriptResult

if TYPE_CHECKING:
    from src.audio_pipeline.transcriber import WhisperTranscriber

logger = logging.getLogger(__name__)

# --- Whisper 싱글턴 ---
_whisper_instance: WhisperTranscriber | None = None


def _get_whisper() -> WhisperTranscriber:
    global _whisper_instance
    if _whisper_instance is None:
        from src.audio_pipeline.transcriber import WhisperTranscriber

        _whisper_instance = WhisperTranscriber()
    return _whisper_instance


# --- 동시성 제한 (lazy init: import 시점에 이벤트 루프 없을 수 있음) ---
_download_sem: asyncio.Semaphore | None = None
_transcribe_sem: asyncio.Semaphore | None = None


def _get_download_sem() -> asyncio.Semaphore:
    global _download_sem
    if _download_sem is None:
        _download_sem = asyncio.Semaphore(2)
    return _download_sem


def _get_transcribe_sem() -> asyncio.Semaphore:
    global _transcribe_sem
    if _transcribe_sem is None:
        _transcribe_sem = asyncio.Semaphore(1)
    return _transcribe_sem


def output_paths(course_name: str, title: str) -> tuple[Path, Path]:
    course_dir = OUTPUT_DIR / _safe_filename(course_name)
    safe_title = _safe_filename(title)
    return course_dir / f"{safe_title}.mp4", course_dir / f"{safe_title}.txt"


def transcript_exists(course_name: str, title: str) -> bool:
    return output_paths(course_name, title)[1].exists()


def _part_path(path: Path) -> Path:
    # 완성된 파일만 원래 이름을 갖게 해야 "이미 받았으면 건너뛰기"가 반쯤 받은 파일을 완성본으로 착각하지 않는다.
    return path.with_name(f"{path.stem}.part{path.suffix}")


class _NonRetryableError(Exception):
    pass


def _brief(e: Exception) -> str:
    # requests 예외 문자열은 urllib3 예외를 튜플째 품고 있어 한 줄 로그로 쓰기엔 너무 길다
    text = str(e)
    if isinstance(e, req_lib.Timeout) or "timed out" in text:
        return "응답 없음"
    if isinstance(e, req_lib.exceptions.ChunkedEncodingError) or "Connection broken" in text:
        return "연결 끊김"
    return text[:120] or type(e).__name__


def _download_mp4(video_url: str, part_path: Path, referer: str, title: str) -> None:
    """HTTP 직접 다운로드 (MP4). 앞선 시도가 남긴 part 파일이 있으면 Range 로 이어받는다."""
    headers = {
        "User-Agent": USER_AGENT,
        "Referer": referer,
    }
    offset = part_path.stat().st_size if part_path.exists() else 0
    if offset:
        headers["Range"] = f"bytes={offset}-"

    with req_lib.get(video_url, stream=True, headers=headers, timeout=DOWNLOAD_TIMEOUT) as resp:
        if resp.status_code == 416:
            part_path.unlink(missing_ok=True)
            raise OSError("이어받기 범위 거부 — 처음부터 다시 받음")
        if 400 <= resp.status_code < 500:
            raise _NonRetryableError(f"HTTP {resp.status_code}")
        resp.raise_for_status()

        if offset and resp.status_code != 206:
            offset = 0
        if offset:
            logger.info("[%s] 다운로드: %dMB 지점부터 이어받기", title, offset // (1024 * 1024))

        length = int(resp.headers.get("Content-Length", 0))
        total = offset + length if length else 0
        downloaded = offset
        last_report = offset
        with open(part_path, "ab" if offset else "wb") as f:
            for chunk in resp.iter_content(chunk_size=DOWNLOAD_CHUNK_SIZE):
                if chunk:
                    f.write(chunk)
                    downloaded += len(chunk)
                    if total and downloaded - last_report >= DOWNLOAD_REPORT_INTERVAL:
                        logger.info(
                            "[%s] 다운로드: %dMB / %dMB (%.0f%%)",
                            title,
                            downloaded // (1024 * 1024),
                            total // (1024 * 1024),
                            downloaded / total * 100,
                        )
                        last_report = downloaded
    if total and downloaded < total:
        raise OSError(f"본문이 중간에 끊김 ({downloaded}/{total} bytes)")


async def _download_hls(video_url: str, part_path: Path, title: str) -> None:
    """ffmpeg로 HLS(m3u8) → MP4 변환 (진행률 실시간 출력). 이어받기는 안 되고 매번 처음부터."""
    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-y",
        "-rw_timeout",
        str(DOWNLOAD_TIMEOUT[1] * 1_000_000),
        "-i",
        video_url,
        "-c",
        "copy",
        "-bsf:a",
        "aac_adtstoasc",
        str(part_path),
    ]
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    # stderr를 실시간 읽으면서 time= 패턴 파싱
    last_log_sec = 0
    stderr_chunks: list[bytes] = []
    assert proc.stderr is not None
    async for line in proc.stderr:
        stderr_chunks.append(line)
        text = line.decode(errors="replace")
        m = re.search(r"time=(\d+):(\d+):(\d+)", text)
        if m:
            sec = int(m.group(1)) * 3600 + int(m.group(2)) * 60 + int(m.group(3))
            if sec - last_log_sec >= 30:
                mm, ss = divmod(sec, 60)
                logger.info("[%s] 다운로드: %d:%02d 처리됨...", title, mm, ss)
                last_log_sec = sec
    await proc.wait()
    if proc.returncode != 0:
        part_path.unlink(missing_ok=True)
        stderr_text = b"".join(stderr_chunks[-20:]).decode(errors="replace")
        last_line = stderr_text.strip().splitlines()[-1] if stderr_text.strip() else ""
        if re.search(r"Server returned 4\d\d", stderr_text):
            raise _NonRetryableError(f"ffmpeg: {last_line}")
        raise RuntimeError(f"ffmpeg 실패: {last_line}")


async def _download_with_retry(
    video_url: str, mp4_path: Path, title: str, referer: str, hls: bool
) -> None:
    loop = asyncio.get_running_loop()
    part_path = _part_path(mp4_path)
    for attempt in range(1, DOWNLOAD_MAX_ATTEMPTS + 1):
        try:
            if hls:
                await _download_hls(video_url, part_path, title)
            else:
                await loop.run_in_executor(
                    None, _download_mp4, video_url, part_path, referer, title
                )
            break
        except _NonRetryableError:
            raise
        except Exception as e:
            if attempt == DOWNLOAD_MAX_ATTEMPTS:
                raise
            backoff = DOWNLOAD_RETRY_BACKOFF_SEC * 2 ** (attempt - 1)
            logger.warning(
                "[%s] 다운로드 중단 (%s) — %d초 후 재시도 (%d/%d)",
                title,
                _brief(e),
                backoff,
                attempt + 1,
                DOWNLOAD_MAX_ATTEMPTS,
            )
            await asyncio.sleep(backoff)
    part_path.replace(mp4_path)


async def download_and_transcribe(
    video_url: str,
    course_name: str,
    title: str,
    *,
    referer: str = "",
    hls: bool = False,
) -> TranscriptResult:
    """영상 다운로드 + 음성→텍스트 전사 (재생과 병렬 실행)"""
    loop = asyncio.get_running_loop()
    result: TranscriptResult = {
        "course": course_name,
        "title": title,
        "mp4": None,
        "txt": None,
        "skipped": False,
    }

    mp4_path, txt_path = output_paths(course_name, title)
    mp4_path.parent.mkdir(parents=True, exist_ok=True)

    if txt_path.exists():
        logger.info("[%s] 스크립트: 이미 있음 — 건너뜀", title)
        result["txt"] = str(txt_path)
        result["skipped"] = True
        if mp4_path.exists():
            result["mp4"] = str(mp4_path)
        return result

    # 1. 다운로드 (동시 2개 제한)
    if mp4_path.exists():
        logger.info("[%s] 다운로드: 이미 있음 — 건너뜀", title)
    else:
        try:
            download_sem = _get_download_sem()
            if download_sem.locked():
                logger.info("[%s] 다운로드: 앞 강의 다운로드가 끝나면 시작 (대기 중)", title)
            async with download_sem:
                logger.info("[%s] 다운로드: 시작...", title)
                await _download_with_retry(video_url, mp4_path, title, referer, hls)
            size_mb = mp4_path.stat().st_size / (1024 * 1024)
            logger.info("[%s] 다운로드: 완료 (%.1fMB)", title, size_mb)
        except _NonRetryableError as e:
            logger.error("[%s] 다운로드 실패: %s — 영상 링크가 만료됐을 수 있음", title, e)
            return result
        except OSError as e:
            resumable = _part_path(mp4_path).exists()
            logger.error(
                "[%s] 다운로드 실패: %s%s",
                title,
                _brief(e),
                " — 다음 실행 때 이어받음" if resumable else "",
            )
            return result
        except RuntimeError as e:
            logger.error("[%s] 다운로드 실패: %s", title, e)
            return result
        except Exception:
            logger.exception("[%s] 다운로드 실패", title)
            return result
    result["mp4"] = str(mp4_path)

    # 2. mp4 → txt (동시 1개 제한 — GPU/CPU 집중)
    try:

        def _transcribe():
            txt_part = _part_path(txt_path)

            logger.info("[%s] 스크립트: [1/2] Whisper 모델 로딩...", title)
            transcriber = _get_whisper()

            logger.info("[%s] 스크립트: [2/2] 음성 → 텍스트 전사 중...", title)
            t_start = time.time()
            transcriber.transcribe(str(mp4_path), str(txt_part))
            txt_part.replace(txt_path)
            elapsed = time.time() - t_start
            em, es = divmod(int(elapsed), 60)
            logger.info("[%s] 스크립트: 전사 완료 (%d분 %d초)", title, em, es)
            return str(txt_path)

        transcribe_sem = _get_transcribe_sem()
        if transcribe_sem.locked():
            logger.info("[%s] 스크립트: 앞 강의 전사가 끝나면 시작 (대기 중)", title)
        async with transcribe_sem:
            result["txt"] = await loop.run_in_executor(None, _transcribe)
        logger.info("[%s] 스크립트: 저장 완료 → %s", title, txt_path.relative_to(PROJECT_DIR))
    except Exception:
        logger.exception("[%s] 전사 실패", title)

    return result
