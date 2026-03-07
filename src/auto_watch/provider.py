"""LMS Provider 프로토콜 및 팩토리"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from playwright.async_api import Page

    from .types import Course, Lecture, ProcessResult, TranscriptResult


class LMSProvider(Protocol):
    """LMS별 차이를 추상화하는 Provider 프로토콜"""

    @property
    def name(self) -> str: ...

    @property
    def display_name(self) -> str: ...

    def get_credentials(self) -> tuple[str, str]: ...

    async def login(self, page: Page) -> None: ...

    async def get_courses(self, page: Page) -> list[Course]: ...

    async def get_lectures(self, page: Page, course_id: str, course_name: str) -> list[Lecture]: ...

    async def process_lecture(
        self, page: Page, lecture: Lecture, *, defer_transcript: bool = False
    ) -> ProcessResult: ...

    async def drain_tasks(self) -> list[TranscriptResult]: ...


def get_provider(school: str) -> LMSProvider:
    """학교 이름으로 Provider 인스턴스 생성"""
    from .config import SCHOOL_CONFIGS

    config = SCHOOL_CONFIGS.get(school)
    if not config:
        raise ValueError(f"지원하지 않는 학교: {school}")

    if school == "ssu":
        from .providers.ssu import SSUProvider

        return SSUProvider(config)
    elif school == "kcu":
        from .providers.kcu import KCUProvider

        return KCUProvider(config)
    else:
        raise ValueError(f"지원하지 않는 학교: {school}")
