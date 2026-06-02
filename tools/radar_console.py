#!/usr/bin/env python3
"""
tools/radar_console.py — Radar Local Event Console pour ADA.

Serveur autonome HTTP sur 127.0.0.1:8787 (par défaut).
Ne jamais importer depuis un module web/ d'ADA.

Usage :
    python tools/radar_console.py
    python tools/radar_console.py --host 127.0.0.1 --port 8787
    python tools/radar_console.py --export events.ndjson
    python tools/radar_console.py --cleanup
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

# S'assurer que la racine du projet est dans sys.path
_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parent
sys.path.insert(0, str(_ROOT))

# ─── Import du store Radar ────────────────────────────────────────────────────
from web.radar.store import (
    count_events, export_ndjson, get_event, init_db, purge_old,
    query_events, query_events_after, latest_timestamp, stats, timeline,
)

# ─── FastAPI / Starlette ──────────────────────────────────────────────────────
from fastapi import FastAPI, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse, StreamingResponse
import uvicorn


app = FastAPI(title="Radar Local Event Console", docs_url=None, redoc_url=None)

# ─── HTML de la console (SPA autonome) ───────────────────────────────────────
_HTML = r"""<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Radar — ADA Local Event Console</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Syne:wght@400;600;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>
:root {
  --bg: #080c10; --bg1: #0d1117; --bg2: #141b24; --bg3: #1a2332;
  --cyan: #00d4ff; --green: #00e676; --orange: #ff9500; --red: #ff4444;
  --yellow: #ffd600; --text: #c8d8e8; --text2: #7a99b8; --border: #1e2f42;
  --font: 'Syne', sans-serif; --mono: 'JetBrains Mono', monospace;
}
* { box-sizing: border-box; margin: 0; padding: 0; }
html, body { height: 100%; background: var(--bg); color: var(--text); font-family: var(--font); font-size: 14px; }
#app { display: grid; grid-template-rows: 56px 1fr; height: 100vh; }

/* ── Header ── */
header { display: flex; align-items: center; gap: 16px; padding: 0 24px;
         background: var(--bg1); border-bottom: 1px solid var(--border); }
header h1 { font-size: 16px; font-weight: 700; color: var(--cyan); letter-spacing: .05em; }
.hstats { display: flex; gap: 20px; margin-left: auto; }
.hstat { display: flex; flex-direction: column; align-items: flex-end; }
.hstat-n { font-size: 18px; font-weight: 700; font-family: var(--mono); color: var(--cyan); }
.hstat-l { font-size: 10px; color: var(--text2); text-transform: uppercase; letter-spacing: .08em; }
.hstat.err .hstat-n { color: var(--red); }
#dot { width: 8px; height: 8px; border-radius: 50%; background: var(--green); animation: pulse 2s infinite; }
@keyframes pulse { 0%,100%{opacity:1} 50%{opacity:.3} }

/* ── Layout ── */
main { display: grid; grid-template-columns: 280px 1fr; overflow: hidden; }

/* ── Sidebar ── */
nav { background: var(--bg1); border-right: 1px solid var(--border); padding: 16px 12px;
      display: flex; flex-direction: column; gap: 4px; overflow-y: auto; }
.nav-section { font-size: 10px; color: var(--text2); text-transform: uppercase;
               letter-spacing: .1em; padding: 12px 8px 4px; }
.nav-btn { display: flex; align-items: center; gap: 10px; padding: 8px 12px; border-radius: 8px;
           cursor: pointer; color: var(--text2); transition: all .15s; border: none;
           background: none; font-family: var(--font); font-size: 13px; width: 100%; text-align: left; }
.nav-btn:hover { background: var(--bg2); color: var(--text); }
.nav-btn.active { background: rgba(0,212,255,.1); color: var(--cyan); }
.nav-icon { width: 16px; text-align: center; flex-shrink: 0; }

/* ── Filters ── */
.filter-bar { display: flex; gap: 8px; flex-wrap: wrap; padding: 12px 20px;
              background: var(--bg1); border-bottom: 1px solid var(--border); }
.filter-bar input, .filter-bar select { background: var(--bg2); border: 1px solid var(--border);
  color: var(--text); padding: 6px 10px; border-radius: 6px; font-family: var(--mono);
  font-size: 12px; outline: none; transition: border .15s; }
.filter-bar input:focus, .filter-bar select:focus { border-color: var(--cyan); }
.filter-bar input { flex: 1; min-width: 160px; }
.btn { padding: 6px 14px; border-radius: 6px; border: none; cursor: pointer;
       font-family: var(--font); font-size: 12px; font-weight: 600; transition: all .15s; }
.btn-cyan { background: rgba(0,212,255,.15); color: var(--cyan); border: 1px solid rgba(0,212,255,.3); }
.btn-cyan:hover { background: rgba(0,212,255,.25); }
.btn-red { background: rgba(255,68,68,.15); color: var(--red); border: 1px solid rgba(255,68,68,.3); }
.btn-sm { padding: 4px 10px; font-size: 11px; }

/* ── Events panel ── */
#content { display: flex; flex-direction: column; overflow: hidden; }
#events-list { flex: 1; overflow-y: auto; padding: 0 20px 20px; }
.event-row { display: grid; grid-template-columns: 90px 64px 220px 1fr 80px;
             gap: 12px; align-items: center; padding: 10px 14px; border-radius: 8px;
             cursor: pointer; transition: background .1s; border-bottom: 1px solid rgba(30,47,66,.5); }
.event-row:hover { background: var(--bg2); }
.event-ts { font-family: var(--mono); font-size: 11px; color: var(--text2); }
.event-level { font-family: var(--mono); font-size: 11px; font-weight: 600;
               padding: 2px 8px; border-radius: 4px; text-align: center; }
.lvl-debug   { color: var(--text2); background: rgba(122,153,184,.1); }
.lvl-info    { color: var(--cyan);  background: rgba(0,212,255,.1); }
.lvl-warning { color: var(--yellow); background: rgba(255,214,0,.1); }
.lvl-error   { color: var(--red);   background: rgba(255,68,68,.15); }
.lvl-critical{ color: #fff;         background: var(--red); }
.event-type { font-family: var(--mono); font-size: 12px; color: var(--text); }
.event-msg  { font-size: 12px; color: var(--text2); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.event-dur  { font-family: var(--mono); font-size: 11px; color: var(--text2); text-align: right; }

/* ── Pagination ── */
.pagination { display: flex; gap: 8px; align-items: center; padding: 12px 20px;
              border-top: 1px solid var(--border); background: var(--bg1); justify-content: center; }
.pagination span { font-size: 12px; color: var(--text2); font-family: var(--mono); }

/* ── Detail panel ── */
#detail-panel { position: fixed; right: 0; top: 56px; bottom: 0; width: 480px;
                background: var(--bg1); border-left: 1px solid var(--border);
                overflow-y: auto; padding: 20px; transform: translateX(100%);
                transition: transform .2s ease; z-index: 100; }
#detail-panel.open { transform: translateX(0); }
#detail-panel h2 { font-size: 14px; color: var(--cyan); margin-bottom: 16px; }
.detail-close { float: right; cursor: pointer; color: var(--text2); font-size: 20px;
                background: none; border: none; color: var(--text2); }
.detail-field { margin-bottom: 12px; }
.detail-label { font-size: 10px; color: var(--text2); text-transform: uppercase;
                letter-spacing: .1em; margin-bottom: 4px; }
.detail-value { font-family: var(--mono); font-size: 12px; color: var(--text);
                background: var(--bg2); padding: 8px 12px; border-radius: 6px;
                word-break: break-all; white-space: pre-wrap; }
.detail-json { background: var(--bg2); border: 1px solid var(--border); border-radius: 6px;
               padding: 12px; font-family: var(--mono); font-size: 11px; color: var(--green);
               white-space: pre; overflow-x: auto; max-height: 300px; overflow-y: auto; }
.badge { display: inline-block; padding: 1px 6px; border-radius: 4px; font-size: 10px;
         font-family: var(--mono); font-weight: 600; }

/* ── Timeline ── */
.timeline { padding: 16px 0; }
.tl-item { display: flex; gap: 12px; margin-bottom: 0; position: relative; }
.tl-item::before { content:''; position: absolute; left: 27px; top: 32px; bottom: -12px;
                   width: 2px; background: var(--border); }
.tl-item:last-child::before { display: none; }
.tl-dot { width: 16px; height: 16px; border-radius: 50%; margin-top: 10px; flex-shrink: 0;
          border: 2px solid; }
.tl-dot-info { border-color: var(--cyan); background: rgba(0,212,255,.2); }
.tl-dot-error { border-color: var(--red); background: rgba(255,68,68,.2); }
.tl-dot-warning { border-color: var(--yellow); background: rgba(255,214,0,.2); }
.tl-content { flex: 1; background: var(--bg2); border-radius: 8px; padding: 10px 14px;
              margin-bottom: 16px; cursor: pointer; transition: background .1s; }
.tl-content:hover { background: var(--bg3); }
.tl-type { font-family: var(--mono); font-size: 12px; color: var(--cyan); }
.tl-msg  { font-size: 12px; color: var(--text2); margin-top: 2px; }
.tl-meta { display: flex; gap: 12px; margin-top: 6px; }
.tl-meta-item { font-family: var(--mono); font-size: 10px; color: var(--text2); }

/* ── Réaltime banner ── */
#realtime-bar { padding: 6px 20px; background: rgba(0,230,118,.05);
                border-bottom: 1px solid rgba(0,230,118,.2);
                font-size: 11px; color: var(--green); font-family: var(--mono);
                display: none; }
#realtime-bar.active { display: block; }

/* ── Live feed ── */
#live-feed { display: none; flex-direction: column; gap: 4px; padding: 12px 20px; }
#live-feed.active { display: flex; }
.live-item { padding: 6px 12px; background: var(--bg2); border-radius: 6px;
             border-left: 3px solid var(--cyan); animation: slidein .2s ease; }
@keyframes slidein { from { opacity: 0; transform: translateY(-8px); } to { opacity: 1; } }
.live-item.err { border-left-color: var(--red); }

/* ── Empty/loading ── */
.empty { text-align: center; padding: 48px; color: var(--text2); font-size: 13px; }
.loading { text-align: center; padding: 48px; color: var(--cyan); font-family: var(--mono); }
</style>
</head>
<body>
<div id="app">
<header>
  <div id="dot"></div>
  <h1>⚡ Radar — ADA Event Console</h1>
  <div class="hstats">
    <div class="hstat"><span class="hstat-n" id="h-total">—</span><span class="hstat-l">Événements</span></div>
    <div class="hstat err"><span class="hstat-n" id="h-errors">—</span><span class="hstat-l">Erreurs</span></div>
    <div class="hstat"><span class="hstat-n" id="h-last" style="font-size:12px;color:var(--text2)">—</span><span class="hstat-l">Dernier</span></div>
  </div>
</header>
<main>
<nav>
  <div class="nav-section">Vues</div>
  <button class="nav-btn active" data-view="stream" onclick="switchView('stream',this)">
    <span class="nav-icon">📡</span> Temps réel
  </button>
  <button class="nav-btn" data-view="history" onclick="switchView('history',this)">
    <span class="nav-icon">📋</span> Historique
  </button>
  <button class="nav-btn" data-view="errors" onclick="switchView('errors',this)">
    <span class="nav-icon">🔴</span> Erreurs
  </button>
  <div class="nav-section">Timelines</div>
  <button class="nav-btn" data-view="req" onclick="showTimelineInput('request_id')">
    <span class="nav-icon">🔁</span> Requête
  </button>
  <button class="nav-btn" data-view="doc" onclick="showTimelineInput('document_id')">
    <span class="nav-icon">📄</span> Document
  </button>
  <button class="nav-btn" data-view="job" onclick="showTimelineInput('job_id')">
    <span class="nav-icon">⚙️</span> Job
  </button>
  <div class="nav-section">Export</div>
  <button class="nav-btn" onclick="exportNDJSON()">
    <span class="nav-icon">⬇️</span> Export NDJSON
  </button>
</nav>
<div id="content">
  <div id="realtime-bar">🟢 SSE connecté — flux temps réel actif</div>

  <!-- Vue temps réel -->
  <div id="view-stream">
    <div style="padding:10px 20px 0;font-size:12px;color:var(--text2)">Les 50 derniers événements + flux temps réel</div>
    <div id="live-feed" class="active"></div>
  </div>

  <!-- Vue historique + erreurs + timeline -->
  <div id="view-history" style="display:none;flex-direction:column;height:100%">
    <div class="filter-bar">
      <input id="f-q" placeholder="Recherche…" oninput="debounceLoad()">
      <select id="f-level" onchange="loadEvents()">
        <option value="">Tous niveaux</option>
        <option>debug</option><option>info</option>
        <option>warning</option><option>error</option><option>critical</option>
      </select>
      <input id="f-type" placeholder="Type ex: rag.search.*" style="max-width:180px" oninput="debounceLoad()">
      <input id="f-module" placeholder="Module" style="max-width:140px" oninput="debounceLoad()">
      <input id="f-req" placeholder="request_id" style="max-width:160px" oninput="debounceLoad()">
      <input id="f-doc" placeholder="document_id" style="max-width:160px" oninput="debounceLoad()">
      <button class="btn btn-cyan btn-sm" onclick="loadEvents()">Filtrer</button>
    </div>
    <div id="events-list"><div class="loading">Chargement…</div></div>
    <div class="pagination">
      <button class="btn btn-cyan btn-sm" id="btn-prev" onclick="prevPage()" disabled>← Préc</button>
      <span id="page-info">Page 1</span>
      <button class="btn btn-cyan btn-sm" id="btn-next" onclick="nextPage()">Suiv →</button>
    </div>
  </div>

  <!-- Timeline panel -->
  <div id="view-timeline" style="display:none;flex-direction:column;height:100%">
    <div class="filter-bar" id="tl-filter-bar">
      <input id="tl-id-input" placeholder="Entrez l'identifiant…" style="flex:1">
      <button class="btn btn-cyan btn-sm" onclick="loadTimeline()">Voir timeline</button>
    </div>
    <div id="timeline-content" style="flex:1;overflow-y:auto;padding:16px 20px">
      <div class="empty">Entrez un identifiant ci-dessus</div>
    </div>
  </div>
</div>
</main>
</div>

<!-- Panneau détail -->
<div id="detail-panel">
  <button class="detail-close" onclick="closeDetail()">✕</button>
  <h2>Détail événement</h2>
  <div id="detail-content"></div>
</div>

<script>
let _page = 0;
const _limit = 50;
let _currentView = 'stream';
let _tlField = 'request_id';
let _sse = null;
let _liveItems = [];
let _debounceTimer = null;

// ── Stats ──────────────────────────────────────────────────────────────────
async function refreshStats() {
  try {
    const s = await fetch('/api/stats').then(r=>r.json());
    document.getElementById('h-total').textContent = s.total ?? '—';
    document.getElementById('h-errors').textContent = s.errors ?? '—';
    const last = s.last_event;
    document.getElementById('h-last').textContent = last ? last.slice(11,19) : '—';
  } catch(e){}
}

// ── SSE ───────────────────────────────────────────────────────────────────
function startSSE() {
  if (_sse) return;
  _sse = new EventSource('/sse/events');
  _sse.onopen = () => {
    document.getElementById('realtime-bar').classList.add('active');
    document.getElementById('dot').style.background = 'var(--green)';
  };
  _sse.onmessage = (e) => {
    try {
      const evt = JSON.parse(e.data);
      if (_currentView === 'stream') prependLiveItem(evt);
      refreshStats();
    } catch(err) {}
  };
  _sse.onerror = () => {
    document.getElementById('realtime-bar').classList.remove('active');
    document.getElementById('dot').style.background = 'var(--red)';
    _sse.close(); _sse = null;
    setTimeout(startSSE, 3000);
  };
}

function prependLiveItem(evt) {
  const feed = document.getElementById('live-feed');
  const div = document.createElement('div');
  div.className = 'live-item' + (evt.level === 'error' || evt.level === 'critical' ? ' err' : '');
  div.innerHTML = `<span style="color:var(--text2);font-family:var(--mono);font-size:11px">${(evt.timestamp||'').slice(11,19)}</span>
    <span class="badge lvl-${evt.level}" style="margin:0 8px">${evt.level}</span>
    <span style="font-family:var(--mono);font-size:12px;color:var(--cyan)">${evt.type}</span>
    <span style="font-size:12px;color:var(--text2);margin-left:10px">${evt.message||''}</span>`;
  div.onclick = () => openDetail(evt);
  feed.insertBefore(div, feed.firstChild);
  _liveItems.unshift(div);
  if (_liveItems.length > 100) {
    const old = _liveItems.pop();
    if (old && old.parentNode) old.parentNode.removeChild(old);
  }
}

// ── Views ─────────────────────────────────────────────────────────────────
function switchView(view, btn) {
  _currentView = view;
  document.querySelectorAll('.nav-btn').forEach(b => b.classList.remove('active'));
  if (btn) btn.classList.add('active');
  document.getElementById('view-stream').style.display = view === 'stream' ? 'block' : 'none';
  document.getElementById('view-history').style.display = view === 'history' || view === 'errors' ? 'flex' : 'none';
  document.getElementById('view-timeline').style.display = view === 'timeline' ? 'flex' : 'none';
  if (view === 'history') { document.getElementById('f-level').value = ''; _page = 0; loadEvents(); }
  if (view === 'errors')  { document.getElementById('f-level').value = 'error'; _page = 0; loadEvents(); }
}

function showTimelineInput(field) {
  _tlField = field;
  _currentView = 'timeline';
  document.querySelectorAll('.nav-btn').forEach(b => b.classList.remove('active'));
  document.getElementById('view-stream').style.display = 'none';
  document.getElementById('view-history').style.display = 'none';
  document.getElementById('view-timeline').style.display = 'flex';
  const labels = {request_id: 'request_id', document_id: 'document_id', job_id: 'job_id'};
  document.getElementById('tl-id-input').placeholder = `Entrez le ${labels[field]}…`;
  document.getElementById('timeline-content').innerHTML = '<div class="empty">Entrez un identifiant ci-dessus</div>';
}

// ── Events list ───────────────────────────────────────────────────────────
function debounceLoad() {
  clearTimeout(_debounceTimer);
  _debounceTimer = setTimeout(() => { _page = 0; loadEvents(); }, 350);
}

async function loadEvents() {
  const list = document.getElementById('events-list');
  list.innerHTML = '<div class="loading">Chargement…</div>';
  const p = new URLSearchParams({
    limit: _limit, offset: _page * _limit,
    q: document.getElementById('f-q')?.value || '',
    level: document.getElementById('f-level')?.value || '',
    type: document.getElementById('f-type')?.value || '',
    module: document.getElementById('f-module')?.value || '',
    request_id: document.getElementById('f-req')?.value || '',
    document_id: document.getElementById('f-doc')?.value || '',
  });
  // Nettoyer les vides
  for (const [k,v] of [...p.entries()]) if (!v) p.delete(k);
  try {
    const evts = await fetch('/api/events?' + p).then(r => r.json());
    renderEventsList(evts, list);
    document.getElementById('btn-prev').disabled = _page === 0;
    document.getElementById('btn-next').disabled = evts.length < _limit;
    document.getElementById('page-info').textContent = `Page ${_page + 1}`;
  } catch(e) {
    list.innerHTML = '<div class="empty">Erreur de chargement</div>';
  }
}

function renderEventsList(evts, container) {
  if (!evts.length) { container.innerHTML = '<div class="empty">Aucun événement</div>'; return; }
  container.innerHTML = evts.map(e => `
    <div class="event-row" onclick='openDetail(${JSON.stringify(e).replace(/'/g,"\\'")})'  >
      <span class="event-ts">${(e.timestamp||'').slice(11,19)}</span>
      <span class="event-level lvl-${e.level}">${e.level}</span>
      <span class="event-type">${e.type}</span>
      <span class="event-msg">${e.message||''}</span>
      <span class="event-dur">${e.duration_ms != null ? e.duration_ms+'ms' : ''}</span>
    </div>`).join('');
}

function prevPage() { if (_page > 0) { _page--; loadEvents(); } }
function nextPage() { _page++; loadEvents(); }

// ── Timeline ──────────────────────────────────────────────────────────────
async function loadTimeline() {
  const id = document.getElementById('tl-id-input').value.trim();
  if (!id) return;
  const cont = document.getElementById('timeline-content');
  cont.innerHTML = '<div class="loading">Chargement…</div>';
  try {
    const evts = await fetch(`/api/timeline/${_tlField}/${encodeURIComponent(id)}`).then(r => r.json());
    if (!evts.length) { cont.innerHTML = '<div class="empty">Aucun événement pour cet identifiant</div>'; return; }
    const total_ms = evts.length > 1
      ? new Date(evts[evts.length-1].timestamp) - new Date(evts[0].timestamp)
      : null;
    cont.innerHTML = `
      <div style="margin-bottom:12px;font-size:12px;color:var(--text2)">
        ${evts.length} événements${total_ms != null ? ` · durée totale <b style="color:var(--cyan)">${total_ms}ms</b>` : ''}
      </div>
      <div class="timeline">
        ${evts.map(e => `
          <div class="tl-item" onclick='openDetail(${JSON.stringify(e).replace(/'/g,"\\'")})'>
            <div class="tl-dot tl-dot-${e.level === 'error' || e.level === 'critical' ? 'error' : e.level === 'warning' ? 'warning' : 'info'}"></div>
            <div class="tl-content">
              <div class="tl-type">${e.type}</div>
              <div class="tl-msg">${e.message||''}</div>
              <div class="tl-meta">
                <span class="tl-meta-item">${(e.timestamp||'').slice(11,23)}</span>
                ${e.duration_ms != null ? `<span class="tl-meta-item" style="color:var(--cyan)">${e.duration_ms}ms</span>` : ''}
                ${e.error_code ? `<span class="tl-meta-item" style="color:var(--red)">${e.error_code}</span>` : ''}
              </div>
            </div>
          </div>`).join('')}
      </div>`;
  } catch(e) {
    cont.innerHTML = '<div class="empty">Erreur de chargement</div>';
  }
}

// ── Detail ────────────────────────────────────────────────────────────────
function openDetail(evt) {
  const panel = document.getElementById('detail-panel');
  const cont = document.getElementById('detail-content');
  const fields = [
    ['ID', evt.id], ['Timestamp', evt.timestamp], ['Level', `<span class="badge lvl-${evt.level}">${evt.level}</span>`],
    ['Type', evt.type], ['Module', evt.module], ['Message', evt.message],
    ['Request ID', evt.request_id], ['Document ID', evt.document_id],
    ['Job ID', evt.job_id], ['Session ID', evt.session_id],
    ['Durée', evt.duration_ms != null ? evt.duration_ms + ' ms' : null],
    ['Error Code', evt.error_code],
  ];
  cont.innerHTML = fields.filter(([,v]) => v).map(([l,v]) => `
    <div class="detail-field">
      <div class="detail-label">${l}</div>
      <div class="detail-value">${v}</div>
    </div>`).join('') +
    (evt.metadata && Object.keys(evt.metadata).length ? `
    <div class="detail-field">
      <div class="detail-label">Métadonnées</div>
      <div class="detail-json">${JSON.stringify(evt.metadata, null, 2)}</div>
    </div>` : '') +
    (evt.exception_info && Object.keys(evt.exception_info).length ? `
    <div class="detail-field">
      <div class="detail-label">Exception</div>
      <div class="detail-json" style="color:var(--red)">${JSON.stringify(evt.exception_info, null, 2)}</div>
    </div>` : '');
  panel.classList.add('open');
}

function closeDetail() {
  document.getElementById('detail-panel').classList.remove('open');
}

// ── Export ────────────────────────────────────────────────────────────────
function exportNDJSON() {
  window.open('/api/export?format=ndjson', '_blank');
}

// ── Init ──────────────────────────────────────────────────────────────────
refreshStats();
setInterval(refreshStats, 10000);
startSSE();

// Charger les derniers évts dans le flux initial
fetch('/api/events?limit=50').then(r=>r.json()).then(evts => {
  evts.slice().reverse().forEach(e => prependLiveItem(e));
}).catch(()=>{});
</script>
</body>
</html>
"""


# ─── Routes API ───────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def index():
    return _HTML


@app.get("/api/health")
async def health():
    try:
        s = stats()
        return {"status": "ok", "service": "radar-local-console", "event_store": "ok", **s}
    except Exception as e:
        return JSONResponse({"status": "error", "detail": str(e)}, status_code=500)


@app.get("/api/stats")
async def get_stats():
    return stats()


@app.get("/api/events")
async def list_events(
    level: str | None = None,
    type: str | None = None,
    module: str | None = None,
    request_id: str | None = None,
    document_id: str | None = None,
    job_id: str | None = None,
    session_id: str | None = None,
    from_ts: str | None = None,
    to_ts: str | None = None,
    q: str | None = None,
    limit: int = Query(50, le=200),
    offset: int = 0,
):
    return query_events(
        level=level, type_=type, module=module,
        request_id=request_id, document_id=document_id,
        job_id=job_id, session_id=session_id,
        from_ts=from_ts, to_ts=to_ts,
        q=q, limit=limit, offset=offset,
    )


@app.get("/api/events/{event_id}")
async def get_event_by_id(event_id: str):
    evt = get_event(event_id)
    if evt is None:
        return JSONResponse({"error": "not found"}, status_code=404)
    return evt


@app.get("/api/timeline/{field}/{value}")
async def get_timeline(field: str, value: str):
    if field not in ("request_id", "document_id", "job_id", "session_id"):
        return JSONResponse({"error": "field must be request_id|document_id|job_id|session_id"}, status_code=400)
    return timeline(field, value)


@app.get("/api/errors")
async def list_errors(limit: int = Query(100, le=500)):
    return query_events(level="error", limit=limit // 2, offset=0) + \
           query_events(level="critical", limit=limit // 2, offset=0)


@app.get("/api/export")
async def export_events(format: str = "ndjson", limit: int = 10_000):
    if format == "ndjson":
        data = export_ndjson(limit=limit)
        return PlainTextResponse(data, media_type="application/x-ndjson",
                                  headers={"Content-Disposition": "attachment; filename=radar_events.ndjson"})
    # JSON
    rows = query_events(limit=limit)
    return JSONResponse(rows, headers={"Content-Disposition": "attachment; filename=radar_events.json"})


# ─── SSE temps réel (polling SQLite — inter-processus) ──────────────────────

@app.get("/sse/events")
async def sse_events(since: str | None = None):
    """Flux SSE par polling SQLite (1,5 s). Fonctionne inter-processus."""
    last_ts = since or latest_timestamp()

    async def event_stream():
        nonlocal last_ts
        yield 'data: {"type":"radar.connected"}\n\n'
        try:
            while True:
                try:
                    new_events = query_events_after(last_ts, limit=50)
                    for evt in new_events:
                        yield f"data: {json.dumps(evt, ensure_ascii=False)}\n\n"
                        last_ts = evt["timestamp"]
                except Exception:
                    pass
                yield ": keepalive\n\n"
                await asyncio.sleep(1.5)
        except asyncio.CancelledError:
            pass

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ─── CLI ──────────────────────────────────────────────────────────────────────

def _parse_args():
    p = argparse.ArgumentParser(description="Radar Local Event Console pour ADA")
    p.add_argument("--host", default="127.0.0.1",
                   help="Adresse d'écoute (défaut: 127.0.0.1)")
    p.add_argument("--port", type=int, default=8787,
                   help="Port d'écoute (défaut: 8787)")
    p.add_argument("--db", default=None,
                   help="Chemin de la base SQLite (défaut: depuis config.py)")
    p.add_argument("--export", metavar="FILE",
                   help="Exporte les événements en NDJSON vers FILE et quitte")
    p.add_argument("--cleanup", action="store_true",
                   help="Purge les événements anciens et quitte")
    p.add_argument("--allow-network-access", action="store_true",
                   help="⚠️  Autorise un bind sur 0.0.0.0 (non recommandé)")
    return p.parse_args()


def main():
    args = _parse_args()

    # Override DB path si fourni
    if args.db:
        import web.radar.store as _store
        _store._db_path = Path(args.db)

    # Initialisation du schéma
    init_db()

    # --export
    if args.export:
        data = export_ndjson(limit=100_000)
        Path(args.export).write_text(data, encoding="utf-8")
        print(f"[Radar] Export terminé → {args.export}")
        return

    # --cleanup
    if args.cleanup:
        try:
            from config import RADAR_RETENTION_DAYS, RADAR_MAX_EVENTS
            removed = purge_old(RADAR_RETENTION_DAYS, RADAR_MAX_EVENTS)
        except Exception:
            removed = purge_old()
        print(f"[Radar] Nettoyage terminé — {removed} événements supprimés")
        return

    # Sécurité réseau
    host = args.host
    if args.allow_network_access and host == "127.0.0.1":
        host = "0.0.0.0"
    if host == "0.0.0.0":
        print(
            "\n⚠️  AVERTISSEMENT : Radar est exposé sur 0.0.0.0."
            "\n   Les événements internes d'ADA seront accessibles sur le réseau local."
            "\n   N'utilisez cette option qu'en environnement de confiance.\n"
        )

    print(f"[Radar] Console démarrée → http://{host}:{args.port}")
    print("[Radar] Ctrl+C pour arrêter")
    uvicorn.run(app, host=host, port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
