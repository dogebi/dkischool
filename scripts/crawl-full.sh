#!/usr/bin/env bash
# 최초 1회 전체 백필(게시판 전체, 증분 모드 = 빈 DB에서는 실질 전체 수집).
# 첨부 파일까지 받으려면: ATT=1 bash scripts/crawl-full.sh
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT" || exit 1
mkdir -p logs

SITE="${SITE:-dkischool}"
WORKERS="${WORKERS:-3}"
LOG="logs/crawl-full.log"
LOCK="data/.crawl.lock"

exec 9>"$LOCK"
if ! flock -n 9; then
  echo "[$(date '+%F %T')] 이미 실행 중 — 종료" | tee -a "$LOG"
  exit 0
fi

ARGS=(crawl --site "$SITE" --mode incremental --workers "$WORKERS")
[ -n "${ATT:-}" ] && ARGS+=(--attachments)

{
  echo "[$(date '+%F %T')] ══ 전체 수집 시작 ══"
  python3 -m dkis "${ARGS[@]}"
  python3 -m dkis export --site "$SITE"
  echo "[$(date '+%F %T')] ══ 전체 수집 완료 ══"
} >>"$LOG" 2>&1

tail -n 4 "$LOG"
