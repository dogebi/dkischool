"""크롤 엔진: 목록 순회 → 상세 수집 → 첨부 메타/다운로드 → 증분 상태 유지.

상세 페이지 요청은 페이지 단위로 소수(기본 3) 병렬로 가져오되 DB 쓰기는 메인 스레드에서
직렬로만 한다(SQLite 단일 연결, 상태 재현 가능). 레이트리밋은 fetch 계층에서 전역으로
걸리므로 병렬이어도 요청률은 설정값을 넘지 않는다.
"""
from __future__ import annotations

import hashlib
import json
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

from .fetch import Fetcher, FetchError, RobotsDisallowed
from .parse import (parse_list, parse_pages, parse_view, is_invalid_path,
                    is_permission_denied, Attachment)
from .store import Store, now

DEFAULT_WORKERS = 3
MAX_WORKERS = 5

# 게시판 종류별 수집 우선순위 (공지/문서 → 행사 → 사진앨범)
KIND_ORDER = {"board": 0, "file": 1, "event": 2, "gallery": 3}


@dataclass
class BoardResult:
    menu_no: int
    name: str = ""
    pages: int = 0
    rows: int = 0
    new: int = 0
    updated: int = 0
    unchanged: int = 0
    details_fetched: int = 0
    attachments_listed: int = 0
    attachments_downloaded: int = 0
    attachments_skipped: int = 0
    errors: int = 0
    stopped_reason: str = ""

    def as_dict(self) -> dict:
        return self.__dict__.copy()


@dataclass
class CrawlResult:
    site_key: str
    mode: str
    started: str = field(default_factory=now)
    finished: str = ""
    boards: list[BoardResult] = field(default_factory=list)

    @property
    def totals(self) -> dict:
        keys = ["pages", "rows", "new", "updated", "unchanged", "details_fetched",
                "attachments_listed", "attachments_downloaded", "attachments_skipped", "errors"]
        return {k: sum(getattr(b, k) for b in self.boards) for k in keys}

    def as_dict(self) -> dict:
        return {"site_key": self.site_key, "mode": self.mode, "started": self.started,
                "finished": self.finished, "boards": [b.as_dict() for b in self.boards],
                "totals": self.totals}


def _safe_name(name: str) -> str:
    bad = '<>:"/\\|?*\n\r\t'
    out = "".join("_" if c in bad else c for c in name).strip(" .")
    return out[:150] or "file"


def _download(fetcher: Fetcher, att, dest: Path) -> tuple[str, int | None, str | None, str]:
    """(status, size, sha256, note) 반환."""
    try:
        status_code, body = fetcher.get_bytes(att.url)
    except RobotsDisallowed as e:
        return "skipped_robots", None, None, str(e)
    except FetchError as e:
        return "error", None, None, str(e)
    if status_code != 200 or not body:
        return "error", None, None, f"HTTP {status_code}"
    if len(body) < 512 and b"<html" in body[:300].lower():
        return "error", None, None, "HTML 응답(파일 아님)"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(body)
    return "downloaded", len(body), hashlib.sha256(body).hexdigest(), ""


def _fetch_many(fetcher: Fetcher, tasks: list[tuple[int, str]],
                workers: int) -> dict[int, tuple[str, str]]:
    """{bno: ('ok', html) | ('err', message)} — 소수 병렬, 예외는 값으로 흡수."""
    out: dict[int, tuple[str, str]] = {}

    def one(item: tuple[int, str]) -> tuple[int, tuple[str, str]]:
        bno, url = item
        try:
            return bno, ("ok", fetcher.get_text(url))
        except (FetchError, RobotsDisallowed) as e:
            return bno, ("err", str(e))

    if workers <= 1 or len(tasks) <= 1:
        for item in tasks:
            bno, v = one(item)
            out[bno] = v
        return out
    with ThreadPoolExecutor(max_workers=workers) as ex:
        for bno, v in ex.map(one, tasks):
            out[bno] = v
    return out


def crawl_board(site: dict, store: Store, fetcher: Fetcher, menu_no: int, *,
                mode: str = "incremental", max_pages: int | None = None,
                limit_posts: int | None = None, with_attachments: bool = False,
                files_root: Path | None = None, run_id: int = 0,
                workers: int = DEFAULT_WORKERS, progress=print) -> BoardResult:
    meta = site["boards"].get(menu_no, {"name": f"menu_{menu_no}", "kind": "board"})
    res = BoardResult(menu_no=menu_no, name=meta["name"])
    page = 1
    max_page_seen = 1
    queued: set[str] = set()
    # 이 게시판을 이전에 끝까지 훑은 적이 있는가? 처음 보는 게시판이면 증분이라도
    # 조기 종료하지 않고 끝까지 걸어가야 한다(1페이지에 아는 글만 있는 반쪽 상태 방지).
    brow = store.get_board(site["key"], menu_no)
    completed_before = bool(brow and brow["full_pass_at"])

    while True:
        if max_pages and page > max_pages:
            res.stopped_reason = f"max_pages={max_pages}"
            break
        url = fetcher.list_url(menu_no, page)
        try:
            html = fetcher.get_text(url)
        except (FetchError, RobotsDisallowed) as e:
            res.errors += 1
            store.log_error(run_id, site["key"], menu_no, None, url, str(e))
            res.stopped_reason = f"목록 실패: {e}"
            break

        if is_invalid_path(html) or is_permission_denied(html):
            res.stopped_reason = "접근제한 또는 잘못된 경로"
            break

        rows = parse_list(html)
        pages, last_page = parse_pages(html, menu_no)
        if last_page:
            max_page_seen = max(max_page_seen, last_page)
        if not rows:
            res.stopped_reason = "빈 목록"
            break

        res.pages += 1
        new_on_page = 0
        pending: list[tuple[int, str]] = []
        row_by_bno = {}

        for row in rows:
            if limit_posts and res.rows >= limit_posts:
                res.stopped_reason = f"limit_posts={limit_posts}"
                break
            res.rows += 1
            row_by_bno[row.bno] = row
            prev = store.get_post(site["key"], menu_no, row.bno)
            if prev is None:
                new_on_page += 1
            # 이미 아는 글이고 목록 정보가 그대로면 상세 재요청 생략(조회수만 갱신)
            unchanged_listing = (prev is not None
                                 and (prev["title"] or "").strip() == row.title.strip()
                                 and (prev["posted_date"] or "") == row.posted_date)
            if unchanged_listing:
                store.conn.execute(
                    "UPDATE posts SET views=MAX(COALESCE(views,0),COALESCE(?,0)), last_seen=? "
                    "WHERE site_key=? AND menu_no=? AND bno=?",
                    (row.views, now(), site["key"], menu_no, row.bno))
                store.conn.commit()
                res.unchanged += 1
                if with_attachments:
                    for att in store.conn.execute(
                            "SELECT url,filename,ext,status FROM attachments "
                            "WHERE site_key=? AND menu_no=? AND bno=?",
                            (site["key"], menu_no, row.bno)).fetchall():
                        if att["status"] == "downloaded" or att["url"] in queued:
                            continue
                        queued.add(att["url"])
                        a = Attachment(filename=att["filename"], url=att["url"], ext=att["ext"])
                        dest = ((files_root or Path(".")) / site["key"] / str(menu_no)
                                / str(row.bno) / _safe_name(a.filename))
                        st, size, sha, note = _download(fetcher, a, dest)
                        store.upsert_attachment(site["key"], menu_no, row.bno, a, status=st,
                                                size=size, sha=sha,
                                                local_path=str(dest) if st == "downloaded" else "",
                                                note=note)
                        res.attachments_downloaded += (st == "downloaded")
                        res.attachments_skipped += (st != "downloaded")
                continue

            pending.append((row.bno, fetcher.view_url(menu_no, row.bno, page)))

        fetched = _fetch_many(fetcher, pending, workers)

        for bno, (kind, payload) in fetched.items():
            row = row_by_bno[bno]
            detail_url = fetcher.view_url(menu_no, bno)
            if kind == "err":
                res.errors += 1
                store.log_error(run_id, site["key"], menu_no, bno, detail_url, payload)
                continue
            res.details_fetched += 1
            vhtml = payload
            if is_permission_denied(vhtml) or is_invalid_path(vhtml):
                store.log_error(run_id, site["key"], menu_no, bno, detail_url,
                                "접근제한/잘못된 경로 응답")
                res.errors += 1
                continue

            post = parse_view(vhtml, menu_no, bno)
            # 상세에서 못 잡은 값은 목록 정보로 보완
            post.title = post.title or row.title
            post.author = post.author or row.author
            post.posted_at = post.posted_at or row.posted_date
            post.views = row.views if row.views is not None else post.views

            status = store.upsert_post(site["key"], post, url=detail_url,
                                       posted_date=row.posted_date,
                                       is_notice=row.is_notice,
                                       has_attachment=bool(post.attachments) or row.has_attachment)
            res.new += (status == "new")
            res.updated += (status == "updated")
            res.unchanged += (status == "unchanged")

            for att in post.attachments:
                res.attachments_listed += 1
                st, size, sha, note, local = "listed", None, None, "", ""
                if with_attachments and att.url not in queued:
                    queued.add(att.url)
                    dest = ((files_root or Path(".")) / site["key"] / str(menu_no)
                            / str(bno) / _safe_name(att.filename))
                    if dest.exists() and dest.stat().st_size > 0:
                        st = "downloaded"
                        size = dest.stat().st_size
                        sha = hashlib.sha256(dest.read_bytes()).hexdigest()
                        local = str(dest)
                    else:
                        st, size, sha, note = _download(fetcher, att, dest)
                        local = str(dest) if st == "downloaded" else ""
                    res.attachments_downloaded += (st == "downloaded")
                    res.attachments_skipped += (st not in ("downloaded", "listed"))
                store.upsert_attachment(site["key"], menu_no, bno, att, status=st,
                                        size=size, sha=sha, local_path=local, note=note)

        progress(f"    · {meta['name']} p{page}/{max_page_seen}: +{new_on_page}신규 "
                 f"(누적 신규 {res.new}, 상세 {res.details_fetched}, 첨부 {res.attachments_listed})")

        # 증분: 이 게시판을 과거에 끝까지 훑은 적이 있고, 이 페이지에 새 글이 없으면 중단
        if mode == "incremental" and completed_before and new_on_page == 0:
            res.stopped_reason = f"신규 0건 (p{page} 도달)"
            break
        if limit_posts and res.rows >= limit_posts:
            res.stopped_reason = res.stopped_reason or f"limit_posts={limit_posts}"
            break
        if not pages or not last_page:
            res.stopped_reason = res.stopped_reason or f"마지막 페이지(p{page})"
            break
        if page >= last_page:
            res.stopped_reason = f"마지막 페이지(p{last_page})"
            break
        page += 1
        if page > 4000:                       # 안전 상한
            res.stopped_reason = "안전 상한 4000p"
            break

    completed = res.stopped_reason.startswith("마지막 페이지") or res.stopped_reason == "빈 목록"
    store.touch_board(site["key"], menu_no, last_page=res.pages, posts_seen=res.rows,
                      total_pages=max_page_seen, completed=completed)
    if completed:
        res.stopped_reason += " · 전체 1회 완주"
    return res


def crawl_site(site: dict, store: Store, *, mode: str = "incremental",
               boards: list[int] | None = None, fetcher: Fetcher | None = None,
               with_attachments: bool = False, files_root: Path | None = None,
               max_pages: int | None = None, limit_posts: int | None = None,
               workers: int = DEFAULT_WORKERS, progress=print) -> CrawlResult:
    store.upsert_site(site)
    target = boards or sorted(
        site["boards"],
        key=lambda m: (KIND_ORDER.get(site["boards"][m].get("kind", "board"), 0), m))
    workers = max(1, min(MAX_WORKERS, workers))
    fetcher = fetcher or Fetcher(
        site["base_url"], encoding=site.get("encoding", "euc-kr"),
        ua=site.get("ua", ""), rate_limit_s=site.get("rate_limit_s", 0.5),
        timeout_s=site.get("timeout_s", 30), retries=site.get("retries", 3),
        robots_url=site.get("robots", {}).get("url", ""),
        respect_robots=site.get("robots", {}).get("respect", True),
        allow_upload=site.get("robots", {}).get("attachment_download_allowed", False) or with_attachments,
    )
    result = CrawlResult(site_key=site["key"], mode=mode)
    run_id = store.start_run(site["key"], mode, target)
    t0 = time.time()
    progress(f"  ▶ {site['name']} ({site['base_url']}) mode={mode} workers={workers} boards={target}")
    for menu_no in target:
        if menu_no not in site["boards"]:
            progress(f"    ! 등록되지 않은 menu_no={menu_no} — 건너뜀")
            continue
        br = crawl_board(site, store, fetcher, menu_no, mode=mode, max_pages=max_pages,
                         limit_posts=limit_posts, with_attachments=with_attachments,
                         files_root=files_root, run_id=run_id, workers=workers, progress=progress)
        result.boards.append(br)
    result.finished = now()
    t = result.totals
    store.finish_run(run_id, pages=t["pages"], posts_new=t["new"], posts_updated=t["updated"],
                     attachments_new=t["attachments_downloaded"], errors=t["errors"],
                     stats_json=json.dumps({"fetcher": fetcher.stats.as_dict(),
                                            "robots": fetcher.robots.as_dict(),
                                            "workers": workers,
                                            "elapsed_s": round(time.time() - t0, 1)},
                                           ensure_ascii=False),
                     notes="; ".join(f"{b.menu_no}:{b.stopped_reason}" for b in result.boards)[:900])
    progress(f"  ✔ 완료 {t['pages']}p / 신규 {t['new']} / 갱신 {t['updated']} / "
             f"첨부목록 {t['attachments_listed']} / 다운로드 {t['attachments_downloaded']} / "
             f"오류 {t['errors']} / {time.time() - t0:.1f}s")
    return result
