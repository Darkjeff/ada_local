/* ================================================================
   ADA — Profile Editor view
   3 onglets : Univers | Profils | Appareils
   Inline editors, drag & drop, preview temps réel
   ================================================================ */
import { showToast, setInputBarVisible, getToken, escapeHtml as _esc } from '/static/core/core.js';

const _CSS = '/static/views/profile-editor/style.css';

// ── State ──────────────────────────────────────────────────────
let _modules   = [];
let _universes = [];
let _profiles  = [];
let _devices   = [];
let _activeTab = 'universes';
let _viewport  = null;

// ── Mount / Unmount ────────────────────────────────────────────
export async function mount(viewport, opts = {}) {
  _viewport = viewport;
  _ensureCSS();
  setInputBarVisible(false);
  viewport.innerHTML = `
    <div class="pe-wrap">
      <div class="pe-tabbar" id="pe-tabbar">
        <button class="pe-tab active" data-tab="universes">Univers</button>
        <button class="pe-tab"        data-tab="profiles">Profils</button>
        <button class="pe-tab"        data-tab="devices">Appareils</button>
      </div>
      <div class="pe-panel" id="pe-panel"></div>
    </div>`;

  // Bind tabs
  viewport.querySelectorAll('.pe-tab').forEach(btn => {
    btn.addEventListener('click', () => {
      viewport.querySelectorAll('.pe-tab').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      _activeTab = btn.dataset.tab;
      _renderTab(_activeTab);
    });
  });

  await _loadAll();
  _renderTab(_activeTab);
}

export function unmount() { _viewport = null; }

// ── Data ───────────────────────────────────────────────────────
async function _loadAll() {
  const h = _headers();
  try {
    const [mRes, uRes, pRes, dRes] = await Promise.all([
      fetch('/api/modules',       { headers: h }).then(r => r.json()),
      fetch('/api/universes',     { headers: h }).then(r => r.json()),
      fetch('/api/profiles',      { headers: h }).then(r => r.json()),
      fetch('/api/admin/devices', { headers: h }).then(r => r.json()).catch(() => []),
    ]);
    _modules   = mRes.modules   || mRes   || [];
    _universes = uRes.universes || uRes   || [];
    _profiles  = pRes.profiles  || pRes   || [];
    _devices   = Array.isArray(dRes) ? dRes : (dRes.devices || []);
  } catch (e) {
    showToast('Erreur chargement : ' + e.message);
  }
}

function _headers() {
  const token = getToken();
  return token
    ? { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' }
    : { 'Content-Type': 'application/json' };
}

function _renderTab(tab) {
  if (tab === 'universes') _renderUniverses();
  else if (tab === 'profiles') _renderProfiles();
  else _renderDevices();
}

// ════════════════════════════════════════════════════════════════
//  ONGLET 1 — UNIVERS
// ════════════════════════════════════════════════════════════════

function _renderUniverses() {
  const panel = document.getElementById('pe-panel');
  if (!panel) return;

  const rows = _universes.map(u => {
    const modLabels = (u.modules || [])
      .map(id => _modules.find(m => m.id === id)?.label || id)
      .join(', ');
    const preview = modLabels.length > 50 ? modLabels.slice(0, 50) + '…' : modLabels;
    const inUse = _profiles.some(p => (p.universe_ids || []).includes(u.id));
    return `
    <div class="pe-row" id="row-u-${u.id}">
      <div class="pe-row-dot" style="background:${_esc(u.color)}"></div>
      <div class="pe-row-body">
        <span class="pe-row-name">${_esc(u.icon)} ${_esc(u.name)}</span>
        <span class="pe-row-meta">${_esc(u.color)} · ${_esc(preview)}</span>
      </div>
      <button class="pe-icon-btn"               data-eu="${_esc(u.id)}" title="Modifier">✎</button>
      <button class="pe-icon-btn danger"         data-du="${_esc(u.id)}"
              data-inuse="${inUse ? '1' : ''}"
              title="${inUse ? 'Utilisé par un profil — suppression possible' : 'Supprimer'}">🗑</button>
    </div>
    <div class="pe-editor-slot" id="slot-u-${u.id}"></div>`;
  }).join('');

  panel.innerHTML = `
    <div class="pe-section-head">
      <span class="pe-section-title">Univers</span>
      <button class="pe-add-btn" id="btn-new-u">+ Nouvel univers</button>
    </div>
    <div id="slot-new-u"></div>
    <div id="pe-u-list">${rows || '<p class="pe-empty">Aucun univers.</p>'}</div>`;

  document.getElementById('btn-new-u').onclick = () => {
    const slot = document.getElementById('slot-new-u');
    if (slot.children.length) { slot.innerHTML = ''; return; }
    _renderUniverseEditor(slot, null);
    slot.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  };
  panel.querySelectorAll('[data-eu]').forEach(btn => {
    btn.onclick = () => {
      const uid  = btn.dataset.eu;
      const slot = document.getElementById(`slot-u-${uid}`);
      if (slot.children.length) { slot.innerHTML = ''; return; }
      // Fermer les autres slots
      panel.querySelectorAll('.pe-editor-slot').forEach(s => { if (s !== slot) s.innerHTML = ''; });
      document.getElementById('slot-new-u').innerHTML = '';
      const u = _universes.find(x => x.id === uid);
      _renderUniverseEditor(slot, u);
      slot.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    };
  });
  panel.querySelectorAll('[data-du]').forEach(btn => {
    btn.onclick = async () => {
      const msg = btn.dataset.inuse
        ? 'Cet univers est utilisé par un ou plusieurs profils.\nLe supprimer le retirera de ces profils.\nContinuer ?'
        : 'Supprimer cet univers ?';
      if (!confirm(msg)) return;
      try {
        const r = await fetch(`/api/universes/${btn.dataset.du}`, { method: 'DELETE', headers: _headers() });
        if (r.status === 204 || r.ok) {
          showToast('Univers supprimé');
          await _loadAll();
          _renderUniverses();
        } else {
          showToast('Erreur suppression');
        }
      } catch (e) { showToast('Erreur : ' + e.message); }
    };
  });
}

// Éditeur d'univers inline
function _renderUniverseEditor(slot, universe) {
  const isNew = !universe;
  const selected = [...(universe?.modules || [])];

  // Groupes de modules
  const byCategory = _groupByCategory(_modules);
  const availHtml  = _buildAvailableModules(byCategory, selected);
  const selHtml    = _buildSelectedModules(selected);

  slot.innerHTML = `
  <div class="pe-editor">
    <div class="pe-editor-row">
      <label>Nom</label>
      <input id="pe-u-name" type="text" value="${_esc(universe?.name || '')}" placeholder="Ex: Maison" />
    </div>
    <div class="pe-editor-row pe-editor-row-inline">
      <div>
        <label>Icône (emoji)</label>
        <input id="pe-u-icon" type="text" value="${_esc(universe?.icon || '◈')}" maxlength="4"
               style="width:70px;text-align:center;font-size:18px" />
      </div>
      <div>
        <label>Couleur</label>
        <div class="pe-color-row">
          <input id="pe-u-color-pick" type="color" value="${_esc(universe?.color || '#00c8f0')}" />
          <input id="pe-u-color-hex"  type="text"  value="${_esc(universe?.color || '#00c8f0')}" maxlength="7" />
        </div>
      </div>
    </div>
    <div class="pe-editor-row">
      <label>Modules</label>
      <div class="pe-dual-list">
        <div class="pe-list-col">
          <div class="pe-list-title">Disponibles</div>
          <div class="pe-list-items" id="pe-u-available">${availHtml}</div>
        </div>
        <div class="pe-list-arrows">
          <button id="pe-u-add-all" title="Tout ajouter">»</button>
          <button id="pe-u-rem-all" title="Tout retirer">«</button>
        </div>
        <div class="pe-list-col">
          <div class="pe-list-title">Sélectionnés <small>(glisser pour réordonner)</small></div>
          <div class="pe-list-items droppable" id="pe-u-selected">${selHtml}</div>
        </div>
      </div>
    </div>
    <div class="pe-editor-actions">
      <button class="pe-btn-secondary" id="pe-u-cancel">Annuler</button>
      <button class="pe-btn-primary"   id="pe-u-save">${isNew ? 'Créer' : 'Enregistrer'}</button>
    </div>
  </div>`;

  // Sync color picker ↔ hex
  const pick = slot.querySelector('#pe-u-color-pick');
  const hex  = slot.querySelector('#pe-u-color-hex');
  pick.addEventListener('input', () => { hex.value = pick.value; });
  hex.addEventListener('input', () => { if (/^#[0-9a-f]{6}$/i.test(hex.value)) pick.value = hex.value; });

  // Clic : disponible → sélectionné
  slot.querySelector('#pe-u-available').addEventListener('click', e => {
    const item = e.target.closest('.pe-module-item');
    if (!item) return;
    const mid = item.dataset.module;
    const m   = _modules.find(x => x.id === mid);
    slot.querySelector('#pe-u-selected').insertAdjacentHTML('beforeend',
      `<div class="pe-module-item selected" data-module="${mid}" draggable="true">
         <span class="pe-drag-handle">⠿</span>
         <span class="pe-module-label">${_esc(m?.label || mid)}</span>
       </div>`);
    item.remove();
    // Supprimer la catégorie si vide
    _cleanEmptyCategories(slot.querySelector('#pe-u-available'));
  });

  // Clic : sélectionné → disponible
  slot.querySelector('#pe-u-selected').addEventListener('click', e => {
    const item = e.target.closest('.pe-module-item');
    if (!item || e.target.classList.contains('pe-drag-handle')) return;
    const mid = item.dataset.module;
    const m   = _modules.find(x => x.id === mid);
    const cat = m?.category || 'tools';
    _addToAvailable(slot.querySelector('#pe-u-available'), mid, m?.label || mid, cat);
    item.remove();
  });

  // Boutons >> et <<
  slot.querySelector('#pe-u-add-all').onclick = () => {
    slot.querySelectorAll('#pe-u-available .pe-module-item').forEach(item => {
      const mid = item.dataset.module;
      const m   = _modules.find(x => x.id === mid);
      slot.querySelector('#pe-u-selected').insertAdjacentHTML('beforeend',
        `<div class="pe-module-item selected" data-module="${mid}" draggable="true">
           <span class="pe-drag-handle">⠿</span>
           <span class="pe-module-label">${_esc(m?.label || mid)}</span>
         </div>`);
    });
    slot.querySelector('#pe-u-available').innerHTML = '';
  };
  slot.querySelector('#pe-u-rem-all').onclick = () => {
    slot.querySelectorAll('#pe-u-selected .pe-module-item').forEach(item => {
      const mid = item.dataset.module;
      const m   = _modules.find(x => x.id === mid);
      _addToAvailable(slot.querySelector('#pe-u-available'), mid, m?.label || mid, m?.category || 'tools');
    });
    slot.querySelector('#pe-u-selected').innerHTML = '';
  };

  // Drag & drop pour réordonner la liste sélectionnée
  _bindDragDrop(slot.querySelector('#pe-u-selected'));

  slot.querySelector('#pe-u-cancel').onclick = () => { slot.innerHTML = ''; };

  slot.querySelector('#pe-u-save').onclick = async () => {
    const name  = slot.querySelector('#pe-u-name').value.trim();
    const icon  = slot.querySelector('#pe-u-icon').value.trim() || '◈';
    const color = slot.querySelector('#pe-u-color-hex').value.trim() || '#00c8f0';
    const mids  = [...slot.querySelectorAll('#pe-u-selected .pe-module-item')]
                    .map(el => el.dataset.module);
    if (!name)         { showToast('Nom requis'); return; }
    if (!mids.length)  { showToast('Au moins 1 module requis'); return; }
    if (!/^#[0-9a-f]{6}$/i.test(color)) { showToast('Couleur hex invalide'); return; }

    try {
      const method = isNew ? 'POST' : 'PUT';
      const url    = isNew ? '/api/universes' : `/api/universes/${universe.id}`;
      const r = await fetch(url, {
        method,
        headers: _headers(),
        body: JSON.stringify({ name, icon, color, module_ids: mids }),
      });
      if (!r.ok) throw new Error(await r.text());
      showToast(isNew ? 'Univers créé' : 'Univers mis à jour');
      slot.innerHTML = '';
      await _loadAll();
      _renderUniverses();
    } catch (e) { showToast('Erreur : ' + e.message); }
  };
}

// ════════════════════════════════════════════════════════════════
//  ONGLET 2 — PROFILS
// ════════════════════════════════════════════════════════════════

function _renderProfiles() {
  const panel = document.getElementById('pe-panel');
  if (!panel) return;

  const rows = _profiles.map(p => {
    const uNames = (p.universe_ids || [])
      .map(uid => _universes.find(u => u.id === uid)?.name || uid)
      .join(', ');
    const uPreview = uNames.length > 45 ? uNames.slice(0, 45) + '…' : uNames;
    const inUse = _devices.some(d => d.profile_id === p.id);
    return `
    <div class="pe-row" id="row-p-${p.id}">
      <div class="pe-row-body">
        <span class="pe-row-name">${_esc(p.name)}</span>
        <span class="pe-row-meta">${_esc(p.theme)} · ${_esc(p.density)} · ${_esc(uPreview || '—')}</span>
      </div>
      <button class="pe-icon-btn"           data-ep="${_esc(p.id)}" title="Modifier">✎</button>
      <button class="pe-icon-btn danger"    data-dp="${_esc(p.id)}" title="Supprimer"
              ${inUse ? 'disabled title="Utilisé par un appareil"' : ''}>🗑</button>
    </div>
    <div class="pe-editor-slot" id="slot-p-${p.id}"></div>`;
  }).join('');

  panel.innerHTML = `
    <div class="pe-section-head">
      <span class="pe-section-title">Profils d'affichage</span>
      <button class="pe-add-btn" id="btn-new-p">+ Nouveau profil</button>
    </div>
    <div id="slot-new-p"></div>
    <div id="pe-p-list">${rows || '<p class="pe-empty">Aucun profil.</p>'}</div>`;

  document.getElementById('btn-new-p').onclick = () => {
    const slot = document.getElementById('slot-new-p');
    if (slot.children.length) { slot.innerHTML = ''; return; }
    _renderProfileEditor(slot, null);
    slot.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  };
  panel.querySelectorAll('[data-ep]').forEach(btn => {
    btn.onclick = () => {
      const pid  = btn.dataset.ep;
      const slot = document.getElementById(`slot-p-${pid}`);
      if (slot.children.length) { slot.innerHTML = ''; return; }
      panel.querySelectorAll('.pe-editor-slot').forEach(s => { if (s !== slot) s.innerHTML = ''; });
      document.getElementById('slot-new-p').innerHTML = '';
      const p = _profiles.find(x => x.id === pid);
      _renderProfileEditor(slot, p);
      slot.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    };
  });
  panel.querySelectorAll('[data-dp]').forEach(btn => {
    btn.onclick = async () => {
      if (!confirm('Supprimer ce profil ?')) return;
      try {
        const r = await fetch(`/api/profiles/${btn.dataset.dp}`, { method: 'DELETE', headers: _headers() });
        if (r.status === 204 || r.ok) {
          showToast('Profil supprimé');
          await _loadAll();
          _renderProfiles();
        } else {
          showToast('Erreur suppression');
        }
      } catch (e) { showToast('Erreur : ' + e.message); }
    };
  });
}

function _renderProfileEditor(slot, profile) {
  const isNew   = !profile;
  const selUids = profile?.universe_ids || [];
  const avail   = _universes.filter(u => !selUids.includes(u.id));
  const sel     = selUids.map(id => _universes.find(u => u.id === id)).filter(Boolean);

  const themeOpts   = ['dark','light','midnight','graphite']
    .map(t => `<option value="${t}"${profile?.theme === t ? ' selected' : ''}>${t}</option>`).join('');
  const densityOpts = [['compact','Compact'],['normal','Normal'],['comfortable','Confortable']]
    .map(([v,l]) => `<option value="${v}"${profile?.density === v ? ' selected' : ''}>${l}</option>`).join('');

  const availHtml = avail.map(u => `
    <div class="pe-universe-item available" data-id="${_esc(u.id)}">
      <span class="pe-uni-dot" style="background:${_esc(u.color)}"></span>
      <span>${_esc(u.name)}</span>
    </div>`).join('');

  const selHtml = sel.map(u => `
    <div class="pe-universe-item selected" data-id="${_esc(u.id)}" draggable="true">
      <span class="pe-drag-handle">⠿</span>
      <span class="pe-uni-dot" style="background:${_esc(u.color)}"></span>
      <span>${_esc(u.name)}</span>
    </div>`).join('');

  slot.innerHTML = `
  <div class="pe-editor">
    <div class="pe-editor-row">
      <label>Nom</label>
      <input id="pe-p-name" type="text" value="${_esc(profile?.name || '')}" placeholder="Ex: Mobile" />
    </div>
    <div class="pe-editor-row pe-editor-row-inline">
      <div>
        <label>Thème</label>
        <select id="pe-p-theme">${themeOpts}</select>
      </div>
      <div>
        <label>Densité</label>
        <select id="pe-p-density">${densityOpts}</select>
      </div>
    </div>
    <div class="pe-editor-row">
      <label>Univers</label>
      <div class="pe-dual-list">
        <div class="pe-list-col">
          <div class="pe-list-title">Disponibles</div>
          <div class="pe-list-items" id="pe-p-available">${availHtml}</div>
        </div>
        <div class="pe-list-col">
          <div class="pe-list-title">Inclus <small>(glisser pour réordonner)</small></div>
          <div class="pe-list-items droppable" id="pe-p-selected">${selHtml}</div>
        </div>
      </div>
    </div>
    <div class="pe-editor-row">
      <label>Univers par défaut</label>
      <select id="pe-p-default"></select>
    </div>
    <div class="pe-editor-row">
      <label>Prévisualisation</label>
      <div class="pe-preview" id="pe-p-preview"></div>
    </div>
    <div class="pe-editor-actions">
      <button class="pe-btn-secondary" id="pe-p-cancel">Annuler</button>
      <button class="pe-btn-primary"   id="pe-p-save">${isNew ? 'Créer' : 'Enregistrer'}</button>
    </div>
  </div>`;

  // Clic disponible → sélectionné
  slot.querySelector('#pe-p-available').addEventListener('click', e => {
    const item = e.target.closest('.pe-universe-item');
    if (!item) return;
    const uid  = item.dataset.id;
    const u    = _universes.find(x => x.id === uid);
    slot.querySelector('#pe-p-selected').insertAdjacentHTML('beforeend',
      `<div class="pe-universe-item selected" data-id="${uid}" draggable="true">
         <span class="pe-drag-handle">⠿</span>
         <span class="pe-uni-dot" style="background:${_esc(u?.color || '#888')}"></span>
         <span>${_esc(u?.name || uid)}</span>
       </div>`);
    item.remove();
    _updateProfilePreview(slot, profile?.default_universe_id);
  });

  // Clic sélectionné → disponible
  slot.querySelector('#pe-p-selected').addEventListener('click', e => {
    const item = e.target.closest('.pe-universe-item');
    if (!item || e.target.classList.contains('pe-drag-handle')) return;
    const uid = item.dataset.id;
    const u   = _universes.find(x => x.id === uid);
    slot.querySelector('#pe-p-available').insertAdjacentHTML('beforeend',
      `<div class="pe-universe-item available" data-id="${uid}">
         <span class="pe-uni-dot" style="background:${_esc(u?.color || '#888')}"></span>
         <span>${_esc(u?.name || uid)}</span>
       </div>`);
    item.remove();
    _updateProfilePreview(slot, profile?.default_universe_id);
  });

  // Drag & drop univers sélectionnés
  const selList = slot.querySelector('#pe-p-selected');
  _bindDragDrop(selList);
  selList.addEventListener('dragend', () => _updateProfilePreview(slot, profile?.default_universe_id));

  // Mise à jour preview au changement de thème
  slot.querySelector('#pe-p-theme').addEventListener('change', () =>
    _updateProfilePreview(slot, profile?.default_universe_id));

  _updateProfilePreview(slot, profile?.default_universe_id);

  slot.querySelector('#pe-p-cancel').onclick = () => { slot.innerHTML = ''; };

  slot.querySelector('#pe-p-save').onclick = async () => {
    const name    = slot.querySelector('#pe-p-name').value.trim();
    const theme   = slot.querySelector('#pe-p-theme').value;
    const density = slot.querySelector('#pe-p-density').value;
    const uids    = [...slot.querySelectorAll('#pe-p-selected .pe-universe-item')]
                      .map(el => el.dataset.id);
    const defU    = slot.querySelector('#pe-p-default').value || null;
    if (!name)       { showToast('Nom requis'); return; }
    if (!uids.length){ showToast('Au moins 1 univers requis'); return; }
    if (defU && !uids.includes(defU)) { showToast('Univers par défaut non inclus'); return; }

    try {
      const method = isNew ? 'POST' : 'PUT';
      const url    = isNew ? '/api/profiles' : `/api/profiles/${profile.id}`;
      const r = await fetch(url, {
        method,
        headers: _headers(),
        body: JSON.stringify({ name, theme, density, universe_ids: uids, default_universe_id: defU }),
      });
      if (!r.ok) throw new Error(await r.text());
      showToast(isNew ? 'Profil créé' : 'Profil mis à jour');
      slot.innerHTML = '';
      await _loadAll();
      _renderProfiles();
    } catch (e) { showToast('Erreur : ' + e.message); }
  };
}

function _updateProfilePreview(slot, currentDefaultId) {
  const preview = slot.querySelector('#pe-p-preview');
  if (!preview) return;

  const theme  = slot.querySelector('#pe-p-theme')?.value || 'dark';
  const items  = [...slot.querySelectorAll('#pe-p-selected .pe-universe-item')];
  const unis   = items.map(el => _universes.find(u => u.id === el.dataset.id)).filter(Boolean);

  const THEME_COLORS = {
    dark:      { bg: '#07090d', nav: '#0a0e14', accent: '#00c8f0' },
    light:     { bg: '#f0f3f7', nav: '#f7f9fc', accent: '#0099cc' },
    midnight:  { bg: '#000308', nav: '#020810', accent: '#00d8ff' },
    graphite:  { bg: '#1a1a1e', nav: '#141416', accent: '#ff6b35' },
  };
  const c = THEME_COLORS[theme] || THEME_COLORS.dark;

  preview.innerHTML = `
  <div class="pe-preview-shell" style="background:${c.bg}">
    <div style="background:${c.nav};width:36px;display:flex;flex-direction:column;
                align-items:center;padding:6px 0;gap:4px;flex-shrink:0">
      ${unis.map(u => `
      <div style="width:22px;height:22px;border-radius:6px;
                  background:${u.color}20;border:1px solid ${u.color}60;
                  display:flex;align-items:center;justify-content:center;
                  font-size:11px" title="${_esc(u.name)}">${u.icon}</div>`).join('')}
    </div>
    <div style="flex:1;background:${c.bg};padding:10px">
      <div style="height:8px;background:${c.accent}20;border-radius:4px;margin-bottom:6px"></div>
      <div style="height:5px;background:${c.accent}10;border-radius:4px;width:70%;margin-bottom:4px"></div>
      <div style="height:5px;background:${c.accent}10;border-radius:4px;width:50%"></div>
    </div>
  </div>`;

  // Mettre à jour le select univers par défaut
  const defSel = slot.querySelector('#pe-p-default');
  if (defSel) {
    const cur = defSel.value || currentDefaultId;
    defSel.innerHTML = unis.length
      ? unis.map(u => `<option value="${u.id}"${u.id === cur ? ' selected' : ''}>${_esc(u.name)}</option>`).join('')
      : '<option value="">— aucun —</option>';
  }
}

// ════════════════════════════════════════════════════════════════
//  ONGLET 3 — APPAREILS
// ════════════════════════════════════════════════════════════════

function _renderDevices() {
  const panel = document.getElementById('pe-panel');
  if (!panel) return;

  const rows = _devices.map(d => `
  <div class="pe-row">
    <span class="pe-row-icon">${_deviceIcon(d.device_name)}</span>
    <div class="pe-row-body">
      <span class="pe-row-name">${_esc(d.device_name)}</span>
      <span class="pe-row-meta">${_esc(d.user_display_name || '—')} · ${_lastSeen(d.last_seen)}</span>
    </div>
    <select class="pe-profile-select" data-device="${_esc(d.id)}">
      <option value=""${!d.profile_id ? ' selected' : ''}>— défaut —</option>
      ${_profiles.map(p =>
        `<option value="${p.id}"${d.profile_id === p.id ? ' selected' : ''}>${_esc(p.name)}</option>`
      ).join('')}
    </select>
  </div>`).join('');

  panel.innerHTML = `
    <div class="pe-section-head">
      <span class="pe-section-title">Appareils enregistrés</span>
    </div>
    <div id="pe-d-list">${rows || '<p class="pe-empty">Aucun appareil enregistré.</p>'}</div>`;

  panel.querySelectorAll('.pe-profile-select').forEach(sel => {
    sel.addEventListener('change', async () => {
      const deviceId  = sel.dataset.device;
      const profileId = sel.value || null;
      try {
        const r = await fetch(`/api/devices/${deviceId}/profile`, {
          method: 'POST',
          headers: _headers(),
          body: JSON.stringify({ profile_id: profileId }),
        });
        if (!r.ok) throw new Error(await r.text());
        showToast('Profil mis à jour');
        const dev = _devices.find(d => d.id === deviceId);
        if (dev) dev.profile_id = profileId;
      } catch (e) { showToast('Erreur : ' + e.message); }
    });
  });
}

// ════════════════════════════════════════════════════════════════
//  HELPERS
// ════════════════════════════════════════════════════════════════

function _groupByCategory(modules) {
  const result = {};
  const ORDER  = ['core', 'maison', 'societe', 'transversal', 'tools'];
  for (const m of modules) {
    const cat = m.category || 'tools';
    if (!result[cat]) result[cat] = [];
    result[cat].push(m);
  }
  // Trier les catégories
  const sorted = {};
  for (const c of ORDER) { if (result[c]) sorted[c] = result[c]; }
  for (const c of Object.keys(result)) { if (!sorted[c]) sorted[c] = result[c]; }
  return sorted;
}

const CAT_LABELS = {
  core: 'Core', maison: 'Maison', societe: 'Société',
  transversal: 'Transversal', tools: 'Outils',
};
function _catLabel(cat) { return CAT_LABELS[cat] || cat; }

function _buildAvailableModules(byCategory, selected) {
  return Object.entries(byCategory).map(([cat, mods]) => {
    const filtered = mods.filter(m => !selected.includes(m.id));
    if (!filtered.length) return '';
    return `
    <div class="pe-cat-label">${_catLabel(cat)}</div>
    ${filtered.map(m =>
      `<div class="pe-module-item available" data-module="${m.id}">
         <span class="pe-module-label">${_esc(m.label)}</span>
       </div>`).join('')}`;
  }).join('');
}

function _buildSelectedModules(selected) {
  return selected.map(id => {
    const m = _modules.find(x => x.id === id);
    return `
    <div class="pe-module-item selected" data-module="${id}" draggable="true">
      <span class="pe-drag-handle">⠿</span>
      <span class="pe-module-label">${_esc(m?.label || id)}</span>
    </div>`;
  }).join('');
}

function _addToAvailable(availEl, mid, label, cat) {
  // Trouver ou créer la section de catégorie
  let catEl = availEl.querySelector(`.pe-cat-label[data-cat="${cat}"]`);
  if (!catEl) {
    catEl = document.createElement('div');
    catEl.className = 'pe-cat-label';
    catEl.dataset.cat = cat;
    catEl.textContent = _catLabel(cat);
    availEl.appendChild(catEl);
  }
  const item = document.createElement('div');
  item.className = 'pe-module-item available';
  item.dataset.module = mid;
  item.innerHTML = `<span class="pe-module-label">${_esc(label)}</span>`;
  catEl.insertAdjacentElement('afterend', item);
}

function _cleanEmptyCategories(availEl) {
  availEl.querySelectorAll('.pe-cat-label').forEach(lbl => {
    const next = lbl.nextElementSibling;
    if (!next || next.classList.contains('pe-cat-label')) lbl.remove();
  });
}

function _bindDragDrop(listEl) {
  let dragged = null;
  listEl.addEventListener('dragstart', e => {
    dragged = e.target.closest('[draggable="true"]');
    setTimeout(() => dragged?.classList.add('dragging'), 0);
  });
  listEl.addEventListener('dragend', () => {
    dragged?.classList.remove('dragging');
    dragged = null;
  });
  listEl.addEventListener('dragover', e => {
    e.preventDefault();
    const target = e.target.closest('[draggable="true"]');
    if (target && dragged && target !== dragged) {
      const rect  = target.getBoundingClientRect();
      const after = e.clientY > rect.top + rect.height / 2;
      listEl.insertBefore(dragged, after ? target.nextSibling : target);
    }
  });
}

function _deviceIcon(name) {
  const n = (name || '').toLowerCase();
  if (n.includes('phone') || n.includes('iphone') || n.includes('mobile')) return '📱';
  if (n.includes('tablet') || n.includes('ipad'))  return '📱';
  if (n.includes('tv') || n.includes('salon'))     return '📺';
  if (n.includes('mac') || n.includes('pc') || n.includes('bureau') || n.includes('desktop')) return '🖥';
  return '📟';
}

function _lastSeen(ts) {
  if (!ts) return 'jamais';
  const diff = Math.floor(Date.now() / 1000 - ts);
  if (diff < 60)    return 'à l\'instant';
  if (diff < 3600)  return `il y a ${Math.floor(diff / 60)} min`;
  if (diff < 86400) return `il y a ${Math.floor(diff / 3600)} h`;
  return `il y a ${Math.floor(diff / 86400)} j`;
}

function _ensureCSS() {
  if (!document.getElementById('css-profile-editor')) {
    const l = document.createElement('link');
    l.id = 'css-profile-editor'; l.rel = 'stylesheet'; l.href = _CSS;
    document.head.appendChild(l);
  }
}
