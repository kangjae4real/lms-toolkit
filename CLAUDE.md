# CLAUDE.md

## 프로젝트 개요

숭실대 LMS 미수강 동영상 강의를 자동 수강 처리 + 스크립트 추출하는 CLI 도구. `src/auto_watch/` 패키지가 핵심.

## 실행

```bash
python -m src.auto_watch
```

## 환경 변수 (.env)

```
USERID=(학번)
PASSWORD=(비밀번호)
```

## 비직관적 사실

- **Python 3.9+** (venv는 3.9, `from __future__ import annotations`로 타입 힌트 호환)
- **headed 브라우저 필수**: 헤드리스면 LTI 플레이어 완료 이벤트 미발생
- **Chrome 경로 하드코딩**: `/Applications/Google Chrome.app/`
- **Whisper 모델 캐시**: `~/.cache/huggingface/hub/` (~1.5GB)
- 출력: `output/과목명/` 에 `.mp4` + `.txt` 저장. WAV는 전사 후 자동 삭제

## 규칙

- `src/auto_watch/`의 사용자 대면 동작 변경 시 관련 문서도 함께 업데이트할 것
- 사용자 대면 메시지 및 문서는 한국어
- Mac 전용 (Windows 미지원)

## Git 커밋

- **코드 변경 후 항상 커밋한다.** 작업 단위(논리적으로 독립된 변경)마다 나눠서 커밋
- Conventional Commits 형식: `<type>(<scope>): <한국어 설명>`
  - type: `feat`, `fix`, `refactor`, `docs`, `test`, `chore`
  - scope: 생략 가능. 마일스톤이 있으면 `feat(M2.5):` 형태로 표기
- 커밋 메시지는 한국어, 첫 줄 72자 이내
- 하나의 커밋에 하나의 관심사 (docs와 구현 코드를 섞지 않는다)
