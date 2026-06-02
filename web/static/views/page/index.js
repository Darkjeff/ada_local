/* ================================================================
   Vue Page — mount / unmount
   Vue générique pour les modules ADA (Planificateur, Domotique…).
   Affiche : description + boutons d'actions + données contextuelles.
   ================================================================ */
import { escapeHtml, fetchJSON, showToast, switchView } from '/static/core/core.js';

const _CSS = '/static/views/page/style.css';

function _ensureCSS() {
  if (!document.getElementById('css-page')) {
    const l = document.createElement('link');
    l.id = 'css-page'; l.rel = 'stylesheet'; l.href = _CSS;
    document.head.appendChild(l);
  }
}

// ── Configuration des pages ─────────────────────────────────────
const PAGE_CONFIG = {
  planner: {
    description: 'Gérez votre agenda et vos tâches.',
    actions: [
      'Quelles sont mes tâches et mon planning du jour ?',
      'Ajoute une tâche : vérifier les sauvegardes ce soir.',
      'Ajoute un événement demain à 14h : réunion projet ADA.',
    ],
  },
  briefing: {
    description: 'Préparez un briefing complet (météo, actualités, agenda).',
    actions: [
      'Fais-moi un briefing de la journée : météo, actualités, agenda.',
      'Donne-moi un briefing court orienté productivité.',
    ],
  },
  home: {
    description: 'Contrôle domotique et état des équipements connectés.',
    actions: [
      'Montre-moi l\'état de mes lumières et appareils connectés.',
      'Allume les lumières du bureau.',
      'Éteins toutes les lumières.',
    ],
  },
  cad: {
    description: 'Conception 3D assistée et génération de modèles STL.',
    actions: [
      'Génère un modèle 3D en STL pour moi.',
      'Crée un boîtier 3D simple pour Raspberry Pi.',
    ],
  },
  web: {
    description: 'Recherche web assistée, synthèse et réponses contextualisées.',
    actions: [
      'Fais une recherche sur le web pour moi.',
      'Cherche les dernières nouvelles IA en France.',
    ],
  },
  printers: {
    description: 'Suivi des imprimantes et statut d\'impression 3D.',
    actions: [
      'Quel est le statut de mes imprimantes 3D ?',
      'Montre la progression des impressions en cours.',
    ],
  },
  skills: {
    description: 'Vue des compétences disponibles et capacités actives.',
    actions: [
      'Quelles sont mes compétences et skills disponibles ?',
      'Montre les skills toujours actives.',
    ],
  },
  senses: {
    description: 'Consultez les données capteurs et mesures en temps réel.',
    actions: [
      'Donne-moi les données des capteurs disponibles.',
      'Quels capteurs ont changé récemment ?',
    ],
  },
  music: {
    description: 'Pilotage musique (lecture, contrôle, volume).',
    actions: [
      'Joue de la musique.',
      'Mets du jazz.',
      'Passe à la chanson suivante.',
    ],
  },
  library: {
    description: 'Recherche dans la bibliothèque Calibre.',
    actions: [
      'Cherche un livre dans ma bibliothèque Calibre.',
      'Trouve un livre de science-fiction.',
    ],
  },
  infrastructure: {
    description: 'État des services ADA (Ollama, n8n, Home Assistant, Docker).',
    actions: [
      'Montre-moi l\'état de l\'infrastructure.',
      'Y a-t-il des alertes sur l\'infrastructure ?',
    ],
  },
};

// ── Rendu des données contextuelles ─────────────────────────────
async function _renderInfra(data, el) {
  const docker   = data.docker   || {};
  const warnings = data.warnings || [];

  // Fetch services, endpoints, tags in parallel
  let builtinSvcs = [], customEps = [], availTags = ['local'];
  try {
    [builtinSvcs, customEps, availTags] = await Promise.all([
      fetchJSON('/api/infra/services'),
      fetchJSON('/api/infra/endpoints'),
      fetchJSON('/api/tags/available'),
    ]);
    if (!Array.isArray(builtinSvcs)) builtinSvcs = [];
    if (!Array.isArray(customEps))   customEps   = [];
    if (!Array.isArray(availTags))   availTags   = ['local'];
  } catch {}

  // Merge into unified list
  const allItems = [
    ...builtinSvcs.map(s => ({ ...s, builtin: true,  url: '' })),
    ...customEps .map(e => ({ ...e, builtin: false, status: e.status || 'unknown' })),
  ];

  const containers = (docker.containers || []).slice(0, 8).map(
    c => `<li>${escapeHtml(c.name)} · ${escapeHtml(c.status || '')}</li>`
  ).join('');

  const warHtml = warnings.length
    ? `<ul class="page-list">${warnings.map(w => `<li>${escapeHtml(w)}</li>`).join('')}</ul>`
    : `<p class="page-muted">Aucune alerte.</p>`;

  const tagOptsSel = availTags.map(t => `<option value="${escapeHtml(t)}">${escapeHtml(t)}</option>`).join('');
  const tagOptsAll = `<option value="">Tous les tags</option>${tagOptsSel}`;

  function _dot(status) {
    const map = { online: '#00ff9d', offline: '#ff3b5c', unknown: '#ffa500' };
    return `<span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:${map[status]||'#888'};flex-shrink:0"></span>`;
  }

  function _tagChips(tags) {
    return (tags || ['local']).map(t => `<span class="ep-tag">${escapeHtml(t)}</span>`).join('');
  }

  function _tagSel(id, tags) {
    return `<select class="ep-tag-sel" id="${id}" multiple title="Tags">${
      availTags.map(t => `<option value="${escapeHtml(t)}"${(tags||[]).includes(t)?' selected':''}>${escapeHtml(t)}</option>`).join('')
    }</select>`;
  }

  function _rowHtml(item) {
    const dim = item.hidden ? 'opacity:0.38;' : '';
    const svcLabel = item.name === 'home_assistant' ? 'Home Assistant' : item.name;
    const urlPart = item.url
      ? `<a href="${escapeHtml(item.url)}" target="_blank" class="ep-url">${escapeHtml(item.url)}</a>`
      : `<span class="ep-url" style="color:#3a4a5a">${escapeHtml(item.status||'')}</span>`;
    const selId = `ts-${escapeHtml(item.name).replace(/\./g,'-')}`;
    const actionBtn = item.builtin
      ? `<button class="ep-hide" data-svc="${escapeHtml(item.name)}" data-hidden="${item.hidden}" title="${item.hidden?'Afficher':'Masquer'}">${item.hidden?'👁':'🙈'}</button>`
      : `<button class="ep-del" data-ep="${escapeHtml(item.name)}" title="Supprimer">✕</button>`;
    return `<div class="ep-row${item.hidden?' ep-hidden':''}" data-name="${escapeHtml(item.name)}" data-status="${item.status||'unknown'}" data-tags="${escapeHtml(JSON.stringify(item.tags||[]))}" style="${dim}">
      ${_dot(item.status||'unknown')}
      <span class="ep-name">${escapeHtml(svcLabel)}</span>
      ${urlPart}
      <div class="ep-tags">${_tagChips(item.tags)}</div>
      ${_tagSel(selId, item.tags)}
      <button class="ep-tag-save" data-name="${escapeHtml(item.name)}" data-builtin="${item.builtin}" data-selid="${selId}" title="Sauvegarder les tags">💾</button>
      ${actionBtn}
    </div>`;
  }

  const tagOpts = availTags.map(t => `<option value="${escapeHtml(t)}">${escapeHtml(t)}</option>`).join('');

  el.innerHTML = `
    <section class="page-panel" id="svc-panel">
      <div style="display:flex;align-items:center;gap:8px;margin-bottom:10px;flex-wrap:wrap">
        <h3 style="margin:0;flex:none">Services</h3>
        <select id="filter-status" style="padding:3px 7px;background:#111820;border:1px solid rgba(255,255,255,0.1);border-radius:6px;color:#e8edf2;font-size:11px">
          <option value="">Tous les états</option>
          <option value="online">En ligne</option>
          <option value="offline">Hors ligne</option>
          <option value="unknown">Inconnu</option>
        </select>
        <select id="filter-tag" style="padding:3px 7px;background:#111820;border:1px solid rgba(255,255,255,0.1);border-radius:6px;color:#e8edf2;font-size:11px">
          ${tagOptsAll}
        </select>
        <label style="font-size:11px;color:#5a6a7a;display:flex;align-items:center;gap:4px;cursor:pointer">
          <input type="checkbox" id="filter-hidden" style="cursor:pointer"> Voir masqués
        </label>
      </div>
      <div id="svc-list">${allItems.map(_rowHtml).join('') || '<p class="page-muted">Aucun service.</p>'}</div>
      <form id="ep-add-form" style="display:flex;gap:6px;margin-top:10px;flex-wrap:wrap">
        <input id="ep-name" placeholder="Nom" style="flex:1;min-width:100px;padding:5px 8px;background:#111820;border:1px solid rgba(255,255,255,0.1);border-radius:6px;color:#e8edf2;font-size:12px">
        <input id="ep-url"  placeholder="URL (https://…)" style="flex:2;min-width:160px;padding:5px 8px;background:#111820;border:1px solid rgba(255,255,255,0.1);border-radius:6px;color:#e8edf2;font-size:12px">
        <select id="ep-tags" multiple title="Tags" style="min-width:120px;padding:4px 6px;background:#111820;border:1px solid rgba(255,255,255,0.1);border-radius:6px;color:#e8edf2;font-size:11px">${tagOpts}</select>
        <button type="submit" style="padding:5px 12px;background:rgba(0,212,255,0.1);border:1px solid rgba(0,212,255,0.4);border-radius:6px;color:#00d4ff;font-size:12px;cursor:pointer">+ Ajouter</button>
      </form>
      <style>
        .ep-row{display:flex;align-items:center;gap:8px;padding:6px 0;border-bottom:1px solid rgba(255,255,255,0.04)}
        .ep-row.ep-hidden{border-bottom-style:dashed}
        .ep-name{font-size:12px;font-weight:700;color:#e8edf2;min-width:90px}
        .ep-url{font-size:11px;color:#5a6a7a;text-decoration:none;flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
        .ep-url:hover{color:#00d4ff}
        .ep-tags{display:flex;gap:4px;flex-wrap:wrap;min-width:40px}
        .ep-tag{font-size:9px;padding:1px 6px;border-radius:8px;background:rgba(0,212,255,0.1);border:1px solid rgba(0,212,255,0.2);color:#00d4ff}
        .ep-tag-sel{font-size:10px;padding:2px 4px;background:#111820;border:1px solid rgba(255,255,255,0.1);border-radius:4px;color:#e8edf2;height:48px}
        .ep-tag-save,.ep-del,.ep-hide{background:none;border:none;cursor:pointer;color:#5a6a7a;font-size:11px;padding:2px 5px}
        .ep-tag-save:hover{color:#00ff9d}.ep-del:hover{color:#ff3b5c}.ep-hide:hover{color:#ffa500}
      </style>
    </section>
    <section class="page-panel"><h3>Docker</h3>
      ${containers ? `<ul class="page-list">${containers}</ul>` : '<p class="page-muted">Aucun container actif.</p>'}
    </section>
    <section class="page-panel"><h3>Alertes</h3>${warHtml}</section>`;

  const panel = el.querySelector('#svc-panel');

  // ── Filter logic ─────────────────────────────────────────────────────────
  function _applyFilters() {
    const stF = panel.querySelector('#filter-status').value;
    const tgF = panel.querySelector('#filter-tag').value;
    const showHidden = panel.querySelector('#filter-hidden').checked;
    panel.querySelectorAll('.ep-row').forEach(row => {
      const status  = row.dataset.status || '';
      const rowTags = JSON.parse(row.dataset.tags || '[]');
      const hidden  = row.classList.contains('ep-hidden');
      let show = true;
      if (!showHidden && hidden) show = false;
      if (stF && status !== stF) show = false;
      if (tgF && !rowTags.includes(tgF)) show = false;
      row.style.display = show ? '' : 'none';
    });
  }

  panel.querySelector('#filter-status').addEventListener('change', _applyFilters);
  panel.querySelector('#filter-tag').addEventListener('change', _applyFilters);
  panel.querySelector('#filter-hidden').addEventListener('change', _applyFilters);

  // ── Save tags ─────────────────────────────────────────────────────────────
  panel.querySelectorAll('.ep-tag-save').forEach(btn => {
    btn.addEventListener('click', async () => {
      const name    = btn.dataset.name;
      const builtin = btn.dataset.builtin === 'true';
      const sel     = panel.querySelector(`#${btn.dataset.selid}`);
      const tags    = Array.from(sel.selectedOptions).map(o => o.value);
      const url = builtin
        ? `/api/infra/services/${encodeURIComponent(name)}/tags`
        : `/api/infra/endpoints/${encodeURIComponent(name)}/tags`;
      await fetch(url, { method: 'PATCH', headers: {'Content-Type':'application/json'}, body: JSON.stringify({tags}) });
      if (typeof showToast === 'function') showToast('Tags mis à jour');
      _renderInfra(data, el);
    });
  });

  // ── Hide / show built-in services ─────────────────────────────────────────
  panel.querySelectorAll('.ep-hide').forEach(btn => {
    btn.addEventListener('click', async () => {
      const name   = btn.dataset.svc;
      const hidden = btn.dataset.hidden !== 'true';
      await fetch(`/api/infra/services/${encodeURIComponent(name)}/hidden`, {
        method: 'PATCH', headers: {'Content-Type':'application/json'},
        body: JSON.stringify({hidden})
      });
      _renderInfra(data, el);
    });
  });

  // ── Delete custom endpoint ────────────────────────────────────────────────
  panel.querySelectorAll('.ep-del').forEach(btn => {
    btn.addEventListener('click', async () => {
      if (!confirm(`Supprimer "${btn.dataset.ep}" ?`)) return;
      await fetch(`/api/infra/endpoints/${encodeURIComponent(btn.dataset.ep)}`, {method:'DELETE'});
      _renderInfra(data, el);
    });
  });

  // ── Add custom endpoint ───────────────────────────────────────────────────
  panel.querySelector('#ep-add-form').addEventListener('submit', async e => {
    e.preventDefault();
    const name = panel.querySelector('#ep-name').value.trim();
    const url  = panel.querySelector('#ep-url').value.trim();
    const sel  = panel.querySelector('#ep-tags');
    const tags = Array.from(sel.selectedOptions).map(o => o.value);
    if (!name || !url) return;
    await fetch('/api/infra/endpoints', {
      method: 'POST', headers: {'Content-Type':'application/json'},
      body: JSON.stringify({name, url, tags: tags.length ? tags : ['local']})
    });
    panel.querySelector('#ep-name').value = '';
    panel.querySelector('#ep-url').value  = '';
    _renderInfra(data, el);
  });
}

function _renderHome(data, el) {
  const entities  = data.entities  || [];
  const providers = data.providers || [];

  // ── Icônes et labels ─────────────────────────────────────────────────────
  const _SC  = { connected:'var(--green)', online:'var(--green)', disconnected:'#ff3b5c', offline:'#ff3b5c', error:'#ff3b5c', unknown:'#ffa500' };
  const _PI  = { kasa:'🔌', home_assistant:'🏠', domoticz:'🏗' };
  const _TI  = { light:'💡', switch:'🔌', media_player:'🎵', sensor:'🌡', binary_sensor:'📡', camera:'📷' };
  const _TL  = { sensor:'Capteurs', binary_sensor:'Capteurs binaires', media_player:'Lecteurs', camera:'Caméras', unknown:'Autres' };

  // ── 1. Barre providers ───────────────────────────────────────────────────
  const provBadges = providers.map(p => {
    const c = _SC[p.status] || '#888';
    return `<span class="domo-prov-badge">
      <i style="width:7px;height:7px;border-radius:50%;background:${c};display:inline-block;flex-shrink:0;vertical-align:middle"></i>
      ${_PI[p.id] || '📡'} ${escapeHtml(p.name)}
      <span style="color:${c};font-size:9px;margin-left:3px">${escapeHtml(p.status || '?')}</span>
    </span>`;
  }).join('');

  // ── 2. Entités par catégorie ──────────────────────────────────────────────
  const domo_scenes    = entities.filter(e => e.type === 'scene');
  const controllable   = entities.filter(e => ['light','switch'].includes(e.type));
  const informational  = entities.filter(e => !['light','switch','scene'].includes(e.type));

  // Scènes Domoticz → boutons d'activation (1 clic, pas de toggle)
  const domoSceneItems = domo_scenes.map(e => {
    const isOn = e.state === 'on';
    return `<button class="scene-btn${isOn ? ' on' : ''}" data-entity-id="${escapeHtml(e.id)}">${escapeHtml(e.name)}</button>`;
  }).join('');

  const _onCount = controllable.filter(e => e.state === 'on').length;
  const toggleItems = controllable.map(e => {
    const isOn = e.state === 'on';
    let sub = (e.zone && e.zone !== 'Other') ? e.zone : '';
    if (e.attributes?.brightness  != null) sub += (sub ? ' · ' : '') + `${Math.round(e.attributes.brightness / 2.55)}%`;
    else if (e.attributes?.temperature != null) sub += (sub ? ' · ' : '') + `${e.attributes.temperature}°`;
    const icon = _TI[e.type] || '⚡';
    return `<div class="dev-card" data-id="${escapeHtml(e.id)}" data-provider="${escapeHtml(e.provider)}" data-name="${escapeHtml(e.name.toLowerCase())}" data-active="${isOn ? '1' : '0'}"${!isOn ? ' hidden' : ''}>
      <div style="display:flex;justify-content:space-between;align-items:flex-start"><span>${icon}</span><div class="sw${isOn ? ' on' : ''}"></div></div>
      <div class="dev-n">${escapeHtml(e.name)}</div>
      ${sub ? `<div class="dev-s">${escapeHtml(sub)}</div>` : ''}
    </div>`;
  }).join('');

  // ── 4. Capteurs et autres → panneaux info ────────────────────────────────
  const byType = {};
  for (const e of informational) (byType[e.type || 'unknown'] ||= []).push(e);

  const infoPanels = Object.keys(byType).map(type => {
    const icon = _TI[type] || '📡';
    const cards = byType[type].map(e => {
      const stRaw  = e.state || '?';
      const unit   = e.attributes?.unit_of_measurement || '';
      return `<div class="sensor-card">
        <div class="sensor-icon">${icon}</div>
        <div class="sensor-val">${escapeHtml(stRaw)}<span style="font-size:9px;font-weight:400">${escapeHtml(unit)}</span></div>
        <div class="sensor-lbl">${escapeHtml(e.name)}</div>
      </div>`;
    }).join('');
    return `<div style="margin-top:6px"><div class="sec">${escapeHtml(_TL[type] || type)}</div><div class="toggle-grid-4">${cards}</div></div>`;
  }).join('');

  el.innerHTML = `
    <div class="domo-wrap">
      ${providers.length ? `<div class="domo-prov-bar">${provBadges}</div>` : ''}
      <div class="sec">Scènes</div>
      <div class="scene-row" id="domo-entity-scenes">
        ${domoSceneItems || '<span style="color:var(--text-dim);font-size:11px">Aucune scène disponible</span>'}
      </div>
      ${controllable.length ? `
        <div class="sec" style="display:flex;align-items:center;justify-content:space-between">
          <span>Groupes &amp; Appareils <span id="domo-dev-count" style="font-size:10px;font-weight:400;color:var(--text-dim)">${_onCount} actif${_onCount > 1 ? 's' : ''} · ${controllable.length} total</span></span>
          <button id="domo-show-all" class="scene-btn" style="padding:2px 8px;font-size:10px;margin:0">Tout afficher</button>
        </div>
        <input id="domo-search" class="domo-search" placeholder="🔍 Rechercher un appareil…">
        <div class="toggle-grid-4" id="domo-toggles">${toggleItems}</div>
      ` : `<p class="page-muted" style="margin-top:12px">Aucune entité contrôlable. Vérifiez la configuration des providers.</p>`}
      ${infoPanels}
    </div>
    <style>
      .domo-wrap{display:flex;flex-direction:column;padding:2px 0;grid-column:1/-1}
      .domo-prov-bar{display:flex;gap:8px;flex-wrap:wrap;padding:6px 0 10px;border-bottom:1px solid var(--border);margin-bottom:2px}
      .domo-prov-badge{display:inline-flex;align-items:center;gap:5px;font-size:11px;padding:4px 10px;border-radius:20px;background:var(--surface);border:1px solid var(--border);color:var(--text)}
    </style>`;

  // Scènes Domoticz : click → POST /api/entity/<id>/toggle (on=true = activate)
  const domoSceneBar = el.querySelector('#domo-entity-scenes');
  if (domoSceneBar) {
    domoSceneBar.addEventListener('click', e => {
      const btn = e.target.closest('.scene-btn');
      if (!btn) return;
      const id = btn.dataset.entityId;
      if (!id) return;
      btn.classList.add('on');
      fetch(`/api/entity/${encodeURIComponent(id)}/toggle`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ on: true }),
      }).then(r => r.json()).then(d => {
        if (!d.ok) btn.classList.remove('on');
        // Retire le highlight après 2s (scène = action ponctuelle)
        setTimeout(() => btn.classList.remove('on'), 2000);
      }).catch(() => btn.classList.remove('on'));
    });
  }

  // Toggles groupes/appareils : click → POST /api/entity/<id>/toggle
  const grid = el.querySelector('#domo-toggles');
  if (grid) {
    // ── Filtre recherche / actifs ──────────────────────────────────────────
    let _showAll = false;
    function _domoFilter(q) {
      const q2 = (q || '').toLowerCase().trim();
      let active = 0, total = 0;
      grid.querySelectorAll('.dev-card').forEach(c => {
        total++;
        const match = !q2 || (c.dataset.name || '').includes(q2);
        const on = c.dataset.active === '1';
        if (on) active++;
        c.hidden = !(match && (_showAll || on));
      });
      const cnt = el.querySelector('#domo-dev-count');
      if (cnt) cnt.textContent = active + ' actif' + (active > 1 ? 's' : '') + ' · ' + total + ' total';
    }
    const searchInput = el.querySelector('#domo-search');
    const showAllBtn  = el.querySelector('#domo-show-all');
    if (searchInput) searchInput.addEventListener('input', e => _domoFilter(e.target.value));
    if (showAllBtn)  showAllBtn.addEventListener('click', () => {
      _showAll = !_showAll;
      showAllBtn.textContent = _showAll ? 'Actifs seuls' : 'Tout afficher';
      _domoFilter(searchInput?.value || '');
    });

    // ── Toggle switch ──────────────────────────────────────────────────────
    grid.addEventListener('click', e => {
      const sw = e.target.closest('.sw');
      if (!sw) return;
      const card = sw.closest('.dev-card');
      const id   = card?.dataset.id;
      if (!id) return;
      const isOn = sw.classList.toggle('on');
      card.dataset.active = isOn ? '1' : '0';
      _domoFilter(searchInput?.value || '');
      fetch(`/api/entity/${encodeURIComponent(id)}/toggle`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${localStorage.getItem('ada_token') || ''}` },
        body: JSON.stringify({ on: isOn }),
      }).then(r => r.json()).then(d => {
        if (!d.ok) { sw.classList.toggle('on'); card.dataset.active = isOn ? '0' : '1'; _domoFilter(searchInput?.value || ''); }
      }).catch(() => { sw.classList.toggle('on'); card.dataset.active = isOn ? '0' : '1'; _domoFilter(searchInput?.value || ''); });
    });
  }
}

function _renderSkills(data, el) {
  const skills = data.skills || [];
  let currentIdx = 0;

  // Build list HTML
  function buildCardsHtml() {
    if (!skills.length) return '<p class="page-muted">Aucune compétence.</p>';
    return skills.map((s, i) => {
      const badge = s.always ? '<span class="sk-always-badge">always-on</span>' : '';
      return `<button class="sk-card${i === currentIdx ? ' sk-card--active' : ''}" data-idx="${i}" type="button">
        <div class="sk-card-row"><span class="sk-card-name">${escapeHtml(s.name)}</span>${badge}</div>
        ${s.description ? `<span class="sk-card-desc">${escapeHtml(s.description)}</span>` : ''}
      </button>`;
    }).join('');
  }

  el.innerHTML = `
    <div class="skills-wrap">
      <aside class="skills-list">
        <div class="sk-list-header">
          <span class="sk-count">${skills.length} compétence${skills.length > 1 ? 's' : ''}</span>
          <button class="sk-btn sk-btn-add" id="sk-add-btn" title="Nouvelle compétence" type="button">+ Ajouter</button>
        </div>
        <div id="sk-cards">${buildCardsHtml()}</div>
      </aside>
      <div class="skills-detail" id="skills-detail"></div>
    </div>`;

  // ── Detail (read) ───────────────────────────────────────────────────────
  function showDetail(i) {
    currentIdx = i;
    // Update active card
    el.querySelectorAll('.sk-card').forEach((b, idx) =>
      b.classList.toggle('sk-card--active', idx === i));
    const s = skills[i];
    const detailEl = el.querySelector('#skills-detail');
    const badge = s.always ? '<span class="sk-always-badge">always-on</span>' : '';
    const triggersHtml = (s.triggers || []).length
      ? s.triggers.map(t => `<span class="sk-trigger">${escapeHtml(t)}</span>`).join('')
      : '<span class="page-muted">—</span>';
    const bodyHtml = s.body
      ? `<pre class="sk-body">${escapeHtml(s.body)}</pre>`
      : '<p class="page-muted">Aucun contenu.</p>';
    detailEl.innerHTML = `
      <div class="sk-detail-header">
        <h2 class="sk-detail-name">${escapeHtml(s.name)}</h2>${badge}
        <button class="sk-btn sk-btn-edit" data-name="${escapeHtml(s.name)}" type="button">Modifier</button>
      </div>
      ${s.description ? `<p class="sk-detail-desc">${escapeHtml(s.description)}</p>` : ''}
      <div class="sk-detail-section">
        <span class="sk-section-label">Déclencheurs</span>
        <div class="sk-triggers-wrap">${triggersHtml}</div>
      </div>
      <div class="sk-detail-section">
        <span class="sk-section-label">Instructions injectées</span>
        ${bodyHtml}
      </div>`;
    detailEl.querySelector('.sk-btn-edit').addEventListener('click', () => showForm(s));
  }

  // ── Form (edit / create) ────────────────────────────────────────────────
  function showForm(skill) {
    const isNew = !skill;
    const s = skill || { name: '', description: '', triggers: [], body: '', always: false };
    const detailEl = el.querySelector('#skills-detail');
    detailEl.innerHTML = `
      <div class="sk-form">
        <div class="sk-form-title">${isNew ? 'Nouvelle compétence' : `Modifier — ${escapeHtml(s.name)}`}</div>
        ${isNew ? `
          <label class="sk-field-label">Nom (identifiant unique)</label>
          <input class="sk-field-input" id="sk-f-name" type="text" placeholder="ma_competence" value="" />
        ` : ''}
        <label class="sk-field-label">Description</label>
        <input class="sk-field-input" id="sk-f-desc" type="text" placeholder="Description courte" value="${escapeHtml(s.description || '')}" />
        <label class="sk-field-label">Déclencheurs (séparés par des virgules)</label>
        <input class="sk-field-input" id="sk-f-triggers" type="text" placeholder="recette, cuisine, ingrédient" value="${escapeHtml((s.triggers || []).join(', '))}" />
        <label class="sk-field-label">Instructions injectées</label>
        <textarea class="sk-field-textarea" id="sk-f-body" rows="10" placeholder="Tu es un expert en...">${escapeHtml(s.body || '')}</textarea>
        <div class="sk-form-actions">
          <button class="sk-btn sk-btn-cancel" id="sk-f-cancel" type="button">Annuler</button>
          <button class="sk-btn sk-btn-save" id="sk-f-save" type="button">${isNew ? 'Créer' : 'Sauvegarder'}</button>
        </div>
        <p class="sk-form-error hidden" id="sk-f-error"></p>
      </div>`;

    detailEl.querySelector('#sk-f-cancel').addEventListener('click', () => {
      if (!isNew) showDetail(currentIdx);
      else if (skills.length) showDetail(0);
      else detailEl.innerHTML = '';
    });

    detailEl.querySelector('#sk-f-save').addEventListener('click', async () => {
      const saveBtn = detailEl.querySelector('#sk-f-save');
      const errEl   = detailEl.querySelector('#sk-f-error');
      const name    = isNew ? detailEl.querySelector('#sk-f-name').value.trim() : s.name;
      const desc    = detailEl.querySelector('#sk-f-desc').value.trim();
      const triggers = detailEl.querySelector('#sk-f-triggers').value
        .split(',').map(t => t.trim()).filter(Boolean);
      const body = detailEl.querySelector('#sk-f-body').value;

      if (!name) { errEl.textContent = 'Le nom est requis.'; errEl.classList.remove('hidden'); return; }
      saveBtn.disabled = true; saveBtn.textContent = '…';
      try {
        const url  = isNew ? '/api/skills' : `/api/skills/${encodeURIComponent(name)}`;
        const method = isNew ? 'POST' : 'PUT';
        const resp = await fetch(url, {
          method,
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ name, description: desc, triggers, body }),
        });
        if (!resp.ok) {
          const e = await resp.json().catch(() => ({ detail: resp.statusText }));
          throw new Error(e.detail || 'Erreur serveur');
        }
        // Reload skills list
        const fresh = await fetchJSON('/api/page/skills');
        _renderSkills(fresh, el);
        // Select the skill we just saved
        const newIdx = (fresh.skills || []).findIndex(x => x.name === name);
        if (newIdx >= 0) {
          // showDetail is bound inside the new _renderSkills call but we need a tiny delay
          setTimeout(() => el.querySelectorAll('.sk-card')[newIdx]?.click(), 50);
        }
      } catch (err) {
        errEl.textContent = err.message;
        errEl.classList.remove('hidden');
        saveBtn.disabled = false;
        saveBtn.textContent = isNew ? 'Créer' : 'Sauvegarder';
      }
    });
  }

  // ── Wire clicks ─────────────────────────────────────────────────────────
  el.querySelector('#sk-cards').addEventListener('click', e => {
    const btn = e.target.closest('.sk-card');
    if (btn) showDetail(Number(btn.dataset.idx));
  });
  el.querySelector('#sk-add-btn').addEventListener('click', () => showForm(null));

  // Show first skill (or empty state)
  if (skills.length) showDetail(0);
  else showForm(null);
}

async function _loadData(pageKey, el) {
  el.innerHTML = '<section class="page-panel"><p class="page-muted">Chargement…</p></section>';
  try {
    if (pageKey === 'infrastructure') { _renderInfra(await fetchJSON('/api/page/infrastructure'), el); return; }
    if (pageKey === 'skills')         { _renderSkills(await fetchJSON('/api/page/skills'), el); return; }
    if (pageKey === 'home')           { _renderHome(await fetchJSON('/api/page/home'), el); return; }
    el.innerHTML = '';  // aucune donnée contextuelle pour les autres pages
  } catch {
    el.innerHTML = '<section class="page-panel"><p class="page-muted">Données indisponibles.</p></section>';
  }
}

// ── État local ──────────────────────────────────────────────────
let _root = null;

export async function mount(vp, opts = {}) {
  _ensureCSS();
  const { page: pageKey = '', hint = '', label = '' } = opts;
  const cfg = PAGE_CONFIG[pageKey] || { description: 'Module ADA.', actions: hint ? [hint] : [] };

  _root = document.createElement('div');
  _root.className = 'view-root page-view';

  const actionsHtml = cfg.actions.map((a) =>
    `<button class="page-action-btn" data-prompt="${escapeHtml(a)}">${escapeHtml(a)}</button>`
  ).join('');

  _root.innerHTML = `
    <div class="page-shell">
      ${pageKey === 'home' ? '' : `<div class="page-top">
        <h2 class="page-title">${escapeHtml(label || pageKey)}</h2>
        <p class="page-desc">${escapeHtml(cfg.description)}</p>
      </div>`}
      <div class="page-data-wrap" id="page-data-wrap"></div>
      ${pageKey === 'home' ? '' : `<div class="page-actions">${actionsHtml}</div>`}
    </div>`;

  vp.appendChild(_root);

  // Clic sur un bouton d'action → chat avec le prompt
  _root.querySelectorAll('.page-action-btn').forEach((btn) => {
    btn.addEventListener('click', () => {
      switchView('chat', { prefill: btn.dataset.prompt, label: 'Discussion' });
    });
  });

  // Données contextuelles (infrastructure, skills)
  await _loadData(pageKey, _root.querySelector('#page-data-wrap'));
}

export function unmount() {
  _root?.remove();
  _root = null;
}
