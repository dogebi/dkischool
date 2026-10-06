#!/usr/bin/env bash
# GitHub Pages 공개 사본 만들기 — 생성된 뷰어를 저장소 루트로 복사한다.
#   사용: bash scripts/publish-pages.sh            (SITE=dkischool 기본)
# 뷰어(web/index.html)는 export 로 생성되므로, 루트 index.html 은 언제나 재생성 대상이다.
# (손으로 고친 루트 index.html 은 다음 실행에서 web/index.html 내용으로 덮인다 → 수정은 dkis/export.py 에서)
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
SITE="${SITE:-dkischool}"

mkdir -p data/export web
[ "${EXPORT:-1}" = "1" ] && python3 -m dkis export --site "$SITE"

cp web/index.html index.html
cp data/export/posts.json data/export/attachments.csv data/export/summary.json ./

# 학교 게시판 데이터 — 검색엔진 노출 차단 메타 삽입(없을 때만)
python3 - <<'PY'
import pathlib, re
p = pathlib.Path("index.html")
html = p.read_text(encoding="utf-8")
if 'name="robots"' not in html:
    html = html.replace('<meta name="generator" content="dkis-archive">',
                        '<meta name="generator" content="dkis-archive">\n'
                        '<meta name="robots" content="noindex, nofollow">', 1)
    p.write_text(html, encoding="utf-8")
    print("robots 메타 삽입")
PY

touch .nojekyll
printf 'User-agent: *\nDisallow: /\n' > robots.txt

printf '공개 사본 준비 완료: index.html %s bytes · posts.json %s bytes\n' \
  "$(stat -c%s index.html)" "$(stat -c%s posts.json)"
printf '커밋: git add index.html posts.json attachments.csv summary.json robots.txt .nojekyll && git commit -m "publish: 뷰어 공개 사본 갱신"\n'
