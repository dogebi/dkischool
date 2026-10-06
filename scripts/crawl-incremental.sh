#!/usr/bin/env bash
# 증분 수집 → 내보내기 → 뷰어 갱신. 크론에서 호출하는 진입점.
# 사용: bash scripts/crawl-incremental.sh            (기본 사이트 전체 게시판)
#       SITE=dkischool BOARDS=47,41 bash scripts/crawl-incremental.sh
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT" || exit 1
mkdir -p logs data/export web

SITE="${SITE:-dkischool}"
BOARDS="${BOARDS:-}"
WORKERS="${WORKERS:-3}"
STAMP="$(date '+%Y-%m-%d %H:%M:%S')"
LOG="logs/crawl-incremental.log"
LOCK="data/.crawl.lock"

# 동시 실행 방지 (크론 중첩 방지)
exec 9>"$LOCK"
if ! flock -n 9; then
  echo "[$STAMP] 이미 실행 중 — 건너뜀" >>"$LOG"
  exit 0
fi

ARGS=(crawl --site "$SITE" --mode incremental --workers "$WORKERS")
[ -n "$BOARDS" ] && ARGS+=(--boards "$BOARDS")

{
  echo "[$STAMP] ── 증분 수집 시작 ($SITE ${BOARDS:-all}) ──"
  python3 -m dkis "${ARGS[@]}"
  echo "[$STAMP] ── 내보내기/뷰어 갱신 ──"
  python3 -m dkis export --site "$SITE"
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] ── 완료 ──"
} >>"$LOG" 2>&1

# ── 공개 사본 갱신 + 배포 (PUBLISH=0 이면 건너뜀) ──────────────────────────
# 크론이 여기까지 오면 공개 사이트가 자동으로 따라온다. 자격증명이 없어 push 가
# 실패해도 수집·뷰어 생성은 이미 끝난 상태이므로, 실패는 로그로만 남긴다.
if [ "${PUBLISH:-1}" = "1" ]; then
  {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] ── 공개 사본 갱신 ──"
    EXPORT=0 bash scripts/publish-pages.sh
    if [ -n "$(git status --porcelain index.html 2>/dev/null)" ]; then
      git add index.html posts.json attachments.csv summary.json robots.txt .nojekyll
      git commit -q -m "publish: $(date '+%m-%d %H:%M') 수집분 공개 사본 반영"
      if GIT_TERMINAL_PROMPT=0 git push -q origin main; then
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] push 완료 — GitHub Pages 재빌드"
      else
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] push 실패 — 커밋은 로컬에 남음(자격증명 확인)"
      fi
    else
      echo "공개 사본 변경 없음 — 커밋 생략"
    fi
  } >>"$LOG" 2>&1
fi

tail -n 6 "$LOG"
