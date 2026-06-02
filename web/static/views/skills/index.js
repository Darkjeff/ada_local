/* ================================================================
   Vue Skills — Visualisation et gestion des AutoSkills SQLite
   MODULE_SKILLS
   ================================================================ */
import { showToast, getToken } from '/static/core/core.js';

const _CSS = '/static/views/skills/style.css';

function _ensureCSS() {
  if (!document.getElementById('css-skills')) {
    const l = document.createElement('link');
    l.id = 'css-skills'; l.rel = 'stylesheet'; l.href = _CSS;
    document.head.appendChild(l);
  }
}

// ── État local ───────────────────────────────────────────────────
let _root    = null;
let _overlay = null;
let _sheet   = null;

let _skills     = [];
let _opSkills   = [];          // SKILL.md opérationnelles
let _mode       = 'ops';       // 'ops' | 'active' | 'archived'
let _searchQ    = '';
let _domainFilt = '';
let _editingId  = null;        // null = nouvelle skill
let _domains    = ['core', 'maison', 'auto', 'custom'];  // peuplé dynamiquement

// ── Helpers ──────────────────────────────────────────────────────
function _esc(s) {
  return String(s ?? '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

function _authHeaders() {
  const t = getToken();
  return t ? { Authorization: `Bearer ${t}` } : {};
}

async function _api(method, path, body) {
  const opts = { method, headers: { ..._authHeaders(), 'Content-Type': 'application/json' } };
  if (body != null) opts.body = JSON.stringify(body);
  const r = await fetch(path, opts);
  if (!r.ok) { const e = await r.json().catch(() => ({})); throw new Error(e.detail || r.statusText); }
  return r.json();
}

// ── Chargement données ───────────────────────────────────────────
async function _loadOps() {
  const data = await _api('GET', '/api/page/skills');
  _opSkills = data.skills || [];
}

async function _load() {
  const qs = new URLSearchParams({ status: _mode });
  if (_domainFilt) qs.set('domain', _domainFilt);
  const data = await _api('GET', `/api/autoskills?${qs}`);
  _skills = data.skills || [];
}

async function _loadCurrent() {
  if (_mode === 'ops') return _loadOps();
  return _load();
}

function _filtered() {
  if (_mode === 'ops') {
    if (!_searchQ) return _opSkills;
    const q = _searchQ.toLowerCase();
    return _opSkills.filter(s =>
      s.name.toLowerCase().includes(q) ||
      (s.description || '').toLowerCase().includes(q) ||
      (s.triggers || []).some(t => t.toLowerCase().includes(q))
    );
  }
  if (!_searchQ) return _skills;
  const q = _searchQ.toLowerCase();
  return _skills.filter(s =>
    s.name.toLowerCase().includes(q) ||
    (s.summary || '').toLowerCase().includes(q) ||
    s.domain.toLowerCase().includes(q) ||
    s.id.toLowerCase().includes(q)
  );
}

// ── Rendu liste ──────────────────────────────────────────────────
function _renderList() {
  if (!_root) return;
  const listEl  = _root.querySelector('#sk-list');
  const statsEl = _root.querySelector('#sk-stats');
  const barEl   = _root.querySelector('#sk-bar');
  const hdrBtns = _root.querySelector('#sk-header-actions');
  const items   = _filtered();

  // Afficher/cacher barre filtre et boutons selon onglet
  const isOps = _mode === 'ops';
  barEl.style.display    = isOps ? 'none' : '';
  hdrBtns.style.display  = isOps ? 'none' : '';

  if (_mode === 'ops') {
    statsEl.textContent = `${items.length} skill(s) opérationnelle(s) chargée(s)`;
    _renderOpsItems(listEl, items);
  } else {
    statsEl.textContent = `${_skills.length} autoskill(s) ${_mode === 'active' ? 'active(s)' : 'archivée(s)'}` +
      (_domainFilt ? ` · domaine: ${_domainFilt}` : '');
    _renderAutoItems(listEl, items);
  }
}

// ── Rendu : skills opérationnelles (SKILL.md) ────────────────────
function _renderOpsItems(listEl, items) {
  if (!items.length) {
    listEl.innerHTML = '<div class="sk-empty">Aucune skill opérationnelle chargée</div>';
    return;
  }
  listEl.innerHTML = '';
  for (const s of items) {
    const div = document.createElement('div');
    div.className = 'sk-card';
    const alwaysBadge = s.always
      ? `<span class="sk-tag source-seed" title="Toujours injectée">⚡ always</span>`
      : '';
    const triggers = (s.triggers || []).slice(0, 6).map(t => `<span class="sk-tag">${_esc(t)}</span>`).join(' ');
    const moreTrig = (s.triggers || []).length > 6
      ? `<span class="sk-tag" style="opacity:.6">+${s.triggers.length - 6}</span>` : '';

    div.innerHTML = `
      <div class="sk-card-head">
        <div class="sk-prio p${s.always ? '1' : '4'}" title="${s.always ? 'Toujours active' : 'Déclenchée par triggers'}">
          ${s.always ? '★' : '◈'}
        </div>
        <div class="sk-card-info">
          <div class="sk-card-name">${_esc(s.name)}</div>
          <div class="sk-card-meta">
            <span class="sk-tag source-seed">SKILL.md</span>
            ${alwaysBadge}
          </div>
          ${s.description ? `<div class="sk-card-summary">${_esc(s.description)}</div>` : ''}
          ${triggers ? `<div class="sk-card-meta" style="margin-top:4px;flex-wrap:wrap;gap:3px">${triggers}${moreTrig}</div>` : ''}
        </div>
      </div>
      <div class="sk-card-actions">
        <button class="sk-btn primary" data-action="view-ops" data-id="${_esc(s.name)}">Voir</button>
        <button class="sk-btn" data-action="edit-ops" data-id="${_esc(s.name)}">Modifier</button>
      </div>`;
    listEl.appendChild(div);
  }
}

// ── Rendu : autoskills (SQLite) ──────────────────────────────────

function _renderAutoItems(listEl, items) {
  if (!items.length) {
    listEl.innerHTML = `<div class="sk-empty">Aucune autoskill ${_mode === 'active' ? 'active' : 'archivée'} trouvée</div>`;
    return;
  }

  listEl.innerHTML = '';
  for (const s of items) {
    const pClass = `p${Math.min(10, Math.max(1, s.priority))}`;
    const srcClass = `source-${s.source}`;
    const div = document.createElement('div');
    div.className = 'sk-card';
    div.dataset.id = s.id;

    const archBtn = _mode === 'active'
      ? `<button class="sk-btn archive" data-action="archive" data-id="${_esc(s.id)}">
           <svg viewBox="0 0 24 24" width="11" height="11"><path d="M20.54 5.23l-1.39-1.68C18.88 3.21 18.47 3 18 3H6c-.47 0-.88.21-1.16.55L3.46 5.23C3.17 5.57 3 6.02 3 6.5V19c0 1.1.9 2 2 2h14c1.1 0 2-.9 2-2V6.5c0-.48-.17-.93-.46-1.27zM6.24 5h11.52l.81.97H5.43L6.24 5zM5 19V8h14v11H5zm8.45-9l-3.45 3.46-1.41-1.42L12 14.46l4.41-4.38L17.83 11.5z" fill="currentColor"/></svg>
           Archiver
         </button>`
      : `<button class="sk-btn restore" data-action="restore" data-id="${_esc(s.id)}">
           <svg viewBox="0 0 24 24" width="11" height="11"><path d="M13 3c-4.97 0-9 4.03-9 9H1l3.89 3.89.07.14L9 12H6c0-3.87 3.13-7 7-7s7 3.13 7 7-3.13 7-7 7c-1.93 0-3.68-.79-4.94-2.06l-1.42 1.42C8.27 19.99 10.51 21 13 21c4.97 0 9-4.03 9-9s-4.03-9-9-9zm-1 5v5l4.28 2.54.72-1.21-3.5-2.08V8H12z" fill="currentColor"/></svg>
           Restaurer
         </button>`;

    const promoteBtn = _mode === 'active' && s.priority > 1
      ? `<button class="sk-btn promote" data-action="promote" data-id="${_esc(s.id)}" title="Monter la priorité">↑ Promouvoir</button>`
      : '';

    const deleteBtn = s.priority > 3
      ? `<button class="sk-btn danger" data-action="delete" data-id="${_esc(s.id)}">✕ Supprimer</button>`
      : '';

    div.innerHTML = `
      <div class="sk-card-head">
        <div class="sk-prio ${pClass}" title="Priorité ${s.priority}">${s.priority}</div>
        <div class="sk-card-info">
          <div class="sk-card-name">${_esc(s.name)}</div>
          <div class="sk-card-meta">
            <span class="sk-tag">${_esc(s.domain)}</span>
            <span class="sk-tag ${srcClass}">${_esc(s.source)}</span>
            ${s.usage_count > 0 ? `<span class="sk-tag" title="Utilisations">⚡ ${s.usage_count}</span>` : ''}
            ${s.success_count > 0 ? `<span class="sk-tag" title="Succès">✓ ${s.success_count}</span>` : ''}
          </div>
          ${s.summary ? `<div class="sk-card-summary">${_esc(s.summary)}</div>` : ''}
        </div>
      </div>
      <div class="sk-card-actions">
        <button class="sk-btn primary" data-action="view" data-id="${_esc(s.id)}">Voir</button>
        ${_mode === 'active' ? `<button class="sk-btn" data-action="edit" data-id="${_esc(s.id)}">Modifier</button>` : ''}
        ${promoteBtn}
        ${archBtn}
        ${deleteBtn}
      </div>`;

    listEl.appendChild(div);
  }
}

// ── Actions carte ─────────────────────────────────────────────────
async function _handleAction(action, id) {
  try {
    if (action === 'view-ops') {
      const s = _opSkills.find(x => x.name === id);
      if (!s) return;
      _sheet.querySelector('#sk-sheet-title').textContent = s.name;
      _sheet.querySelector('#sk-sheet-body').innerHTML = `
        <div class="sk-card-meta" style="margin-bottom:8px">
          <span class="sk-tag source-seed">SKILL.md</span>
          ${s.always ? '<span class="sk-tag source-seed">⚡ always</span>' : ''}
        </div>
        ${s.description ? `<p style="font-size:12px;color:var(--text-dim);margin:0 0 10px">${_esc(s.description)}</p>` : ''}
        ${(s.triggers || []).length ? `
          <div class="sk-form-label">Triggers</div>
          <div style="display:flex;flex-wrap:wrap;gap:4px;margin-bottom:10px">
            ${s.triggers.map(t => `<span class="sk-tag">${_esc(t)}</span>`).join('')}
          </div>` : ''}
        <div class="sk-form-label">Contenu injecté</div>
        <div class="sk-content-preview">${_esc(s.body || '(vide)')}</div>`;
      _sheet.querySelector('#sk-sheet-footer').innerHTML = `
        <button class="sk-btn" id="sk-sheet-cancel">Fermer</button>
        <button class="sk-btn primary" id="sk-sheet-edit-ops">Modifier</button>`;
      _sheet.querySelector('#sk-sheet-cancel').addEventListener('click', _closeSheet);
      _sheet.querySelector('#sk-sheet-edit-ops').addEventListener('click', () => { _closeSheet(); _openEditOps(s); });
      _openSheet();
      return;
    }
    if (action === 'edit-ops') {
      const s = _opSkills.find(x => x.name === id);
      if (s) _openEditOps(s);
      return;
    }
    if (action === 'view') {
      const s = _skills.find(x => x.id === id);
      if (s) _openView(s);
      return;
    }
    if (action === 'edit') {
      const s = _skills.find(x => x.id === id);
      if (s) _openEdit(s);
      return;
    }
    if (action === 'promote') {
      await _api('PATCH', `/api/autoskills/${encodeURIComponent(id)}/promote`);
      showToast('Priorité montée ↑');
    } else if (action === 'archive') {
      await _api('PATCH', `/api/autoskills/${encodeURIComponent(id)}/archive`);
      showToast('Skill archivée');
    } else if (action === 'restore') {
      await _api('PATCH', `/api/autoskills/${encodeURIComponent(id)}/restore`);
      showToast('Skill restaurée');
    } else if (action === 'delete') {
      if (!confirm(`Supprimer définitivement la skill "${id}" ?`)) return;
      await _api('DELETE', `/api/autoskills/${encodeURIComponent(id)}`);
      showToast('Skill supprimée');
    }
    await _load();
    _renderList();
  } catch (e) {
    showToast(`Erreur : ${e.message}`);
  }
}

// ── Bottom sheet : édition SKILL.md opérationnelle ───────────────
function _openEditOps(s) {
  _sheet.querySelector('#sk-sheet-title').textContent = `Modifier : ${s.name}`;
  _sheet.querySelector('#sk-sheet-body').innerHTML = `
    <div class="sk-form-label">Description</div>
    <input id="sk-ops-desc" class="sk-form-input" value="${_esc(s.description || '')}" placeholder="Description courte">
    <div class="sk-form-label">Triggers (un par ligne)</div>
    <textarea id="sk-ops-triggers" class="sk-form-textarea" style="min-height:80px" placeholder="mot-clé\nautre trigger">${_esc((s.triggers || []).join('\n'))}</textarea>
    <div class="sk-form-label">Contenu injecté</div>
    <textarea id="sk-ops-body" class="sk-form-textarea" style="min-height:140px" placeholder="Instructions injectées dans le prompt…">${_esc(s.body || '')}</textarea>`;
  _sheet.querySelector('#sk-sheet-footer').innerHTML = `
    <button class="sk-btn" id="sk-sheet-cancel">Annuler</button>
    <button class="sk-btn primary" id="sk-sheet-save-ops">Enregistrer</button>`;
  _sheet.querySelector('#sk-sheet-cancel').addEventListener('click', _closeSheet);
  _sheet.querySelector('#sk-sheet-save-ops').addEventListener('click', async () => {
    const desc     = _sheet.querySelector('#sk-ops-desc').value.trim();
    const triggers = _sheet.querySelector('#sk-ops-triggers').value
      .split('\n').map(t => t.trim()).filter(Boolean);
    const body     = _sheet.querySelector('#sk-ops-body').value.trim();
    const btn = _sheet.querySelector('#sk-sheet-save-ops');
    btn.disabled = true; btn.textContent = 'Enregistrement…';
    try {
      await _api('PUT', `/api/skills/${encodeURIComponent(s.name)}`, { description: desc, triggers, body });
      showToast('Skill opérationnelle mise à jour ✓');
      _closeSheet();
      await _loadOps();
      _renderList();
    } catch (e) {
      showToast(`Erreur : ${e.message}`);
      btn.disabled = false; btn.textContent = 'Enregistrer';
    }
  });
  _openSheet();
}

// ── Bottom sheet : vue lecture ───────────────────────────────────
function _openView(s) {
  _editingId = null;
  _sheet.querySelector('#sk-sheet-title').textContent = s.name;
  _sheet.querySelector('#sk-sheet-body').innerHTML = `
    <div class="sk-card-meta" style="margin-bottom:8px">
      <span class="sk-tag">${_esc(s.domain)}</span>
      <span class="sk-tag source-${s.source}">${_esc(s.source)}</span>
      <span class="sk-tag">Priorité ${s.priority}</span>
      <span class="sk-tag">Status: ${s.status}</span>
    </div>
    ${s.summary ? `<p style="font-size:12px;color:var(--text-dim);margin:0 0 10px">${_esc(s.summary)}</p>` : ''}
    <div class="sk-form-label">Contenu</div>
    <div class="sk-content-preview">${_esc(s.content)}</div>
    <div style="font-size:11px;color:var(--text-dim);margin-top:10px">
      Créé : ${s.created_at} · Mis à jour : ${s.updated_at}
      ${s.last_used ? ` · Dernier usage : ${s.last_used}` : ''}
    </div>`;
  _sheet.querySelector('#sk-sheet-footer').innerHTML = `
    <button class="sk-btn" id="sk-sheet-cancel">Fermer</button>
    ${s.status === 'active' ? `<button class="sk-btn primary" id="sk-sheet-edit">Modifier</button>` : ''}`;
  _sheet.querySelector('#sk-sheet-cancel').addEventListener('click', _closeSheet);
  _sheet.querySelector('#sk-sheet-edit')?.addEventListener('click', () => { _closeSheet(); _openEdit(s); });
  _openSheet();
}

// ── Bottom sheet : formulaire création/édition ───────────────────
function _openEdit(s) {
  const isNew = !s;
  _editingId = s?.id || null;
  _sheet.querySelector('#sk-sheet-title').textContent = isNew ? 'Nouvelle skill' : `Modifier : ${s.name}`;
  _sheet.querySelector('#sk-sheet-body').innerHTML = `
    <div class="sk-form-label">Nom *</div>
    <input id="sk-f-name" class="sk-form-input" placeholder="Nom de la skill" value="${_esc(s?.name || '')}">
    <div class="sk-form-label">Résumé</div>
    <input id="sk-f-summary" class="sk-form-input" placeholder="Une phrase de résumé" value="${_esc(s?.summary || '')}">
    <div class="sk-form-label">Domaine</div>
    <select id="sk-f-domain" class="sk-form-select">
      ${_domains.map(d => `<option value="${d}" ${(s?.domain || 'core') === d ? 'selected' : ''}>${d}</option>`).join('')}
    </select>
    <div class="sk-form-label">Priorité (1 = toujours active, 10 = rare)</div>
    <input id="sk-f-priority" class="sk-form-input" type="number" min="1" max="10" value="${s?.priority ?? 5}">
    <div class="sk-form-label">Contenu *</div>
    <textarea id="sk-f-content" class="sk-form-textarea" placeholder="Instructions, procédures, connaissances…">${_esc(s?.content || '')}</textarea>`;
  _sheet.querySelector('#sk-sheet-footer').innerHTML = `
    <button class="sk-btn" id="sk-sheet-cancel">Annuler</button>
    <button class="sk-btn primary" id="sk-sheet-save">${isNew ? 'Créer' : 'Enregistrer'}</button>`;
  _sheet.querySelector('#sk-sheet-cancel').addEventListener('click', _closeSheet);
  _sheet.querySelector('#sk-sheet-save').addEventListener('click', () => _saveSkill(s?.id));
  _openSheet();
}

async function _saveSkill(existingId) {
  const name     = _sheet.querySelector('#sk-f-name').value.trim();
  const summary  = _sheet.querySelector('#sk-f-summary').value.trim();
  const domain   = _sheet.querySelector('#sk-f-domain').value;
  const priority = parseInt(_sheet.querySelector('#sk-f-priority').value, 10);
  const content  = _sheet.querySelector('#sk-f-content').value.trim();

  if (!name || !content) { showToast('Nom et contenu requis'); return; }

  const saveBtn = _sheet.querySelector('#sk-sheet-save');
  saveBtn.disabled = true;
  saveBtn.textContent = 'Enregistrement…';

  try {
    await _api('POST', '/api/autoskills', {
      ...(existingId ? { id: existingId } : {}),
      name, summary, domain, priority, content, source: 'manual',
    });
    showToast(existingId ? 'Skill mise à jour' : 'Skill créée ✓');
    _closeSheet();
    await _load();
    _renderList();
  } catch (e) {
    showToast(`Erreur : ${e.message}`);
    saveBtn.disabled = false;
    saveBtn.textContent = existingId ? 'Enregistrer' : 'Créer';
  }
}

function _openSheet() {
  _overlay.classList.add('open');
  _sheet.classList.add('open');
}

function _closeSheet() {
  _overlay.classList.remove('open');
  _sheet.classList.remove('open');
}

// ── Montage ──────────────────────────────────────────────────────
export async function mount(container, _opts = {}) {
  _ensureCSS();

  // Wrapper principal
  _root = document.createElement('div');
  _root.id = 'skills-view';
  _root.innerHTML = `
    <div class="sk-header">
      <span class="sk-title">Compétences</span>
      <div class="sk-header-actions" id="sk-header-actions">
        <button class="sk-btn primary" id="sk-new-btn">+ Nouvelle</button>
        <button class="sk-btn" id="sk-maintenance-btn" title="Maintenance (archivage auto)">
          <svg viewBox="0 0 24 24" width="13" height="13"><path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-1 17.93c-3.95-.49-7-3.85-7-7.93 0-.62.08-1.21.21-1.79L9 15v1c0 1.1.9 2 2 2v1.93zm6.9-2.54c-.26-.81-1-1.39-1.9-1.39h-1v-3c0-.55-.45-1-1-1H8v-2h2c.55 0 1-.45 1-1V7h2c1.1 0 2-.9 2-2v-.41c2.93 1.19 5 4.06 5 7.41 0 2.08-.8 3.97-2.1 5.39z" fill="currentColor"/></svg>
          Maintenance
        </button>
      </div>
    </div>
    <div class="sk-tabs">
      <div class="sk-tab on" data-mode="ops">Opérationnelles</div>
      <div class="sk-tab" data-mode="active">AutoSkills</div>
      <div class="sk-tab" data-mode="archived">Archivées</div>
    </div>
    <div class="sk-bar" id="sk-bar" style="display:none">
      <input id="sk-search" class="sk-search" placeholder="Rechercher…" type="search">
      <select id="sk-domain" class="sk-domain-filter">
        <option value="">Tous les domaines</option>
      </select>
    </div>
    <div class="sk-stats" id="sk-stats">Chargement…</div>
    <div class="sk-list" id="sk-list"></div>`;

  container.appendChild(_root);

  // Bottom sheet overlay
  _overlay = document.createElement('div');
  _overlay.className = 'sk-overlay';
  _overlay.addEventListener('click', _closeSheet);

  _sheet = document.createElement('div');
  _sheet.className = 'sk-sheet';
  _sheet.innerHTML = `
    <div class="sk-sheet-handle"></div>
    <div class="sk-sheet-head">
      <span class="sk-sheet-title" id="sk-sheet-title"></span>
      <button class="sk-sheet-close" id="sk-sheet-x">✕</button>
    </div>
    <div class="sk-sheet-body" id="sk-sheet-body"></div>
    <div class="sk-sheet-footer" id="sk-sheet-footer"></div>`;

  document.body.appendChild(_overlay);
  document.body.appendChild(_sheet);

  // Swipe bas pour fermer
  let _ty = 0;
  _sheet.addEventListener('touchstart', e => { _ty = e.touches[0].clientY; }, { passive: true });
  _sheet.addEventListener('touchend',   e => { if (e.changedTouches[0].clientY - _ty > 60) _closeSheet(); }, { passive: true });
  _sheet.querySelector('#sk-sheet-x').addEventListener('click', _closeSheet);

  // Événements header
  _root.querySelector('#sk-new-btn').addEventListener('click', () => _openEdit(null));
  _root.querySelector('#sk-maintenance-btn').addEventListener('click', async () => {
    try {
      const r = await _api('POST', '/api/autoskills/maintenance');
      showToast(`Maintenance : ${r.archived ?? 0} skill(s) archivée(s)`);
      await _load();
      _renderList();
    } catch (e) { showToast(`Erreur : ${e.message}`); }
  });

  // Tabs
  _root.querySelectorAll('.sk-tab').forEach(tab => {
    tab.addEventListener('click', async () => {
      _root.querySelectorAll('.sk-tab').forEach(t => t.classList.remove('on'));
      tab.classList.add('on');
      _mode = tab.dataset.mode;
      _searchQ = '';
      const searchEl = _root.querySelector('#sk-search');
      if (searchEl) searchEl.value = '';
      await _loadCurrent();
      _renderList();
    });
  });

  // Recherche
  _root.querySelector('#sk-search').addEventListener('input', e => {
    _searchQ = e.target.value;
    _renderList();
  });

  // Filtre domaine
  _root.querySelector('#sk-domain').addEventListener('change', async e => {
    _domainFilt = e.target.value;
    await _load();
    _renderList();
  });

  // Délégation clicks sur les cartes
  _root.querySelector('#sk-list').addEventListener('click', e => {
    const btn = e.target.closest('[data-action]');
    if (!btn) return;
    _handleAction(btn.dataset.action, btn.dataset.id);
  });

  // Chargement initial (onglet Opérationnelles)
  try {
    await _loadDomains();
    // Peupler le filtre domaine dynamiquement
    const domSel = _root.querySelector('#sk-domain');
    if (domSel) {
      domSel.innerHTML = '<option value="">Tous les domaines</option>' +
        _domains.map(d => `<option value="${d}">${d}</option>`).join('');
    }
    await _loadCurrent();
    _renderList();
  } catch (e) {
    _root.querySelector('#sk-stats').textContent = 'Erreur de chargement';
    _root.querySelector('#sk-list').innerHTML = `<div class="sk-empty">Impossible de charger les skills : ${_esc(e.message)}</div>`;
  }
}

export function unmount() {
  _closeSheet();
  _overlay?.remove();
  _sheet?.remove();
  _root?.remove();
  _root = null; _overlay = null; _sheet = null;
  _skills = []; _opSkills = []; _mode = 'ops'; _searchQ = ''; _domainFilt = ''; _editingId = null;
}
