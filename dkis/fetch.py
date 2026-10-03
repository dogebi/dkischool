"""HTTP 계층: 레이트리밋 · 재시도/백오프 · robots · EUC-KR 디코딩 · 통계.

프록시(xray)를 우회한다 — 이 사이트는 직결로 접속되고, 프록시를 태우면 로컬/중계
경로가 끼어 실패율이 올라간다.
"""
from __future__ import annotations

import random
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field


class FetchError(RuntimeError):
    pass


class RobotsDisallowed(FetchError):
    pass


@dataclass
class Stats:
    requests: int = 0
    bytes_in: int = 0
    retries: int = 0
    errors: int = 0
    by_status: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {
            "requests": self.requests,
            "bytes_in": self.bytes_in,
            "retries": self.retries,
            "errors": self.errors,
            "by_status": dict(sorted(self.by_status.items())),
        }


class RobotsCache:
    """robots.txt 의 Disallow 규칙만 구현 (이 사이트는 User-agent: * / Disallow: /upload/ 한 줄)."""

    def __init__(self, fetcher: "Fetcher", url: str, respect: bool = True):
        self.respect = respect
        self.url = url
        self.rules: list[str] = []
        self.fetched_at: float | None = None
        self._fetcher = fetcher

    def load(self) -> None:
        if not self.respect or not self.url:
            return
        try:
            _, body = self._fetcher.get_bytes(self.url, _skip_robots=True)
            text = body.decode("utf-8", "replace")
            for line in text.splitlines():
                line = line.strip()
                if line.lower().startswith("disallow:"):
                    path = line.split(":", 1)[1].strip()
                    if path:
                        self.rules.append(path)
        except Exception:
            self.rules = []
        self.fetched_at = time.time()

    def allowed(self, path: str) -> bool:
        if not self.respect or self.fetched_at is None:
            return True
        for rule in self.rules:
            if path.startswith(rule):
                return False
        return True

    def as_dict(self) -> dict:
        return {"respect": self.respect, "disallow": list(self.rules)}


class Fetcher:
    def __init__(self, base_url: str, *, encoding: str = "euc-kr", ua: str = "",
                 rate_limit_s: float = 0.5, timeout_s: int = 30, retries: int = 3,
                 robots_url: str = "", respect_robots: bool = True,
                 allow_upload: bool = True, verbose: bool = False):
        self.base_url = base_url.rstrip("/")
        self.encoding = encoding
        self.rate_limit_s = max(0.0, rate_limit_s)
        self.timeout_s = timeout_s
        self.retries = max(1, retries)
        self.verbose = verbose
        self.stats = Stats()
        self._last_request = 0.0
        self._lock = threading.Lock()      # 레이트리밋/통계는 병렬 수집에서도 직렬화
        self._opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        self.ua = ua or "dkis-archive/0.1"
        self.robots = RobotsCache(self, robots_url, respect=respect_robots)
        # /upload/ 다운로드를 robots 금지와 별개로 허용할지 (운영자 명시 동의)
        self.allow_upload = allow_upload
        self._robots_loaded = False

    # ---- 내부 -------------------------------------------------------------
    def _throttle(self) -> None:
        with self._lock:
            delta = time.monotonic() - self._last_request
            if delta < self.rate_limit_s:
                time.sleep(self.rate_limit_s - delta)
            self._last_request = time.monotonic()

    def _bump(self, status: int, nbytes: int = 0) -> None:
        with self._lock:
            self.stats.requests += 1
            self.stats.bytes_in += nbytes
            self.stats.by_status[status] = self.stats.by_status.get(status, 0) + 1

    def _prepare_path(self, path_or_url: str) -> tuple[str, str]:
        """(full_url, path) 반환. 한글 파일명 등은 퍼센트 인코딩."""
        raw = path_or_url
        if raw.startswith("http://") or raw.startswith("https://"):
            full = raw
            path = urllib.parse.urlsplit(raw).path or "/"
        else:
            if not raw.startswith("/"):
                raw = "/" + raw
            full = self.base_url + urllib.parse.quote(raw, safe="/?&=%:.,+~()[]'")
            path = urllib.parse.urlsplit(raw).path
        return full, path

    # ---- 공개 API ---------------------------------------------------------
    def get_bytes(self, path_or_url: str, *, _skip_robots: bool = False) -> tuple[int, bytes]:
        full, path = self._prepare_path(path_or_url)
        if not _skip_robots:
            if not self._robots_loaded:
                self.robots.load()
                self._robots_loaded = True
            if not self.robots.allowed(path):
                # /upload/ 는 robots Disallow 지점 — 운영자가 명시 허용한 경우만 통과
                if path.startswith("/upload/") and self.allow_upload:
                    pass
                else:
                    raise RobotsDisallowed(f"robots.txt Disallow: {path}")

        last_err: Exception | None = None
        for attempt in range(1, self.retries + 1):
            self._throttle()
            req = urllib.request.Request(full, headers={
                "User-Agent": self.ua,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8",
                "Connection": "close",
            })
            try:
                with self._opener.open(req, timeout=self.timeout_s) as resp:
                    body = resp.read()
                    self._bump(resp.status, len(body))
                    return resp.status, body
            except urllib.error.HTTPError as e:
                self._bump(e.code)
                if e.code in (404, 403, 410):        # 재시도 무의미
                    body = e.read()
                    return e.code, body
                last_err = e
            except Exception as e:                    # noqa: BLE001 (네트워크 계열 전부)
                last_err = e
            if attempt < self.retries:
                with self._lock:
                    self.stats.retries += 1
                sleep = (0.8 * (2 ** (attempt - 1))) + random.uniform(0, 0.4)
                if self.verbose:
                    print(f"    [retry {attempt}/{self.retries}] {full} — {last_err} ({sleep:.1f}s)")
                time.sleep(sleep)
        with self._lock:
            self.stats.errors += 1
        raise FetchError(f"{full} — {self.retries}회 실패: {last_err}")

    def get_text(self, path_or_url: str) -> str:
        _, body = self.get_bytes(path_or_url)
        return body.decode(self.encoding, "replace")

    # ---- URL 빌더 ---------------------------------------------------------
    def list_url(self, menu_no: int, page: int = 1) -> str:
        return f"/?menu_no={menu_no}&board_mode=list&page={page}"

    def view_url(self, menu_no: int, bno: int, page: int = 1) -> str:
        return f"/?menu_no={menu_no}&board_mode=view&bno={bno}&page={page}"

    def search_url(self, menu_no: int, keyword: str, page: int = 1) -> str:
        q = urllib.parse.quote(keyword.encode(self.encoding))
        return f"/?menu_no={menu_no}&board_mode=list&issearch=Y&keyword={q}&page={page}"
