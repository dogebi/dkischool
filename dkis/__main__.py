"""CLI 진입점.

사용 예:
  python3 -m dkis sites
  python3 -m dkis crawl  --site dkischool --mode full
  python3 -m dkis crawl  --site dkischool --boards 47,41        # 증분(기본)
  python3 -m dkis crawl  --site dkischool --all --attachments   # 첨부 다운로드 포함
  python3 -m dkis stats  --site dkischool
  python3 -m dkis export --site dkischool
  python3 -m dkis view   --site dkischool --serve 8388
  python3 -m dkis selftest
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from .config import get_site, list_sites
from .crawl import crawl_site
from .export import export_json, build_viewer
from .fetch import Fetcher
from .parse import parse_list, parse_pages, parse_view
from .store import Store

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB = ROOT / "data" / "dkis.sqlite3"
FILES_ROOT = ROOT / "data" / "files"
EXPORT_DIR = ROOT / "data" / "export"
WEB_DIR = ROOT / "web"


def _parse_boards(spec: str | None) -> list[int] | None:
    if not spec:
        return None
    if spec.strip().lower() == "all":
        return None
    return [int(x) for x in spec.replace(" ", "").split(",") if x]


def cmd_sites(args) -> int:
    for s in list_sites():
        print(f"{s['key']:12s} {s['name']}  ({s['base_url']}, school_code={s.get('school_code','-')})")
        for menu_no in sorted(s["boards"]):
            b = s["boards"][menu_no]
            print(f"    menu_no={menu_no:<4} {b['name']:16s} kind={b.get('kind','board')}")
    return 0


def _open(args) -> tuple[dict, Store]:
    site = get_site(args.site)
    store = Store(args.db or DEFAULT_DB)
    store.upsert_site(site)
    return site, store


def cmd_crawl(args) -> int:
    site, store = _open(args)
    boards = _parse_boards(args.boards)
    if args.attachments and not site["robots"].get("attachment_download_allowed", False):
        print("  ⚠ 첨부 다운로드가 켜졌습니다. 이 사이트의 robots.txt 는 '/upload/' 를 Disallow 로 "
              "선언하고 있습니다 — 운영자 판단 하에 진행하되, 과도한 요청은 피하십시오.")
    result = crawl_site(site, store, mode=args.mode, boards=boards,
                        with_attachments=args.attachments, files_root=FILES_ROOT,
                        max_pages=args.max_pages, limit_posts=args.limit_posts,
                        workers=args.workers)
    store.close()
    if args.json:
        print(json.dumps(result.as_dict(), ensure_ascii=False, indent=1))
    return 0 if result.totals["errors"] == 0 else 1


def cmd_stats(args) -> int:
    _, store = _open(args)
    s = store.stats(args.site)
    sb = store.conn.execute(
        "SELECT menu_no,name,kind,last_crawled,posts_seen,total_pages,full_pass_at "
        "FROM boards WHERE site_key=? ORDER BY menu_no", (args.site,)).fetchall()
    print(f"■ {args.site} — 게시글 {s['posts']}건 / 첨부 {s['attachments']}건 "
          f"(다운로드 {s['attachments_downloaded']})")
    print("\n[게시판]")
    per = {r["menu_no"]: r for r in s["per_board"]}
    for b in sb:
        p = per.get(b["menu_no"], {})
        done = "완주" if b["full_pass_at"] else "미완주"
        print(f"  menu_no={b['menu_no']:<4} {b['name']:18s} 글 {p.get('c',0):>5}  "
              f"최신 {(p.get('latest') or '-')[:19]:<19} 페이지 {b['posts_seen']}/{b['total_pages'] or '-'} "
              f"{done}  마지막수집 {b['last_crawled'] or '-'}")
    if s["by_attachment_ext"]:
        print("\n[첨부 확장자]", ", ".join(f"{r['ext']}:{r['c']}" for r in s["by_attachment_ext"]))
    print("\n[최근 실행]")
    for r in s["runs"]:
        print(f"  #{r['id']} {r['mode']:11s} {r['started_at']} → {r['finished_at'] or '(진행/중단)'} "
              f"신규 {r['posts_new']} 갱신 {r['posts_updated']} 첨부 {r['attachments_new']} 오류 {r['errors']}")
    store.close()
    if args.json:
        print(json.dumps(s, ensure_ascii=False, indent=1, default=str))
    return 0


def cmd_export(args) -> int:
    site, store = _open(args)
    out = Path(args.out) if args.out else EXPORT_DIR
    info = export_json(store, site, out)
    viewer = build_viewer(store, site, WEB_DIR, generated=time.strftime("%Y-%m-%d %H:%M"))
    store.close()
    print(f"  ✔ JSON/CSV: {info['posts']}건 → {info['out']}")
    print(f"  ✔ 뷰어    : {viewer}")
    return 0


def cmd_view(args) -> int:
    site, store = _open(args)
    viewer = build_viewer(store, site, WEB_DIR, generated=time.strftime("%Y-%m-%d %H:%M"))
    store.close()
    print(f"  ✔ 뷰어 생성: {viewer}")
    if args.serve:
        import functools
        import http.server
        import socketserver
        handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(WEB_DIR))
        with socketserver.TCPServer(("127.0.0.1", args.serve), handler) as httpd:
            print(f"  ▶ http://127.0.0.1:{args.serve}/  (Ctrl+C 종료)")
            httpd.serve_forever()
    return 0


def cmd_selftest(args) -> int:
    """소규모 실크롤로 파서·저장·내보내기 경로를 한 번에 검증."""
    site = get_site(args.site)
    db = Path(args.db) if args.db else ROOT / "data" / "selftest.sqlite3"
    if db.exists():
        db.unlink()
    store = Store(db)
    fetcher = Fetcher(site["base_url"], encoding=site["encoding"],
                      rate_limit_s=site["rate_limit_s"], timeout_s=site["timeout_s"],
                      robots_url=site["robots"]["url"], respect_robots=True, allow_upload=False)
    ok = True

    def check(label, cond, extra=""):
        nonlocal ok
        print(f"  {'PASS' if cond else 'FAIL'}  {label} {extra}")
        ok = ok and bool(cond)

    # 1) robots
    fetcher.robots.load()
    check("robots.txt 로드", fetcher.robots.fetched_at is not None,
          f"disallow={fetcher.robots.rules}")
    check("robots: 게시판 경로 허용", fetcher.robots.allowed("/?menu_no=47&board_mode=list"))
    check("robots: /upload/ 금지", not fetcher.robots.allowed("/upload/board/x.hwp"))

    # 2) 목록 파싱
    html = fetcher.get_text(fetcher.list_url(47, 1))
    rows = parse_list(html)
    check("목록 파싱", len(rows) > 5, f"{len(rows)}행, 첫 bno={rows[0].bno if rows else '-'}")
    check("목록 필드(제목/작성자/날짜)",
          bool(rows and rows[0].title and rows[0].author and rows[0].posted_date),
          f"{rows[0].title[:20] if rows else ''}")
    nums, last = parse_pages(html, 47)
    check("페이징 파싱(총 페이지 수)", bool(last and last > 1),
          f"pager={nums[:5]}… total_pages={last}")

    # 3) 상세 파싱
    p = parse_view(fetcher.get_text(fetcher.view_url(47, rows[0].bno)), 47, rows[0].bno)
    check("상세 제목", bool(p.title), p.title[:40])
    check("상세 본문", len(p.content_text) > 20, f"{len(p.content_text)}자")
    check("상세 첨부 감지", isinstance(p.attachments, list), f"{len(p.attachments)}개")

    # 4) 저장 + 증분
    r1 = crawl_site(site, store, mode="incremental", boards=[47], limit_posts=5,
                    progress=lambda *_: None, files_root=FILES_ROOT)
    n1 = store.stats(site["key"])["posts"]
    r2 = crawl_site(site, store, mode="incremental", boards=[47], limit_posts=5, progress=lambda *_: None)
    n2 = store.stats(site["key"])["posts"]
    check("DB 저장", n1 == 5, f"{n1}건")
    check("증분 재실행 시 중복 없음", n1 == n2, f"{n2}건")
    check("2회차 상세 재요청 없음", r2.totals["details_fetched"] == 0,
          f"fetched={r2.totals['details_fetched']}")

    # 5) 내보내기 + 뷰어
    info = export_json(store, site, ROOT / "data" / "selftest_export")
    v = build_viewer(store, site, ROOT / "data" / "selftest_web")
    check("JSON 내보내기", info["posts"] == n2, f"{info['posts']}건")
    check("뷰어 생성", Path(v).exists() and Path(v).stat().st_size > 2000,
          f"{Path(v).stat().st_size}B")
    store.close()
    print(f"\n  {'✅ SELFTEST PASS' if ok else '❌ SELFTEST FAIL'}")
    return 0 if ok else 1


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="dkis", description="withschool 기반 학교 게시판 아카이버")
    p.add_argument("--db", default=None, help="SQLite 경로 (기본: data/dkis.sqlite3)")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("sites", help="등록된 사이트/게시판 목록")
    s.set_defaults(func=cmd_sites)

    c = sub.add_parser("crawl", help="크롤 실행")
    c.add_argument("--site", default="dkischool")
    c.add_argument("--boards", help="쉼표 구분 menu_no (기본: 전체)")
    c.add_argument("--all", action="store_true", help="전체 게시판(증분/전체는 --mode)")
    c.add_argument("--mode", choices=["incremental", "full"], default="incremental")
    c.add_argument("--max-pages", type=int, default=None)
    c.add_argument("--limit-posts", type=int, default=None)
    c.add_argument("--attachments", action="store_true", help="/upload/ 파일도 다운로드")
    c.add_argument("--workers", type=int, default=3, help="상세 페이지 병렬 수집 수 (1~5)")
    c.add_argument("--json", action="store_true", help="결과를 JSON으로 출력")
    c.set_defaults(func=cmd_crawl)

    st = sub.add_parser("stats", help="수집 현황")
    st.add_argument("--site", default="dkischool")
    st.add_argument("--json", action="store_true")
    st.set_defaults(func=cmd_stats)

    e = sub.add_parser("export", help="JSON/CSV 내보내기 + 뷰어 생성")
    e.add_argument("--site", default="dkischool")
    e.add_argument("--out", default=None)
    e.set_defaults(func=cmd_export)

    v = sub.add_parser("view", help="뷰어 생성(필요 시 로컬 서빙)")
    v.add_argument("--site", default="dkischool")
    v.add_argument("--serve", type=int, default=None, help="예: 8388")
    v.set_defaults(func=cmd_view)

    t = sub.add_parser("selftest", help="파서/저장/증분/내보내기 자체 검증")
    t.add_argument("--site", default="dkischool")
    t.set_defaults(func=cmd_selftest)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
