"""플러그인 인터페이스 및 discovery"""

from __future__ import annotations

import importlib.metadata
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from argparse import ArgumentParser, Namespace

    from playwright.async_api import Page

    from .types import Course

logger = logging.getLogger(__name__)


@dataclass
class PluginMenuEntry:
    """CLI 메뉴에 표시할 항목"""

    label: str
    description: str


class LMSPlugin(Protocol):
    """플러그인이 구현해야 할 프로토콜 (duck typing)"""

    @property
    def name(self) -> str: ...

    @property
    def menu_entry(self) -> PluginMenuEntry: ...

    def add_arguments(self, parser: ArgumentParser) -> None: ...

    def should_handle(self, args: Namespace) -> bool: ...

    async def run(self, page: Page, courses: list[Course]) -> str | None: ...


def discover_plugins() -> list[LMSPlugin]:
    """entry_points에서 lms_toolkit.plugins 그룹의 플러그인을 탐색"""
    plugins: list[LMSPlugin] = []
    for ep in importlib.metadata.entry_points(group="lms_toolkit.plugins"):
        try:
            plugin_cls = ep.load()
            plugins.append(plugin_cls())
            logger.debug("플러그인 로드: %s (%s)", ep.name, ep.value)
        except Exception:
            logger.warning("플러그인 로드 실패: %s", ep.name, exc_info=True)
    return plugins
