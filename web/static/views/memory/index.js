/* ================================================================
   Vue Mémoire sémantique — mount / unmount
   ================================================================ */
import { showToast } from '/static/core/core.js';

const _CSS = '/static/views/memory/style.css';

function _ensureCSS() {
  if (!document.getElementById('css-memory')) {
    const l = document.createElement('link');
    l.id = 'css-memory'; l.rel = 'stylesheet'; l.href = _CSS;
    document.head.appendChild(l);
  }
}

// ── État du module ──────────────────────────────────────────────
let _root    = null;
let _sheet   = null;
let _overlay = null;
let _results = [];
let _currentId = null;

// ── Rendu liste ─────────────────────────────────────────────────
function _escHtml(s) {
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

function _renderList(root, mode) {
  const countEl = root.querySelector('#mem-count');
  const listEl  = root.querySelector('#mem-list');
  countEl.textContent = `${_results.length} souvenir(s) ${mode}`;
  if (!_results.length) {
    listEl.innerHTML = '<div class="mem-empty">Aucun souvenir trouvé</div>';
    return;
  }
  listEl.innerHTML = '';
  for (const m of _results) {
    const isUser  = m.role === 'user';
    const snippet = m.content.replace(/\n/g, ' ').slice(0, 80);
    const div = document.createElement('div');
    div.className = `mem-item${isUser ? '' : ' role-ada'}`;
    div.dataset.id = m.id;
    div.innerHTML = `
      <div class="mem-item-icon">${isUser ? '👤' : '🤖'}</div>
      <div class="mem-item-body">
        <div class="mem-item-ts">${_escHtml(m.ts_fmt)}</div>
        <div class="mem-item-snippet">${_escHtml(snippet)}</div>
      </div>`;
    div.addEventListener('click', () => _openSheet(m.id));
    listEl.appendChild(div);
  }
}

// ── Chargement données ──────────────────────────────────────────
async function _refreshStats(root) {
  try {
    const d = await (await fetch('/api/memory/stats')).json();
    root.querySelector('#mem-stats').textContent =
      `${d.total ?? 0} souvenirs · ${d.sessions ?? 0} sessions · ${d.consolidated ?? 0} consolidation(s)`;
  } catch { root.querySelector('#mem-stats').textContent = 'Erreur'; }
}

async function _refreshConsolidated(root) {
  try {
    const items = await (await fetch('/api/memory/consolidated?days=5')).json();
    const el = root.querySelector('#mem-consolidated-text');
    if (!items.length) { el.textContent = 'Aucune consolidation — lance la première manuellement.'; return; }
    const lines = [];
    for (const c of items.slice(0, 3)) {
      const facts = (c.facts || []).slice(0, 2).join(' · ');
      lines.push(`📅 ${c.date} (${c.raw_count} échanges) — ${c.summary.slice(0, 120)}`);
      if (facts) lines.push(`   Faits : ${facts}`);
    }
    el.textContent = lines.join('\n');
  } catch { /* ignore */ }
}

async function _loadRecent(root) {
  root.querySelector('#mem-count').textContent = 'Chargement…';
  root.querySelector('#mem-list').innerHTML = '';
  try {
    const r = await fetch('/api/memory/recent?limit=50');
    _results = await r.json();
    _renderList(root, 'récents');
  } catch {
    root.querySelector('#mem-list').innerHTML = '<div class="mem-empty">Erreur de chargement</div>';
  }
}

async function _search(root, query) {
  root.querySelector('#mem-count').textContent = 'Recherche…';
  root.querySelector('#mem-list').innerHTML = '';
  try {
    const r = await fetch('/api/memory/search', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ query }),
    });
    _results = await r.json();
    _renderList(root, query.trim() ? 'trouvés' : 'récents');
  } catch {
    root.querySelector('#mem-list').innerHTML = '<div class="mem-empty">Erreur de recherche</div>';
  }
}

// ── Bottom sheet ────────────────────────────────────────────────
function _openSheet(id) {
  const m = _results.find((x) => x.id === id);
  if (!m || !_sheet) return;
  _currentId = id;

  const isUser = m.role === 'user';
  const date = new Date(m.timestamp * 1000).toLocaleString('fr-FR', {
    weekday: 'short', day: '2-digit', month: 'short',
    hour: '2-digit', minute: '2-digit',
  });
  _sheet.querySelector('#mem-sheet-meta').textContent =
    `${isUser ? 'Toi' : 'ADA'}  ·  ${date}  ·  session ${(m.session_id || '').slice(0, 8)}…`;
  _sheet.querySelector('#mem-sheet-content').textContent = m.content;

  _sheet.classList.add('open');
  _overlay.classList.add('open');
}

function _closeSheet() {
  _sheet?.classList.remove('open');
  _overlay?.classList.remove('open');
  _currentId = null;
}

// ── Mount ───────────────────────────────────────────────────────
export async function mount(vp) {
  _ensureCSS();

  _root = document.createElement('div');
  _root.className = 'view-root mem-view';
  _root.innerHTML = `
    <div class="mem-header">
      <div>
        <div class="mem-title">Mémoire sémantique</div>
        <div class="mem-stats" id="mem-stats">…</div>
      </div>
      <button class="mem-consolidate-btn" id="mem-consolidate-btn">
        <svg viewBox="0 0 24 24" width="16" height="16"><path d="M17.65 6.35C16.2 4.9 14.21 4 12 4c-4.42 0-7.99 3.58-7.99 8s3.57 8 7.99 8c3.73 0 6.84-2.55 7.73-6h-2.08c-.82 2.33-3.04 4-5.65 4-3.31 0-6-2.69-6-6s2.69-6 6-6c1.66 0 3.14.69 4.22 1.78L13 11h7V4l-2.35 2.35z" fill="currentColor"/></svg>
        Consolider
      </button>
    </div>

    <div class="mem-consolidated-banner">
      <div class="mem-consolidated-title">🧠 Mémoire consolidée (résumés nuitéens)</div>
      <div class="mem-consolidated-text" id="mem-consolidated-text">Chargement…</div>
    </div>

    <div class="mem-search-bar">
      <input type="search" id="mem-search-input" class="mem-search-input"
        placeholder="Rechercher… (vide = récents)" autocomplete="off" />
      <button class="mem-btn-accent" id="mem-search-btn">Chercher</button>
      <button class="mem-btn-ghost"  id="mem-recent-btn">Récents</button>
    </div>

    <div class="mem-count" id="mem-count">—</div>
    <div class="mem-list"  id="mem-list"><div class="mem-empty">Chargement…</div></div>`;

  vp.appendChild(_root);

  // Bottom sheet (global overlay, ajouté à body)
  _overlay = document.createElement('div');
  _overlay.className = 'mem-sheet-overlay';
  _overlay.addEventListener('click', _closeSheet);

  _sheet = document.createElement('div');
  _sheet.className = 'mem-sheet';
  _sheet.innerHTML = `
    <div class="mem-sheet-handle"></div>
    <div class="mem-sheet-meta"    id="mem-sheet-meta"></div>
    <div class="mem-sheet-content" id="mem-sheet-content"></div>
    <div class="mem-sheet-actions">
      <button class="mem-btn-ghost"  id="mem-copy-btn">
        <svg viewBox="0 0 24 24" width="16" height="16"><path d="M16 1H4c-1.1 0-2 .9-2 2v14h2V3h12V1zm3 4H8c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h11c1.1 0 2-.9 2-2V7c0-1.1-.9-2-2-2zm0 16H8V7h11v14z" fill="currentColor"/></svg>
        Copier
      </button>
      <button class="mem-btn-danger" id="mem-delete-btn">
        <svg viewBox="0 0 24 24" width="16" height="16"><path d="M6 19c0 1.1.9 2 2 2h8c1.1 0 2-.9 2-2V7H6v12zM19 4h-3.5l-1-1h-5l-1 1H5v2h14V4z" fill="currentColor"/></svg>
        Supprimer
      </button>
    </div>`;
  document.body.appendChild(_overlay);
  document.body.appendChild(_sheet);

  // Swipe bas pour fermer
  let _ty = 0;
  _sheet.addEventListener('touchstart', (e) => { _ty = e.touches[0].clientY; }, { passive: true });
  _sheet.addEventListener('touchend',   (e) => { if (e.changedTouches[0].clientY - _ty > 60) _closeSheet(); }, { passive: true });

  // Boutons bottom sheet
  _sheet.querySelector('#mem-copy-btn').addEventListener('click', () => {
    const txt = _sheet.querySelector('#mem-sheet-content').textContent;
    navigator.clipboard.writeText(txt).then(
      () => showToast('Souvenir copié'),
      () => showToast('Copie impossible'),
    );
  });

  _sheet.querySelector('#mem-delete-btn').addEventListener('click', async () => {
    if (_currentId === null) return;
    try {
      await fetch(`/api/memory/${_currentId}`, { method: 'DELETE' });
      _results = _results.filter((m) => m.id !== _currentId);
      _closeSheet();
      _renderList(_root, 'récents');
      _refreshStats(_root);
      showToast('Souvenir supprimé');
    } catch { showToast('Erreur lors de la suppression'); }
  });

  // Consolider
  const consolidateBtn = _root.querySelector('#mem-consolidate-btn');
  consolidateBtn.addEventListener('click', async () => {
    consolidateBtn.disabled = true;
    consolidateBtn.textContent = 'En cours…';
    try {
      await fetch('/api/memory/consolidate', { method: 'POST' });
      showToast('Consolidation lancée en arrière-plan');
      setTimeout(() => {
        _refreshConsolidated(_root);
        _refreshStats(_root);
        consolidateBtn.disabled = false;
        consolidateBtn.innerHTML = `<svg viewBox="0 0 24 24" width="16" height="16"><path d="M17.65 6.35C16.2 4.9 14.21 4 12 4c-4.42 0-7.99 3.58-7.99 8s3.57 8 7.99 8c3.73 0 6.84-2.55 7.73-6h-2.08c-.82 2.33-3.04 4-5.65 4-3.31 0-6-2.69-6-6s2.69-6 6-6c1.66 0 3.14.69 4.22 1.78L13 11h7V4l-2.35 2.35z" fill="currentColor"/> </svg> Consolider`;
      }, 8000);
    } catch { showToast('Erreur de consolidation'); consolidateBtn.disabled = false; }
  });

  // Recherche
  _root.querySelector('#mem-search-btn').addEventListener('click', () =>
    _search(_root, _root.querySelector('#mem-search-input').value));
  _root.querySelector('#mem-recent-btn').addEventListener('click', () => {
    _root.querySelector('#mem-search-input').value = '';
    _loadRecent(_root);
  });
  _root.querySelector('#mem-search-input').addEventListener('keydown', (e) => {
    if (e.key === 'Enter') _search(_root, e.target.value);
  });

  // Chargement initial
  await Promise.all([_refreshStats(_root), _refreshConsolidated(_root), _loadRecent(_root)]);
}

export function unmount() {
  _closeSheet();
  _overlay?.remove();
  _sheet?.remove();
  _root?.remove();
  _root = null; _sheet = null; _overlay = null;
}
