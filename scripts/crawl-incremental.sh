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

tail -n 6 "$LOG"
