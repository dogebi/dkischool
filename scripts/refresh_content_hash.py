#!/usr/bin/env python3
"""content_hash 재계산 (1회성 유지보수).

2026-10-06: `content_hash` 입력에서 조회수(views)를 제거했다(`dkis/store.py`).
기존 행은 조회수가 섞인 옛 해시를 들고 있으므로, 다음 증분 수집에서 '수정됨'으로
잘못 잡히지 않도록 저장된 필드로 해시를 다시 계산해 채운다. 여러 번 실행해도 안전하다.

사용:
    python3 scripts/refresh_content_hash.py            # data/dkis.sqlite3
    python3 scripts/refresh_content_hash.py --db data/other.sqlite3
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dkis.store import Store, sha256_text  # noqa: E402

DEFAULT_DB = ROOT / "data" / "dkis.sqlite3"


def main() -> int:
    ap = argparse.ArgumentParser(description="content_hash 재계산")
    ap.add_argument("--db", default=str(DEFAULT_DB))
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    st = Store(args.db)
    rows = st.conn.execute(
        "SELECT site_key,menu_no,bno,title,content_text,author,content_hash FROM posts").fetchall()

    changed = 0
    for r in rows:
        new = sha256_text("|".join([r["title"] or "", r["content_text"] or "", r["author"] or ""]))
        if new != r["content_hash"]:
            changed += 1
            if not args.dry_run:
                st.conn.execute(
                    "UPDATE posts SET content_hash=? WHERE site_key=? AND menu_no=? AND bno=?",
                    (new, r["site_key"], r["menu_no"], r["bno"]))
    if not args.dry_run:
        st.conn.commit()
    print(f"{'[dry-run] ' if args.dry_run else ''}해시 재계산: 전체 {len(rows)}건 중 {changed}건 변경")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
