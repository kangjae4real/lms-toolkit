import logging
import platform

from src.auto_watch.util import format_duration

logger = logging.getLogger(__name__)

PARAGRAPH_SEC = 30


def format_paragraphs(segments: list[tuple[float, str]]) -> str:
    """(시작초, 텍스트) 구간들을 약 30초 문단으로 묶고 문단마다 [시각]을 붙인다."""
    paragraphs: list[tuple[float, list[str]]] = []
    for start, text in segments:
        text = text.strip()
        if not text:
            continue
        if not paragraphs or start - paragraphs[-1][0] >= PARAGRAPH_SEC:
            paragraphs.append((start, []))
        paragraphs[-1][1].append(text)
    return "\n".join(
        f"[{format_duration(start)}]\n{' '.join(texts)}\n" for start, texts in paragraphs
    )


# CTranslate2에 Metal 백엔드가 없어 faster-whisper는 Apple GPU를 못 쓴다.
# 같은 오디오 기준 CPU 2.5배속 → mlx 13배속이라 arm64에서는 mlx를 우선한다.
MLX_REPO = "mlx-community/whisper-large-v3-turbo"

# 기본값(True)이면 한 번 잘못 들은 말이 다음 구간 프롬프트로 넘어가 "B B B…" 반복 루프가
# 되고, 그동안의 실제 발화를 덮어쓴다. 문맥이 끊긴다고 켜면 안 된다.
CONDITION_ON_PREVIOUS_TEXT = False

MLX_FRAMES_PER_SEC = 100  # mlx_whisper.audio: SAMPLE_RATE 16000 / HOP_LENGTH 160
PROGRESS_REPORT_SEC = 60


def _log_progress(done_sec: float, total_sec: float) -> None:
    seg_m, seg_s = divmod(int(done_sec), 60)
    dur_m, dur_s = divmod(int(total_sec), 60)
    logger.info(
        "스크립트: 전사 %d:%02d/%d:%02d (%.0f%%)",
        seg_m,
        seg_s,
        dur_m,
        dur_s,
        done_sec / total_sec * 100,
    )


class _MlxProgress:
    """mlx_whisper 내부의 tqdm.tqdm 자리에 끼워 넣는 대체품.
    진짜 tqdm 막대는 병렬 다운로드 로그 줄과 섞여 깨지므로 로그 줄로 바꿔 찍는다."""

    def __init__(self, total: int, **_kwargs) -> None:
        self._total_sec = total / MLX_FRAMES_PER_SEC
        self._done_sec = 0.0
        self._last_report = 0.0

    def __enter__(self) -> "_MlxProgress":
        return self

    def __exit__(self, *_exc) -> None:
        pass

    def update(self, n: int) -> None:
        self._done_sec += n / MLX_FRAMES_PER_SEC
        if self._total_sec and self._done_sec - self._last_report >= PROGRESS_REPORT_SEC:
            _log_progress(self._done_sec, self._total_sec)
            self._last_report = self._done_sec


def _load_mlx_model() -> str:
    """mlx_whisper 는 첫 transcribe 호출 때 모델을 올린다. 그러면 로딩 시간이
    전사 진행률 없는 구간으로 보여서 미리 올린다."""
    import mlx.core as mx
    from huggingface_hub import snapshot_download
    from huggingface_hub.errors import LocalEntryNotFoundError
    from mlx_whisper.transcribe import ModelHolder  # type: ignore[import-untyped]

    try:
        path = snapshot_download(MLX_REPO, local_files_only=True)
    except LocalEntryNotFoundError:
        logger.info("Whisper 모델 첫 다운로드 (~1.5GB)...")
        path = snapshot_download(MLX_REPO)
    # transcribe 기본 dtype(fp16)과 맞춰야 한다. ModelHolder 는 경로만 비교해서
    # 여기서 다른 dtype 으로 올리면 전사도 조용히 그 dtype 으로 돈다
    ModelHolder.get_model(path, mx.float16)
    return path


class WhisperTranscriber:
    def __init__(self, model_name: str = "turbo") -> None:
        self._use_mlx = False
        if platform.machine() == "arm64":
            try:
                import mlx_whisper  # noqa: F401

                self._use_mlx = True
                logger.info("mlx-whisper 사용 (Apple GPU)")
                self._mlx_path = _load_mlx_model()
                return
            except ImportError:
                logger.warning("mlx-whisper 없음 — faster-whisper(CPU)로 대체")

        from faster_whisper import WhisperModel

        logger.info("faster-whisper 모델 로드 중: %s", model_name)
        self.model = WhisperModel(model_name, device="cpu", compute_type="int8")

    def transcribe(self, audio_path: str, txt_path: str) -> None:
        if self._use_mlx:
            self._transcribe_mlx(audio_path, txt_path)
            return

        segments, info = self.model.transcribe(
            audio_path,
            language="ko",
            beam_size=5,
            condition_on_previous_text=CONDITION_ON_PREVIOUS_TEXT,
        )
        duration = info.duration

        collected: list[tuple[float, str]] = []
        last_report = 0
        for segment in segments:
            collected.append((segment.start, segment.text))
            if duration and segment.end - last_report >= PROGRESS_REPORT_SEC:
                _log_progress(segment.end, duration)
                last_report = segment.end

        with open(txt_path, "w", encoding="utf-8") as f:
            f.write(format_paragraphs(collected))
        logger.debug("Whisper 변환 완료: %s", txt_path)
        logger.info("감지된 언어: %s (확률: %.2f)", info.language, info.language_probability)

    def _transcribe_mlx(self, audio_path: str, txt_path: str) -> None:
        import importlib
        from types import SimpleNamespace
        from typing import Any

        import mlx.core as mx
        import mlx_whisper

        # mlx_whisper.transcribe 속성은 같은 이름의 함수가 덮고 있어 모듈을 따로 꺼낸다
        mlx_transcribe_mod: Any = importlib.import_module("mlx_whisper.transcribe")

        orig_tqdm = mlx_transcribe_mod.tqdm
        mlx_transcribe_mod.tqdm = SimpleNamespace(tqdm=_MlxProgress)
        try:
            result = mlx_whisper.transcribe(
                audio_path,
                path_or_hf_repo=self._mlx_path,
                language="ko",
                condition_on_previous_text=CONDITION_ON_PREVIOUS_TEXT,
            )
            segments = [(seg["start"], seg["text"]) for seg in result["segments"]]
            with open(txt_path, "w", encoding="utf-8") as f:
                f.write(format_paragraphs(segments))
            logger.debug("Whisper 변환 완료: %s", txt_path)
        finally:
            mlx_transcribe_mod.tqdm = orig_tqdm
            # mlx는 Metal 버퍼 풀을 스스로 반환하지 않는다. 자동 수강은 전사가 끝나도
            # 브라우저 대기로 프로세스가 몇 시간 살아 있어, 안 지우면 그동안 계속 점유한다.
            freed = mx.get_cache_memory()
            mx.clear_cache()
            if freed:
                logger.info("GPU 캐시 반환: %.1fGB", freed / 1e9)
