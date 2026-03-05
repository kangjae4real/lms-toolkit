"""설정 상수 및 환경변수 로딩"""

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# 인증
USERID = os.getenv("USERID")
PASSWORD = os.getenv("PASSWORD")

# LMS URL
BASE_URL = "https://canvas.ssu.ac.kr"
MYPAGE_URL = f"{BASE_URL}/accounts/1/external_tools/67?launch_type=global_navigation"

# 파일 경로
PROJECT_DIR = Path(__file__).parent.parent.parent
OUTPUT_DIR = PROJECT_DIR / "output"

# 브라우저
CHROME_PATH = os.getenv(
    "CHROME_PATH",
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
)
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/122.0.0.0 Safari/537.36"
)

# 타임아웃 (밀리초)
LOGIN_TIMEOUT_MS = 10_000
SELECTOR_TIMEOUT_MS = 15_000
IFRAME_TIMEOUT_MS = 20_000
RESUME_DIALOG_TIMEOUT_MS = 5_000
RESUME_DIALOG_POST_PLAY_TIMEOUT_MS = 10_000

# 재생 모니터링
PLAYBACK_LOG_INTERVAL_SEC = 30
PLAYBACK_COMPLETION_THRESHOLD = 99.5
PLAYBACK_TIMEOUT_BUFFER_SEC = 60

# 다운로드
DOWNLOAD_CHUNK_SIZE = 65_536
DOWNLOAD_REPORT_INTERVAL = 50 * 1024 * 1024
