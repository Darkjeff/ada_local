/**
 * web/static/views/infra/index.js
 * Vue Infrastructure — gestion multi-instance Proxmox VE + PBS + Profils de backup.
 * Chargée via _loadSubView('sub-infra', 'infra').
 */

const CSS = `
.infra-view{padding:16px 20px;max-width:900px}
.infra-sec{margin-bottom:28px}
.infra-sec-hd{display:flex;align-items:center;justify-content:space-between;margin-bottom:12px;border-bottom:1px solid rgba(255,255,255,.07);padding-bottom:8px}
.infra-sec-title{font-size:.85rem;font-weight:600;color:#94a3b8;text-transform:uppercase;letter-spacing:.06em}
.infra-add-btn{font-size:.75rem;padding:4px 12px;border-radius:6px;border:1px solid rgba(0,212,255,.3);background:rgba(0,212,255,.08);color:#00d4ff;cursor:pointer;transition:background .15s}
.infra-add-btn:hover{background:rgba(0,212,255,.15)}

/* Instance cards */
.infra-card{display:flex;align-items:center;gap:10px;padding:10px 14px;background:rgba(255,255,255,.03);border:1px solid rgba(255,255,255,.07);border-radius:10px;margin-bottom:8px;transition:border-color .15s}
.infra-card:hover{border-color:rgba(255,255,255,.14)}
.infra-dot{width:8px;height:8px;border-radius:50%;flex-shrink:0;background:#334155}
.infra-dot.ok{background:#4caf50}
.infra-dot.err{background:#ef5350}
.infra-dot.testing{background:#f59e0b;animation:infra-pulse 1s infinite}
@keyframes infra-pulse{0%,100%{opacity:1}50%{opacity:.4}}
.infra-info{flex:1;min-width:0}
.infra-name{font-size:.88rem;font-weight:600;color:#e2e8f0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.infra-meta{font-size:.75rem;color:#64748b;margin-top:2px}
.infra-tags{display:flex;gap:4px;flex-wrap:wrap;margin-top:4px}
.infra-tag{font-size:.68rem;padding:1px 7px;border-radius:4px;background:rgba(255,255,255,.06);color:#94a3b8}
.infra-tag.universe{background:rgba(0,212,255,.1);color:#67e8f9}
.infra-tag.company{background:rgba(245,158,11,.1);color:#fcd34d}
.infra-disabled{opacity:.42}
.infra-actions{display:flex;gap:6px;flex-shrink:0}
.infra-btn{font-size:.72rem;padding:4px 10px;border-radius:6px;border:1px solid rgba(255,255,255,.1);background:rgba(255,255,255,.04);color:#94a3b8;cursor:pointer;transition:background .12s}
.infra-btn:hover{background:rgba(255,255,255,.09)}
.infra-btn.primary{border-color:rgba(0,212,255,.3);color:#00d4ff;background:rgba(0,212,255,.06)}
.infra-btn.danger{border-color:rgba(239,83,80,.3);color:#ef5350;background:rgba(239,83,80,.06)}
.infra-btn:disabled{opacity:.4;cursor:default}

/* Status badge loaded */
.infra-loaded{font-size:.68rem;padding:1px 7px;border-radius:4px;background:rgba(76,175,80,.12);color:#4caf50;margin-left:4px}
.infra-unloaded{font-size:.68rem;padding:1px 7px;border-radius:4px;background:rgba(100,116,139,.12);color:#64748b;margin-left:4px}

/* Form */
.infra-form{background:rgba(255,255,255,.02);border:1px solid rgba(255,255,255,.1);border-radius:10px;padding:16px;margin-top:8px;display:none}
.infra-form.open{display:block}
.infra-form-grid{display:grid;grid-template-columns:1fr 1fr;gap:10px}
.infra-form-grid.cols3{grid-template-columns:1fr 1fr 1fr}
.infra-form label{display:flex;flex-direction:column;gap:4px;font-size:.76rem;color:#94a3b8}
.infra-form label span{font-size:.72rem;color:#64748b;text-transform:uppercase;letter-spacing:.04em}
.infra-input{background:rgba(255,255,255,.06);border:1px solid rgba(255,255,255,.1);border-radius:6px;padding:6px 10px;color:#e2e8f0;font-size:.82rem;width:100%;box-sizing:border-box;outline:none;transition:border-color .15s}
.infra-input:focus{border-color:rgba(0,212,255,.4)}
.infra-form-row{display:flex;gap:8px;margin-top:12px;align-items:center;flex-wrap:wrap}
.infra-status-msg{font-size:.78rem;flex:1}
.infra-status-msg.ok{color:#4caf50}
.infra-status-msg.err{color:#ef5350}
.infra-divider{border:none;border-top:1px solid rgba(255,255,255,.06);margin:20px 0}
.infra-empty{color:#64748b;font-size:.82rem;padding:10px 0}
.infra-section-note{font-size:.76rem;color:#475569;margin-top:-6px;margin-bottom:10px}
`;

function _css(id, code) {
  if (!document.getElementById(id)) {
    const s = document.createElement('style');
    s.id = id;
    s.textContent = code;
    document.head.appendChild(s);
  }
}

let _tok = '';

async function _api(method, path, body) {
  const opts = { method, headers: { 'Content-Type': 'application/json', ...(_tok ? { Authorization: 'Bearer ' + _tok } : {}) } };
  if (body) opts.body = JSON.stringify(body);
  const r = await fetch(path, opts);
  if (!r.ok) { const e = await r.json().catch(() => ({ detail: r.statusText })); throw new Error(e.detail || r.statusText); }
  return r.json();
}

// ── Universe meta ─────────────────────────────────────────────

const _UNI = {
  opent: { label: 'OpenTechno', color: '#00d4ff' },
  home:  { label: 'Maison',     color: '#a78bfa' },
  uscss: { label: 'USCSS',      color: '#f59e0b' },
  margep:{ label: 'MargePro',   color: '#4ade80' },
};

// ── Status dot ────────────────────────────────────────────────

function _dotClass(tested, ok) {
  if (!tested) return '';
  return ok ? 'ok' : 'err';
}

// ── Instance card HTML ────────────────────────────────────────

function _instCard(inst, type, testState) {
  const disabled = !inst.enabled;
  const dot = testState ? (testState.ok ? 'ok' : 'err') : '';
  const tags = (inst.tags || []).map(t => `<span class="infra-tag">${t}</span>`).join('');
  const uniLabel = _UNI[inst.universe]?.label || inst.universe || '';
  const loaded = type === 'pve'
    ? `<span class="infra-loaded">chargé</span>`
    : '';
  const statusText = testState
    ? (testState.ok
        ? `v${testState.version || '?'} · ${testState.nodes ?? testState.datastores ?? '?'} ${type === 'pve' ? 'nodes' : 'datastores'}`
        : testState.error || 'Erreur')
    : '—';

  return `
  <div class="infra-card ${disabled ? 'infra-disabled' : ''}" id="icard-${type}-${inst.id}">
    <div class="infra-dot ${dot}" id="idot-${type}-${inst.id}"></div>
    <div class="infra-info">
      <div class="infra-name">${inst.id} <span style="font-weight:400;color:#64748b">· ${inst.label}</span>
        <span class="infra-${inst.enabled ? 'loaded' : 'unloaded'}">${inst.enabled ? 'activé' : 'désactivé'}</span>
      </div>
      <div class="infra-meta">${inst.host}:${inst.port} — <span id="istatus-${type}-${inst.id}">${statusText}</span></div>
      <div class="infra-tags">
        ${uniLabel ? `<span class="infra-tag universe">${uniLabel}</span>` : ''}
        ${inst.company_id ? `<span class="infra-tag company">${inst.company_id}</span>` : ''}
        ${tags}
      </div>
    </div>
    <div class="infra-actions">
      <button class="infra-btn" id="ibtn-test-${type}-${inst.id}"
              onclick="_infraTest('${type}','${inst.id}')">Test</button>
      <button class="infra-btn primary"
              onclick="_infraEdit('${type}','${inst.id}')">✎</button>
      <button class="infra-btn danger"
              onclick="_infraDelete('${type}','${inst.id}')">✕</button>
    </div>
  </div>`;
}

function _profileCard(p) {
  return `
  <div class="infra-card" id="pcard-${p.id}">
    <div class="infra-info">
      <div class="infra-name">${p.id} <span style="font-weight:400;color:#64748b">· ${p.label}</span></div>
      <div class="infra-meta">${p.storage} · ${p.compress} · ${p.mode} · <code style="font-size:.72rem">${p.schedule || '—'}</code></div>
      <div class="infra-tags">
        ${p.universe ? `<span class="infra-tag universe">${_UNI[p.universe]?.label || p.universe}</span>` : ''}
        ${(p.tags||[]).map(t => `<span class="infra-tag">${t}</span>`).join('')}
      </div>
    </div>
    <div class="infra-actions">
      <button class="infra-btn primary" onclick="_infraEditProfile('${p.id}')">✎</button>
      <button class="infra-btn danger"  onclick="_infraDeleteProfile('${p.id}')">✕</button>
    </div>
  </div>`;
}

// ── Form builders ─────────────────────────────────────────────

function _uniOptions(current) {
  return Object.entries(_UNI).map(([v, m]) =>
    `<option value="${v}" ${current === v ? 'selected' : ''}>${m.label}</option>`
  ).join('');
}

function _companyOptions(current, companies) {
  const none = `<option value="" ${!current ? 'selected' : ''}>— Aucune —</option>`;
  const opts = companies.map(c =>
    `<option value="${c.id}" ${current === c.id ? 'selected' : ''}>${c.name}</option>`
  ).join('');
  return none + opts;
}

function _pbsOptions(current, pbsList) {
  const none = `<option value="" ${!current ? 'selected' : ''}>— Aucun PBS —</option>`;
  const opts = pbsList.map(p =>
    `<option value="${p.id}" ${current === p.id ? 'selected' : ''}>${p.label}</option>`
  ).join('');
  return none + opts;
}

function _instForm(id, inst, companies, pbsList) {
  const v = inst || {};
  return `
  <div class="infra-form open" id="${id}">
    <div class="infra-form-grid">
      <label><span>ID unique *</span><input class="infra-input" name="id" value="${v.id||''}" placeholder="pve-opent" ${inst ? 'readonly' : ''}></label>
      <label><span>Nom affiché *</span><input class="infra-input" name="label" value="${v.label||''}" placeholder="Proxmox OpenTechno"></label>
      <label><span>Hôte *</span><input class="infra-input" name="host" value="${v.host||''}" placeholder="192.168.1.10"></label>
      <label><span>Port</span><input class="infra-input" name="port" type="number" value="${v.port||8006}"></label>
      <label><span>Utilisateur</span><input class="infra-input" name="user" value="${v.user||'root@pam'}"></label>
      <label><span>Token Name</span><input class="infra-input" name="token_name" value="${v.token_name||'ada'}"></label>
    </div>
    <div class="infra-form-grid" style="margin-top:10px">
      <label style="grid-column:1/-1"><span>Token Value</span><input class="infra-input" name="token_value" type="password" value="" placeholder="${inst ? '(inchangé si vide)' : 'xxxx-xxxx-xxxx'}"></label>
    </div>
    <div class="infra-form-grid cols3" style="margin-top:10px">
      <label><span>Univers</span>
        <select class="infra-input" name="universe">${_uniOptions(v.universe||'opent')}</select>
      </label>
      <label><span>Société</span>
        <select class="infra-input" name="company_id">${_companyOptions(v.company_id, companies)}</select>
      </label>
      <label><span>PBS associé</span>
        <select class="infra-input" name="pbs_id">${_pbsOptions(v.pbs_id, pbsList)}</select>
      </label>
    </div>
    <div class="infra-form-grid" style="margin-top:10px">
      <label><span>Tags (séparés par virgule)</span><input class="infra-input" name="tags" value="${(v.tags||[]).join(', ')}"></label>
      <label style="justify-content:center;flex-direction:row;align-items:center;gap:10px;padding-top:16px">
        <input type="checkbox" name="verify_ssl" ${v.verify_ssl ? 'checked' : ''} style="width:16px;height:16px">
        <span style="font-size:.82rem;color:#94a3b8">Vérifier le certificat SSL</span>
      </label>
    </div>
    <div style="margin-top:10px">
      <label style="flex-direction:row;align-items:center;gap:10px">
        <input type="checkbox" name="enabled" ${v.enabled !== false ? 'checked' : ''} style="width:16px;height:16px">
        <span style="font-size:.82rem;color:#94a3b8">Instance activée</span>
      </label>
    </div>
    <div class="infra-form-row">
      <button class="infra-btn primary" onclick="_infraSave('pve','${id}','${inst?.id||''}')">💾 Enregistrer</button>
      <button class="infra-btn" onclick="_infraTestForm('${id}')">⚡ Tester la connexion</button>
      <button class="infra-btn" onclick="_infraCloseForm('${id}')">Annuler</button>
      <span class="infra-status-msg" id="${id}-status"></span>
    </div>
  </div>`;
}

function _pbsForm(id, pbs, companies) {
  const v = pbs || {};
  return `
  <div class="infra-form open" id="${id}">
    <div class="infra-form-grid">
      <label><span>ID unique *</span><input class="infra-input" name="id" value="${v.id||''}" placeholder="pbs-opent" ${pbs ? 'readonly' : ''}></label>
      <label><span>Nom affiché *</span><input class="infra-input" name="label" value="${v.label||''}" placeholder="PBS OpenTechno"></label>
      <label><span>Hôte *</span><input class="infra-input" name="host" value="${v.host||''}" placeholder="192.168.1.11"></label>
      <label><span>Port</span><input class="infra-input" name="port" type="number" value="${v.port||8007}"></label>
      <label><span>Utilisateur</span><input class="infra-input" name="user" value="${v.user||'root@pam'}"></label>
      <label><span>Token Name</span><input class="infra-input" name="token_name" value="${v.token_name||'ada'}"></label>
    </div>
    <div class="infra-form-grid" style="margin-top:10px">
      <label style="grid-column:1/-1"><span>Token Value</span><input class="infra-input" name="token_value" type="password" value="" placeholder="${pbs ? '(inchangé si vide)' : 'xxxx-xxxx-xxxx'}"></label>
    </div>
    <div class="infra-form-grid cols3" style="margin-top:10px">
      <label><span>Univers</span>
        <select class="infra-input" name="universe">${_uniOptions(v.universe||'opent')}</select>
      </label>
      <label><span>Société</span>
        <select class="infra-input" name="company_id">${_companyOptions(v.company_id, companies)}</select>
      </label>
      <label><span>Tags</span><input class="infra-input" name="tags" value="${(v.tags||[]).join(', ')}"></label>
    </div>
    <div style="margin-top:10px">
      <label style="flex-direction:row;align-items:center;gap:10px">
        <input type="checkbox" name="enabled" ${v.enabled !== false ? 'checked' : ''} style="width:16px;height:16px">
        <span style="font-size:.82rem;color:#94a3b8">Instance activée</span>
      </label>
    </div>
    <div class="infra-form-row">
      <button class="infra-btn primary" onclick="_infraSave('pbs','${id}','${pbs?.id||''}')">💾 Enregistrer</button>
      <button class="infra-btn" onclick="_infraTestForm('${id}')">⚡ Tester la connexion</button>
      <button class="infra-btn" onclick="_infraCloseForm('${id}')">Annuler</button>
      <span class="infra-status-msg" id="${id}-status"></span>
    </div>
  </div>`;
}

function _profileForm(id, profile) {
  const v = profile || {};
  const r = v.retention || {};
  const compressOpts = ['zstd','lzo','gzip','none'].map(c =>
    `<option value="${c}" ${v.compress===c?'selected':''}>${c}</option>`).join('');
  const modeOpts = ['snapshot','suspend','stop'].map(m =>
    `<option value="${m}" ${v.mode===m?'selected':''}>${m}</option>`).join('');
  return `
  <div class="infra-form open" id="${id}">
    <div class="infra-form-grid">
      <label><span>ID unique *</span><input class="infra-input" name="id" value="${v.id||''}" ${profile ? 'readonly' : ''}></label>
      <label><span>Nom affiché *</span><input class="infra-input" name="label" value="${v.label||''}"></label>
      <label><span>Storage (ID PBS ou nom local)</span><input class="infra-input" name="storage" value="${v.storage||''}"></label>
      <label><span>Compression</span><select class="infra-input" name="compress">${compressOpts}</select></label>
      <label><span>Mode</span><select class="infra-input" name="mode">${modeOpts}</select></label>
      <label><span>Schedule (cron, info)</span><input class="infra-input" name="schedule" value="${v.schedule||''}"></label>
    </div>
    <div class="infra-form-grid cols3" style="margin-top:10px">
      <label><span>keep_last</span><input class="infra-input" name="keep_last" type="number" value="${r.keep_last||3}"></label>
      <label><span>keep_daily</span><input class="infra-input" name="keep_daily" type="number" value="${r.keep_daily||7}"></label>
      <label><span>keep_weekly</span><input class="infra-input" name="keep_weekly" type="number" value="${r.keep_weekly||4}"></label>
      <label><span>keep_monthly</span><input class="infra-input" name="keep_monthly" type="number" value="${r.keep_monthly||0}"></label>
      <label><span>Univers</span><select class="infra-input" name="universe">${_uniOptions(v.universe||'opent')}</select></label>
      <label><span>Tags</span><input class="infra-input" name="tags" value="${(v.tags||[]).join(', ')}"></label>
    </div>
    <div class="infra-form-row">
      <button class="infra-btn primary" onclick="_infraSaveProfile('${id}','${profile?.id||''}')">💾 Enregistrer</button>
      <button class="infra-btn" onclick="_infraCloseForm('${id}')">Annuler</button>
      <span class="infra-status-msg" id="${id}-status"></span>
    </div>
  </div>`;
}

// ── Form data readers ─────────────────────────────────────────

function _readForm(formEl) {
  const get = n => formEl.querySelector(`[name="${n}"]`)?.value?.trim() || '';
  const check = n => formEl.querySelector(`[name="${n}"]`)?.checked || false;
  return { get, check };
}

// ── Actions globales (appelées via onclick) ───────────────────

window._infraTest = async (type, id) => {
  const dot = document.getElementById(`idot-${type}-${id}`);
  const st  = document.getElementById(`istatus-${type}-${id}`);
  const btn = document.getElementById(`ibtn-test-${type}-${id}`);
  if (dot) { dot.className = 'infra-dot testing'; }
  if (btn) btn.disabled = true;
  try {
    const path = type === 'pve'
      ? `/api/proxmox/test?instance_id=${id}`
      : `/api/pbs/test?pbs_id=${id}`;
    const data = await _api('GET', path);
    if (dot) dot.className = 'infra-dot ' + (data.ok ? 'ok' : 'err');
    if (st) st.textContent = data.ok
      ? `v${data.version||'?'} · ${data.nodes ?? data.datastores ?? '?'} ${type === 'pve' ? 'nodes' : 'datastores'}`
      : (data.error || 'Erreur');
  } catch(e) {
    if (dot) dot.className = 'infra-dot err';
    if (st) st.textContent = e.message;
  } finally {
    if (btn) btn.disabled = false;
  }
};

window._infraEdit = (type, id) => {
  const formId = `form-edit-${type}-${id}`;
  const existing = document.getElementById(formId);
  if (existing) { existing.remove(); return; }
  const card = document.getElementById(`icard-${type}-${id}`);
  if (!card) return;
  const formContainer = document.createElement('div');
  formContainer.id = formId + '-wrap';

  // Get current instance data from the page cache
  const inst = _instCache[type]?.[id] || {};
  const html = type === 'pve'
    ? _instForm(formId, inst, _companiesCache, _pbsCacheList)
    : _pbsForm(formId, inst, _companiesCache);
  formContainer.innerHTML = html;
  card.after(formContainer);
  // Restore token placeholder
  const tokenInput = formContainer.querySelector('[name="token_value"]');
  if (tokenInput) tokenInput.placeholder = '(laisser vide pour conserver)';
};

window._infraDelete = async (type, id) => {
  const label = _instCache[type]?.[id]?.label || id;
  if (!confirm(`Supprimer l'instance "${label}" ? Cette action est irréversible.`)) return;
  try {
    const path = type === 'pve'
      ? `/api/proxmox/instances/${encodeURIComponent(id)}`
      : `/api/pbs/instances/${encodeURIComponent(id)}`;
    await _api('DELETE', path);
    const card = document.getElementById(`icard-${type}-${id}`);
    if (card) {
      const wrap = document.getElementById(`form-edit-${type}-${id}-wrap`);
      if (wrap) wrap.remove();
      card.remove();
    }
    delete _instCache[type][id];
  } catch(e) {
    alert(`Erreur lors de la suppression : ${e.message}`);
  }
};

window._infraTestForm = async (formId) => {
  const form = document.getElementById(formId);
  if (!form) return;
  const { get, check } = _readForm(form);
  const statusEl = document.getElementById(formId + '-status');
  if (statusEl) { statusEl.textContent = 'Test en cours…'; statusEl.className = 'infra-status-msg'; }
  const id = get('id');
  const type = formId.includes('-pbs-') || formId.includes('pbs-') ? 'pbs' : 'pve';
  try {
    const path = type === 'pve'
      ? `/api/proxmox/test?instance_id=${encodeURIComponent(id)}`
      : `/api/pbs/test?pbs_id=${encodeURIComponent(id)}`;
    const data = await _api('GET', path);
    if (statusEl) {
      statusEl.className = 'infra-status-msg ' + (data.ok ? 'ok' : 'err');
      statusEl.textContent = data.ok
        ? `✓ Connecté — v${data.version||'?'} · ${data.nodes ?? data.datastores ?? '?'} ${type === 'pve' ? 'nodes' : 'datastores'}`
        : `✗ ${data.error || 'Connexion échouée'}`;
    }
  } catch(e) {
    if (statusEl) { statusEl.className = 'infra-status-msg err'; statusEl.textContent = '✗ ' + e.message; }
  }
};

window._infraSave = async (type, formId, originalId) => {
  const form = document.getElementById(formId);
  if (!form) return;
  const { get, check } = _readForm(form);
  const statusEl = document.getElementById(formId + '-status');

  const id = get('id') || originalId;
  const tokenValue = get('token_value');
  const payload = {
    id,
    label:      get('label'),
    host:       get('host'),
    port:       parseInt(get('port')) || (type === 'pve' ? 8006 : 8007),
    user:       get('user') || 'root@pam',
    token_name: get('token_name') || 'ada',
    token_value: tokenValue || (originalId ? undefined : ''),
    verify_ssl: check('verify_ssl'),
    enabled:    check('enabled'),
    universe:   get('universe'),
    company_id: get('company_id') || null,
    tags:       get('tags').split(',').map(t => t.trim()).filter(Boolean),
    ...(type === 'pve' ? { pbs_id: get('pbs_id') || null } : {}),
  };
  if (!payload.id || !payload.label || !payload.host) {
    if (statusEl) { statusEl.className = 'infra-status-msg err'; statusEl.textContent = '✗ ID, Nom et Hôte sont requis'; }
    return;
  }
  // Remove undefined token if editing
  if (tokenValue === '' && originalId) delete payload.token_value;

  try {
    const path = type === 'pve' ? '/api/proxmox/instances' : '/api/pbs/instances';
    const data = await _api('POST', path, payload);
    if (statusEl) { statusEl.className = 'infra-status-msg ok'; statusEl.textContent = `✓ ${data.action === 'created' ? 'Créée' : 'Mise à jour'}`; }
    setTimeout(() => { window._infraMount?.(); }, 1000);
    if (typeof showToast === 'function') showToast(`Instance "${payload.label}" enregistrée`);
  } catch(e) {
    if (statusEl) { statusEl.className = 'infra-status-msg err'; statusEl.textContent = '✗ ' + e.message; }
  }
};

window._infraEditProfile = (id) => {
  const formId = `form-edit-profile-${id}`;
  const existing = document.getElementById(formId);
  if (existing) { existing.remove(); return; }
  const card = document.getElementById(`pcard-${id}`);
  if (!card) return;
  const wrap = document.createElement('div');
  wrap.id = formId + '-wrap';
  const profile = _profileCache[id] || {};
  wrap.innerHTML = _profileForm(formId, profile);
  card.after(wrap);
};

window._infraDeleteProfile = async (id) => {
  const label = _profileCache[id]?.label || id;
  if (!confirm(`Supprimer le profil "${label}" ? Cette action est irréversible.`)) return;
  try {
    await _api('DELETE', `/api/proxmox/profiles/${encodeURIComponent(id)}`);
    const card = document.getElementById(`pcard-${id}`);
    if (card) {
      const wrap = document.getElementById(`form-edit-profile-${id}-wrap`);
      if (wrap) wrap.remove();
      card.remove();
    }
    delete _profileCache[id];
  } catch(e) {
    alert(`Erreur lors de la suppression : ${e.message}`);
  }
};

window._infraSaveProfile = async (formId, originalId) => {
  const form = document.getElementById(formId);
  if (!form) return;
  const { get } = _readForm(form);
  const statusEl = document.getElementById(formId + '-status');
  const payload = {
    id:       get('id') || originalId,
    label:    get('label'),
    storage:  get('storage'),
    compress: get('compress') || 'zstd',
    mode:     get('mode') || 'snapshot',
    schedule: get('schedule'),
    universe: get('universe'),
    tags:     get('tags').split(',').map(t => t.trim()).filter(Boolean),
    retention: {
      keep_last:    parseInt(form.querySelector('[name="keep_last"]')?.value) || 3,
      keep_daily:   parseInt(form.querySelector('[name="keep_daily"]')?.value) || 7,
      keep_weekly:  parseInt(form.querySelector('[name="keep_weekly"]')?.value) || 4,
      keep_monthly: parseInt(form.querySelector('[name="keep_monthly"]')?.value) || 0,
    },
  };
  if (!payload.id || !payload.label || !payload.storage) {
    if (statusEl) { statusEl.className = 'infra-status-msg err'; statusEl.textContent = '✗ ID, Nom et Storage sont requis'; }
    return;
  }
  try {
    const data = await _api('POST', '/api/proxmox/profiles', payload);
    if (statusEl) { statusEl.className = 'infra-status-msg ok'; statusEl.textContent = '✓ Enregistré'; }
    setTimeout(() => { window._infraMount?.(); }, 1000);
  } catch(e) {
    if (statusEl) { statusEl.className = 'infra-status-msg err'; statusEl.textContent = '✗ ' + e.message; }
  }
};

window._infraCloseForm = (formId) => {
  const wrap = document.getElementById(formId + '-wrap') || document.getElementById(formId);
  if (wrap) wrap.remove();
};

// ── Page-level caches ─────────────────────────────────────────
let _instCache = { pve: {}, pbs: {} };
let _pbsCacheList = [];
let _companiesCache = [];
let _profileCache = {};

// ── Mount ─────────────────────────────────────────────────────

export async function mount(container, opts = {}) {
  _css('infra-css', CSS);
  _tok = opts.token || '';

  window._infraMount = () => mount(container, opts);

  container.innerHTML = `<div style="padding:24px;color:#64748b;font-size:.82rem">Chargement…</div>`;

  // Charger les données en parallèle
  let instances = [], pbsList = [], profiles = [], companies = [];
  let svcList = [], svcEndpoints = [], infraPage = {}, dockerUniMap = {};
  try {
    [instances, pbsList, profiles, svcList, svcEndpoints, infraPage, dockerUniMap] = await Promise.all([
      _api('GET', '/api/proxmox/instances').catch(() => []),
      _api('GET', '/api/pbs/instances').catch(() => []),
      _api('GET', '/api/proxmox/profiles').catch(() => []),
      _api('GET', '/api/infra/services').catch(() => []),
      _api('GET', '/api/infra/endpoints').catch(() => []),
      _api('GET', '/api/page/infrastructure').catch(() => ({})),
      _api('GET', '/api/infra/docker/universes').catch(() => ({})),
    ]);
    // Sociétés pour les selects (optionnel)
    try { companies = await _api('GET', '/api/societe/companies'); } catch {}
  } catch(e) {
    container.innerHTML = `<div style="padding:24px;color:#ef5350;font-size:.82rem">Erreur : ${e.message}</div>`;
    return;
  }

  // Peupler les caches
  _pbsCacheList = pbsList;
  _companiesCache = companies;
  instances.forEach(i => { _instCache.pve[i.id] = i; });
  pbsList.forEach(p => { _instCache.pbs[p.id] = p; });
  profiles.forEach(p => { _profileCache[p.id] = p; });

  // ── Filtre univers : détection automatique depuis le panel actif ──────
  const _panelUni = opts.universe || container.closest('.uni-panel')?.id?.replace('uni-', '') || null;
  // Mapping panel-slug → universe IDs stockés sur les instances
  const _PANEL_TO_UNI = { home: ['home'], co: ['opent','uscss','margep'], plan: [], tools: [] };
  const _autoUnis = _panelUni ? (_PANEL_TO_UNI[_panelUni] || null) : null;
  let _uniFilter = _autoUnis; // null = tout afficher

  function _filterItems(list) {
    if (!_uniFilter || !_uniFilter.length) return list;
    return list.filter(i => !i.universe || _uniFilter.includes(i.universe));
  }

  function _renderLists() {
    const fInst = _filterItems(instances);
    const fPbs  = _filterItems(pbsList);
    const fProf = _filterItems(profiles);

    const pveEl = container.querySelector('#pve-list');
    const pbsEl = container.querySelector('#pbs-list');
    const proEl = container.querySelector('#profile-list');
    if (pveEl) pveEl.innerHTML = fInst.length ? fInst.map(i => _instCard(i,'pve',null)).join('') : `<div class="infra-empty">Aucune instance Proxmox</div>`;
    if (pbsEl) pbsEl.innerHTML = fPbs.length  ? fPbs.map(p => _instCard(p,'pbs',null)).join('') : `<div class="infra-empty">Aucun serveur PBS</div>`;
    if (proEl) proEl.innerHTML = fProf.length ? fProf.map(p => _profileCard(p)).join('')        : `<div class="infra-empty">Aucun profil de backup</div>`;

    // Filtrer les lignes services locaux et docker par universe
    ['#svc-status-list', '#docker-list'].forEach(sel => {
      const el = container.querySelector(sel);
      if (!el) return;
      el.querySelectorAll('[data-universe]').forEach(row => {
        const rowUni = row.dataset.universe || '';
        const show = !_uniFilter || !_uniFilter.length || !rowUni || _uniFilter.includes(rowUni);
        row.style.display = show ? 'flex' : 'none';
      });
    });

    // Mettre à jour le chip filtre
    const chip = container.querySelector('#infra-uni-chip');
    if (chip) {
      if (_uniFilter) {
        const labels = _uniFilter.map(u => _UNI[u]?.label || u).join(', ');
        chip.innerHTML = `Univers\u00a0: <b>${labels}</b> <span style="cursor:pointer;margin-left:4px" title="Tout afficher" id="infra-uni-clear">\u00d7</span>`;
        chip.style.display = 'inline-flex';
        container.querySelector('#infra-uni-clear')?.addEventListener('click', () => {
          _uniFilter = null;
          _renderLists();
        });
      } else {
        chip.innerHTML = `<span style="cursor:pointer" id="infra-uni-reset">Filtrer : ${_autoUnis ? (_PANEL_TO_UNI[_panelUni]||[]).map(u=>_UNI[u]?.label||u).join(', ') : '—'}</span>`;
        if (_autoUnis) container.querySelector('#infra-uni-reset')?.addEventListener('click', () => { _uniFilter = _autoUnis; _renderLists(); });
      }
    }
  }

  const _initPve  = _filterItems(instances);
  const _initPbs  = _filterItems(pbsList);
  const _initProf = _filterItems(profiles);

  // HTML instances PVE
  const pveCards = _initPve.length
    ? _initPve.map(i => _instCard(i, 'pve', null)).join('')
    : `<div class="infra-empty">Aucune instance Proxmox configurée</div>`;

  // HTML PBS
  const pbsCards = _initPbs.length
    ? _initPbs.map(p => _instCard(p, 'pbs', null)).join('')
    : `<div class="infra-empty">Aucun serveur PBS configuré</div>`;

  // HTML profils
  const profileCards = _initProf.length
    ? _initProf.map(p => _profileCard(p)).join('')
    : `<div class="infra-empty">Aucun profil de backup défini</div>`;

  // ── Services locaux & Docker ──────────────────────────────────────────────
  function _statusDot(s) {
    const c = s === 'online' ? '#4caf50' : s === 'offline' ? '#ef5350' : '#f59e0b';
    return `<span style="display:inline-block;width:7px;height:7px;border-radius:50%;background:${c};flex-shrink:0"></span>`;
  }

  function _uniSelect(current, typeKey, itemName) {
    const cur = current || '';
    const curColor = (cur && _UNI[cur]) ? _UNI[cur].color : '#64748b';
    const opts = '<option value="">— Univers —</option>' +
      Object.entries(_UNI).map(([id, u]) =>
        '<option value="' + id + '"' + (cur === id ? ' selected' : '') + '>' + u.label + '</option>'
      ).join('');
    return '<select class="infra-uni-sel" data-type="' + typeKey + '" data-item="' + itemName + '"' +
      ' onchange="window._infraSetUni(this)"' +
      ' style="background:#1e293b;color:' + curColor + ';border:1px solid rgba(255,255,255,.12);' +
      'border-radius:4px;padding:2px 6px;font-size:.72rem;cursor:pointer;min-width:90px">' +
      opts + '</select>';
  }

  const allSvcs = [
    ...svcList.map(s => ({...s, builtin: true})),
    ...svcEndpoints.map(e => ({...e, builtin: false, status: e.status || 'unknown'})),
  ].filter(s => !s.hidden);

  const svcRows = allSvcs.map(s => {
    const name = s.name === 'home_assistant' ? 'Home Assistant' : s.name;
    const urlPart = s.url
      ? '<a href="' + s.url + '" target="_blank" style="font-size:10px;color:#67e8f9;text-decoration:none;flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="' + s.url + '">' + s.url + '</a>'
      : '<span style="font-size:10px;color:#475569;flex:1">' + (s.status||'') + '</span>';
    const typeKey = s.builtin ? 'services' : 'endpoints';
    return '<div data-universe="' + (s.universe||'') + '" style="display:flex;align-items:center;gap:7px;padding:5px 0;border-bottom:1px solid rgba(255,255,255,.04)">' +
      _statusDot(s.status||'unknown') +
      '<span style="font-size:.82rem;font-weight:600;color:#e2e8f0;min-width:110px">' + name + '</span>' +
      urlPart +
      _uniSelect(s.universe, typeKey, s.name) +
      '</div>';
  }).join('') || '<div class="infra-empty">Aucun service configuré</div>';

  const dockerContainers = (infraPage.docker && infraPage.docker.containers ? infraPage.docker.containers : []);
  const dockerRows = dockerContainers.map(c => {
    const running = (c.status||'').toLowerCase().indexOf('up') === 0 || c.status === 'running';
    const dot = running ? '#4caf50' : '#ef5350';
    return '<div data-universe="' + (dockerUniMap[c.name]||'') + '" style="display:flex;align-items:center;gap:7px;padding:4px 0;border-bottom:1px solid rgba(255,255,255,.04)">' +
      '<span style="display:inline-block;width:7px;height:7px;border-radius:50%;background:' + dot + ';flex-shrink:0"></span>' +
      '<span style="font-size:.82rem;color:#e2e8f0;flex:1">' + c.name + '</span>' +
      '<span style="font-size:10px;color:#64748b;margin-right:4px">' + (c.status||'') + '</span>' +
      _uniSelect(dockerUniMap[c.name], 'docker', c.name) +
      '</div>';
  }).join('') || '<div class="infra-empty">Aucun container Docker détecté</div>';

  const warnings = infraPage.warnings || [];
  const warnRows = warnings.length
    ? warnings.map(w => `<div style="font-size:.8rem;color:#fcd34d;padding:3px 0">⚠ ${w}</div>`).join('')
    : '';

  container.innerHTML = `
  <div class="infra-view">

    ${_autoUnis ? `<div style="display:flex;align-items:center;gap:8px;margin-bottom:14px;flex-wrap:wrap">
      <span id="infra-uni-chip" style="display:inline-flex;align-items:center;gap:4px;font-size:.75rem;padding:3px 10px;border-radius:20px;background:rgba(0,212,255,.08);border:1px solid rgba(0,212,255,.2);color:#67e8f9"></span>
    </div>` : ''}

    <div class="infra-sec">
      <div class="infra-sec-hd">
        <span class="infra-sec-title">🔗 Services locaux</span>
        <a href="#" style="font-size:.72rem;color:#67e8f9" onclick="event.preventDefault();window._infraMount && window._infraMount()">↻</a>
      </div>
      ${warnRows}
      <div id="svc-status-list">${svcRows}</div>
    </div>

    <hr class="infra-divider">

    <div class="infra-sec">
      <div class="infra-sec-hd">
        <span class="infra-sec-title">🐳 Docker</span>
        <span style="font-size:.72rem;color:#64748b">${dockerContainers.length} container${dockerContainers.length > 1 ? 's' : ''}</span>
      </div>
      <div id="docker-list">${dockerRows}</div>
    </div>

    <hr class="infra-divider">

    <div class="infra-sec">
      <div class="infra-sec-hd">
        <span class="infra-sec-title">🖥️ Instances Proxmox VE</span>
        <button class="infra-add-btn" onclick="_infraShowNewForm('pve')">+ Ajouter</button>
      </div>
      <div class="infra-section-note">Pris en compte au prochain redémarrage du serveur ADA</div>
      <div id="pve-list">${pveCards}</div>
      <div id="form-new-pve-wrap"></div>
    </div>

    <hr class="infra-divider">

    <div class="infra-sec">
      <div class="infra-sec-hd">
        <span class="infra-sec-title">🗄️ Serveurs PBS</span>
        <button class="infra-add-btn" onclick="_infraShowNewForm('pbs')">+ Ajouter</button>
      </div>
      <div id="pbs-list">${pbsCards}</div>
      <div id="form-new-pbs-wrap"></div>
    </div>

    <hr class="infra-divider">

    <div class="infra-sec">
      <div class="infra-sec-hd">
        <span class="infra-sec-title">📋 Profils de backup</span>
        <button class="infra-add-btn" onclick="_infraShowNewForm('profile')">+ Ajouter</button>
      </div>
      <div id="profile-list">${profileCards}</div>
      <div id="form-new-profile-wrap"></div>
    </div>

  </div>`;

  // Initialiser le chip de filtre univers
  if (_autoUnis) _renderLists();

  // Handler universe select pour services / endpoints / docker
  window._infraSetUni = async function(sel) {
    const typeKey = sel.dataset.type;
    const name    = sel.dataset.item;
    const value   = sel.value;
    sel.disabled  = true;
    try {
      const url = typeKey === 'docker'
        ? '/api/infra/docker/' + encodeURIComponent(name) + '/universe'
        : '/api/infra/' + typeKey + '/' + encodeURIComponent(name) + '/universe';
      await fetch(url, {
        method: 'PATCH',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({universe: value})
      });
      sel.style.color = (value && _UNI[value]) ? _UNI[value].color : '#64748b';
      // Mettre à jour data-universe sur la ligne parente pour que le filtre fonctionne
      const row = sel.closest('[data-universe]');
      if (row) row.dataset.universe = value;
      if (typeKey === 'docker') dockerUniMap[name] = value;
    } catch(e) { console.error('_infraSetUni', e); }
    sel.disabled = false;
  };
}

window._infraShowNewForm = (type) => {
  const wrapId = `form-new-${type}-wrap`;
  const wrap = document.getElementById(wrapId);
  if (!wrap) return;
  if (wrap.innerHTML) { wrap.innerHTML = ''; return; }
  const formId = `form-new-${type}`;
  if (type === 'pve') {
    wrap.innerHTML = _instForm(formId, null, _companiesCache, _pbsCacheList);
  } else if (type === 'pbs') {
    wrap.innerHTML = _pbsForm(formId, null, _companiesCache);
  } else {
    wrap.innerHTML = _profileForm(formId, null);
  }
};

export function unmount() {
  window._infraMount = null;
  window._infraTest  = null;
}
