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
    --paper:#f5f4f0; --panel:#fff; --panel-2:#eceae4;
    --ink:#191a1c; --ink-2:#54585f; --ink-3:#8b8f97;
    --rule:#dedcd5; --rule-soft:#eae8e2;
    --accent:#9b3d1e; --mark:#f2e3cb;
    --mono:ui-monospace,"Cascadia Mono","Consolas","Liberation Mono",monospace;
    --sans:-apple-system,BlinkMacSystemFont,"Segoe UI","Malgun Gothic","Apple SD Gothic Neo","Noto Sans KR",sans-serif;
    --barh:56px;
  }
  *{box-sizing:border-box}
  html{-webkit-text-size-adjust:100%}
  body{margin:0;background:var(--panel);color:var(--ink);
       font:14px/1.6 var(--sans);-webkit-font-smoothing:antialiased}
  a{color:var(--accent);text-decoration:none;border-bottom:1px solid #ddc2b6}
  a:hover{border-bottom-color:var(--accent)}
  :focus-visible{outline:2px solid var(--accent);outline-offset:2px;border-radius:2px}

  .app{display:grid;grid-template-columns:286px minmax(0,1fr);min-height:100vh}

  /* ── 좌측 패널 ─────────────────────────────────────────── */
  aside{background:var(--paper);border-right:1px solid var(--rule);
        padding:26px 22px 34px;position:sticky;top:0;height:100vh;overflow:auto}
  aside h1{margin:0 0 2px;font-size:15px;font-weight:650;letter-spacing:-.01em}
  .ename{margin:0 0 3px;font-size:11.5px;color:var(--ink-3)}
  .src{font-size:11.5px}
  .stats{margin:20px 0 0;border-top:1px solid var(--rule)}
  .stats div{display:flex;justify-content:space-between;align-items:baseline;
             gap:10px;padding:6px 0;border-bottom:1px solid var(--rule-soft);font-size:12.5px}
  .stats span{color:var(--ink-2)}
  .stats b{font:12px/1 var(--mono);font-variant-numeric:tabular-nums;font-weight:600}
  .nav{margin:24px 0 0}
  .nav h2{margin:0 0 7px;font-size:10.5px;font-weight:600;letter-spacing:.08em;
          color:var(--ink-3);text-transform:uppercase}
  .nav button{display:flex;width:100%;align-items:baseline;gap:8px;text-align:left;
              background:none;border:0;border-left:2px solid transparent;padding:6px 8px 6px 9px;
              font:inherit;font-size:13px;color:var(--ink-2);cursor:pointer;border-radius:0}
  .nav button:hover{background:var(--panel-2);color:var(--ink)}
  .nav button[aria-current=true]{background:var(--panel-2);color:var(--ink);
              font-weight:600;border-left-color:var(--accent)}
  .nav .n{margin-left:auto;font:11px/1.4 var(--mono);color:var(--ink-3);
          font-variant-numeric:tabular-nums}
  .note{margin:26px 0 0;padding:12px 0 0;border-top:1px solid var(--rule);
        font-size:11px;line-height:1.6;color:var(--ink-3)}

  /* ── 본문 ──────────────────────────────────────────────── */
  main{min-width:0;display:flex;flex-direction:column;background:var(--panel)}
  .bar{position:sticky;top:0;z-index:6;display:flex;flex-wrap:wrap;align-items:center;gap:10px;
       padding:12px 24px;background:var(--panel);border-bottom:1px solid var(--rule)}
  input[type=search],select{padding:7px 10px;border:1px solid var(--rule);border-radius:3px;
       background:var(--paper);font:inherit;font-size:13px;color:var(--ink);max-width:100%}
  input[type=search]{flex:1 1 240px;min-width:160px;max-width:420px}
  input[type=search]::placeholder{color:var(--ink-3)}
  select{cursor:pointer}
  .chk{display:inline-flex;align-items:center;gap:6px;font-size:12.5px;color:var(--ink-2);cursor:pointer}
  .chk input{accent-color:var(--accent);margin:0}
  .count{margin-left:auto;font:11.5px/1.4 var(--mono);color:var(--ink-3);
         font-variant-numeric:tabular-nums;white-space:nowrap}

  .list{padding:0 24px 34px}
  .row{display:grid;grid-template-columns:50px 84px minmax(0,1fr) 84px 96px 54px;
       gap:0 14px;align-items:baseline;padding:10px 8px}
  .head{position:sticky;top:var(--barh);z-index:4;background:var(--panel);
        border-bottom:1px solid var(--rule);padding:9px 8px;
        font:10.5px/1.4 var(--sans);letter-spacing:.06em;color:var(--ink-3)}
  .head span:last-child,.c-views{text-align:right}
  .item{border-bottom:1px solid var(--rule-soft)}
  .post{cursor:pointer;color:inherit}
  .post:hover{background:var(--paper)}
  .post[aria-expanded=true]{background:var(--paper)}
  .c-no,.c-views{font:11.5px/1.6 var(--mono);color:var(--ink-3);font-variant-numeric:tabular-nums;
       text-align:right;white-space:nowrap}
  .c-board{font:11px/1.6 var(--mono);color:var(--ink-3);overflow:hidden;
       text-overflow:ellipsis;white-space:nowrap}
  .c-title{min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:var(--ink)}
  .c-title .nt{display:inline-block;margin-right:7px;padding:1px 5px;border:1px solid var(--rule);
       border-radius:3px;background:var(--panel-2);color:var(--ink-2);
       font:10px/1.5 var(--mono);vertical-align:1px}
  .c-title .at{display:inline-block;margin-left:7px;padding:0 4px;border:1px solid var(--rule);
       border-radius:3px;color:var(--ink-3);font:10px/1.5 var(--mono);vertical-align:1px}
  .c-title .at b{font-weight:600;color:var(--ink-2)}
  .c-who,.c-date{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;
       font-size:12.5px;color:var(--ink-2)}
  .c-date{font:11.5px/1.6 var(--mono);color:var(--ink-3);font-variant-numeric:tabular-nums}
  mark{background:var(--mark);color:inherit;padding:0 1px}

  /* ── 펼친 본문 ─────────────────────────────────────────── */
  .pane{display:none;padding:0 8px 24px 148px}
  .pane.open{display:block}
  .meta{display:flex;flex-wrap:wrap;gap:6px 16px;padding:8px 0;margin-bottom:14px;
        border-top:1px solid var(--rule-soft);border-bottom:1px solid var(--rule-soft);
        font:11.5px/1.6 var(--mono);color:var(--ink-3)}
  .meta b{font-weight:600;color:var(--ink-2)}
  .txt{white-space:pre-wrap;overflow-wrap:anywhere;max-width:74ch;margin:0 0 16px;
       font-size:13.5px;line-height:1.78;color:var(--ink)}
  .txt.none{color:var(--ink-3);font-size:12.5px}
  .thumbs{display:flex;flex-wrap:wrap;gap:8px;margin:0 0 16px}
  .thumbs a{display:block;line-height:0;border:1px solid var(--rule);border-radius:2px;overflow:hidden}
  .thumbs a:hover{border-color:var(--accent)}
  .thumbs img{display:block;max-width:230px;max-height:150px;width:auto;height:auto;background:var(--panel-2)}
  h3.sec{margin:0 0 4px;font-size:10.5px;font-weight:600;letter-spacing:.08em;
         color:var(--ink-3);text-transform:uppercase}
  ul.files{list-style:none;margin:0 0 6px;padding:0}
  ul.files li{display:flex;align-items:baseline;gap:10px;padding:5px 0;
       border-bottom:1px solid var(--rule-soft);font-size:12.5px}
  ul.files .fn{overflow-wrap:anywhere}
  ul.files .st{font:10px/1.5 var(--mono);color:var(--ink-3);border:1px solid var(--rule);
       border-radius:3px;padding:0 4px;white-space:nowrap}
  ul.files .sz{margin-left:auto;font:11px/1.6 var(--mono);color:var(--ink-3);
       font-variant-numeric:tabular-nums;white-space:nowrap}
  .more{display:block;width:100%;margin:16px 0 0;padding:10px;background:var(--paper);
       border:1px solid var(--rule);border-radius:3px;font:inherit;font-size:12.5px;
       color:var(--ink-2);cursor:pointer}
  .more:hover{background:var(--panel-2);color:var(--ink)}
  .empty{padding:64px 8px;color:var(--ink-3);font-size:13px}
  .empty b{color:var(--ink-2);font-weight:600}
  footer{padding:14px 24px;border-top:1px solid var(--rule);font-size:11.5px;
         color:var(--ink-3);display:flex;flex-wrap:wrap;gap:6px 16px}
  footer .r{margin-left:auto}

  @media (max-width:1000px){
    .app{grid-template-columns:1fr}
    aside{position:static;height:auto;border-right:0;border-bottom:1px solid var(--rule);
          padding:20px}
    .nav ul{display:flex;flex-wrap:wrap;gap:2px}
    .nav button{width:auto;border-left:0;border-bottom:2px solid transparent;padding:5px 9px}
    .nav button[aria-current=true]{border-left-color:transparent;border-bottom-color:var(--accent)}
    .note{margin-top:18px}
  }
  @media (max-width:880px){
    .row{grid-template-columns:minmax(0,1fr) 84px 94px;padding:10px 4px}
    .c-no,.c-board,.c-views{display:none}
    .head span:nth-child(1),.head span:nth-child(2),.head span:nth-child(6){display:none}
    .pane{padding-left:8px}
    .bar,.list,footer{padding-left:14px;padding-right:14px}
  }
  @media (max-width:600px){
    .row{grid-template-columns:minmax(0,1fr) 84px}
    .c-who{display:none}
    .head span:nth-child(4){display:none}
    .count{width:100%;margin-left:0}
  }
</style>
</head>
<body>
<div class="app">
  <aside>
    <h1>%%TITLE%%</h1>
    <p class="ename">%%TITLE_EN%%</p>
    <div class="src"><a href="%%BASE_URL%%" target="_blank" rel="noopener">%%BASE_URL%%</a></div>

    <div class="stats" id="stats"></div>

    <nav class="nav" id="nav">
      <h2>게시판</h2>
      <ul id="navul" style="list-style:none;margin:0;padding:0"></ul>
    </nav>

    <p class="note">%%NOTE%%</p>
  </aside>

  <main>
    <div class="bar" id="bar">
      <input type="search" id="q" placeholder="제목 · 본문 · 작성자 · 첨부 검색" autocomplete="off">
      <select id="sort" aria-label="정렬">
        <option value="date_desc">최신순</option>
        <option value="date_asc">오래된순</option>
        <option value="views_desc">조회순</option>
        <option value="board">게시판순</option>
      </select>
      <label class="chk"><input type="checkbox" id="onlyatt"> 첨부만</label>
      <span class="count" id="count"></span>
    </div>

    <div class="list">
      <div class="row head" id="head">
        <span>번호</span><span>게시판</span><span>제목</span>
        <span>작성자</span><span>작성일</span><span>조회</span>
      </div>
      <div id="rows"></div>
      <button class="more" id="more" hidden></button>
    </div>

    <footer>
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
  var rowsEl = $('rows'), moreEl = $('more'), qEl = $('q'),
      sortEl = $('sort'), attEl = $('onlyatt'), cntEl = $('count');

  var state = { board: '', kw: '', sort: 'date_desc', only: false, shown: BATCH };
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
    var box = $('stats');
    box.innerHTML = [
      ['게시글', STATS.posts], ['첨부', STATS.attachments],
      ['게시판', STATS.boards], ['기간', STATS.span]
    ].map(function (r) {
      return '<div><span>' + esc(r[0]) + '</span><b>' + esc(r[1]) + '</b></div>';
    }).join('');

    var list = document.createElement('ul');
    var mk = function (no, name, count, latest) {
      var li = document.createElement('li');
      var b = document.createElement('button');
      b.type = 'button';
      b.setAttribute('aria-current', String(state.board === no));
      b.title = latest ? latest + ' 까지' : '수집 없음';
      b.innerHTML = '<span>' + esc(name) + '</span><span class="n">' + count + '</span>';
      b.addEventListener('click', function () { setBoard(no); });
      li.appendChild(b);
      return li;
    };
    var total = POSTS.length;
    list.appendChild(mk('', '전체', total, STATS.latest));
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
    return '<div class="post row" data-k="' + esc(p.k) + '" role="button" tabindex="0" aria-expanded="false">' +
      '<div class="c-no">' + esc(p.n) + '</div>' +
      '<div class="c-board">' + esc(p.bname || '') + '</div>' +
      '<div class="c-title" title="' + esc(p.t) + '">' +
        (p.nt ? '<span class="nt">공지</span>' : '') + title + ext + '</div>' +
      '<div class="c-who">' + hl(p.a || '', kw) + '</div>' +
      '<div class="c-date">' + esc(p.d || '') + '</div>' +
      '<div class="c-views">' + (p.v == null ? '' : esc(p.v)) + '</div>' +
    '</div>' +
    '<div class="pane" data-pane="' + esc(p.k) + '"></div>';
  }

  function paneHtml(p) {
    var fs = ATTS[p.k] || [];
    var meta = [];
    if (p.at) { meta.push('<span>' + esc(p.at) + '</span>'); }
    if (p.v != null) { meta.push('<span>조회 <b>' + esc(p.v) + '</b></span>'); }
    meta.push('<span>' + esc(p.bname || '') + '</span>');
    meta.push('<a href="' + esc(localUrl(p)) + '" target="_blank" rel="noopener">원문 보기 &rarr;</a>');

    var thumbs = (p.im || []).map(function (u) {
      return '<a href="' + esc(u) + '" target="_blank" rel="noopener">' +
             '<img src="' + esc(u) + '" alt="" loading="lazy" referrerpolicy="no-referrer"></a>';
    }).join('');

    var files = fs.length
      ? '<h3 class="sec">첨부 ' + fs.length + '</h3><ul class="files">' + fs.map(function (f) {
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
      (thumbs ? '<h3 class="sec">이미지 ' + p.im.length + '</h3><div class="thumbs">' + thumbs + '</div>' : '') +
      files;
  }

  function render() {
    compute();
    var kw = state.kw;
    var n = Math.min(state.shown, view.length);
    var buf = [];
    for (var i = 0; i < n; i++) { buf.push(rowHtml(view[i], kw)); }
    rowsEl.innerHTML = buf.join('') ||
      '<div class="empty"><b>' + esc(kw || '조건') + '</b> 에 해당하는 글이 없습니다.</div>';

    cntEl.textContent = (view.length === POSTS.length
      ? POSTS.length + '건'
      : view.length + ' / ' + POSTS.length + '건');
    var rest = view.length - n;
    moreEl.hidden = rest <= 0;
    moreEl.textContent = rest > 0 ? '더 보기 — ' + n + ' / ' + view.length + '건 (' + rest + '건 남음)' : '';
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
  sortEl.addEventListener('change', function () {
    state.sort = sortEl.value;
    state.shown = BATCH;
    render();
  });
  attEl.addEventListener('change', function () {
    state.only = attEl.checked;
    state.shown = BATCH;
    render();
  });

  document.addEventListener('keydown', function (e) {
    if (e.key === '/' && document.activeElement !== qEl) { e.preventDefault(); qEl.focus(); }
    if (e.key === 'Escape' && document.activeElement === qEl) { qEl.value = ''; qEl.dispatchEvent(new Event('input')); }
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
