#!/bin/bash
# git commit 전 문서 업데이트 리마인더
# PreToolUse 훅: src/auto_watch/ 등 코드 변경 시 docs staged 여부 확인

COMMAND=$(jq -r '.tool_input.command' < /dev/stdin)

# git commit 아니면 통과
echo "$COMMAND" | grep -q 'git commit' || exit 0

# 문서 업데이트 트리거 파일 확인
TRIGGER=$(git diff --cached --name-only | grep -E '^(src/auto_watch/|install\.sh|run\.sh|pyproject\.toml)')
[ -z "$TRIGGER" ] && exit 0

# 문서 파일이 같이 staged 되어 있는지
DOCS=$(git diff --cached --name-only | grep -E '^(README\.md|spec\.md|CLAUDE\.md)')

if [ -z "$DOCS" ]; then
  jq -n '{
    hookSpecificOutput: {
      hookEventName: "PreToolUse",
      additionalContext: "⚠️ 코드 변경(src/auto_watch/, install.sh 등)이 staged에 있지만 문서(README.md, spec.md, CLAUDE.md)가 없습니다. CLAUDE.md 규칙에 따라 문서 업데이트가 필요한지 확인하세요. 불필요하면 그대로 커밋해도 됩니다."
    }
  }'
fi
