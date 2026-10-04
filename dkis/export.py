"""산출물: JSON/CSV 내보내기 + 자체 포함 단일 HTML 뷰어 생성.

뷰어는 외부 리소스(CDN·웹폰트·이미지)를 일절 쓰지 않는 단일 파일이다.
템플릿은 `%%TOKEN%%` 치환 방식이라 CSS/JS 의 중괄호를 이스케이프할 필요가 없다.
"""
from __future__ import annotations

import csv
import html as htmllib
import json
import re
from pathlib import Path

from .store import Store

# ── 뷰어 템플릿 ────────────────────────────────────────────────────────────
# 치환 토큰: %%TITLE%% %%TITLE_EN%% %%BASE_URL%% %%GENERATED%% %%STATS%%
#           %%BOARDS%% %%POSTS%% %%ATTS%% %%EXPORT_LINKS%%
VIEWER_TEMPLATE = r"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="utf-8">
<title>%%TITLE%% 게시판 아카이브</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="light">
<meta name="generator" content="dkis-archive">
<style>
  :root{
    /* 교표에서 따온 기관 팔레트 — 남색(校名) · 녹색(테두리) · 금색 */
    --navy:#1e2c56; --navy-2:#2b3d6d; --navy-soft:#eef1f8;
    --paper:#f4f5f8; --panel:#fff; --panel-2:#eceef3; --hover:#f7f8fb; --sel:#eef1f8;
    --ink:#191b20; --ink-2:#4b5060; --ink-3:#818699;
    --rule:#d6dae3; --rule-soft:#e8eaf1;
    --accent:#2c7a3f; --accent-soft:#e9f1ea; --mark:#fdf0c0;
    --notice:#b5322a; --notice-soft:#fbeeec;
    --gold:#e0b23c;
    --band:#17233f;   /* 교명 띠 바탕 — 다크 모드에서도 짙은 남색 유지 */
    --mono:ui-monospace,"Cascadia Mono","Consolas","Liberation Mono",monospace;
    --sans:-apple-system,BlinkMacSystemFont,"Segoe UI","Malgun Gothic","Apple SD Gothic Neo","Noto Sans KR",sans-serif;
    --mh:56px; --barh:60px; --indent:180px;
  }
  *{box-sizing:border-box}
  html{-webkit-text-size-adjust:100%}
  body{margin:0;background:var(--panel);color:var(--ink);
       font:14px/1.62 var(--sans);-webkit-font-smoothing:antialiased}
  a{color:var(--accent);text-decoration:none;border-bottom:1px solid #c2d5cb}
  a:hover{border-bottom-color:var(--accent)}
  :focus-visible{outline:2px solid var(--accent);outline-offset:2px;border-radius:2px}
  button{font:inherit;color:inherit}
  /* 국제학교 표기 — 한글 라벨 옆에 붙는 영문 소자 */
  .en{font:9.5px/1.4 var(--mono);font-weight:400;letter-spacing:.08em;color:var(--ink-3)}

  /* ── 상단 교명 띠 (한국 학교 사이트식 고정 헤더) ───────── */
  .masthead{position:sticky;top:0;z-index:20;height:var(--mh);display:flex;
        align-items:center;gap:14px;padding:0 28px;background:var(--band);
        color:#fff;border-bottom:2px solid var(--gold)}
  .masthead .brand{display:flex;flex-direction:column;justify-content:center;min-width:0}
  .masthead .kr{font-size:15.5px;font-weight:700;line-height:1.25;white-space:nowrap}
  .masthead .en{font:9.5px/1.4 var(--mono);letter-spacing:.13em;text-transform:uppercase;
        color:#b9c3dc;white-space:nowrap}
  .masthead .sep{width:1px;height:24px;background:rgba(255,255,255,.22);flex:0 0 auto}
  .masthead .tag{font-size:12.5px;color:#e2e7f3;white-space:nowrap}
  .masthead .right{margin-left:auto;display:flex;align-items:center;gap:16px;
        font:11px/1.4 var(--mono);color:#b9c3dc;font-variant-numeric:tabular-nums;
        white-space:nowrap}
  .masthead a{color:#fff;border-bottom:1px solid rgba(255,255,255,.45)}
  .masthead a:hover{border-bottom-color:#fff}

  .app{display:grid;grid-template-columns:304px minmax(0,1fr);min-height:calc(100vh - var(--mh))}

  /* ── 좌측: 소장 정보 + 게시판 색인 ─────────────────────── */
  aside{background:var(--paper);border-right:1px solid var(--rule);
        padding:24px 24px 30px;position:sticky;top:var(--mh);
        height:calc(100vh - var(--mh));overflow:auto}
  .mark{display:inline-block;margin:0 0 10px;font-size:11px;font-weight:650;
        letter-spacing:.24em;color:#fff;background:var(--accent);padding:3px 8px 3px 10px}
  aside h1{margin:0;font-size:20px;line-height:1.3;font-weight:700;letter-spacing:-.02em;
        color:var(--navy)}
  .ename{margin:4px 0 0;font:10.5px/1.5 var(--mono);color:var(--ink-3);
         letter-spacing:.06em;text-transform:uppercase}
  .src{margin:12px 0 0;padding:10px 0 0;border-top:2px solid var(--navy);font-size:12px}
  .src a{font-family:var(--mono);font-size:11.5px}
  .addr{margin:8px 0 0;font:10.5px/1.55 var(--mono);color:var(--ink-3)}

  .stats{margin:16px 0 0;display:grid;grid-template-columns:1fr 1fr;
         border-top:2px solid var(--navy);border-left:1px solid var(--rule-soft);
         background:var(--panel)}
  .stats div{padding:9px 10px;border-right:1px solid var(--rule-soft);
             border-bottom:1px solid var(--rule-soft)}
  .stats dt{font-size:11px;color:var(--ink-3);margin:0}
  .stats dd{margin:3px 0 0;font:600 13px/1.3 var(--mono);font-variant-numeric:tabular-nums;
             color:var(--navy)}
  .stats .wide{grid-column:1 / -1}
  .stats .wide dd{font-size:12px;font-weight:500}

  .nav{margin:24px 0 0}
  .nav h2{margin:0 0 8px;padding:0 0 6px 8px;border-left:3px solid var(--accent);
          border-bottom:1px solid var(--rule);font-size:12px;font-weight:700;
          color:var(--navy);letter-spacing:.02em}
  .nav ul{list-style:none;margin:0;padding:0}
  .nav button{display:flex;width:100%;align-items:baseline;gap:8px;text-align:left;
              background:none;border:0;border-left:3px solid transparent;
              padding:6px 8px 6px 8px;border-radius:0;font-size:13px;color:var(--ink-2);
              cursor:pointer}
  .nav button:hover{background:var(--panel-2);color:var(--ink)}
  .nav button[aria-current=true]{background:var(--navy-soft);color:var(--navy);font-weight:700;
              border-left-color:var(--accent)}
  .nav .n{margin-left:auto;font:11px/1.4 var(--mono);color:var(--ink-3);
          font-variant-numeric:tabular-nums}
  .nav button[aria-current=true] .n{color:var(--navy-2)}
  .note{margin:22px 0 0;padding:12px 0 0;border-top:1px solid var(--rule);
        font-size:11px;line-height:1.65;color:var(--ink-3)}

  /* ── 본문 ──────────────────────────────────────────────── */
  main{min-width:0;display:flex;flex-direction:column;background:var(--panel)}
  .bar{position:sticky;top:var(--mh);z-index:6;display:flex;flex-wrap:wrap;align-items:center;
       gap:10px 12px;padding:12px 28px;background:var(--panel);
       border-bottom:1px solid var(--rule)}
  .find{position:relative;flex:1 1 260px;max-width:460px;display:flex;align-items:center}
  input[type=search]{width:100%;padding:8px 56px 8px 11px;border:1px solid var(--rule);
       border-radius:2px;background:var(--paper);font:inherit;font-size:13px;color:var(--ink)}
  input[type=search]:focus{background:var(--panel);border-color:var(--navy)}
  input[type=search]::placeholder{color:var(--ink-3)}
  /* 브라우저 기본 '지우기' 단추 제거 — 뷰어의 × 버튼과 겹친다 */
  input[type=search]::-webkit-search-cancel-button,
  input[type=search]::-webkit-search-decoration{-webkit-appearance:none;appearance:none}
  .find kbd{position:absolute;right:34px;font:10.5px/1 var(--mono);color:var(--ink-3);
       border:1px solid var(--rule);border-radius:2px;padding:3px 5px;background:var(--panel)}
  .find .x{position:absolute;right:6px;width:22px;height:22px;line-height:1;border:0;
       border-radius:2px;background:none;color:var(--ink-3);font-size:15px;cursor:pointer;
       padding:0}
  .find .x:hover{background:var(--panel-2);color:var(--ink)}

  .seg{display:inline-flex;border:1px solid var(--rule);border-radius:0;
       overflow:hidden;background:var(--panel)}
  .seg button{border:0;border-left:1px solid var(--rule);background:none;
       padding:8px 12px;font-size:12.5px;color:var(--ink-2);cursor:pointer}
  .seg button:first-child{border-left:0}
  .seg button:hover{background:var(--panel-2);color:var(--ink)}
  .seg button[aria-pressed=true]{background:var(--navy);color:#fff;font-weight:650}
  .seg .en{font-size:9.5px;letter-spacing:.06em;color:var(--ink-3);margin-left:4px}
  .seg button[aria-pressed=true] .en{color:#c3cbe1}
  .count{margin-left:auto;font:11.5px/1.4 var(--mono);color:var(--ink-3);
         font-variant-numeric:tabular-nums;white-space:nowrap}

  .list{padding:0 28px 40px}
  .row{display:grid;grid-template-columns:52px 92px minmax(0,1fr) 96px 92px 48px;
       gap:0 14px;align-items:baseline;padding:9px 8px;border-left:3px solid transparent}
  .head{position:sticky;top:calc(var(--mh) + var(--barh));z-index:4;background:var(--navy-soft);
        border-bottom:1px solid var(--navy);padding:0 8px;
        font-family:var(--sans);font-size:12px;font-weight:650;color:var(--navy-2)}
  .head > span{align-self:stretch;display:flex;align-items:center;padding:10px 0}
  .head .en{font:9.5px/1 var(--mono);font-weight:400;letter-spacing:.06em;color:var(--ink-3);
        margin-left:4px}
  .head .sortable{border:0;background:none;padding:0;font:inherit;color:inherit;cursor:pointer;
        display:inline-flex;align-items:center;gap:4px}
  .head .sortable .en{margin-left:2px}
  .head .sortable:hover{color:var(--navy)}
  .head .sortable::after{content:"";width:0;height:0;border-left:3.5px solid transparent;
        border-right:3.5px solid transparent;border-top:4px solid currentColor;opacity:.35}
  .head .sortable[aria-pressed=true]{color:var(--navy);font-weight:700}
  .head .sortable[aria-pressed=true]::after{opacity:1}
  .head .sortable[aria-pressed=true].asc::after{border-top:0;border-bottom:4px solid currentColor}
  .head .r{justify-content:flex-end}
  .c-views,.head .r,.c-views *{text-align:right}

  .item{border-bottom:1px solid var(--rule-soft)}
  .post{cursor:pointer;color:inherit}
  .post:hover{background:var(--hover);border-left-color:var(--navy-2)}
  .post[aria-expanded=true]{background:var(--sel);border-left-color:var(--accent)}
  .c-no,.c-views{font:11.5px/1.62 var(--mono);color:var(--ink-3);
        font-variant-numeric:tabular-nums;text-align:right;white-space:nowrap}
  .c-no{text-align:center}
  .head > span:first-child{justify-content:center}
  .c-board{font-family:var(--sans);font-size:11.5px;line-height:1.7;color:var(--ink-3);
        overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
  .c-title{min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:var(--ink);
        font-size:14px}
  .c-title .nt{display:inline-block;margin-right:7px;padding:1px 5px;border:1px solid #e3c4c1;
        border-radius:2px;background:var(--notice-soft);color:var(--notice);
        font-size:10px;font-weight:650;line-height:1.5;vertical-align:1px}
  .c-title .at{display:inline-block;margin-left:7px;padding:0 4px;border:1px solid var(--rule);
        border-radius:2px;color:var(--ink-3);font:10px/1.5 var(--mono);vertical-align:1px}
  .c-title .at b{font-weight:600;color:var(--ink-2)}
  .c-who,.c-date{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;
        font-size:12.5px;color:var(--ink-2)}
  .c-date{font:11.5px/1.7 var(--mono);color:var(--ink-3);font-variant-numeric:tabular-nums}
  .c-meta{display:none}
  mark{background:var(--mark);color:inherit;padding:0 1px}

  /* ── 펼친 본문 ─────────────────────────────────────────── */
  .pane{display:none;padding:0 8px 26px var(--indent)}
  .pane.open{display:block}
  .meta{display:flex;flex-wrap:wrap;gap:6px 22px;padding:10px 0;margin:0 0 16px;
        border-top:1px solid var(--rule);border-bottom:1px solid var(--rule-soft);
        font:12px/1.6 var(--mono);color:var(--ink-2)}
  .meta em{font-style:normal;color:var(--ink-3);margin-right:6px}
  .meta .go{margin-left:auto}
  .txt{white-space:pre-wrap;overflow-wrap:anywhere;max-width:72ch;margin:0 0 20px;
       font-size:14px;line-height:1.8;color:var(--ink)}
  .txt.none{color:var(--ink-3);font-size:13px;max-width:60ch}
  h3.sec{margin:0 0 8px;padding:0 0 5px 8px;border-left:3px solid var(--accent);
       border-bottom:1px solid var(--rule);font-size:12px;font-weight:700;color:var(--navy)}
  .thumbs{display:grid;grid-template-columns:repeat(auto-fill,minmax(148px,1fr));
       gap:8px;margin:0 0 22px}
  .thumbs a{display:block;border:1px solid var(--rule);border-radius:2px;overflow:hidden;
       background:var(--panel-2);line-height:0}
  .thumbs a:hover{border-color:var(--accent)}
  .thumbs img{display:block;width:100%;height:132px;object-fit:cover}
  ul.files{list-style:none;margin:0 0 8px;padding:0;border-top:1px solid var(--rule-soft)}
  ul.files li{display:flex;align-items:baseline;gap:10px;padding:7px 0;
       border-bottom:1px solid var(--rule-soft);font-size:13px}
  ul.files .fn{overflow-wrap:anywhere;border-bottom:0}
  ul.files .st{font:10px/1.5 var(--mono);color:var(--ink-3);border:1px solid var(--rule);
       border-radius:3px;padding:0 4px;white-space:nowrap}
  ul.files .sz{margin-left:auto;font:11px/1.6 var(--mono);color:var(--ink-3);
       font-variant-numeric:tabular-nums;white-space:nowrap}
  .more{display:block;width:100%;margin:18px 0 0;padding:11px;background:var(--paper);
       border:1px solid var(--rule);border-radius:3px;font-size:12.5px;color:var(--ink-2);
       cursor:pointer}
  .more:hover{background:var(--panel-2);color:var(--ink)}
  .empty{padding:60px 8px 64px;color:var(--ink-3);font-size:13px}
  .empty b{color:var(--ink);font-weight:600}
  .empty p{margin:6px 0 14px;font-size:12.5px}
  .empty button{padding:8px 13px;background:var(--paper);border:1px solid var(--rule);
       border-radius:3px;font-size:12.5px;color:var(--ink-2);cursor:pointer}
  .empty button:hover{background:var(--panel-2);color:var(--ink)}
  footer{padding:15px 28px;border-top:2px solid var(--navy);font-size:11.5px;color:var(--ink-3);
        display:flex;flex-wrap:wrap;gap:6px 14px;align-items:baseline}
  footer a{font-family:var(--mono);font-size:11px}
  footer .r{margin-left:auto}

  /* ── 밀도 토글 (보통 / 조밀) ───────────────────────────── */
  body.dens-compact .row{padding:5px 8px}
  body.dens-compact .c-title{font-size:13.5px}
  body.dens-compact .c-no,body.dens-compact .c-views{line-height:1.45}
  body.dens-compact .head span{padding:8px 0}
  body.dens-compact .pane{padding-bottom:18px}
  body.dens-compact .meta{padding:8px 0;margin-bottom:12px}
  body.dens-compact .txt{margin-bottom:14px;line-height:1.7}
  body.dens-compact .thumbs img{height:112px}

  /* ── 다크 모드 (툴바 토글 · 기본은 라이트) ─────────────── */
  body.theme-dark{
    --band:#101728;
    --paper:#14171d; --panel:#1b1f27; --panel-2:#262b36; --hover:#20242e; --sel:#202837;
    --ink:#eceef4; --ink-2:#b3b9c6; --ink-3:#878d9c;
    --rule:#333947; --rule-soft:#282d38;
    --accent:#7fc08f; --accent-soft:#22302a; --mark:#4d431c;
    --navy:#c3cdec; --navy-2:#9fadd8; --navy-soft:#232a3d;
    --notice:#e08b80; --notice-soft:#33211f;
  }
  body.theme-dark a{border-bottom-color:#39544a}
  body.theme-dark a:hover{border-bottom-color:var(--accent)}
  body.theme-dark mark{color:#f3f0e8}
  body.theme-dark .mark{color:#101728}
  body.theme-dark .c-title .nt{border-color:#5a3b38}
  body.theme-dark input[type=search]{background:#141821}
  body.theme-dark input[type=search]:focus{background:#10131a}
  body.theme-dark .seg button:hover{background:#242a36}
  body.theme-dark .seg button[aria-pressed=true]{background:#2b3a63;color:#eef1f8}
  body.theme-dark .seg button[aria-pressed=true] .en{color:#b3bfe0}
  body.theme-dark .find kbd{background:#242a36}
  body.theme-dark .more{background:#141821}
  body.theme-dark .more:hover{background:#242a36}
  body.theme-dark .empty button{background:#141821;color:var(--ink-2)}
  body.theme-dark .empty button:hover{background:#242a36;color:var(--ink)}
  body.theme-dark .thumbs a{background:#141821}

  @media (max-width:1040px){
    .app{grid-template-columns:1fr}
    aside{position:static;height:auto;border-right:0;border-bottom:1px solid var(--rule);
          padding:22px}
    .nav ul{display:flex;flex-wrap:wrap;gap:2px}
    .nav button{width:auto;border-left:0;border-bottom:3px solid transparent;padding:6px 10px}
    .nav button[aria-current=true]{border-left-color:transparent;
          border-bottom-color:var(--accent)}
    .note{margin-top:18px}
  }
  @media (max-width:880px){
    .row{grid-template-columns:minmax(0,1fr) 74px;gap:2px 12px;padding:11px 6px}
    .c-no,.c-board{display:none}
    .c-title,.c-meta,.c-views{grid-column:auto}
    .c-meta{display:flex;flex-wrap:wrap;gap:4px 10px;font:11px/1.5 var(--mono);
          color:var(--ink-3);grid-column:1 / -1;order:3}
    .c-views{order:2}
    .c-date,.c-who{display:none}
    .head > span:nth-child(1),.head > span:nth-child(2),.head > span:nth-child(4),
    .head > span:nth-child(5){display:none}
    .head{padding:0 6px}
    .head .en{display:none}
    .pane{padding-left:8px}
    .bar,.list,footer{padding-left:16px;padding-right:16px}
    .find{max-width:none}
    .masthead{gap:10px;padding:0 16px}
    .masthead .tag{display:none}
  }
  @media (max-width:600px){
    aside{padding:18px}
    .bar{gap:8px;padding:11px 14px}
    .count{width:100%;margin-left:0}
    .list,footer{padding-left:10px;padding-right:10px}
    .thumbs{grid-template-columns:repeat(auto-fill,minmax(120px,1fr))}
    .thumbs img{height:112px}
    .seg button{padding:8px 9px}
    .seg .en{display:none}
    .masthead{padding:0 12px}
    .masthead .en,.masthead .gen,.masthead .sep{display:none}
  }
</style>
</head>
<body>
<header class="masthead">
  <div class="brand">
    <span class="kr">%%TITLE%%</span>
    <span class="en">%%TITLE_EN%%</span>
  </div>
  <span class="sep" aria-hidden="true"></span>
  <div class="tag"><b>게시판 아카이브</b> · Board Archive</div>
  <div class="right">
    <span class="gen">수집 %%GENERATED%%</span>
    <a href="%%BASE_URL%%" target="_blank" rel="noopener">원문 사이트</a>
  </div>
</header>
<div class="app">
  <aside>
    <p class="mark">소장 자료</p>
    <h1>%%TITLE%%</h1>
    <p class="ename">%%TITLE_EN%%</p>
    <div class="src"><a href="%%BASE_URL%%" target="_blank" rel="noopener">%%BASE_URL%%</a></div>
    <p class="addr">No.73 Zhenpeng Industry District, Jinzhou New District, Dalian, Liaoning, China</p>

    <dl class="stats" id="stats"></dl>

    <nav class="nav" id="nav">
      <h2>게시판 색인 <span class="en">Board Index</span></h2>
      <ul id="navul"></ul>
    </nav>

    <p class="note">%%NOTE%%</p>
  </aside>

  <main>
    <div class="bar" id="bar">
      <div class="find">
        <input type="search" id="q" autocomplete="off" aria-label="검색 / Search"
               placeholder="제목·본문·작성자·첨부 검색 (title, body, author, file)">
        <kbd>/</kbd>
        <button type="button" class="x" id="clear" aria-label="검색어 지우기" hidden>×</button>
      </div>
      <div class="seg" id="sortseg" role="group" aria-label="정렬">
        <button type="button" data-sort="date_desc" aria-pressed="true">최신<span class="en">Newest</span></button>
        <button type="button" data-sort="date_asc" aria-pressed="false">오래된<span class="en">Oldest</span></button>
        <button type="button" data-sort="views_desc" aria-pressed="false">조회<span class="en">Views</span></button>
        <button type="button" data-sort="board" aria-pressed="false">게시판<span class="en">Board</span></button>
      </div>
      <div class="seg" role="group" aria-label="필터">
        <button type="button" id="onlyatt" aria-pressed="false">첨부만<span class="en">Files</span></button>
      </div>
      <div class="seg" id="densseg" role="group" aria-label="행 밀도">
        <button type="button" data-dens="cozy" aria-pressed="true">보통<span class="en">Cozy</span></button>
        <button type="button" data-dens="compact" aria-pressed="false">조밀<span class="en">Compact</span></button>
      </div>
      <div class="seg" role="group" aria-label="테마">
        <button type="button" id="theme" aria-pressed="false">어둡게<span class="en">Dark</span></button>
      </div>
      <span class="count" id="count"></span>
    </div>

    <div class="list">
      <div class="row head" id="head">
        <span>번호<span class="en">No.</span></span>
        <span><button type="button" class="sortable" id="h-board" aria-pressed="false">게시판<span class="en">Board</span></button></span>
        <span>제목<span class="en">Title</span></span>
        <span>작성자<span class="en">Writer</span></span>
        <span><button type="button" class="sortable" id="h-date" aria-pressed="true">작성일<span class="en">Date</span></button></span>
        <span class="r"><button type="button" class="sortable r" id="h-views" aria-pressed="false">조회</button></span>
      </div>
      <div id="rows"></div>
      <button class="more" id="more" hidden></button>
    </div>

    <footer>
      <span><b>%%TITLE%%</b> <span class="en">%%TITLE_EN%%</span></span>
      <span>수집 <b>%%GENERATED%%</b></span>
      <span>%%EXPORT_LINKS%%</span>
      <span class="r">데이터 출처·권리: 원 사이트(학교) 소유</span>
    </footer>
  </main>
</div>

<script id="data" type="application/json">%%POSTS%%</script>
<script id="atts" type="application/json">%%ATTS%%</script>
<script id="boards" type="application/json">%%BOARDS%%</script>
<script id="statsjson" type="application/json">%%STATS%%</script>
<script>
(function () {
  'use strict';
  var POSTS  = JSON.parse(document.getElementById('data').textContent);
  var ATTS   = JSON.parse(document.getElementById('atts').textContent);
  var BOARDS = JSON.parse(document.getElementById('boards').textContent);
  var STATS  = JSON.parse(document.getElementById('statsjson').textContent);
  var SITE   = { name: %%JS_TITLE%%, nameEn: %%JS_TITLE_EN%%, base: %%JS_BASE_URL%% };

  var BATCH = 150;
  // 첨부 상태 라벨 — 파일 다운로드 없이 목록만 기록한 경우가 기본값이다.
  var ST = { listed: '원문', downloaded: '보관', skipped_robots: '정책제외', error: '오류' };
  var $ = function (id) { return document.getElementById(id); };
  var rowsEl = $('rows'), moreEl = $('more'), qEl = $('q'), clearEl = $('clear'),
      segEl = $('sortseg'), attEl = $('onlyatt'), cntEl = $('count'),
      densEl = $('densseg'), themeEl = $('theme'),
      hDate = $('h-date'), hViews = $('h-views'), hBoard = $('h-board');

  var state = { board: '', kw: '', sort: 'date_desc', only: false, shown: BATCH, dens: 'cozy' };
  var view = [];

  /* ── helpers ─────────────────────────────────────────── */
  var ESC = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' };
  function esc(s) { return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) { return ESC[c]; }); }

  function rxEscape(s) { return s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'); }

  // 원문 → 검색어 하이라이트된 안전한 HTML
  function hl(raw, kw) {
    raw = String(raw == null ? '' : raw);
    if (!kw) { return esc(raw); }
    var re = new RegExp(rxEscape(kw), 'gi'), out = '', last = 0, m;
    while ((m = re.exec(raw)) !== null) {
      if (m[0] === '') { re.lastIndex++; continue; }
      out += esc(raw.slice(last, m.index)) + '<mark>' + esc(m[0]) + '</mark>';
      last = m.index + m[0].length;
    }
    return out + esc(raw.slice(last));
  }

  function fmtSize(n) {
    if (!n && n !== 0) { return ''; }
    if (n < 1024) { return n + ' B'; }
    if (n < 1048576) { return (n / 1024).toFixed(n < 10240 ? 1 : 0) + ' KB'; }
    return (n / 1048576).toFixed(1) + ' MB';
  }

  function dateKey(p) { return p.d || ''; }

  function localUrl(p) { return SITE.base + p.u; }

  /* ── 좌측 패널 ───────────────────────────────────────── */
  function renderSide() {
    var rows = [
      ['게시글', 'Posts', STATS.posts], ['첨부', 'Files', STATS.attachments],
      ['게시판', 'Boards', STATS.boards],
      ['기간', 'Period', STATS.span, 'wide']
    ];
    $('stats').innerHTML = rows.map(function (r) {
      return '<div' + (r[3] ? ' class="' + r[3] + '"' : '') + '><dt>' + esc(r[0]) +
             ' <span class="en">' + esc(r[1]) + '</span></dt>' +
             '<dd>' + esc(r[2]) + '</dd></div>';
    }).join('');

    var list = document.createElement('ul');
    var mk = function (no, name, count, latest) {
      var li = document.createElement('li');
      var b = document.createElement('button');
      b.type = 'button';
      b.setAttribute('aria-current', String(state.board === no));
      b.title = latest ? latest + ' 까지 수집' : '수집 없음';
      b.innerHTML = '<span>' + esc(name) + '</span><span class="n">' + count + '</span>';
      b.addEventListener('click', function () { setBoard(no); });
      li.appendChild(b);
      return li;
    };
    list.appendChild(mk('', '전체', POSTS.length, STATS.latest));
    BOARDS.forEach(function (b) { list.appendChild(mk(String(b.no), b.name, b.count, b.latest)); });
    $('navul').replaceChildren(list);
  }

  function setBoard(no) {
    state.board = no;
    state.shown = BATCH;
    renderSide();
    render();
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }

  /* ── 정렬 UI 동기화 ──────────────────────────────────── */
  function syncSort() {
    var s = state.sort;
    Array.prototype.forEach.call(segEl.querySelectorAll('button'), function (b) {
      b.setAttribute('aria-pressed', String(b.dataset.sort === s));
    });
    hDate.setAttribute('aria-pressed', String(s === 'date_desc' || s === 'date_asc'));
    hDate.classList.toggle('asc', s === 'date_asc');
    hViews.setAttribute('aria-pressed', String(s === 'views_desc'));
    hBoard.setAttribute('aria-pressed', String(s === 'board'));
  }

  function setSort(s) {
    state.sort = s;
    state.shown = BATCH;
    syncSort();
    render();
  }

  /* ── 목록 ────────────────────────────────────────────── */
  function haystack(p) {
    if (!p._h) {
      p._h = (p.t + ' ' + p.a + ' ' + (p.x || '') + ' ' + (p.bname || '') + ' ' +
              (ATTS[p.k] || []).map(function (f) { return f.filename; }).join(' ')).toLowerCase();
    }
    return p._h;
  }

  function compute() {
    var kw = state.kw.toLowerCase();
    view = POSTS.filter(function (p) {
      if (state.board && String(p.m) !== state.board) { return false; }
      var fs = ATTS[p.k] || [];
      if (state.only && !fs.length) { return false; }
      if (kw && haystack(p).indexOf(kw) === -1) { return false; }
      return true;
    });
    var s = state.sort;
    view.sort(function (x, y) {
      if (s === 'board') {
        return (x.m - y.m) || dateKey(y).localeCompare(dateKey(x));
      }
      if (s === 'views_desc') {
        return ((y.v || -1) - (x.v || -1)) || dateKey(y).localeCompare(dateKey(x));
      }
      var d = dateKey(x), e = dateKey(y);
      if (!d && !e) { return (y.m - x.m) || (y.n - x.n); }
      if (!d) { return 1; }
      if (!e) { return -1; }
      return s === 'date_asc' ? d.localeCompare(e) : e.localeCompare(d);
    });
    if (state.shown > view.length) { state.shown = view.length; }
  }

  function rowHtml(p, kw) {
    var fs = ATTS[p.k] || [];
    var ext = fs.length
      ? '<span class="at">' + esc(fs[0].ext || 'file') + (fs.length > 1 ? ' <b>+' + (fs.length - 1) + '</b>' : '') + '</span>'
      : '';
    var title = (p.t ? hl(p.t, kw) : '<span style="color:var(--ink-3)">(제목 없음)</span>');
    var meta = [
      esc(p.bname || ''),
      esc(p.d || ''),
      p.v == null ? '' : '조회 ' + esc(p.v)
    ].filter(Boolean).map(function (s) { return '<span>' + s + '</span>'; }).join('');
    return '<div class="post row" data-k="' + esc(p.k) + '" role="button" tabindex="0" aria-expanded="false">' +
      '<div class="c-no">' + esc(p.n) + '</div>' +
      '<div class="c-board">' + esc(p.bname || '') + '</div>' +
      '<div class="c-title" title="' + esc(p.t) + '">' +
        (p.nt ? '<span class="nt">공지</span>' : '') + title + ext + '</div>' +
      '<div class="c-who">' + hl(p.a || '', kw) + '</div>' +
      '<div class="c-date">' + esc(p.d || '') + '</div>' +
      '<div class="c-views">' + (p.v == null ? '' : esc(p.v)) + '</div>' +
      '<div class="c-meta">' + meta + '</div>' +
    '</div>' +
    '<div class="pane" data-pane="' + esc(p.k) + '"></div>';
  }

  function paneHtml(p) {
    var fs = ATTS[p.k] || [];
    var meta = [];
    if (p.at) { meta.push('<span><em>작성</em>' + esc(p.at) + '</span>'); }
    if (p.v != null) { meta.push('<span><em>조회</em>' + esc(p.v) + '</span>'); }
    meta.push('<span><em>게시판</em>' + esc(p.bname || '') + '</span>');
    meta.push('<span class="go"><a href="' + esc(localUrl(p)) + '" target="_blank" rel="noopener">원문 보기 <span class="en">Original</span> &rarr;</a></span>');

    var thumbs = (p.im || []).map(function (u) {
      return '<a href="' + esc(u) + '" target="_blank" rel="noopener">' +
             '<img src="' + esc(u) + '" alt="" loading="lazy" referrerpolicy="no-referrer"></a>';
    }).join('');

    var files = fs.length
      ? '<h3 class="sec">첨부 ' + fs.length + '건 <span class="en">Files</span></h3><ul class="files">' + fs.map(function (f) {
          var href = f.local ? '../' + f.local : f.url;
          return '<li><a class="fn" href="' + esc(href) + '" target="_blank" rel="noopener">' +
                 esc(f.filename) + '</a>' +
                 '<span class="st">' + esc(ST[f.status] || f.status || '') + '</span>' +
                 '<span class="sz">' + fmtSize(f.size) + '</span></li>';
        }).join('') + '</ul>'
      : '';

    var txt = p.x && p.x.trim().length > 2
      ? '<div class="txt">' + esc(p.x) + '</div>'
      : '<div class="txt none">수집된 본문 텍스트가 없습니다 — 본문이 이미지·첨부로만 구성된 글입니다. 원문에서 확인하세요.</div>';

    return '<div class="meta">' + meta.join('') + '</div>' + txt +
      (thumbs ? '<h3 class="sec">이미지 ' + p.im.length + '장 <span class="en">Images</span></h3><div class="thumbs">' + thumbs + '</div>' : '') +
      files;
  }

  function render() {
    compute();
    var kw = state.kw;
    var n = Math.min(state.shown, view.length);
    var buf = [];
    for (var i = 0; i < n; i++) { buf.push(rowHtml(view[i], kw)); }
    rowsEl.innerHTML = buf.join('') ||
      '<div class="empty"><b>' + esc(kw || '선택한 게시판') + '</b> 에 해당하는 글이 없습니다.' +
      '<p>검색어를 바꾸거나 게시판 색인에서 다른 게시판을 고르면 결과가 나옵니다.</p>' +
      '<button type="button" id="reset">전체 게시글로 돌아가기</button></div>';

    cntEl.textContent = (view.length === POSTS.length
      ? POSTS.length + '건'
      : view.length + ' / ' + POSTS.length + '건');
    var rest = view.length - n;
    moreEl.hidden = rest <= 0;
    moreEl.textContent = rest > 0 ? '더 보기 — ' + n + ' / ' + view.length + '건 (' + rest + '건 남음)' : '';
    clearEl.hidden = !qEl.value;
    measure();
  }

  function toggle(el) {
    var pane = rowsEl.querySelector('.pane[data-pane="' + el.dataset.k + '"]');
    if (!pane) { return; }
    var open = el.getAttribute('aria-expanded') === 'true';
    el.setAttribute('aria-expanded', String(!open));
    if (!open && !pane.dataset.filled) {
      var p = view.filter(function (x) { return x.k === el.dataset.k; })[0];
      if (p) { pane.innerHTML = paneHtml(p); pane.dataset.filled = '1'; }
    }
    pane.classList.toggle('open', !open);
  }

  rowsEl.addEventListener('click', function (e) {
    if (e.target.closest('#reset') || e.target.id === 'reset') {
      state.board = ''; state.kw = ''; state.only = false; state.shown = BATCH;
      qEl.value = ''; attEl.setAttribute('aria-pressed', 'false');
      renderSide(); render();
      return;
    }
    var el = e.target.closest('.post');
    if (!el) { return; }
    if (e.target.closest('a')) { return; }
    toggle(el);
  });
  rowsEl.addEventListener('keydown', function (e) {
    if (e.key !== 'Enter' && e.key !== ' ') { return; }
    var el = e.target.closest('.post');
    if (el) { e.preventDefault(); toggle(el); }
  });

  moreEl.addEventListener('click', function () {
    state.shown += BATCH;
    render();
  });

  var timer = null;
  qEl.addEventListener('input', function () {
    clearTimeout(timer);
    timer = setTimeout(function () {
      state.kw = qEl.value.trim();
      state.shown = BATCH;
      render();
    }, 110);
  });
  clearEl.addEventListener('click', function () {
    qEl.value = '';
    state.kw = '';
    state.shown = BATCH;
    render();
    qEl.focus();
  });
  segEl.addEventListener('click', function (e) {
    var b = e.target.closest('button[data-sort]');
    if (b) { setSort(b.dataset.sort); }
  });
  attEl.addEventListener('click', function () {
    state.only = !state.only;
    attEl.setAttribute('aria-pressed', String(state.only));
    state.shown = BATCH;
    render();
  });

  /* ── 행 밀도 (보통/조밀, localStorage 유지) ───────────── */
  function setDens(v) {
    state.dens = v;
    document.body.classList.toggle('dens-compact', v === 'compact');
    Array.prototype.forEach.call(densEl.querySelectorAll('button'), function (b) {
      b.setAttribute('aria-pressed', String(b.dataset.dens === v));
    });
    try { localStorage.setItem('dkis-dens', v); } catch (err) { /* 파일 직접 열람 시 무시 */ }
    measure();
  }
  densEl.addEventListener('click', function (e) {
    var b = e.target.closest('button[data-dens]');
    if (b) { setDens(b.dataset.dens); }
  });

  /* ── 테마 (라이트 기본 / 다크 토글, localStorage 유지) ── */
  function setTheme(dark) {
    document.body.classList.toggle('theme-dark', dark);
    themeEl.setAttribute('aria-pressed', String(dark));
    themeEl.innerHTML = dark ? '밝게<span class="en">Light</span>' : '어둡게<span class="en">Dark</span>';
    var m = document.querySelector('meta[name=color-scheme]');
    if (m) { m.setAttribute('content', dark ? 'dark' : 'light'); }
    try { localStorage.setItem('dkis-theme', dark ? 'dark' : 'light'); } catch (err) { /* 무시 */ }
  }
  themeEl.addEventListener('click', function () {
    setTheme(!document.body.classList.contains('theme-dark'));
  });
  hDate.addEventListener('click', function () {
    setSort(state.sort === 'date_asc' ? 'date_desc' : 'date_asc');
  });
  hViews.addEventListener('click', function () { setSort('views_desc'); });
  hBoard.addEventListener('click', function () { setSort('board'); });

  document.addEventListener('keydown', function (e) {
    if (e.key === '/' && document.activeElement !== qEl) { e.preventDefault(); qEl.focus(); }
    if (e.key === 'Escape' && document.activeElement === qEl) {
      qEl.value = ''; state.kw = ''; render();
    }
  });

  var raf = null;
  function measure() {
    if (raf) { return; }
    raf = requestAnimationFrame(function () {
      raf = null;
      document.documentElement.style.setProperty('--barh', $('bar').offsetHeight + 'px');
    });
  }
  window.addEventListener('resize', measure);

  var totalAtt = POSTS.reduce(function (a, p) { return a + (ATTS[p.k] || []).length; }, 0);
  var dates = POSTS.map(function (p) { return p.d; }).filter(Boolean).sort();
  STATS.posts = POSTS.length;
  STATS.attachments = totalAtt;
  STATS.boards = BOARDS.filter(function (b) { return b.count > 0; }).length;
  STATS.span = dates.length ? dates[0] + ' ~ ' + dates[dates.length - 1] : '-';
  STATS.latest = dates.length ? dates[dates.length - 1] : '';

  renderSide();
  syncSort();
  var savedDens = 'cozy';
  try { savedDens = localStorage.getItem('dkis-dens') || 'cozy'; } catch (err) { /* 무시 */ }
  setDens(savedDens === 'compact' ? 'compact' : 'cozy');
  var savedTheme = 'light';
  try { savedTheme = localStorage.getItem('dkis-theme') || 'light'; } catch (err) { /* 무시 */ }
  setTheme(savedTheme === 'dark');
  compute();
  render();
  measure();
})();
</script>
</body>
</html>
"""

_TOKEN_RE = re.compile(r"%%[A-Z_]+%%")


def _fill(tpl: str, **kv) -> str:
    """%%TOKEN%% 치환. 토큰이 남아 있으면 즉시 실패한다(조용한 누락 방지)."""
    out = tpl
    for k, v in kv.items():
        out = out.replace(f"%%{k}%%", v)
    left = set(_TOKEN_RE.findall(out))
    if left:
        raise ValueError(f"뷰어 템플릿에 치환되지 않은 토큰: {sorted(left)}")
    return out


def _js(v) -> str:
    """JSON 문자열을 <script> 안에 안전하게 넣기 위한 이스케이프."""
    return json.dumps(v, ensure_ascii=False).replace("</", "<\\/")


def export_json(store: Store, site: dict, out_dir: str | Path, *, text_limit: int = 4000) -> dict:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    posts = []
    for r in store.iter_posts(site["key"]):
        posts.append({
            "key": f'{r["menu_no"]}:{r["bno"]}',
            "menu_no": r["menu_no"],
            "board": site["boards"].get(r["menu_no"], {}).get("name", str(r["menu_no"])),
            "bno": r["bno"],
            "title": r["title"],
            "author": r["author"],
            "posted_at": r["posted_at"],
            "posted_date": r["posted_date"],
            "views": r["views"],
            "notice": bool(r["is_notice"]),
            "has_attachment": bool(r["has_attachment"]),
            "url": site["base_url"] + (r["url"] or ""),
            "text": (r["content_text"] or "")[:text_limit],
            "images": json.loads(r["images_json"] or "[]"),
        })
    atts = {}
    rows = store.conn.execute(
        "SELECT menu_no,bno,filename,url,ext,size_bytes,sha256,local_path,status "
        "FROM attachments WHERE site_key=? ORDER BY menu_no,bno", (site["key"],)).fetchall()
    for a in rows:
        atts.setdefault(f'{a["menu_no"]}:{a["bno"]}', []).append({
            "filename": a["filename"], "url": site["base_url"] + (a["url"] or ""),
            "ext": a["ext"], "size_bytes": a["size_bytes"], "sha256": a["sha256"],
            "local": a["local_path"] or "", "status": a["status"],
        })

    (out / "posts.json").write_text(json.dumps(posts, ensure_ascii=False, indent=1), encoding="utf-8")
    (out / "attachments.json").write_text(json.dumps(atts, ensure_ascii=False, indent=1), encoding="utf-8")
    with (out / "attachments.csv").open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["menu_no", "board", "bno", "filename", "ext", "size_bytes", "sha256", "status", "url"])
        for a in rows:
            w.writerow([a["menu_no"], site["boards"].get(a["menu_no"], {}).get("name", ""),
                        a["bno"], a["filename"], a["ext"], a["size_bytes"], a["sha256"],
                        a["status"], site["base_url"] + (a["url"] or "")])
    with (out / "posts.csv").open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["menu_no", "board", "bno", "title", "author", "posted_date", "views", "notice",
                    "has_attachment", "url"])
        for p in posts:
            w.writerow([p["menu_no"], p["board"], p["bno"], p["title"], p["author"],
                        p["posted_date"], p["views"], int(p["notice"]), int(p["has_attachment"]), p["url"]])

    summary = store.stats(site["key"])
    summary["site"] = {k: site[k] for k in ("key", "name", "base_url", "school_code") if k in site}
    summary["exported_posts"] = len(posts)
    summary["exported_attachments"] = sum(len(v) for v in atts.values())
    (out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
    return {"posts": len(posts), "attachments": sum(len(v) for v in atts.values()), "out": str(out)}


def build_viewer(store: Store, site: dict, out_dir: str | Path, *, generated: str = "") -> str:
    """자체 포함 단일 HTML 뷰어 생성 (외부 리소스 없음)."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    base = site["base_url"]

    posts, atts = [], {}
    for r in store.iter_posts(site["key"]):
        posts.append({
            "k": f'{r["menu_no"]}:{r["bno"]}',
            "m": r["menu_no"],
            "n": r["bno"],
            "t": r["title"] or "",
            "a": r["author"] or "",
            "d": r["posted_date"] or "",
            "at": r["posted_at"] or r["posted_date"] or "",
            "v": r["views"],
            "nt": bool(r["is_notice"]),
            "u": r["url"] or "",
            "x": (r["content_text"] or "")[:4000],
            "bname": site["boards"].get(r["menu_no"], {}).get("name", str(r["menu_no"])),
            "im": [base + u if u.startswith("/") else u
                   for u in json.loads(r["images_json"] or "[]")],
        })
    for a in store.conn.execute(
            "SELECT menu_no,bno,filename,url,ext,size_bytes,local_path,status "
            "FROM attachments WHERE site_key=? ORDER BY menu_no,bno", (site["key"],)).fetchall():
        atts.setdefault(f'{a["menu_no"]}:{a["bno"]}', []).append(
            {"filename": a["filename"], "url": base + (a["url"] or ""), "ext": a["ext"],
             "size": a["size_bytes"], "local": a["local_path"] or "", "status": a["status"]})

    counts: dict[int, int] = {}
    latest: dict[int, str] = {}
    for row in store.conn.execute(
            "SELECT menu_no, COUNT(*) c, MAX(posted_date) mx FROM posts WHERE site_key=? "
            "GROUP BY menu_no", (site["key"],)):
        counts[row["menu_no"]] = row["c"]
        latest[row["menu_no"]] = row["mx"] or ""
    boards = [{"no": m, "name": site["boards"][m]["name"],
               "kind": site["boards"][m].get("kind", "board"),
               "count": counts.get(m, 0), "latest": latest.get(m, "")}
              for m in sorted(site["boards"])]

    links = " · ".join(f'<a href="{f}">{f}</a>' for f in
                       ("posts.json", "attachments.csv", "summary.json"))
    html = _fill(
        VIEWER_TEMPLATE,
        TITLE=htmllib.escape(site["name"]),
        TITLE_EN=htmllib.escape(site.get("name_en", "")),
        BASE_URL=htmllib.escape(base),
        GENERATED=htmllib.escape(generated or "-"),
        NOTE=(f'withschool(w.cms) 기반 게시판 아카이브. 수집 시각 {htmllib.escape(generated or "-")} · '
              f'첨부 파일은 robots.txt 정책에 따라 목록만 기록되고 실제 파일은 원 사이트에서 받습니다.'),
        EXPORT_LINKS=links,
        POSTS=_js(posts),
        ATTS=_js(atts),
        BOARDS=_js(boards),
        STATS=_js({"posts": 0, "attachments": 0, "boards": 0, "span": "", "latest": ""}),
        JS_TITLE=_js(site["name"]),
        JS_TITLE_EN=_js(site.get("name_en", "")),
        JS_BASE_URL=_js(base),
    )
    target = out / "index.html"
    target.write_text(html, encoding="utf-8")
    return str(target)
