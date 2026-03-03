"""CLI 사용자 인터페이스 및 유틸리티 함수"""

from __future__ import annotations

import re
import select
import sys
from datetime import datetime


def _input_with_timeout(prompt: str, timeout: int = 10) -> str | None:
    """timeout초 안에 입력이 없으면 None 반환 (Unix 전용)."""
    print(prompt, end="", flush=True)
    ready, _, _ = select.select([sys.stdin], [], [], timeout)
    if ready:
        return sys.stdin.readline().strip()
    print()
    return None


def _format_duration(total_sec: int) -> str:
    """초를 H:MM:SS 또는 M:SS 형식으로 변환"""
    total_m, total_s = divmod(total_sec, 60)
    total_h, total_m = divmod(total_m, 60)
    if total_h:
        return f"{total_h}:{total_m:02d}:{total_s:02d}"
    return f"{total_m}:{total_s:02d}"


def select_lectures(all_lectures: list[dict]) -> list[dict]:
    """강의 목록 표시 (과목별 그룹, 상태 표시) + 사용자 선택 → 선택된 강의 리스트 반환"""
    if not all_lectures:
        return []

    unwatched = [l for l in all_lectures if not l.get("isCompleted")]
    completed = [l for l in all_lectures if l.get("isCompleted")]

    print("\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print(f"  전체 강의 {len(all_lectures)}개 (미수강 {len(unwatched)} / 수강완료 {len(completed)}):")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

    total_sec = 0
    unwatched_sec = 0
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

    # 과목별 그룹핑 (순서 유지)
    from collections import OrderedDict
    groups = OrderedDict()  # type: OrderedDict[str, list[tuple[int, dict]]]
    for i, lec in enumerate(all_lectures, 1):
        cn = lec.get("courseName", "unknown")
        if cn not in groups:
            groups[cn] = []
        groups[cn].append((i, lec))

    for course_name, items in groups.items():
        course_unwatched = sum(1 for _, l in items if not l.get("isCompleted"))
        course_total = len(items)
        if course_unwatched > 0:
            header = f"{course_name} (미수강 {course_unwatched} / 전체 {course_total})"
        else:
            header = f"{course_name} (수강 완료)"
        print(f"\n  ── {header} ──")

        for idx, lec in items:
            m, s = divmod(lec["durationSec"], 60)
            total_sec += lec["durationSec"]
            if not lec.get("isCompleted"):
                unwatched_sec += lec["durationSec"]

            status = "V" if lec.get("isCompleted") else " "

            # D-day: 수강완료는 표시 안 함
            d_day = ""
            if not lec.get("isCompleted") and lec.get("deadline"):
                deadline_dt = datetime.fromisoformat(lec["deadline"].replace("Z", "+00:00")).replace(tzinfo=None)
                days_left = (deadline_dt - today).days
                d_day = f" D-{days_left}" if days_left >= 0 else f" D+{abs(days_left)}"

            print(f"  [{idx:2d}] {status}  {lec['courseName']} — {lec['title']} ({m}:{s:02d}){d_day}")

    print(f"\n  총 재생시간: {_format_duration(total_sec)} (미수강: {_format_duration(unwatched_sec)})")
    print()

    first = True
    while True:
        try:
            if first:
                choice = _input_with_timeout(
                    "번호 (예: 1,2,3 / all / q) [10초 후 자동 all]: "
                )
                first = False
                if choice is None:
                    print("  ⏱ 10초 타임아웃 → 전체 선택")
                    return all_lectures
                choice = choice.lower()
            else:
                choice = input("번호 (예: 1,2,3 / all / q): ").strip().lower()
        except EOFError:
            return []

        if choice == "q":
            return []
        if choice == "all":
            return all_lectures

        # 번호 파싱
        try:
            indices = [int(x.strip()) for x in choice.split(",") if x.strip()]
            selected = []
            for idx in indices:
                if 1 <= idx <= len(all_lectures):
                    selected.append(all_lectures[idx - 1])
                else:
                    print(f"  [WARN] {idx}번은 범위 밖 (1~{len(all_lectures)})")
            if selected:
                return selected
            print("  유효한 번호를 입력하세요.")
        except ValueError:
            print("  숫자, all, q 중 하나를 입력하세요.")


def _is_target_video_url(url: str) -> bool:
    """재생 중인 강의 영상 URL인지 판별"""
    if not url.endswith(".mp4"):
        return False
    if "commons.ssu.ac.kr" not in url and "commonscdn.com" not in url:
        return False
    if "intro.mp4" in url or "media_files" not in url:
        return False
    return True


def _safe_filename(name: str) -> str:
    """파일시스템에 안전한 파일명으로 변환"""
    return re.sub(r'[\\/:*?"<>|]', '_', name).strip()
