"""config.py 상수 테스트"""

from src.auto_watch.config import (
    BASE_URL,
    CHROME_PATH,
    DOWNLOAD_CHUNK_SIZE,
    OUTPUT_DIR,
    PLAYBACK_COMPLETION_THRESHOLD,
    PROJECT_DIR,
    USER_AGENT,
)


def test_base_url():
    assert BASE_URL.startswith("https://")
    assert "ssu.ac.kr" in BASE_URL


def test_project_dir_exists():
    assert PROJECT_DIR.exists()
    assert (PROJECT_DIR / "pyproject.toml").exists()


def test_output_dir_is_under_project():
    assert str(OUTPUT_DIR).startswith(str(PROJECT_DIR))


def test_chrome_path_is_string():
    assert isinstance(CHROME_PATH, str)
    assert len(CHROME_PATH) > 0


def test_user_agent_contains_chrome():
    assert "Chrome" in USER_AGENT


def test_download_chunk_size_positive():
    assert DOWNLOAD_CHUNK_SIZE > 0


def test_completion_threshold_range():
    assert 90 <= PLAYBACK_COMPLETION_THRESHOLD <= 100
