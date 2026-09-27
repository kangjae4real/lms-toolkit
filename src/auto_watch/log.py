"""로깅 설정"""

import logging
import sys


def setup_logging(verbose: bool = False) -> None:
    """애플리케이션 로깅 초기화. stderr로 출력."""
    level = logging.DEBUG if verbose else logging.INFO
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter("[%(levelname)s] %(message)s"))
    logging.basicConfig(level=level, handlers=[handler])
    # huggingface_hub 가 모델 확인 요청마다 INFO 로 URL 을 찍는다
    logging.getLogger("httpx").setLevel(logging.WARNING)
