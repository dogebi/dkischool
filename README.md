# dkis-archive — withschool 기반 학교 게시판 아카이버

`dkischool.org`(대련한국국제학교 / Dalian Korea International School) 게시판을 수집·보관하는
독립 실행형 크롤러 겸 아카이브 툴킷입니다. 사이트 하나에 하드코딩된 스크립트가 아니라
**withschool(w.cms) 계열 학교 사이트를 사이트 추가만으로 대상에 넣는 구조**입니다.

- 의존성 **없음** — 파이썬 표준 라이브러리만 사용(3.10+). `pip install` 불필요.
- **증분 수집** — 2회차부터는 새 글만 가져옵니다(목록이 그대로면 상세 페이지 재요청 생략).
- **robots.txt 준수** — `/upload/` Disallow 를 인식하며, 첨부 파일 다운로드는 기본 비활성입니다.
- **SQLite 아카이브 + 단일 HTML 뷰어** — 검색·게시판 필터·첨부 목록 포함, 외부 리소스 없음.

---

## 1. 빠른 시작

```bash
cd /mnt/d/dev/dkischool-crawler

python3 -m dkis sites                     # 등록된 사이트/게시판 보기
python3 -m dkis selftest                  # 파서·저장·증분·내보내기 자체 검증(네트워크 소량 사용)

python3 -m dkis crawl --site dkischool --boards 47 --max-pages 1   # 맛보기
bash scripts/crawl-full.sh                # 최초 전체 수집(백필)
python3 -m dkis stats  --site dkischool   # 수집 현황
python3 -m dkis export --site dkischool   # JSON/CSV + web/index.html 뷰어 생성
python3 -m dkis view   --site dkischool --serve 8388   # 뷰어 생성 후 로컬 서빙
```

뷰어는 `web/index.html` 단일 파일입니다 — CSS·JS·데이터가 모두 파일 안에 들어가고
외부 CDN이나 웹폰트를 쓰지 않습니다(본문 이미지와 첨부 링크는 원 사이트 URL을 가리킵니다).
2,500건 규모를 150건씩 나눠 그리므로 첫 화면이 즉시 뜹니다.

화면은 학교 교표에서 따온 기관 팔레트(남색 교명 띠 + 금색 괘선, 녹색 포인트)로 맞췄고,
표 머리글·정렬·소장 정보 라벨은 한글 + 영문 소자를 병기합니다 — 국제학교 문서의 인상을
로고 이미지 대신 서체 위계와 헤어라인으로 냅니다.

- 좌측: 소장 정보(게시글·첨부·게시판·기간) + 게시판 색인(건수, 최신 수집일은 툴팁)
- 검색: 제목·본문·작성자·첨부 파일명, 일치 구간 하이라이트, `×` 버튼·`Esc` 초기화,
  `/` 키로 검색창 포커스
- 정렬: 최신 / 오래된 / 조회 / 게시판 세그먼트, 표 머리글(게시판·작성일·조회) 클릭 정렬
- 첨부만 보기 토글, 행 밀도 토글(보통/조밀), 테마 토글(라이트 기본/다크) — 밀도·테마는
  localStorage에 기억됩니다
- 행 클릭 시 본문·이미지·첨부 목록 펼치기(이미지는 썸네일 그리드)
- 결과가 없으면 전체 게시글로 돌아가는 버튼을 함께 보여 줍니다
- 880px 이하에서는 행이 2단(제목 + 게시판·날짜·조회 메타 줄)으로 접힙니다

## 2. CLI

| 명령 | 설명 |
|---|---|
| `sites` | 등록 사이트와 게시판 목록 |
| `crawl --site S [--boards 47,41] [--mode incremental\|full] [--max-pages N] [--limit-posts N] [--workers 1~5] [--attachments] [--json]` | 수집 |
| `stats --site S [--json]` | 게시판별 건수·최신일·최근 실행 이력 |
| `export --site S [--out DIR]` | posts.json / posts.csv / attachments.csv / attachments.json / summary.json + 뷰어 |
| `view --site S [--serve PORT]` | 뷰어 재생성(옵션: 로컬 서빙) |
| `selftest [--site S]` | robots·목록파싱·상세파싱·저장·증분·내보내기 검증 |

`--db` 는 전역 옵션이라 하위 명령 앞에 옵니다: `python3 -m dkis --db data/other.sqlite3 crawl ...`

기본 수집 순서는 게시판 종류별 우선순위(공지/문서 → 행사 → 사진앨범)입니다.
`--boards` 로 명시하면 그 순서를 그대로 따릅니다.

## 3. 디렉터리

```
dkis/
  config.py   사이트 레지스트리(사이트 추가 지점)
  fetch.py    HTTP: 레이트리밋(전역)·재시도/백오프·robots·EUC-KR 디코딩·통계
  parse.py    목록/상세 파서(마크업 골격은 파일 상단 주석 참조)
  store.py    SQLite 스키마 + upsert
  crawl.py    오케스트레이션(증분/전체, 소수 병렬 상세수집, 첨부)
  export.py   JSON/CSV + 단일 HTML 뷰어 생성
  __main__.py CLI
scripts/
  crawl-full.sh         최초 백필(flock 중복방지)
  crawl-incremental.sh  크론용 증분 수집 + 내보내기 + 뷰어 갱신
  latency_probe.py      대상 사이트 응답지연 실측
data/
  dkis.sqlite3          본 DB (WAL)
  files/                첨부 저장소(다운로드 활성 시)
  export/               posts.json 등 산출물
logs/, web/             실행 로그, 생성된 뷰어
```

## 4. 데이터 모델(SQLite)

- `sites`, `boards` — 사이트/게시판 메타, 마지막 수집 시각·페이지
- `posts` — `(site_key, menu_no, bno)` PK. 제목/작성자/작성일/조회수/본문(HTML+텍스트)/이미지/`content_hash`
- `attachments` — 파일명·URL·확장자·크기·sha256·로컬경로·`status`
  (`listed` = 메타만, `downloaded`, `skipped_robots`, `error`)
- `runs`, `errors` — 실행 이력과 실패 목록(게시판·bno·URL·메시지)

`content_hash` 로 본문 변경(수정된 공지 등)을 감지해 `updated` 로 집계합니다.

## 5. 크론

```bash
bash scripts/crawl-incremental.sh          # 증분 수집 → export → 뷰어 갱신(로그: logs/crawl-incremental.log)
```
Hermes 크론 등록 예(6시간마다):
```
no_agent 스크립트: /mnt/d/dev/dkischool-crawler/scripts/crawl-incremental.sh
```
`flock` 으로 중복 실행을 막으므로 수집이 길어져도 안전합니다.

## 6. 사이트 추가

`dkis/config.py` 의 `SITES` 에 항목을 추가합니다.

```python
"other-school": {
    "name": "○○학교", "base_url": "http://example.org", "school_code": "10000",
    "encoding": "euc-kr", "rate_limit_s": 1.0, "timeout_s": 30, "retries": 3,
    "boards": {47: {"name": "공지사항", "kind": "board"}},
    "robots": {"url": "http://example.org/robots.txt", "respect": True,
               "attachment_download_allowed": False},
}
```
파서는 withschool 마크업(`?menu_no=…&board_mode=list|view&bno=…`, `table.h_board`,
`icon_HWP.gif` 첨부 아이콘)을 기준으로 하므로 같은 CMS면 그대로 동작합니다.

## 7. 수집 예절 / 주의

- 기본 레이트리밋은 **요청 간 0.5초**(전역)이며 `--workers` 로 상세 페이지만 소수 병렬(최대 5)합니다.
- `robots.txt` 가 `/upload/` 를 Disallow 로 선언하고 있습니다. 첨부 **파일 다운로드**는
  `--attachments`(또는 `ATT=1 bash scripts/crawl-full.sh`)로만 켜지며, 실행 시 경고를 출력합니다.
  첨부 **메타데이터**(파일명·URL·확장자)는 다운로드 없이도 항상 기록됩니다.
- 수집 데이터의 권리는 원 사이트(학교)에 있습니다. 외부 배포 전 이용 조건을 확인하십시오.

## 8. 공개 (GitHub Pages)

```bash
bash scripts/publish-pages.sh        # 뷰어를 저장소 루트 index.html 로 복사 + 내보내기 파일 동봉
git add index.html posts.json attachments.csv summary.json robots.txt .nojekyll && \
  git commit -m "publish: 뷰어 공개 사본 갱신" && git push origin main
```

- 사이트: `https://dogebi.github.io/dkischool/` — Pages 소스는 `main` 브랜치 루트(`/`)입니다.
- 루트 `index.html` 은 **생성물**입니다. 손으로 고치면 다음 `publish-pages.sh` 실행에서 덮이므로
  화면 수정은 항상 `dkis/export.py` 의 `VIEWER_TEMPLATE` 에서 합니다.
- `robots.txt`(`Disallow: /`) 와 `index.html` 의 `<meta name="robots" content="noindex, nofollow">` 로
  검색엔진 수집을 막아 둡니다. 노출이 필요하면 이 두 곳을 지웁니다.
- 첨부 파일 실물은 저장소에 넣지 않습니다(robots `/upload/` 정책) — 뷰어의 첨부 링크는 원 사이트 파일을 엽니다.

