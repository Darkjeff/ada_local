/* ================================================================
   Vue Briefing — Flux RSS configurable avec mots-clés et sources
   ================================================================ */
import { showToast, setInputBarVisible, escapeHtml } from '/static/core/core.js';

const _CSS = '/static/views/briefing/style.css';
function _ensureCSS() {
  if (!document.getElementById('css-briefing')) {
    const l = document.createElement('link');
    l.id = 'css-briefing'; l.rel = 'stylesheet'; l.href = _CSS;
    document.head.appendChild(l);
  }
}

// ── État ──────────────────────────────────────────────────────
let _articles  = [];
let _sources   = [];
let _keywords  = [];
let _activeTab = 'Tout';
let _loading   = false;

// ── Helpers date ──────────────────────────────────────────────
function _fmtDate(raw) {
  if (!raw) return '';
  try {
    const d = new Date(raw);
    if (isNaN(d)) return raw.slice(0, 16);
    return d.toLocaleDateString('fr-FR', { day: 'numeric', month: 'short' })
      + ' · ' + d.toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit' });
  } catch { return raw.slice(0, 16); }
}

// ── Template principal ────────────────────────────────────────
function _html() {
  return `
<div class="br-wrap">

  <!-- Header -->
  <div class="br-header">
    <div class="br-header-left">
      <h1 class="br-title">📰 Briefing</h1>
      <div class="br-kw-bar" id="br-kw-bar"></div>
    </div>
    <div class="br-header-actions">
      <button class="br-btn-icon" id="br-settings-btn" title="Paramètres sources">⚙</button>
      <button class="br-btn-icon" id="br-refresh-btn" title="Actualiser">↻</button>
    </div>
  </div>

  <!-- Tabs catégories -->
  <div class="br-tabs" id="br-tabs"></div>

  <!-- Breaking bar -->
  <div class="br-breaking" id="br-breaking" style="display:none">
    <span class="br-breaking-label">BREAKING</span>
    <span class="br-breaking-text" id="br-breaking-text"></span>
  </div>

  <!-- Grille articles -->
  <div class="br-grid" id="br-grid">
    ${_skeletons(6)}
  </div>

  <!-- Panneau paramètres (slide-in) -->
  <div class="br-settings-overlay" id="br-overlay"></div>
  <aside class="br-settings-panel" id="br-settings-panel">
    <div class="br-sp-header">
      <span>⚙ Paramètres</span>
      <button class="br-sp-close" id="br-sp-close">✕</button>
    </div>

    <!-- Mots-clés -->
    <section class="br-sp-section">
      <div class="br-sp-title">Mots-clés</div>
      <div class="br-sp-sub">Filtrer les articles contenant ces termes</div>
      <div class="br-chips" id="br-kw-chips"></div>
      <div class="br-sp-add-row">
        <input class="br-sp-input" id="br-kw-input" placeholder="Ajouter un mot-clé…" autocomplete="off">
        <button class="br-sp-add-btn" id="br-kw-add">+</button>
      </div>
    </section>

    <!-- Sources RSS -->
    <section class="br-sp-section">
      <div class="br-sp-title">Sources RSS</div>
      <div class="br-sp-sub">Flux utilisés pour récupérer les articles</div>
      <ul class="br-sources-list" id="br-sources-list"></ul>
      <details class="br-sp-details">
        <summary>+ Ajouter une source</summary>
        <div class="br-sp-form">
          <input class="br-sp-input" id="br-src-url"  placeholder="URL du flux RSS" autocomplete="off">
          <input class="br-sp-input" id="br-src-name" placeholder="Nom (ex: Le Monde)" autocomplete="off">
          <input class="br-sp-input" id="br-src-cat"  placeholder="Catégorie (ex: Politique)" autocomplete="off">
          <button class="br-sp-save-btn" id="br-src-add">Ajouter</button>
        </div>
      </details>
    </section>
  </aside>

</div>`;
}

function _skeletons(n) {
  return Array.from({length: n}, () => `
  <div class="br-card br-card-sk">
    <div class="br-card-img sk-block"></div>
    <div class="br-card-body">
      <div class="sk-line"></div>
      <div class="sk-line short"></div>
      <div class="sk-line xshort"></div>
    </div>
  </div>`).join('');
}

// ── Rendu ─────────────────────────────────────────────────────
function _renderTabs(root) {
  const cats = ['Tout', ...[...new Set(_articles.map(a => a.category).filter(Boolean))]];
  if (!cats.includes(_activeTab)) _activeTab = 'Tout';
  root.querySelector('#br-tabs').innerHTML = cats.map(c => `
    <button class="br-tab${c === _activeTab ? ' active' : ''}" data-cat="${c}">${c}</button>
  `).join('');
}

function _renderKwBar(root) {
  root.querySelector('#br-kw-bar').innerHTML = _keywords.length
    ? _keywords.map(k => `<span class="br-kw-chip">${k}</span>`).join('')
    : '';
}

function _renderBreaking(root) {
  const bar  = root.querySelector('#br-breaking');
  const text = root.querySelector('#br-breaking-text');
  const top  = _articles.filter(a => a.category === 'Top Stories')[0];
  if (top) {
    text.textContent = top.title + (top.source ? ` (${top.source})` : '');
    bar.style.display = '';
    bar.onclick = () => top.url && window.open(top.url, '_blank', 'noopener');
  } else {
    bar.style.display = 'none';
  }
}

function _renderGrid(root) {
  const filtered = _activeTab === 'Tout'
    ? _articles
    : _articles.filter(a => a.category === _activeTab);

  if (!filtered.length) {
    root.querySelector('#br-grid').innerHTML =
      '<p class="br-empty">Aucun article' +
      (_keywords.length ? ' pour ces mots-clés.' : '. Actualisez le flux.') + '</p>';
    return;
  }

  root.querySelector('#br-grid').innerHTML = filtered.map(a => `
    <a class="br-card" href="${escapeHtml(a.url || '#')}" target="_blank" rel="noopener">
      ${a.image ? `<div class="br-card-img"><img src="${escapeHtml(a.image)}" alt="" loading="lazy"></div>` : ''}
      <div class="br-card-body">
        <div class="br-card-cat">${escapeHtml(a.category || '')}</div>
        <div class="br-card-title">${escapeHtml(a.title)}</div>
        <div class="br-card-meta">${escapeHtml(a.source || '')}${a.source && a.date ? ' · ' : ''}${_fmtDate(a.date)}</div>
      </div>
    </a>`).join('');
}

function _renderSettingsPanel(root) {
  // Chips mots-clés
  root.querySelector('#br-kw-chips').innerHTML = _keywords.length
    ? _keywords.map(k => `<span class="br-chip" data-kw="${k}">${k} <button class="br-chip-del" data-kw="${k}">×</button></span>`).join('')
    : '<span class="br-sp-sub">Aucun filtre actif (tous les articles affichés)</span>';

  // Sources
  root.querySelector('#br-sources-list').innerHTML = _sources.map((s, i) => `
    <li class="br-src-item">
      <div class="br-src-info">
        <span class="br-src-name">${s.name}</span>
        <span class="br-src-cat">${s.category}</span>
        <span class="br-src-url">${s.url.replace(/^https?:\/\//, '').slice(0, 48)}…</span>
      </div>
      <button class="br-src-del" data-idx="${i}">🗑</button>
    </li>`).join('') || '<li class="br-sp-sub">Aucune source configurée</li>';
}

// ── API ───────────────────────────────────────────────────────
async function _loadConfig(root) {
  try {
    const cfg = await fetch('/api/briefing/config').then(r => r.json());
    _sources  = cfg.sources  || [];
    _keywords = cfg.keywords || [];
    _renderKwBar(root);
    _renderSettingsPanel(root);
  } catch { /* ignore */ }
}

async function _loadFeed(root, refresh = false) {
  if (_loading) return;
  _loading = true;
  const btn = root.querySelector('#br-refresh-btn');
  if (btn) { btn.textContent = '⏳'; btn.disabled = true; }
  root.querySelector('#br-grid').innerHTML = _skeletons(6);

  try {
    const url = '/api/briefing/feed' + (refresh ? '?refresh=true' : '');
    const r = await fetch(url);
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    _articles = await r.json();
    if (!Array.isArray(_articles)) throw new Error('Réponse invalide');
    _renderTabs(root);
    _renderBreaking(root);
    _renderGrid(root);
  } catch (e) {
    console.error('[Briefing] _loadFeed error:', e);
    const grid = root.querySelector('#br-grid');
    if (grid) grid.innerHTML = `<p class="br-empty" style="color:#f87171">⚠ ${escapeHtml(e.message)}</p>`;
    showToast('Erreur Briefing : ' + e.message);
  } finally {
    _loading = false;
    if (btn) { btn.textContent = '↻'; btn.disabled = false; }
  }
}

async function _saveConfig() {
  await fetch('/api/briefing/config', {
    method: 'PUT',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({sources: _sources, keywords: _keywords}),
  });
}

// ── Événements paramètres ─────────────────────────────────────
function _bindSettings(root) {
  const panel   = root.querySelector('#br-settings-panel');
  const overlay = root.querySelector('#br-overlay');
  const open  = () => { panel.classList.add('open'); overlay.classList.add('open'); };
  const close = () => { panel.classList.remove('open'); overlay.classList.remove('open'); };

  root.querySelector('#br-settings-btn').addEventListener('click', open);
  root.querySelector('#br-sp-close').addEventListener('click', close);
  overlay.addEventListener('click', close);

  // Ajouter mot-clé
  const addKw = () => {
    const input = root.querySelector('#br-kw-input');
    const kw = input.value.trim().toLowerCase();
    if (!kw) return;
    if (!_keywords.includes(kw)) {
      _keywords.push(kw);
      _saveConfig();
      _renderKwBar(root);
      _renderSettingsPanel(root);
      _renderGrid(root); // re-filtre
    }
    input.value = '';
  };
  root.querySelector('#br-kw-add').addEventListener('click', addKw);
  root.querySelector('#br-kw-input').addEventListener('keydown', e => { if (e.key === 'Enter') { e.preventDefault(); addKw(); } });

  // Supprimer mot-clé (délégation)
  root.querySelector('#br-kw-chips').addEventListener('click', e => {
    const btn = e.target.closest('.br-chip-del');
    if (!btn) return;
    _keywords = _keywords.filter(k => k !== btn.dataset.kw);
    _saveConfig();
    _renderKwBar(root);
    _renderSettingsPanel(root);
    _renderGrid(root);
  });

  // Supprimer source (délégation)
  root.querySelector('#br-sources-list').addEventListener('click', e => {
    const btn = e.target.closest('.br-src-del');
    if (!btn) return;
    _sources.splice(Number(btn.dataset.idx), 1);
    _saveConfig();
    _renderSettingsPanel(root);
    showToast('Source supprimée');
  });

  // Ajouter source
  root.querySelector('#br-src-add').addEventListener('click', async () => {
    const url  = root.querySelector('#br-src-url').value.trim();
    const name = root.querySelector('#br-src-name').value.trim();
    const cat  = root.querySelector('#br-src-cat').value.trim() || 'Général';
    if (!url || !name) { showToast('URL et nom requis'); return; }
    if (!url.startsWith('http')) { showToast('URL invalide'); return; }
    _sources.push({url, name, category: cat});
    await _saveConfig();
    root.querySelector('#br-src-url').value  = '';
    root.querySelector('#br-src-name').value = '';
    root.querySelector('#br-src-cat').value  = '';
    _renderSettingsPanel(root);
    showToast('Source ajoutée');
  });
}

// ── mount / unmount ───────────────────────────────────────────
export async function mount(container) {
  _ensureCSS();
  setInputBarVisible(false);
  container.innerHTML = _html();

  // Tabs : délégation
  container.querySelector('#br-tabs').addEventListener('click', e => {
    const btn = e.target.closest('.br-tab');
    if (!btn) return;
    _activeTab = btn.dataset.cat;
    container.querySelectorAll('.br-tab').forEach(t => t.classList.toggle('active', t.dataset.cat === _activeTab));
    _renderGrid(container);
  });

  // Refresh
  container.querySelector('#br-refresh-btn').addEventListener('click', () => _loadFeed(container, true));

  _bindSettings(container);

  await _loadConfig(container);
  await _loadFeed(container, false);
}

export function unmount() {
  _articles  = [];
  _activeTab = 'Tout';
  _loading   = false;
}
