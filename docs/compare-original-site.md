# 원본 학교 사이트 vs 아카이브 뷰어 — 차이점 정리

> 작성: 2026-10-04 · 비교 대상: `http://dkischool.org/?menu_no=47&board_mode=list`(공지사항)
> 및 `...&board_mode=view&bno=729`(상세) ↔ 이 저장소가 생성하는 `web/index.html`

## 한 줄 요약

원본은 **학교 홈페이지 안의 게시판 한 칸**(최신 12건씩 페이지 이동)이고,
아카이브는 **13개 게시판 2,479건을 한 파일에 담은 검색·정렬 가능한 색인**이다.
정보 구조가 "메뉴 탐색"에서 "검색/정렬/필터 조회"로 바뀐 것이 가장 큰 차이다.

## 항목별 비교 (원본 실측 기준)

| 항목 | 원본 사이트 | 아카이브 뷰어 |
|---|---|---|
| 성격 | 학교 홈페이지 + 게시판(메뉴별 별도 페이지) | 게시판 전문 색인(단일 HTML 1개) |
| 화면 구성 | 로고·대메뉴 6개·좌측 서브메뉴·배너 슬라이더·breadcrumb | 교명 띠(고정) + 소장 정보 + 게시판 색인 + 목록 |
| 브랜드 표기 | 로고 이미지 + 한글 교명 | 교명 띠에 한글+영문 교명, 라벨 한글·영문 병기 |
| 한 화면 글 수 | 12건/페이지 (페이징: 처음·이전·1~11·다음·마지막) | 150건 배치 렌더 + "더 보기" |
| 검색 | 게시판 **내** 검색(제목 등 keyfield + keyword) | **13개 게시판 통합** 검색 — 제목·본문·작성자·첨부 파일명, 일치 구간 하이라이트 |
| 정렬 | 최신순 고정 | 최신 / 오래된 / 조회 / 게시판 (+표 머리글 클릭 정렬) |
| 필터 | 없음 | 첨부만 보기, 게시판 색인 클릭 |
| 본문 열람 | 상세 페이지로 이동 | 행 클릭 시 즉시 펼침(본문 + 이미지 썸네일 + 첨부 목록) |
| 다크 모드·밀도 | 없음 | 테마 토글(라이트/다크), 행 밀도 토글(보통/조밀) — localStorage 유지 |
| 모바일 | `<meta viewport>` 없음, `#wrap min-width:1000px`·`#header min-width:1120px` 고정폭 → 가로 스크롤/축소 | 880px 이하 2단 행, 600px 이하 툴바·이미지 재배치 |
| 외부 의존 | withschool.co.kr 스킨 CSS + upload70.withschool.co.kr 이미지 + Google Fonts(나눔고딕) `@import` + jQuery 1.8.3·design.js·bn.js·sliderkit | **외부 요청 0** (CSS·JS·데이터 내장, 이미지·첨부만 원 사이트 URL) |
| 인코딩 | EUC-KR | UTF-8 단일 파일 |
| 무게 | 목록 HTML 27KB + CSS 4종 약 33KB + 이미지 26개(배너 PNG 1장 482KB) + 스크립트 다수 | index.html 1.54MB(데이터 포함), 추가 요청 없음 |
| 오프라인/사내망 | 불가(서버 필요) | 가능(파일 하나로 열림) |
| 키보드 접근성 | 표 레이아웃·포커스 링 없음 | `/` 검색 포커스, `Esc` 초기화, `aria-*`·포커스 링 |
| 첨부 | 파일명 클릭 시 `/upload/...` 다운로드 | 메타(파일명·확장자·용량)만 보관, 링크는 원 사이트 파일을 직접 연다 (robots `/upload/` Disallow 동일 적용) |
| 글쓰기·로그인·댓글 | 있음(홈페이지 기능) | 없음(읽기 전용 색인) |
| 과거 글 접근 | 게시판별 페이지 이동(공지 66페이지, 가정통신문 85페이지) | 검색·정렬로 즉시 도달 |
| 수명 | 홈페이지 개편·서버 이전 시 소실 위험 | SQLite + JSON/CSV 내보내기로 보존 |

## 아키텍처 비교 — 백엔드 / 프런트엔드

**원본(dkischool.org)은 백엔드가 있는 동적 CMS다. 아카이브 뷰어는 런타임 백엔드가 없다(정적 파일).**

### 원본 — 클래식 ASP + CMS 임대형

| 계층 | 실측 근거 |
|---|---|
| 백엔드 | `default.asp?menu_no=47&board_mode=list\|view\|write` — 모든 게시판이 `.asp` 하나로 라우팅(HTML 내 `.asp` 참조 28곳), 검색 폼 `action="default.asp" method="get"` |
| 세션 | 응답 헤더 `Set-Cookie: ASPSESSIONIDQQRSDTAB=…; path=/` → 서버 세션 기반(클래식 ASP) |
| 동적 생성 | `Cache-Control: no-cache,…,private`, `Pragma: no-cache`, `Expires: 0`, `P3P: CP=…` → 파일이 아니라 요청마다 조립되는 페이지 |
| 데이터 | 게시판 DB(서버 측) + 첨부 파일 서버 `upload70.withschool.co.kr`, 본문 이미지 `dkis.withschool.co.kr/upload/editor/…` |
| 스킨 | `http://www.withschool.co.kr/css/board_design/blue.css` → withschool(w.cms) 임대 스킨 |
| 인증 | `board_mode=write` 200 응답에 "회원·글쓰기" 안내, HOME/LOGIN/SITEMAP → 회원 로그인·글쓰기 백엔드 |
| 프런트 | 서버 렌더 HTML + CSS 4종(style·common·contents·board blue) + jQuery 1.8.3, design.js, bn.js, sliderkit — SPA 아님 |
| 인코딩 | EUC-KR |

### 아카이브 뷰어 — 런타임 백엔드 없음, 빌드 시점 파이프라인만

| 계층 | 실측 |
|---|---|
| 런타임 | 정적 파일만(GitHub Pages). 서버 프로세스·DB 서버·API 엔드포인트 없음 |
| 프런트 | 단일 HTML + 인라인 CSS(283줄) + 바닐라 JS(352줄) + 데이터 인라인(POSTS 993KB·ATTS 519KB). jQuery·React·Vue·Bootstrap·Tailwind 0, 외부 CSS 0 |
| 런타임 호출 | `fetch(`·`XMLHttpRequest`·`$.ajax`·WebSocket **0건** — 페이지는 서버 호출 없이 동작. 글을 펼칠 때만 원 사이트 이미지(`dkis.withschool.co.kr/upload/…`)와 첨부·원문 링크를 부른다 |
| 백엔드 역할(빌드 시점) | 파이썬 표준 라이브러리 크롤러(robots 준수·레이트리밋·EUC-KR 디코딩) → SQLite(`data/dkis.sqlite3`) → `dkis export` → 단일 index.html. 크론(`scripts/crawl-incremental.sh`)이 증분 갱신 |
| 데이터 배포본 | `posts.json`(1.8MB)·`attachments.csv`·`summary.json` 정적 다운로드. SQLite 원본은 저장소에 넣지 않는다 |

즉 "단순 HTML/CSS인가"라는 질문에는: **원본은 ASP 백엔드 + DB + 세션을 가진 3계층 사이트**,
**아카이브는 백엔드 없는 정적 단일 파일(HTML+CSS+바닐라 JS+데이터 내장)** 이며, 크롤러·SQLite·크론이
"서버 대신 빌드 시점에" 데이터를 공급한다.

## 색·시각 언어

- 원본: 네이비 블루 계열(표 헤더 `#2f82b4`, 상단 메뉴 바 파랑), 학교 로고, 배너 슬라이더 중심
- 아카이브(현재): 학교 **교표에서 따온 기관 팔레트** — 남색(교명) `#1e2c56` · 녹색 `#2c7a3f` · 금색 괘선 `#e0b23c`.
  상단에 원본과 같은 성격의 **교명 띠**(한글 교명 + 영문, 금색 하단 괘선)를 두고, 좌측 "소장 자료" 칩·
  표 머리글·버튼 라벨은 한글 + 영문 소자를 병기한다. 원본의 로고·배너 이미지를 쓰는 대신
  서체 위계와 헤어라인으로 같은 "기관 문서" 인상을 낸다.

## 아카이브가 원본보다 약한 지점 (의도된 범위)

1. 학교 홈페이지 프레임(로고·메뉴·배너)은 없다 — 게시판 색인에 집중.
2. 실시간이 아니다 — 크론(증분 수집) 주기만큼 지연된다.
3. 첨부 실물은 로컬 보관하지 않는다(robots 정책) — 메타데이터만.
4. 크롤 시점의 본문 텍스트는 4,000자까지 보관한다(그 이상은 원문 확인).

## 참고 스크린샷

`data/_compare/` — `original_list.png`, `original_view.png`, `archive_list.png`, `archive_dark.png`
