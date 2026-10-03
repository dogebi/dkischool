"""파서: withschool(w.cms) 게시판의 목록/상세 마크업을 구조화한다.

마크업 골격(실측):

목록  <tr><td> 719 </td>
        <td class="h_left"><a href="default.asp?board_mode=view&menu_no=47&bno=729&...">제목</a></td>
        <td>작성자</td><td>2026-10-02</td><td>58</td>
        <td><img src='.../icon_HWP.gif' alt='첨부'></td></tr>
      · 공지 고정글은 첫 칸이 숫자 대신 "공지"
      · 첨부 아이콘: icon_HWP.gif / icon_xls.gif / icon_pdf.gif / icon_no.gif(첨부없음)

상세  <table class="h_board">
        <caption> 게시판 {제목}</caption>
        <tr><th colspan="2">{제목}</th></tr>
        <tr><th class="h_view_name">작 성 자</th><td class="h_view_title">김정경</td></tr>
        <tr><th ...>등록일</th><td>2026-10-02 오전 11:41:00 (HIT : 57)</td></tr>
        <tr><th ...>첨부파일</th><td><!-- 첨부파일정보 --><a href='javascript:location.href="/upload/board/....hwp"'>파일명</a><!--// 첨부파일정보 --></td></tr>
        <tr><td class="h_content"><div id="bbs_view_contents">본문</div></td></tr>
"""
from __future__ import annotations

import html as htmllib
import re
from dataclasses import dataclass, field, asdict

TAG_RE = re.compile(r"<[^>]+>")
SCRIPT_RE = re.compile(r"<(script|style)\b.*?</\1>", re.S | re.I)
WS_RE = re.compile(r"[ \t\r\f\v]+")
NL_RE = re.compile(r"\n{3,}")

ATT_ICON_RE = re.compile(r"icon_([A-Za-z0-9]+)\.gif", re.I)
VIEW_LINK_RE = re.compile(r"board_mode=view&(?:amp;)?menu_no=(\d+)&(?:amp;)?bno=(\d+)", re.I)


def clean_text(fragment: str) -> str:
    """태그 제거 + 엔티티 복원 + 공백 정리."""
    s = SCRIPT_RE.sub(" ", fragment)
    s = TAG_RE.sub(" ", s)
    s = htmllib.unescape(s)
    s = s.replace("\xa0", " ")
    s = WS_RE.sub(" ", s)
    s = NL_RE.sub("\n\n", s)
    return s.strip()


def first_int(text: str) -> int | None:
    m = re.search(r"\d[\d,]*", text or "")
    return int(m.group(0).replace(",", "")) if m else None


@dataclass
class ListRow:
    bno: int
    title: str
    author: str = ""
    posted_date: str = ""
    views: int | None = None
    is_notice: bool = False
    attach_ext: str = ""
    has_attachment: bool = False


@dataclass
class Attachment:
    filename: str
    url: str
    ext: str = ""

    def __post_init__(self) -> None:
        if not self.ext:
            m = re.search(r"\.([A-Za-z0-9]{1,8})$", self.filename)
            self.ext = m.group(1).lower() if m else ""


@dataclass
class Post:
    menu_no: int
    bno: int
    title: str
    author: str = ""
    posted_at: str = ""
    views: int | None = None
    content_html: str = ""
    content_text: str = ""
    attachments: list[Attachment] = field(default_factory=list)
    board_title: str = ""
    images: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        d = asdict(self)
        return d


# --------------------------------------------------------------------------- 목록
def parse_list(html: str) -> list[ListRow]:
    rows: list[ListRow] = []
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.S | re.I):
        m = VIEW_LINK_RE.search(tr)
        if not m:
            continue
        bno = int(m.group(2))
        cells = [clean_text(c) for c in re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S | re.I)]
        if not cells:
            continue
        first = cells[0] if cells else ""
        is_notice = not first.replace(",", "").isdigit()
        # 제목 칸 = 두 번째 td (없으면 전체 텍스트)
        title_cell = cells[1] if len(cells) > 1 else clean_text(tr)
        title = re.sub(r"\s+", " ", title_cell).strip()
        author = cells[2] if len(cells) > 2 else ""
        date = cells[3] if len(cells) > 3 else ""
        views = first_int(cells[4]) if len(cells) > 4 else None
        last = cells[-1] if cells else ""
        icon = ATT_ICON_RE.search(tr)
        ext = icon.group(1).lower() if icon else ""
        has_att = bool(icon) and ext != "no"
        if not has_att:
            # 일부 목록은 아이콘 대신 파일명을 노출
            has_att = bool(re.search(r"/upload/", tr, re.I))
        rows.append(ListRow(bno=bno, title=title, author=author, posted_date=date,
                            views=views, is_notice=is_notice,
                            attach_ext=ext if has_att else "", has_attachment=has_att))
    # bno 중복 제거(같은 글이 제목/아이콘 양쪽에 링크되는 경우)
    seen, out = set(), []
    for r in rows:
        if r.bno in seen:
            continue
        seen.add(r.bno)
        out.append(r)
    return out


def parse_pages(html: str, menu_no: int) -> tuple[list[int], int | None]:
    """페이징 영역에서 (페이지 번호 목록, 마지막 페이지 번호) 반환.

    실제 마크업:
      <div class="h_paging">
        [처음]&nbsp;<a href='default.asp?board_mode=list&issearch=&keyfield=&keyword=&menu_no=47&page=1' ...>◁ 이전</a>
        ... <a href='...&page=66' title='마지막페이지로 이동'>[마지막]</a>
      </div>
    menu_no 가 href 뒤쪽에 오므로 menu_no 로 앵커링하면 매칭에 실패한다 — 페이징 div 안의
    page= 숫자를 그대로 모으고, [마지막] 링크에서 총 페이지 수를 읽는다.
    """
    m = re.search(r'<div class="h_paging">(.*?)</div>', html, re.S | re.I)
    seg = m.group(1) if m else ""
    if not seg:
        return [], 1                      # 페이징 영역 없음 = 단일 페이지
    nums = sorted({int(n) for n in re.findall(r"page=(\d+)", seg)})
    last = None
    m2 = re.search(r"page=(\d+)[^>]*>\s*\[마지막\]", seg)
    if not m2:
        m2 = re.search(r"\[마지막\][^>]*page=(\d+)", seg)
    if m2:
        last = int(m2.group(1))
    if last is None and nums:
        last = max(nums)
    return nums, last


# --------------------------------------------------------------------------- 상세
def parse_view(html: str, menu_no: int, bno: int) -> Post:
    board_title = ""
    m = re.search(r'<div class="con_title">.*?<h2[^>]*>(.*?)</h2>', html, re.S | re.I)
    if m:
        board_title = clean_text(m.group(1))

    title = ""
    m = re.search(r'<table[^>]+class="h_board".*?</table>', html, re.S | re.I)
    table = m.group(0) if m else html
    m = re.search(r"<caption>(.*?)</caption>", table, re.S | re.I)
    if m:
        title = re.sub(r"^\s*게시판\s*", "", clean_text(m.group(1)))
    if not title:
        m = re.search(r'<tr>\s*<th[^>]*colspan="?2"?[^>]*>(.*?)</th>', table, re.S | re.I)
        if m:
            title = clean_text(m.group(1))

    def labelled(label: str) -> str:
        m = re.search(rf'<th[^>]*>\s*{label}\s*</th>\s*<td[^>]*>(.*?)</td>', table, re.S | re.I)
        return clean_text(m.group(1)) if m else ""

    author = labelled("작\\s*성\\s*자")
    date_cell = labelled("등록일")
    posted_at = re.sub(r"\(HIT.*", "", date_cell).strip()
    views = None
    m = re.search(r"HIT\s*:\s*([\d,]+)", date_cell or html, re.I)
    if m:
        views = int(m.group(1).replace(",", ""))

    # 첨부: <!-- 첨부파일정보 --> 블록 안의 href (javascript:location.href="/upload/...")
    attachments: list[Attachment] = []
    block = ""
    m = re.search(r"<!--\s*첨부파일정보\s*-->(.*?)<!--//\s*첨부파일정보\s*-->", table, re.S | re.I)
    if m:
        block = m.group(1)
    for href, name in re.findall(r"""href=['"]([^'"]*?/upload/[^'"]+)['"][^>]*>(.*?)</a>""", block, re.S | re.I):
        url = re.sub(r'^javascript:location\.href=["\']?', "", href).strip()
        fn = clean_text(name) or url.rsplit("/", 1)[-1]
        attachments.append(Attachment(filename=fn, url=url))
    # 블록 파싱 실패 시 표 전체에서 /upload/ 링크 회수
    if not attachments:
        for href in re.findall(r"""href=['"]([^'"]*?/upload/[^'"]+)['"]""", table, re.I):
            url = re.sub(r'^javascript:location\.href=["\']?', "", href).strip()
            attachments.append(Attachment(filename=url.rsplit("/", 1)[-1], url=url))

    # 본문
    content_html = ""
    m = re.search(r'<div id="bbs_view_contents"[^>]*>(.*?)</div>\s*(?:</td>|</tr>)', html, re.S | re.I)
    if m:
        content_html = m.group(1)
    else:
        m = re.search(r'<td[^>]*class="h_content"[^>]*>(.*?)</td>', html, re.S | re.I)
        content_html = m.group(1) if m else ""
    content_html = re.sub(r"<!--.*?-->", " ", content_html, flags=re.S)
    content_text = clean_text(content_html)
    images = [u for u in re.findall(r"""<img[^>]+src=["']([^"']+)["']""", content_html, re.I)
              if "/upload/" in u.lower()]

    return Post(menu_no=menu_no, bno=bno, title=title.strip(), author=author,
                posted_at=posted_at, views=views, content_html=content_html.strip(),
                content_text=content_text, attachments=attachments,
                board_title=board_title, images=images)


def is_permission_denied(html: str) -> bool:
    """'접근권한이 없습니다' 알림 스텁(114바이트) 감지."""
    return "권한이 없습니다" in html and len(html) < 400


def is_invalid_path(html: str) -> bool:
    return "잘못된경로" in html and len(html) < 200
