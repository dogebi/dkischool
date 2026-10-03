"""사이트 레지스트리.

이 크롤러는 특정 사이트 하나가 아니라 **withschool(w.cms) 기반 학교 사이트** 일반을
대상으로 한다. 사이트를 추가하려면 SITES 에 항목 하나만 넣으면 된다
(base_url + euc-kr + `?menu_no=NN&board_mode=list|view&bno=NNN` 규약).

robots 정책은 사이트별로 명시한다 — robots.txt 가 /upload/ 를 금지하는 사이트에서는
첨부 **파일 다운로드**는 기본 비활성(메타데이터만 기록)이고, 운영자가
`--attachments` 로 명시적으로 켜야 한다.
"""

DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36 dkis-archive/0.1"
)

SITES = {
    "dkischool": {
        "name": "대련한국국제학교",
        "name_en": "Dalian Korea International School",
        "base_url": "http://dkischool.org",
        "school_code": "10177",
        "encoding": "euc-kr",
        "vendor": "withschool (w.cms)",
        "rate_limit_s": 0.5,      # 요청 간 최소 간격
        "timeout_s": 30,
        "retries": 3,
        "boards": {
            47:  {"name": "공지사항",         "kind": "board"},
            41:  {"name": "가정통신문",       "kind": "board"},
            40:  {"name": "학교앨범",         "kind": "gallery"},
            42:  {"name": "보건실",           "kind": "board"},
            43:  {"name": "급식실",           "kind": "board"},
            44:  {"name": "게시판",           "kind": "board"},
            45:  {"name": "학생회",           "kind": "board"},
            46:  {"name": "컵스카우트",       "kind": "board"},
            74:  {"name": "한글학교 소식",     "kind": "board"},
            79:  {"name": "도서실 공지사항",   "kind": "board"},
            81:  {"name": "도서신청 및 기타",  "kind": "board"},
            86:  {"name": "행사일정",         "kind": "event"},
            94:  {"name": "교육계획서",       "kind": "file"},
            96:  {"name": "학교규정집",       "kind": "file"},
            49:  {"name": "졸업생 대학진학 현황", "kind": "board"},
            132: {"name": "학부모회 게시판",   "kind": "board"},
        },
        # robots.txt: "User-agent: * / Disallow: /upload/"
        "robots": {
            "url": "http://dkischool.org/robots.txt",
            "respect": True,
            "attachment_download_allowed": False,   # /upload/ 금지 → 기본 OFF
        },
    },
}


def get_site(key: str) -> dict:
    if key not in SITES:
        raise KeyError(f"알 수 없는 사이트: {key} (등록: {', '.join(SITES)})")
    site = dict(SITES[key])
    site["key"] = key
    return site


def list_sites() -> list[dict]:
    return [get_site(k) for k in SITES]
