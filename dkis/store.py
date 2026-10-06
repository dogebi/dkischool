"""SQLite 저장소 — 게시글/첨부/크롤 실행 이력. 증분 크롤의 기준 상태를 여기서 읽는다."""
from __future__ import annotations

import hashlib
import json
import sqlite3
import time
from pathlib import Path

SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS sites (
  site_key     TEXT PRIMARY KEY,
  name         TEXT,
  base_url     TEXT,
  school_code  TEXT,
  created_at   TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS boards (
  site_key     TEXT NOT NULL,
  menu_no      INTEGER NOT NULL,
  name         TEXT,
  kind         TEXT,
  first_seen   TEXT,
  last_crawled TEXT,
  last_page    INTEGER DEFAULT 0,
  posts_seen   INTEGER DEFAULT 0,
  PRIMARY KEY (site_key, menu_no)
);

CREATE TABLE IF NOT EXISTS posts (
  site_key      TEXT NOT NULL,
  menu_no       INTEGER NOT NULL,
  bno           INTEGER NOT NULL,
  title         TEXT,
  author        TEXT,
  posted_at     TEXT,
  posted_date   TEXT,
  views         INTEGER,
  is_notice     INTEGER DEFAULT 0,
  has_attachment INTEGER DEFAULT 0,
  content_html  TEXT,
  content_text  TEXT,
  images_json   TEXT,
  url           TEXT,
  content_hash  TEXT,
  first_seen    TEXT,
  last_seen     TEXT,
  updated_at    TEXT,
  PRIMARY KEY (site_key, menu_no, bno)
);
CREATE INDEX IF NOT EXISTS idx_posts_date  ON posts(site_key, posted_at DESC);
CREATE INDEX IF NOT EXISTS idx_posts_board ON posts(site_key, menu_no, bno DESC);

CREATE TABLE IF NOT EXISTS attachments (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  site_key     TEXT NOT NULL,
  menu_no      INTEGER NOT NULL,
  bno          INTEGER NOT NULL,
  filename     TEXT,
  url          TEXT,
  ext          TEXT,
  size_bytes   INTEGER,
  sha256       TEXT,
  local_path   TEXT,
  status       TEXT DEFAULT 'listed',   -- listed | downloaded | skipped_robots | error
  note         TEXT,
  updated_at   TEXT,
  UNIQUE (site_key, menu_no, bno, url)
);
CREATE INDEX IF NOT EXISTS idx_att_post ON attachments(site_key, menu_no, bno);

CREATE TABLE IF NOT EXISTS runs (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  site_key     TEXT,
  mode         TEXT,
  started_at   TEXT,
  finished_at  TEXT,
  boards       TEXT,
  pages        INTEGER DEFAULT 0,
  posts_new    INTEGER DEFAULT 0,
  posts_updated INTEGER DEFAULT 0,
  attachments_new INTEGER DEFAULT 0,
  errors       INTEGER DEFAULT 0,
  stats_json   TEXT,
  notes        TEXT
);

CREATE TABLE IF NOT EXISTS errors (
  id        INTEGER PRIMARY KEY AUTOINCREMENT,
  run_id    INTEGER,
  site_key  TEXT,
  menu_no   INTEGER,
  bno       INTEGER,
  url       TEXT,
  message   TEXT,
  at        TEXT DEFAULT (datetime('now'))
);
"""


def now() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())


def sha256_text(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8", "replace")).hexdigest()


class Store:
    def __init__(self, db_path: str | Path):
        self.path = Path(db_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.path), timeout=30)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        self._migrate()
        self.conn.commit()

    def _migrate(self) -> None:
        """기존 DB에 추가된 컬럼을 채운다(스키마는 CREATE IF NOT EXISTS 라 신규 컬럼이 안 붙는다)."""
        cols = {r["name"] for r in self.conn.execute("PRAGMA table_info(boards)")}
        if "total_pages" not in cols:
            self.conn.execute("ALTER TABLE boards ADD COLUMN total_pages INTEGER DEFAULT 0")
        if "full_pass_at" not in cols:
            self.conn.execute("ALTER TABLE boards ADD COLUMN full_pass_at TEXT")

    # ---- 기본 -------------------------------------------------------------
    def close(self) -> None:
        self.conn.commit()
        self.conn.close()

    def upsert_site(self, site: dict) -> None:
        self.conn.execute(
            "INSERT INTO sites(site_key,name,base_url,school_code) VALUES(?,?,?,?) "
            "ON CONFLICT(site_key) DO UPDATE SET name=excluded.name, base_url=excluded.base_url, "
            "school_code=excluded.school_code",
            (site["key"], site["name"], site["base_url"], site.get("school_code", "")),
        )
        for menu_no, meta in site["boards"].items():
            self.conn.execute(
                "INSERT INTO boards(site_key,menu_no,name,kind,first_seen) VALUES(?,?,?,?,?) "
                "ON CONFLICT(site_key,menu_no) DO UPDATE SET name=excluded.name, kind=excluded.kind",
                (site["key"], int(menu_no), meta["name"], meta.get("kind", "board"), now()),
            )
        self.conn.commit()

    def touch_board(self, site_key: str, menu_no: int, *, last_page: int = 0,
                    posts_seen: int = 0, total_pages: int = 0, completed: bool = False) -> None:
        self.conn.execute(
            "UPDATE boards SET last_crawled=?, last_page=MAX(last_page,?), "
            "posts_seen=MAX(posts_seen,?), total_pages=MAX(COALESCE(total_pages,0),?), "
            "full_pass_at=CASE WHEN ? THEN ? ELSE full_pass_at END "
            "WHERE site_key=? AND menu_no=?",
            (now(), last_page, posts_seen, total_pages, 1 if completed else 0, now(),
             site_key, menu_no),
        )
        self.conn.commit()

    def get_board(self, site_key: str, menu_no: int) -> sqlite3.Row | None:
        cur = self.conn.execute("SELECT * FROM boards WHERE site_key=? AND menu_no=?",
                                (site_key, menu_no))
        return cur.fetchone()

    # ---- 게시글 -----------------------------------------------------------
    def existing_bnos(self, site_key: str, menu_no: int) -> set[int]:
        cur = self.conn.execute("SELECT bno FROM posts WHERE site_key=? AND menu_no=?",
                                (site_key, menu_no))
        return {r["bno"] for r in cur.fetchall()}

    def get_post(self, site_key: str, menu_no: int, bno: int) -> sqlite3.Row | None:
        cur = self.conn.execute("SELECT * FROM posts WHERE site_key=? AND menu_no=? AND bno=?",
                                (site_key, menu_no, bno))
        return cur.fetchone()

    def upsert_post(self, site_key: str, post, *, url: str = "", posted_date: str = "",
                    is_notice: bool = False, has_attachment: bool = False) -> str:
        """('new'|'updated'|'unchanged') 반환."""
        # content_hash 입력에 조회수(views)를 넣지 않는다 — 조회수는 열람할 때마다 서버가
        # 증가시키므로, 해시에 포함하면 '내용이 같은 글'도 매 수집마다 '수정됨'으로 집계된다
        # (크롤 자신이 조회수를 올려 다시 수정으로 잡히는 순환). 조회수는 아래 unchanged
        # 경로에서 계속 최신값으로 갱신한다.
        chash = sha256_text("|".join([post.title or "", post.content_text or "",
                                      post.author or ""]))
        prev = self.get_post(site_key, post.menu_no, post.bno)
        payload = (
            post.title, post.author, post.posted_at, posted_date, post.views,
            1 if is_notice else 0, 1 if has_attachment else 0,
            post.content_html, post.content_text, json.dumps(post.images, ensure_ascii=False),
            url, chash, now(), now(),
        )
        if prev is None:
            self.conn.execute(
                "INSERT INTO posts(site_key,menu_no,bno,title,author,posted_at,posted_date,views,"
                "is_notice,has_attachment,content_html,content_text,images_json,url,content_hash,"
                "first_seen,last_seen,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (site_key, post.menu_no, post.bno) + (payload[0], payload[1], payload[2], payload[3],
                                                      payload[4], payload[5], payload[6], payload[7],
                                                      payload[8], payload[9], payload[10], payload[11],
                                                      payload[12], payload[12], payload[13]),
            )
            status = "new"
        else:
            if prev["content_hash"] == chash:
                self.conn.execute(
                    "UPDATE posts SET last_seen=?, views=MAX(COALESCE(views,0),COALESCE(?,0)) "
                    "WHERE site_key=? AND menu_no=? AND bno=?",
                    (now(), post.views, site_key, post.menu_no, post.bno))
                status = "unchanged"
            else:
                self.conn.execute(
                    "UPDATE posts SET title=?,author=?,posted_at=?,posted_date=?,views=?,is_notice=?,"
                    "has_attachment=?,content_html=?,content_text=?,images_json=?,url=?,content_hash=?,"
                    "last_seen=?,updated_at=? WHERE site_key=? AND menu_no=? AND bno=?",
                    (payload[0], payload[1], payload[2], payload[3], payload[4], payload[5], payload[6],
                     payload[7], payload[8], payload[9], payload[10], payload[11], payload[12],
                     payload[13], site_key, post.menu_no, post.bno))
                status = "updated"
        self.conn.commit()
        return status

    # ---- 첨부 -------------------------------------------------------------
    def upsert_attachment(self, site_key: str, menu_no: int, bno: int, att, *,
                          status: str = "listed", size=None, sha=None, local_path="",
                          note: str = "") -> None:
        self.conn.execute(
            "INSERT INTO attachments(site_key,menu_no,bno,filename,url,ext,size_bytes,sha256,"
            "local_path,status,note,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?) "
            "ON CONFLICT(site_key,menu_no,bno,url) DO UPDATE SET filename=excluded.filename, "
            "ext=excluded.ext, size_bytes=COALESCE(excluded.size_bytes,attachments.size_bytes), "
            "sha256=COALESCE(excluded.sha256,attachments.sha256), "
            "local_path=CASE WHEN excluded.local_path<>'' THEN excluded.local_path ELSE attachments.local_path END, "
            "status=excluded.status, note=excluded.note, updated_at=excluded.updated_at",
            (site_key, menu_no, bno, att.filename, att.url, att.ext, size, sha, local_path,
             status, note, now()),
        )
        self.conn.commit()

    def attachment_status(self, url: str) -> str | None:
        cur = self.conn.execute("SELECT status FROM attachments WHERE url=? LIMIT 1", (url,))
        row = cur.fetchone()
        return row["status"] if row else None

    # ---- 실행 이력 --------------------------------------------------------
    def start_run(self, site_key: str, mode: str, boards: list[int]) -> int:
        cur = self.conn.execute(
            "INSERT INTO runs(site_key,mode,started_at,boards) VALUES(?,?,?,?)",
            (site_key, mode, now(), ",".join(map(str, boards))))
        self.conn.commit()
        return int(cur.lastrowid)

    def finish_run(self, run_id: int, **kw) -> None:
        fields = ["finished_at", "pages", "posts_new", "posts_updated", "attachments_new",
                  "errors", "stats_json", "notes"]
        vals = {"finished_at": now()}
        vals.update({k: v for k, v in kw.items() if k in fields})
        cols = ", ".join(f"{k}=?" for k in vals)
        self.conn.execute(f"UPDATE runs SET {cols} WHERE id=?", (*vals.values(), run_id))
        self.conn.commit()

    def log_error(self, run_id: int, site_key: str, menu_no: int | None, bno: int | None,
                  url: str, message: str) -> None:
        self.conn.execute(
            "INSERT INTO errors(run_id,site_key,menu_no,bno,url,message) VALUES(?,?,?,?,?,?)",
            (run_id, site_key, menu_no, bno, url, message[:500]))
        self.conn.commit()

    # ---- 조회 -------------------------------------------------------------
    def stats(self, site_key: str | None = None) -> dict:
        where, args = ("WHERE site_key=?", (site_key,)) if site_key else ("", ())
        out: dict = {}
        out["posts"] = self.conn.execute(f"SELECT COUNT(*) c FROM posts {where}", args).fetchone()["c"]
        out["attachments"] = self.conn.execute(
            f"SELECT COUNT(*) c FROM attachments {where}", args).fetchone()["c"]
        out["attachments_downloaded"] = self.conn.execute(
            f"SELECT COUNT(*) c FROM attachments {where + (' AND' if where else 'WHERE')} status='downloaded'",
            args).fetchone()["c"]
        out["boards"] = [dict(r) for r in self.conn.execute(
            "SELECT menu_no,name,kind,last_crawled,posts_seen FROM boards "
            + ("WHERE site_key=? " if site_key else "") + "ORDER BY menu_no",
            args if site_key else ()).fetchall()]
        out["per_board"] = [dict(r) for r in self.conn.execute(
            "SELECT menu_no, COUNT(*) c, MAX(posted_at) latest FROM posts "
            + ("WHERE site_key=? " if site_key else "") + "GROUP BY menu_no ORDER BY c DESC",
            args if site_key else ()).fetchall()]
        out["by_attachment_ext"] = [dict(r) for r in self.conn.execute(
            "SELECT ext, COUNT(*) c FROM attachments "
            + ("WHERE site_key=? " if site_key else "") + "GROUP BY ext ORDER BY c DESC LIMIT 15",
            args if site_key else ()).fetchall()]
        out["runs"] = [dict(r) for r in self.conn.execute(
            "SELECT * FROM runs " + ("WHERE site_key=? " if site_key else "")
            + "ORDER BY id DESC LIMIT 8", args if site_key else ()).fetchall()]
        return out

    def iter_posts(self, site_key: str, menu_no: int | None = None):
        sql = "SELECT * FROM posts WHERE site_key=?"
        args: list = [site_key]
        if menu_no:
            sql += " AND menu_no=?"
            args.append(menu_no)
        sql += " ORDER BY menu_no, bno DESC"
        return self.conn.execute(sql, args)
