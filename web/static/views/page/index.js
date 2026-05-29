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
function _renderInfra(data, el) {
  const services  = data.services  || {};
  const docker    = data.docker    || {};
  const warnings  = data.warnings  || [];

  const serviceRows = Object.entries(services).map(([k, v]) => {
    const label = k === 'home_assistant' ? 'Home Assistant' : k;
    return `<div class="page-status-row"><span><i class="page-dot ${v.status||'unknown'}"></i>${escapeHtml(label)}</span><b>${escapeHtml(v.status||'unknown')}</b></div>`;
  }).join('');

  const containers = (docker.containers || []).slice(0, 8).map(
    (c) => `<li>${escapeHtml(c.name)} · ${escapeHtml(c.status||'')}</li>`
  ).join('');

  const warHtml = warnings.length
    ? `<ul class="page-list">${warnings.map((w) => `<li>${escapeHtml(w)}</li>`).join('')}</ul>`
    : `<p class="page-muted">Aucune alerte.</p>`;

  el.innerHTML = `
    <section class="page-panel"><h3>Services</h3>
      <div class="page-status-list">${serviceRows || '<p class="page-muted">Aucune donnée.</p>'}</div>
    </section>
    <section class="page-panel"><h3>Docker</h3>
      ${containers ? `<ul class="page-list">${containers}</ul>` : '<p class="page-muted">Aucun container actif.</p>'}
    </section>
    <section class="page-panel"><h3>Alertes</h3>${warHtml}</section>`;
}

function _renderHome(data, el) {
  const entities  = data.entities  || [];
  const providers = data.providers || [];

  if (!entities.length) {
    el.innerHTML = '<section class="page-panel"><p class="page-muted">Aucune entité domotique trouvée. Vérifiez la configuration des providers (HA, Kasa, Domoticz).</p></section>';
    return;
  }

  // Statut providers
  const provHtml = providers.map((p) => {
    const dot = p.status === 'connected' ? 'online' : p.status === 'disconnected' ? 'offline' : 'unknown';
    return `<div class="page-status-row"><span><i class="page-dot ${dot}"></i>${escapeHtml(p.name)}</span><b>${escapeHtml(p.status || '?')}</b></div>`;
  }).join('');

  // Grouper par type
  const TYPE_LABELS = { light: 'Lumières', switch: 'Switches', media_player: 'Lecteurs', sensor: 'Capteurs', binary_sensor: 'Capteurs binaires', camera: 'Caméras', unknown: 'Autres' };
  const STATE_ICON  = { on: '🟢', off: '⚫', playing: '▶️', unavailable: '🔴' };

  const byType = {};
  for (const e of entities) {
    const t = e.type || 'unknown';
    if (!byType[t]) byType[t] = [];
    byType[t].push(e);
  }

  // Priorité d'affichage
  const TYPE_ORDER = ['light', 'switch', 'media_player', 'sensor', 'binary_sensor', 'camera', 'unknown'];
  const sortedTypes = [
    ...TYPE_ORDER.filter((t) => byType[t]),
    ...Object.keys(byType).filter((t) => !TYPE_ORDER.includes(t)),
  ];

  const panelsHtml = sortedTypes.map((type) => {
    const group = byType[type];
    const rows = group.map((e) => {
      const icon  = STATE_ICON[e.state] || '🟡';
      let extra = '';
      if (e.attributes?.brightness != null) extra = ` · ${Math.round(e.attributes.brightness / 2.55)}%`;
      else if (e.attributes?.temperature != null) extra = ` · ${e.attributes.temperature}°`;
      else if (e.attributes?.humidity != null) extra = ` · ${e.attributes.humidity}%`;
      const zone = e.zone && e.zone !== 'Other' ? `<span class="page-muted"> [${escapeHtml(e.zone)}]</span>` : '';
      return `<div class="page-status-row"><span>${icon} ${escapeHtml(e.name)}${zone}</span><b>${escapeHtml(e.state || '?')}${escapeHtml(extra)}</b></div>`;
    }).join('');
    return `<section class="page-panel"><h3>${escapeHtml(TYPE_LABELS[type] || type)} (${group.length})</h3><div class="page-status-list">${rows}</div></section>`;
  }).join('');

  el.innerHTML = `
    <section class="page-panel"><h3>Providers</h3>
      ${provHtml || '<p class="page-muted">Aucun provider configuré.</p>'}
      <div class="page-status-row" style="margin-top:6px"><span>Total entités</span><b>${data.count || 0}</b></div>
    </section>
    ${panelsHtml}`;
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
      <div class="page-top">
        <h2 class="page-title">${escapeHtml(label || pageKey)}</h2>
        <p class="page-desc">${escapeHtml(cfg.description)}</p>
      </div>
      <div class="page-data-wrap" id="page-data-wrap"></div>
      <div class="page-actions">${actionsHtml}</div>
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
