/* ================================================================
   Vue Paramètres — 5 onglets de configuration
   ================================================================ */
import { showToast, setInputBarVisible } from '/static/core/core.js';

const _CSS = '/static/views/settings/style.css';

function _ensureCSS() {
  if (!document.getElementById('css-settings')) {
    const l = document.createElement('link');
    l.id = 'css-settings'; l.rel = 'stylesheet'; l.href = _CSS;
    document.head.appendChild(l);
  }
}

// ── State ─────────────────────────────────────────────────────
let _cfg = {};
let _models = [];
let _saveTimer = null;

// ── Helpers ───────────────────────────────────────────────────
function _get(key) {
  const parts = key.split('.');
  let v = _cfg;
  for (const p of parts) { if (v == null) return ''; v = v[p]; }
  return v ?? '';
}

function _debounce(fn, ms = 600) {
  return (...args) => {
    clearTimeout(_saveTimer);
    _saveTimer = setTimeout(() => fn(...args), ms);
  };
}

async function _save(key, value) {
  try {
    const r = await fetch('/api/settings', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ key, value }),
    });
    if (!r.ok) throw new Error(await r.text());
    _showSaveDot();
    // update local cache
    const parts = key.split('.');
    let obj = _cfg;
    for (let i = 0; i < parts.length - 1; i++) {
      if (obj[parts[i]] == null) obj[parts[i]] = {};
      obj = obj[parts[i]];
    }
    obj[parts[parts.length - 1]] = value;
  } catch (e) {
    showToast('Erreur sauvegarde : ' + e.message);
  }
}

function _showSaveDot() {
  const dot = document.getElementById('s-savedot');
  if (!dot) return;
  dot.classList.add('show');
  setTimeout(() => dot.classList.remove('show'), 1800);
}

// ── Row builders ──────────────────────────────────────────────

function _mkToggle(key, label, desc = '') {
  const checked = _get(key) ? 'checked' : '';
  return `
  <div class="s-row">
    <div class="s-row-info">
      <div class="s-row-label">${label}</div>
      ${desc ? `<div class="s-row-desc">${desc}</div>` : ''}
    </div>
    <label class="s-toggle">
      <input type="checkbox" ${checked} data-key="${key}" data-type="bool">
      <span class="s-toggle-track"></span>
    </label>
  </div>`;
}

function _mkText(key, label, desc = '', placeholder = '', type = 'text', extraClass = '') {
  const val = _get(key);
  return `
  <div class="s-row">
    <div class="s-row-info">
      <div class="s-row-label">${label}</div>
      ${desc ? `<div class="s-row-desc">${desc}</div>` : ''}
    </div>
    <input class="s-input ${extraClass}" type="${type}" placeholder="${placeholder}"
      value="${String(val).replace(/"/g, '&quot;')}" data-key="${key}">
  </div>`;
}

function _mkSelect(key, label, desc = '', options = []) {
  const current = String(_get(key));
  const opts = options.map(o => {
    const v = typeof o === 'string' ? o : o.value;
    const l = typeof o === 'string' ? o : o.label;
    return `<option value="${v}" ${v === current ? 'selected' : ''}>${l}</option>`;
  }).join('');
  return `
  <div class="s-row">
    <div class="s-row-info">
      <div class="s-row-label">${label}</div>
      ${desc ? `<div class="s-row-desc">${desc}</div>` : ''}
    </div>
    <select class="s-input narrow" data-key="${key}">${opts}</select>
  </div>`;
}

function _mkModelSelect(key, label, desc = '') {
  const current = String(_get(key));
  const opts = Array.isArray(_models) ? _models.map(m => `<option value="${m}" ${m === current ? 'selected' : ''}>${m}</option>`).join('') : `<option value="${current}">${current || '—'}</option>`;
  return `
  <div class="s-row">
    <div class="s-row-info">
      <div class="s-row-label">${label}</div>
      ${desc ? `<div class="s-row-desc">${desc}</div>` : ''}
    </div>
    <div class="s-model-row">
      <select class="s-input" data-key="${key}">${opts}</select>
    </div>
  </div>`;
}

function _mkUrlRow(key, label, desc = '', testId) {
  const val = _get(key);
  return `
  <div class="s-row">
    <div class="s-row-info">
      <div class="s-row-label">${label}</div>
      ${desc ? `<div class="s-row-desc">${desc}</div>` : ''}
    </div>
    <div class="s-row-end">
      <input class="s-input wide" type="url" value="${String(val).replace(/"/g, '&quot;')}"
        data-key="${key}" placeholder="http://">
      <button class="s-btn" data-test="${testId}">Test</button>
    </div>
  </div>`;
}

function _mkNumber(key, label, desc = '', min = 0, max = 100, step = 1) {
  const val = _get(key);
  return `
  <div class="s-row">
    <div class="s-row-info">
      <div class="s-row-label">${label}</div>
      ${desc ? `<div class="s-row-desc">${desc}</div>` : ''}
    </div>
    <input class="s-input narrow" type="number" min="${min}" max="${max}" step="${step}"
      value="${val}" data-key="${key}">
  </div>`;
}

function _sec(title, rows) {
  return `<div class="s-section"><h3 class="s-section-title">${title}</h3>${rows}</div>`;
}

// ── Module cards ──────────────────────────────────────────────
async function _mkModules() {
  let mods = [];
  try {
    const _tok = localStorage.getItem('ada_token');
    const h = _tok ? { 'Authorization': 'Bearer ' + _tok } : {};
    mods = await fetch('/api/plugins/catalog', { headers: h }).then(r => r.json());
  } catch {
    mods = [];
  }
  if (!mods.length) {
    return `<div class="s-section"><p style="color:var(--text-dim);font-size:12px">Impossible de charger le catalogue de plugins.</p></div>`;
  }
  const cards = mods.map(m => {
    const on = m.enabled;
    return `
    <div class="s-module-card ${on ? 'enabled' : ''}" data-mod="modules.${m.key}">
      <div class="mod-icon">${m.icon}</div>
      <div class="mod-label">${m.label}</div>
      <div class="mod-sub">${m.sub}</div>
      <div class="mod-badge">${on ? 'Activé' : 'Désactivé'}</div>
    </div>`;
  }).join('');
  return `<div class="s-section">
    <h3 class="s-section-title">Modules optionnels — menu &amp; onglets</h3>
    <div class="s-modules">${cards}</div>
  </div>`;
}

// ── Panel Plugins ────────────────────────────────────────────
async function _panelPlugins() {
  return _mkModules();
}

// ── Panels ────────────────────────────────────────────────────
function _panelAccueil() {
  return [
    _sec('Profil', [
      _mkText('user.name', 'Votre prénom', 'Utilisé dans les briefings et Telegram', 'Aurelien'),
      _mkSelect('language', 'Langue interface', '', [
        { value: 'fr', label: 'Français' },
        { value: 'en', label: 'English' },
      ]),
      _mkSelect('theme', 'Thème', 'Apparence de l\'application', ['Light','Dark','Auto']),
    ].join('')),

    _sec('Météo', [
      _mkText('weather.city', 'Ville', 'Nom affiché dans le briefing', 'Paris, FR'),
      _mkNumber('weather.latitude', 'Latitude', '', -90, 90, 0.0001),
      _mkNumber('weather.longitude', 'Longitude', '', -180, 180, 0.0001),
    ].join('')),

    _sec('Général', [
      _mkNumber('general.max_history', 'Historique max', 'Nombre de messages conservés', 5, 100),
      _mkToggle('general.auto_fetch_news', 'Actualités auto', 'Charger les news au démarrage'),
    ].join('')),

    _sec('Telegram', [
      _mkToggle('telegram.enabled', 'Activer Telegram', 'Accès ADA via bot Telegram'),
      _mkText('telegram.token', 'Token bot', 'Obtenu via @BotFather', '123456:ABCdef…'),
      _mkText('telegram.owner_chat_id', 'Owner Chat ID', 'Votre identifiant Telegram', '123456789'),
    ].join('')),

    _sec('Briefing matinal', [
      _mkToggle('briefing.enabled', 'Activer le briefing', 'Résumé météo + news chaque matin'),
      _mkSelect('briefing.hour', 'Heure d\'envoi', '', [5,6,7,8,9,10].map(h => ({ value: h, label: `${h}h00` }))),
    ].join('')),
  ].join('');
}

function _panelLLM() {
  return [
    _sec('Connexion Ollama', [
      _mkUrlRow('ollama_url', 'URL Ollama', 'Serveur Ollama local ou distant', 'ollama'),
      `<div class="s-row"><div class="s-row-info"><div class="s-row-label">Modèles disponibles</div>
        <div class="s-row-desc" id="models-count">Chargement…</div></div>
        <button class="s-btn" id="refresh-models">↻ Actualiser</button></div>`,
    ].join('')),

    _sec('Modèles IA', [
      _mkModelSelect('models.chat', 'Modèle principal', 'Utilisé pour la discussion générale'),
      _mkModelSelect('models.web_agent', 'Modèle Web Agent', 'Modèle vision pour l\'agent web'),
    ].join('')),

    _sec('Gérer les modèles Ollama', [
      `<div class="s-row">
        <div class="s-row-info">
          <div class="s-row-label">Télécharger un modèle</div>
          <div class="s-row-desc">ex: mistral:latest · llama3.2:3b · gemma3:4b · qwen2.5:7b</div>
        </div>
        <div class="s-row-end">
          <input class="s-input wide" id="pull-model-input" placeholder="nom:tag" type="text" autocomplete="off">
          <button class="s-btn" id="pull-model-btn">⬇ Télécharger</button>
        </div>
      </div>`,
      `<div id="pull-progress" style="display:none;padding:4px 0 8px">
        <div style="font-size:11px;color:#5a6a7a;font-family:ui-monospace,monospace;margin-bottom:4px" id="pull-status">Téléchargement…</div>
        <div style="height:3px;background:rgba(255,255,255,0.08);border-radius:2px">
          <div id="pull-bar" style="height:100%;background:#00d4ff;border-radius:2px;width:0%;transition:width .4s"></div>
        </div>
      </div>`,
      `<div id="installed-models-list" style="display:flex;flex-direction:column;gap:6px;margin-top:4px"></div>`,
    ].join('')),

    _sec('Routage sémantique', [
      _mkText('semantic_router.embedding_model', 'Modèle d\'embedding',
        'Pour le routeur Ollama (ex: nomic-embed-text)', 'nomic-embed-text'),
      _mkNumber('semantic_router.confidence_threshold', 'Seuil de confiance',
        'Minimum pour router (0.1 – 1.0)', 0, 1, 0.05),
    ].join('')),

    _sec('N8N (automatisation)', [
      _mkUrlRow('n8n.url', 'URL N8N', 'Serveur N8N local', 'n8n'),
      _mkToggle('n8n.fallback_enabled', 'Fallback N8N', 'Utiliser N8N si fonction locale échoue'),
    ].join('')),
  ].join('');
}

function _panelDomotique() {
  return [
    _sec('Home Assistant', [
      _mkToggle('home_assistant.enabled', 'Activer Home Assistant', ''),
      _mkUrlRow('home_assistant.url', 'URL Home Assistant', 'ex: http://homeassistant.local:8123', 'ha'),
      _mkText('home_assistant.token', 'Token long durée', 'Créé dans Profil → Tokens', '', 'password'),
      _mkText('home_assistant.tts_service', 'Service TTS', 'Entité TTS Home Assistant', 'tts.piper'),
      _mkToggle('home_assistant.door_alert_enabled', 'Alerte porte', 'Notifier via Telegram à l\'ouverture'),
      _mkText('home_assistant.door_entity', 'Entité porte', 'Entity ID du capteur de porte', 'binary_sensor.porte'),
      _mkText('home_assistant.door_message', 'Message alerte porte', '', '🚪 Un visiteur !'),
    ].join('')),

    _sec('Domoticz', [
      _mkToggle('domoticz.enabled', 'Activer Domoticz', ''),
      _mkUrlRow('domoticz.url', 'URL Domoticz', 'ex: http://192.168.1.10:8080', 'domoticz'),
      _mkText('domoticz.username', 'Utilisateur', 'Laisser vide si pas d\'auth', 'admin'),
      _mkText('domoticz.password', 'Mot de passe', '', '', 'password'),
    ].join('')),

    _sec('Kasa (TP-Link)', [
      _mkToggle('kasa.enabled', 'Activer Kasa', 'Découverte automatique des prises Kasa sur le réseau'),
    ].join('')),
  ].join('');
}

function _panelPrint3D() {
  return [
    _sec('Imprimante K1', [
      _mkText('k1.ip', 'Adresse IP', 'IP de l\'imprimante K1 sur le réseau', '192.168.1.xxx'),
      _mkText('k1.password', 'Mot de passe SSH', '', '', 'password'),
    ].join('')),

    _sec('CAD / Build123D', [
      `<div class="s-row"><div class="s-row-info">
        <div class="s-row-label">Modèle de génération 3D</div>
        <div class="s-row-desc">Utilise le modèle LLM configuré dans l'onglet LLM → Modèle principal</div>
      </div></div>`,
    ].join('')),
  ].join('');
}

function _panelMusique() {
  return [
    _sec('Navidrome', [
      _mkUrlRow('navidrome.url', 'URL Navidrome', 'ex: http://localhost:4533', 'navidrome'),
      _mkText('navidrome.user', 'Utilisateur', '', 'admin'),
      _mkText('navidrome.password', 'Mot de passe', '', '', 'password'),
    ].join('')),

  ].join('');
}

function _panelBibliotheque() {
  return [
    _sec('Calibre-Web', [
      _mkUrlRow('calibre.url', 'URL Calibre-Web', 'ex: http://192.168.1.70:8083', 'calibre'),
      _mkText('calibre.username', 'Nom d\'utilisateur', 'Identifiant Calibre-Web', ''),
      _mkText('calibre.password', 'Mot de passe', 'Mot de passe Calibre-Web', '', 'password'),
    ].join('')),
  ].join('');
}

// MODULE_SOCIETE: panel settings
async function _panelSociete() {
  let companies = [];
  try {
    const r = await fetch('/api/societe/companies');
    if (r.ok) companies = await r.json();
  } catch {}

  const rows = companies.length
    ? companies.map(c => `
      <div class="sc-row" data-cid="${c.id}">
        <span class="sc-logo">${c.logo || '🏢'}</span>
        <span class="sc-name">${c.name}</span>
        <span class="sc-tag sc-tag--${c.type || 'client'}">${c.type || 'client'}</span>
        <span class="sc-tag sc-tag--${c.status || 'active'}">${c.status || 'active'}</span>
        <button class="s-btn sc-edit-btn" data-cid="${c.id}" title="Modifier">✏️</button>
        <button class="s-btn danger sc-del-btn" data-cid="${c.id}" title="Supprimer">✕</button>
      </div>`).join('')
    : '<div style="color:#64748b;font-size:.85rem;padding:.5rem 0">Aucune société enregistrée</div>';

  return `
  ${_sec('Activation', [
    _mkToggle('modules.societe', 'Activer le module Sociétés CRM',
      'Active le tableau de bord, les API et la navigation — pris en compte au prochain démarrage'),
  ].join(''))}

  ${_sec(`Sociétés enregistrées (${companies.length})`, `<div id="sc-list">${rows}</div>`)}

  ${_sec('Ajouter une société', `
    <div class="sc-form" id="sc-add-form">
      <div class="sc-form-row">
        <input class="s-input" id="sc-f-id"    placeholder="ID unique* (ex: acme)" />
        <input class="s-input" id="sc-f-name"  placeholder="Nom affiché *" />
      </div>
      <div class="sc-form-row">
        <input class="s-input sc-emoji" id="sc-f-logo"  placeholder="🏢" value="🏢" />
        <input class="s-input sc-color" id="sc-f-color" type="color" value="#5E6AD2" />
        <select class="s-input" id="sc-f-type">
          <option value="SARL">SARL</option>
          <option value="SAS">SAS</option>
          <option value="EI">EI (Entreprise Individuelle)</option>
          <option value="SCI">SCI</option>
          <option value="Holding">Holding</option>
          <option value="Autre">Autre</option>
        </select>
        <select class="s-input" id="sc-f-status">
          <option value="active">active</option>
          <option value="archive">archive</option>
        </select>
      </div>
      <div class="sc-form-row">
        <input class="s-input" id="sc-f-email"   placeholder="Email" />
        <input class="s-input" id="sc-f-phone"   placeholder="Téléphone" />
        <input class="s-input" id="sc-f-website" placeholder="Site web" />
      </div>
      <div class="sc-form-row">
        <textarea class="s-input sc-notes" id="sc-f-notes" placeholder="Notes internes…" rows="2"></textarea>
      </div>
      <button class="s-btn primary" id="sc-add-btn">➕ Ajouter la société</button>
      <span id="sc-add-status" style="margin-left:.75rem;font-size:.85rem"></span>
    </div>
  `)}`;
}

// ── Panel Auth ────────────────────────────────────────────────
let _authUsers = [];
let _authGroups = {};

async function _panelAuth() {
  // Charger la config auth
  let authEnabled = false;
  let isAdmin = false;
  let users = [];
  let groups = {};
  try {
    const cfg = await fetch('/api/auth/config').then(r => r.json());
    authEnabled = cfg.enabled || false;
    groups = cfg.groups || {};
  } catch {}

  // Quand auth désactivée : accès admin libre (réseau local) — permet de préparer les comptes
  if (!authEnabled) {
    isAdmin = true;
    try {
      users = await fetch('/api/auth/admin/users').then(r => r.ok ? r.json() : []);
      _authUsers = users;
      _authGroups = groups;
    } catch {}
  } else {
    try {
      const me = await fetch('/api/auth/me').then(r => r.json());
      isAdmin = me.groups?.includes('admin');
      if (isAdmin) {
        users = await fetch('/api/auth/admin/users').then(r => r.json());
      }
      _authUsers = users;
      _authGroups = groups;
    } catch {}
  }

  const groupBadges = Object.keys(groups).map(g =>
    `<span class="auth-group-badge">${g}</span>`
  ).join(' ');

  const usersHtml = isAdmin && users.length > 0 ? `
    <div class="auth-users-list">
      ${users.map(u => `
        <div class="auth-user-row" data-uid="${u.id}">
          <div class="auth-user-info">
            <span class="auth-user-name">${u.display_name}</span>
            <span class="auth-user-login">@${u.username}</span>
            <span class="auth-user-badges">${(u.groups || []).map(g =>
              `<span class="auth-group-badge">${g}</span>`).join('')}
            </span>
          </div>
          <div class="auth-user-actions">
            <span class="auth-user-devices">${u.device_count || 0} appareil(s)</span>
            <button class="s-btn auth-invite-btn" data-uid="${u.id}" data-name="${u.display_name}">
              QR invitation
            </button>
            ${u.id !== '_self' ? `<button class="s-btn danger auth-del-btn" data-uid="${u.id}">✕</button>` : ''}
          </div>
        </div>`).join('')}
    </div>` : '';

  const createForm = isAdmin ? `
    <div class="auth-create-form">
      <h4 class="s-section-title" style="margin-bottom:.75rem">Créer un utilisateur</h4>
      <div style="display:flex;gap:.5rem;flex-wrap:wrap">
        <input id="auth-new-username"     class="s-input" type="text" placeholder="login" style="flex:1;min-width:100px"/>
        <input id="auth-new-displayname"  class="s-input" type="text" placeholder="Prénom" style="flex:1;min-width:100px"/>
        <select id="auth-new-groups" class="s-input" style="min-width:130px">
          ${Object.keys(groups).map(g => `<option value="${g}">${g}</option>`).join('')}
        </select>
        <button class="s-btn" id="auth-create-user-btn">Créer</button>
      </div>
    </div>` : '';

  const myDevices = authEnabled ? `
    <div class="s-section">
      <h3 class="s-section-title">Mes appareils</h3>
      <div id="auth-devices-list"><span style="color:#64748b;font-size:.85rem">Chargement…</span></div>
      <div style="margin-top:.75rem;display:flex;gap:.5rem;flex-wrap:wrap">
        <button class="s-btn" id="auth-gen-recovery">Générer des codes de récupération</button>
      </div>
      <div id="auth-recovery-codes" class="auth-recovery-codes hidden"></div>
    </div>` : '';

  return `
  ${_sec('Authentification', [
    _mkToggle('auth.enabled', 'Activer l\'authentification',
      'Protège toutes les routes par JWT. Un redémarrage du serveur applique le changement.'),
    authEnabled ? `<div class="s-row">
      <div class="s-row-info">
        <div class="s-row-label">Groupes disponibles</div>
        <div class="s-row-desc">Chaque groupe donne accès à un sous-ensemble de menus.</div>
      </div>
      <div>${groupBadges}</div>
    </div>` : '',
  ].join(''))}

  ${isAdmin ? `
  <div class="s-section">
    <h3 class="s-section-title">Utilisateurs (${users.length})</h3>
    ${!authEnabled && users.length === 0 ? `<div style="color:#f59e0b;font-size:.85rem;margin-bottom:.75rem;padding:.5rem .75rem;background:#451a03;border-radius:6px">⚠️ Créez au moins un utilisateur avant d'activer l'authentification.</div>` : ''}
    ${usersHtml}
    ${createForm}
    <div id="auth-invite-qr" class="auth-invite-qr hidden"></div>
  </div>` : ''}

  ${myDevices}`;
}

// ── MODULE_DOCUMENTS: panel RAG documentaire ─────────────────
async function _panelDocuments() {
  // Charger le statut en direct depuis l'API
  let status = null;
  try {
    const r = await fetch('/api/documents/status');
    if (r.ok) status = await r.json();
  } catch {}

  const st = status?.stats || {};
  const mt = status?.mount || {};
  const statsHtml = status ? `
    <div class="doc-stat-grid">
      <div class="doc-stat"><span class="doc-stat-n">${st.documents ?? '—'}</span><span class="doc-stat-l">Documents</span></div>
      <div class="doc-stat"><span class="doc-stat-n">${st.chunks ?? '—'}</span><span class="doc-stat-l">Chunks FTS5</span></div>
      <div class="doc-stat"><span class="doc-stat-n">${st.total_size_bytes ? Math.round(st.total_size_bytes/1024) + ' Ko' : '—'}</span><span class="doc-stat-l">Taille totale</span></div>
      <div class="doc-stat"><span class="doc-stat-n">${st.last_update ? st.last_update.slice(0,16).replace('T',' ') : '—'}</span><span class="doc-stat-l">Dernière MAJ</span></div>
    </div>` : '<div style="color:#64748b;font-size:.85rem">Statistiques indisponibles</div>';

  const mountBadge = mt.ok === true
    ? `<span style="color:#4caf50">✓ Monté (${mt.device || 'OK'})</span>`
    : mt.ok === false
    ? `<span style="color:#ef5350">✗ ${mt.reason || 'Non monté'}</span>`
    : '<span style="color:#64748b">—</span>';

  return `
  ${_sec('Activation', [
    _mkToggle('documents.enabled', 'Activer la base documentaire RAG',
      'Indexe les fichiers Markdown et les injecte dans le contexte du chat (SQLite FTS5)'),
  ].join(''))}

  ${_sec('Chemin source', [
    _mkText('documents.root_path', 'Dossier racine', 'Chemin absolu vers le dossier de documentation Markdown', '/mnt/nvme/docs'),
    _mkText('documents.index_path', 'Chemin de la base SQLite', 'Laisser vide pour utiliser data/documents.db', ''),
  ].join(''))}

  ${_sec('Vérification de montage', [
    _mkToggle('documents.require_mount', 'Exiger un point de montage valide',
      'Interdit l\'indexation si le disque n\'est pas monté correctement'),
    _mkText('documents.expected_mount_path', 'Point de montage attendu', 'Ex: /mnt/nvme', '/mnt/nvme'),
    _mkText('documents.expected_device_hint', 'Indice device (optionnel)', 'Ex: nvme0n1, sdb, D:', ''),
    `<div class="s-row">
      <div class="s-row-info">
        <div class="s-row-label">État du montage</div>
        <div class="s-row-desc" id="doc-mount-status">${mountBadge}</div>
      </div>
      <button class="s-btn" id="doc-check-mount-btn">Vérifier</button>
    </div>`,
  ].join(''))}

  ${_sec('Indexation', [
    _mkToggle('documents.auto_index_on_startup', 'Indexation automatique au démarrage',
      'Réindexe les fichiers nouveaux ou modifiés à chaque lancement du serveur'),
    _mkNumber('documents.chunk_size', 'Taille des chunks (caractères)', 'Taille maximale d\'un chunk Markdown', 400, 4000, 100),
    _mkNumber('documents.chunk_overlap', 'Overlap (caractères)', 'Chevauchement entre chunks consécutifs', 0, 800, 50),
    `<div class="s-row">
      <div class="s-row-info">
        <div class="s-row-label">Actions</div>
        <div class="s-row-desc" id="doc-reindex-status"></div>
      </div>
      <div style="display:flex;gap:8px;flex-wrap:wrap">
        <button class="s-btn primary" id="doc-reindex-btn">⟳ Réindexer</button>
        <button class="s-btn" id="doc-reindex-force-btn">⟳ Forcer tout</button>
        <button class="s-btn danger" id="doc-delete-index-btn">✕ Vider l'index</button>
      </div>
    </div>`,
  ].join(''))}

  ${_sec('Contexte RAG (injection LLM)', [
    _mkNumber('documents.max_context_chunks', 'Chunks max injectés', 'Nombre de chunks documentaires injectés dans le prompt', 1, 20, 1),
    _mkNumber('documents.max_context_chars', 'Caractères max injectés', 'Limite de taille du contexte documentaire', 1000, 20000, 500),
    _mkNumber('documents.min_query_length', 'Longueur minimale de requête', 'Requêtes plus courtes ignorent le RAG', 1, 20, 1),
    _mkToggle('documents.include_sources_in_answer', 'Inclure les sources', 'Ajoute les chemins de fichiers dans le contexte'),
  ].join(''))}

  ${_sec('Statistiques', statsHtml)}`;
}

// ── Build HTML ────────────────────────────────────────────────
async function _buildHTML() {
  const [authHtml, societeHtml, pluginsHtml, documentsHtml] = await Promise.all([
    _panelAuth(),
    _panelSociete(),
    _panelPlugins(),
    _panelDocuments(),
  ]);
  // Visibilité initiale des onglets selon les modules actifs
  const _tabVis = (mod) => _get(`modules.${mod}`) ? '' : 'display:none';
  return `
<div class="settings-wrap">
  <div class="s-tabbar">
    <button class="s-tab active" data-panel="general">🏠 Accueil</button>
    <button class="s-tab" data-panel="plugins">🧩 Plugins</button>
    <button class="s-tab" data-panel="llm">🤖 LLM</button>
    <button class="s-tab" data-mod-tab="domotique" data-panel="domotique" style="${_tabVis('domotique')}">💡 Domotique</button>
    <button class="s-tab" data-mod-tab="print3d" data-panel="print3d" style="${_tabVis('print3d')}">🖨 Impression 3D</button>
    <button class="s-tab" data-mod-tab="music" data-panel="music" style="${_tabVis('music')}">🎵 Musique</button>
    <button class="s-tab" data-mod-tab="bibliotheque" data-panel="bibliotheque" style="${_tabVis('bibliotheque')}">📚 Bibliothèque</button>
    <button class="s-tab" data-mod-tab="societe" data-panel="societe" style="${_tabVis('societe')}">🏢 Sociétés</button>
    <button class="s-tab" data-panel="documents">📂 Documents</button>
    <button class="s-tab" data-panel="auth">🔐 Auth</button>
    <span class="s-save-dot" id="s-savedot"></span>
  </div>
  <div class="s-panels">
    <div class="s-panel active" id="panel-general">${_panelAccueil()}</div>
    <div class="s-panel" id="panel-plugins">${pluginsHtml}</div>
    <div class="s-panel" id="panel-llm">${_panelLLM()}</div>
    <div class="s-panel" id="panel-domotique">${_panelDomotique()}</div>
    <div class="s-panel" id="panel-print3d">${_panelPrint3D()}</div>
    <div class="s-panel" id="panel-music">${_panelMusique()}</div>
    <div class="s-panel" id="panel-bibliotheque">${_panelBibliotheque()}</div>
    <div class="s-panel" id="panel-societe">${societeHtml}</div>
    <div class="s-panel" id="panel-documents">${documentsHtml}</div>
    <div class="s-panel" id="panel-auth">${authHtml}</div>
  </div>
</div>`;
}

// ── Events ────────────────────────────────────────────────────
const _debouncedSave = _debounce(_save, 700);

function _bindEvents(root) {
  // Tab switching
  root.querySelectorAll('.s-tab').forEach(tab => {
    tab.addEventListener('click', () => {
      root.querySelectorAll('.s-tab').forEach(t => t.classList.remove('active'));
      root.querySelectorAll('.s-panel').forEach(p => p.classList.remove('active'));
      tab.classList.add('active');
      root.getElementById?.('panel-' + tab.dataset.panel)?.classList.add('active');
      // querySelector inside root (root is the viewport div)
      root.querySelector('#panel-' + tab.dataset.panel)?.classList.add('active');
    });
  });

  // Text / number inputs (debounced)
  root.querySelectorAll('input[data-key]').forEach(el => {
    el.addEventListener('input', () => {
      const type = el.dataset.type;
      const val = type === 'bool' ? el.checked : (el.type === 'number' ? Number(el.value) : el.value);
      _debouncedSave(el.dataset.key, val);
    });
  });

  // Checkboxes (immediate)
  root.querySelectorAll('input[data-type="bool"]').forEach(el => {
    el.addEventListener('change', () => _save(el.dataset.key, el.checked));
  });

  // Selects (immediate)
  root.querySelectorAll('select[data-key]').forEach(el => {
    el.addEventListener('change', () => {
      const v = el.type === 'number' || el.dataset.numtype ? Number(el.value) : el.value;
      // briefing.hour should be a number
      const val = (el.dataset.key === 'briefing.hour') ? Number(el.value) : el.value;
      _save(el.dataset.key, val);
    });
  });

  // Module cards
  root.querySelectorAll('.s-module-card').forEach(card => {
    card.addEventListener('click', () => {
      const key = card.dataset.mod;
      const current = _get(key);
      const next = !current;
      // Mise à jour immédiate du cache local (AVANT applyModuleVisibility)
      const parts = key.split('.');
      let obj = _cfg;
      for (let i = 0; i < parts.length - 1; i++) {
        if (!obj[parts[i]]) obj[parts[i]] = {};
        obj = obj[parts[i]];
      }
      obj[parts[parts.length - 1]] = next;
      // UI
      card.classList.toggle('enabled', next);
      card.querySelector('.mod-badge').textContent = next ? 'Activé' : 'Désactivé';
      applyModuleVisibility();
      // Persistance asynchrone
      _save(key, next);
    });
  });

  // Test buttons
  root.querySelectorAll('[data-test]').forEach(btn => {
    btn.addEventListener('click', () => _testConnection(btn, root));
  });

  // Refresh models
  const refreshBtn = root.querySelector('#refresh-models');
  if (refreshBtn) {
    refreshBtn.addEventListener('click', () => _loadModels(root));
  }

  // Pull model
  const pullBtn   = root.querySelector('#pull-model-btn');
  const pullInput = root.querySelector('#pull-model-input');
  if (pullBtn && pullInput) {
    const _startPull = async () => {
      const name = pullInput.value.trim();
      if (!name) return;
      const progress  = root.querySelector('#pull-progress');
      const statusEl  = root.querySelector('#pull-status');
      const barEl     = root.querySelector('#pull-bar');
      pullBtn.disabled = true;
      pullInput.disabled = true;
      if (progress) progress.style.display = 'block';
      if (statusEl) statusEl.textContent = `Démarrage du téléchargement de ${name}…`;
      if (barEl) barEl.style.width = '0%';
      try {
        const resp = await fetch('/api/ollama/pull', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ name }),
        });
        const reader  = resp.body.getReader();
        const decoder = new TextDecoder();
        let buf = '';
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          buf += decoder.decode(value, { stream: true });
          const lines = buf.split('\n');
          buf = lines.pop();
          for (const line of lines) {
            if (!line.startsWith('data:')) continue;
            const raw = line.slice(5).trim();
            if (raw === '[DONE]') break;
            try {
              const d = JSON.parse(raw);
              if (d.error) { if (statusEl) statusEl.textContent = `Erreur : ${d.error}`; break; }
              if (d.status && statusEl) statusEl.textContent = d.status;
              if (d.total && d.completed && barEl) {
                barEl.style.width = Math.round((d.completed / d.total) * 100) + '%';
              }
            } catch {}
          }
        }
        if (statusEl) statusEl.textContent = `${name} téléchargé ✓`;
        if (barEl) barEl.style.width = '100%';
        pullInput.value = '';
        await _loadModels(root);
      } catch(e) {
        if (statusEl) statusEl.textContent = `Erreur : ${e.message}`;
      } finally {
        pullBtn.disabled = false;
        pullInput.disabled = false;
        setTimeout(() => { if (progress) progress.style.display = 'none'; }, 3000);
      }
    };
    pullBtn.addEventListener('click', _startPull);
    pullInput.addEventListener('keydown', e => { if (e.key === 'Enter') _startPull(); });
  }
}

async function _testConnection(btn, root) {
  const testId = btn.dataset.test;
  btn.disabled = true;
  btn.textContent = '…';

  let url = '';
  let ok = false;
  try {
    if (testId === 'ollama') {
      url = _cfg.ollama_url || '';
      const base = url.replace(/\/api\/?$/, '');
      const r = await fetch('/api/status');
      ok = (await r.json()).ollama === 'online';
    } else if (testId === 'ha') {
      url = (_cfg.home_assistant?.url || '').rstrip('/') + '/api/';
      const r = await fetch(url, { headers: { Authorization: `Bearer ${_cfg.home_assistant?.token || ''}` }, signal: AbortSignal.timeout(5000) });
      ok = r.ok;
    } else if (testId === 'domoticz') {
      url = (_cfg.domoticz?.url || '').replace(/\/$/, '') + '/json.htm?type=command&param=getversion';
      const r = await fetch(`/api/proxy/get?url=${encodeURIComponent(url)}`, { signal: AbortSignal.timeout(5000) });
      ok = r.ok;
    } else if (testId === 'navidrome') {
      const base = (_cfg.navidrome?.url || '').replace(/\/$/, '');
      const u = _cfg.navidrome?.user || '';
      const p = _cfg.navidrome?.password || '';
      const testUrl = `${base}/rest/ping.view?u=${u}&p=${p}&v=1.16.0&c=ada&f=json`;
      const r = await fetch(testUrl, { signal: AbortSignal.timeout(5000) });
      const data = await r.json();
      ok = data?.['subsonic-response']?.status === 'ok';
    } else if (testId === 'calibre') {
      url = (_cfg.calibre?.url || '').replace(/\/$/, '') + '/ajax/library-info';
      const r = await fetch(url, { signal: AbortSignal.timeout(5000) });
      ok = r.ok;
    } else if (testId === 'n8n') {
      url = (_cfg.n8n?.url || '').replace(/\/$/, '') + '/healthz';
      const r = await fetch(url, { signal: AbortSignal.timeout(5000) });
      ok = r.ok;
    }
  } catch { ok = false; }

  btn.disabled = false;
  btn.textContent = ok ? '✓ OK' : '✗ Erreur';
  btn.style.color = ok ? '#4caf50' : '#ef5350';
  setTimeout(() => { btn.textContent = 'Test'; btn.style.color = ''; }, 3000);
}

async function _loadModels(root) {
  const countEl = root.querySelector('#models-count');
  if (countEl) countEl.textContent = 'Chargement…';
  try {
    const r = await fetch('/api/ollama/models');
    const data = await r.json();
    _models = Array.isArray(data) ? data : [];
    if (countEl) countEl.textContent = `${_models.length} modèle(s) disponible(s)`;
    // Refresh model selects
    ['models.chat', 'models.web_agent'].forEach(key => {
      const sel = root.querySelector(`select[data-key="${key}"]`);
      if (!sel) return;
      const current = _get(key);
      sel.innerHTML = _models.map(m => `<option value="${m}" ${m === current ? 'selected' : ''}>${m}</option>`).join('');
    });
    // Refresh installed models list
    const listEl = root.querySelector('#installed-models-list');
    if (listEl) {
      listEl.innerHTML = _models.length ? _models.map(m => `
        <div style="display:flex;align-items:center;gap:8px;padding:6px 10px;
          background:rgba(255,255,255,0.03);border:1px solid rgba(255,255,255,0.06);
          border-radius:8px">
          <span style="font-size:11px;font-family:ui-monospace,monospace;color:#e8edf2;flex:1">${m}</span>
          <button class="s-btn" style="font-size:10px;padding:3px 10px;color:#ff3b5c;border-color:rgba(255,59,92,0.3)"
            data-delete-model="${m}">✕ Supprimer</button>
        </div>`).join('')
        : '<div style="font-size:11px;color:#5a6a7a">Aucun modèle installé</div>';
      // Bind delete buttons
      listEl.querySelectorAll('[data-delete-model]').forEach(btn => {
        btn.addEventListener('click', async () => {
          const name = btn.dataset.deleteModel;
          if (!confirm(`Supprimer le modèle "${name}" ? Cette action est irréversible.`)) return;
          btn.disabled = true;
          btn.textContent = '…';
          try {
            const res = await fetch(`/api/ollama/models/${encodeURIComponent(name)}`, { method: 'DELETE' });
            const data = await res.json();
            if (data.ok) await _loadModels(root);
            else btn.textContent = '✗ Erreur';
          } catch { btn.textContent = '✗ Erreur'; }
        });
      });
    }
  } catch {
    if (countEl) countEl.textContent = 'Ollama inaccessible';
  }
}

// ── Nav module visibility ─────────────────────────────────────
export function applyModuleVisibility() {
  // Visibilité des éléments de navigation principaux
  const map = {
    domotique:    ['[data-page="home"]', '[data-view="cameras"]'],
    print3d:      ['[data-page="printers"]', '[data-page="cad"]'],
    music:        ['[data-page="music"]'],
    bibliotheque: ['[data-page="library"]'],
  };
  Object.entries(map).forEach(([mod, selectors]) => {
    const on = _get(`modules.${mod}`);
    selectors.forEach(sel => {
      document.querySelectorAll(sel).forEach(el => {
        el.style.display = on ? '' : 'none';
      });
    });
  });

  // Visibilité des onglets de configuration dans les Paramètres
  if (!_root) return;
  const modTabMap = ['domotique', 'print3d', 'music', 'bibliotheque', 'societe'];
  modTabMap.forEach(mod => {
    const on  = _get(`modules.${mod}`);
    const tab = _root.querySelector(`[data-mod-tab="${mod}"]`);
    if (!tab) return;
    tab.style.display = on ? '' : 'none';
    // Si cet onglet était actif et qu'on le masque → revenir sur Accueil
    if (!on && tab.classList.contains('active')) {
      _root.querySelectorAll('.s-tab').forEach(t => t.classList.remove('active'));
      _root.querySelectorAll('.s-panel').forEach(p => p.classList.remove('active'));
      _root.querySelector('[data-panel="general"]')?.classList.add('active');
      _root.querySelector('#panel-general')?.classList.add('active');
    }
  });
}

// ── MODULE_DOCUMENTS: event bindings ────────────────────────
function _bindDocumentsEvents(root) {
  const panel = root.querySelector('#panel-documents');
  if (!panel) return;

  // Vérifier le montage
  panel.querySelector('#doc-check-mount-btn')?.addEventListener('click', async () => {
    const btn = panel.querySelector('#doc-check-mount-btn');
    const statusEl = panel.querySelector('#doc-mount-status');
    if (btn) btn.disabled = true;
    try {
      const r = await fetch('/api/documents/status');
      const data = await r.json();
      const mt = data.mount || {};
      if (statusEl) {
        statusEl.innerHTML = mt.ok
          ? `<span style="color:#4caf50">✓ Monté (${mt.device || 'OK'}) — ${mt.filesystem || ''} sur ${mt.root_path}</span>`
          : `<span style="color:#ef5350">✗ ${mt.reason || 'Non monté'}</span>`;
      }
    } catch (e) {
      if (statusEl) statusEl.innerHTML = `<span style="color:#ef5350">Erreur : ${e.message}</span>`;
    } finally {
      if (btn) btn.disabled = false;
    }
  });

  // Réindexer (incrémental)
  panel.querySelector('#doc-reindex-btn')?.addEventListener('click', () => _doReindex(panel, false));
  // Réindexer (forcer tout)
  panel.querySelector('#doc-reindex-force-btn')?.addEventListener('click', () => _doReindex(panel, true));

  // Vider l'index
  panel.querySelector('#doc-delete-index-btn')?.addEventListener('click', async () => {
    if (!confirm('Vider entièrement l\'index documentaire ? Les fichiers sources ne sont pas touchés.')) return;
    const statusEl = panel.querySelector('#doc-reindex-status');
    try {
      const r = await fetch('/api/documents/index', { method: 'DELETE' });
      const data = await r.json();
      if (statusEl) statusEl.innerHTML = '<span style="color:#4caf50">Index vidé ✓</span>';
      setTimeout(() => { if (statusEl) statusEl.innerHTML = ''; }, 3000);
      // Rafraîchir les stats
      await _refreshDocStats(panel);
    } catch (e) {
      if (statusEl) statusEl.innerHTML = `<span style="color:#ef5350">Erreur : ${e.message}</span>`;
    }
  });
}

async function _doReindex(panel, force) {
  const statusEl = panel.querySelector('#doc-reindex-status');
  const btn = panel.querySelector(force ? '#doc-reindex-force-btn' : '#doc-reindex-btn');
  if (btn) btn.disabled = true;
  if (statusEl) statusEl.innerHTML = '<span style="color:#94a3b8">Indexation en cours…</span>';
  try {
    const r = await fetch('/api/documents/reindex', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ force }),
    });
    const data = await r.json();
    if (!r.ok) throw new Error(data.detail || r.statusText);
    const res = data.result || {};
    const total = (res.indexed || 0) + (res.updated || 0);
    if (statusEl) statusEl.innerHTML =
      `<span style="color:#4caf50">✓ ${total} traités, ${res.skipped || 0} ignorés, ${res.deleted || 0} supprimés${res.errors ? ', ' + res.errors + ' erreurs' : ''}</span>`;
    setTimeout(() => { if (statusEl) statusEl.innerHTML = ''; }, 5000);
    await _refreshDocStats(panel);
  } catch (e) {
    if (statusEl) statusEl.innerHTML = `<span style="color:#ef5350">Erreur : ${e.message}</span>`;
  } finally {
    if (btn) btn.disabled = false;
  }
}

async function _refreshDocStats(panel) {
  try {
    const r = await fetch('/api/documents/status');
    const data = await r.json();
    const st = data.stats || {};
    const grid = panel.querySelector('.doc-stat-grid');
    if (!grid) return;
    const vals = [
      st.documents ?? '—',
      st.chunks ?? '—',
      st.total_size_bytes ? Math.round(st.total_size_bytes / 1024) + ' Ko' : '—',
      st.last_update ? st.last_update.slice(0, 16).replace('T', ' ') : '—',
    ];
    grid.querySelectorAll('.doc-stat-n').forEach((el, i) => {
      if (vals[i] !== undefined) el.textContent = vals[i];
    });
  } catch {}
}

// ── Auth event bindings ───────────────────────────────────────
function _bindAuthEvents(root) {
  // Bloquer l'activation si aucun utilisateur enregistré
  const authToggle = root.querySelector('input[data-key="auth.enabled"]');
  if (authToggle) {
    authToggle.addEventListener('change', async (e) => {
      if (!e.target.checked) return; // désactivation toujours permise
      try {
        const users = await fetch('/api/auth/admin/users').then(r => r.ok ? r.json() : []);
        if (!Array.isArray(users) || users.length === 0) {
          e.target.checked = false;
          // Annuler la sauvegarde déjà déclenchée par _bindEvents
          await fetch('/api/settings', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ key: 'auth.enabled', value: false }),
          });
          showToast('⚠️ Créez au moins un utilisateur avant d\'activer l\'auth !');
          return;
        }
      } catch {
        e.target.checked = false;
        showToast('Impossible de vérifier les utilisateurs');
      }
    }, true); // capture phase → s'exécute avant le listener de _bindEvents
  }

  // Créer un utilisateur
  root.querySelector('#auth-create-user-btn')?.addEventListener('click', async () => {
    const username     = root.querySelector('#auth-new-username')?.value.trim();
    const display_name = root.querySelector('#auth-new-displayname')?.value.trim() || username;
    const groups       = [root.querySelector('#auth-new-groups')?.value || 'assistant'];
    if (!username) { showToast('Nom d\'utilisateur requis'); return; }
    try {
      const r = await fetch('/api/auth/admin/users', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username, display_name, groups }),
      });
      if (r.ok) { showToast('Utilisateur créé'); location.reload(); }
      else { const d = await r.json(); showToast(d.detail || 'Erreur'); }
    } catch { showToast('Erreur réseau'); }
  });

  // Supprimer un utilisateur
  root.querySelectorAll('.auth-del-btn').forEach(btn => {
    btn.addEventListener('click', async () => {
      if (!confirm('Désactiver cet utilisateur ?')) return;
      const uid = btn.dataset.uid;
      try {
        await fetch(`/api/auth/admin/users/${uid}`, { method: 'DELETE' });
        showToast('Utilisateur désactivé');
        btn.closest('.auth-user-row').remove();
      } catch { showToast('Erreur'); }
    });
  });

  // QR invitation
  root.querySelectorAll('.auth-invite-btn').forEach(btn => {
    btn.addEventListener('click', async () => {
      const uid  = btn.dataset.uid;
      const name = btn.dataset.name;
      try {
        const r = await fetch('/api/auth/admin/invite', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ user_id: uid, device_name: `Appareil de ${name}` }),
        });
        const data = await r.json();
        const area = root.querySelector('#auth-invite-qr');
        if (area && data.qr_png_b64) {
          area.innerHTML = `
            <p style="color:#94a3b8;font-size:.85rem;margin-bottom:.5rem">
              QR d'invitation pour <strong>${name}</strong> (valable 1h)
            </p>
            <img src="data:image/png;base64,${data.qr_png_b64}"
                 style="width:180px;height:180px;border-radius:8px" alt="QR invite"/>
            <p style="color:#64748b;font-size:.75rem;margin-top:.4rem;word-break:break-all">
              ${data.enroll_url}
            </p>`;
          area.classList.remove('hidden');
        }
      } catch { showToast('Erreur génération QR'); }
    });
  });

  // Codes de récupération
  root.querySelector('#auth-gen-recovery')?.addEventListener('click', async () => {
    try {
      const r = await fetch('/api/auth/recovery/generate', { method: 'POST' });
      const data = await r.json();
      const area = root.querySelector('#auth-recovery-codes');
      if (area) {
        area.innerHTML = `
          <p style="color:#fbbf24;font-size:.85rem;margin-bottom:.5rem">
            ⚠️ Conservez ces codes en lieu sûr. Ils ne seront plus affichés.
          </p>
          <div class="recovery-codes-grid">${data.codes.map(c =>
            `<code class="recovery-code">${c}</code>`).join('')}
          </div>`;
        area.classList.remove('hidden');
      }
    } catch { showToast('Erreur'); }
  });

  // Révoquer un appareil
  root.addEventListener('click', async (e) => {
    const btn = e.target.closest('.auth-revoke-device');
    if (!btn) return;
    const did = btn.dataset.did;
    if (!confirm('Révoquer cet appareil ?')) return;
    try {
      await fetch(`/api/auth/devices/${did}`, { method: 'DELETE' });
      showToast('Appareil révoqué');
      btn.closest('.auth-device-row')?.remove();
    } catch { showToast('Erreur'); }
  });
}

async function _loadMyDevices(root) {
  const list = root.querySelector('#auth-devices-list');
  if (!list) return;
  try {
    const r = await fetch('/api/auth/devices');
    if (!r.ok) { list.innerHTML = '<span style="color:#64748b;font-size:.85rem">Non disponible</span>'; return; }
    const devices = await r.json();
    if (!devices.length) { list.innerHTML = '<span style="color:#64748b;font-size:.85rem">Aucun appareil enregistré</span>'; return; }
    list.innerHTML = devices.map(d => `
      <div class="auth-device-row">
        <span class="auth-device-name">${d.device_name}</span>
        <span class="auth-device-date">${d.last_seen
          ? new Date(d.last_seen * 1000).toLocaleDateString('fr')
          : 'Jamais vu'}</span>
        <button class="s-btn danger auth-revoke-device" data-did="${d.id}">Révoquer</button>
      </div>`).join('');
  } catch { list.innerHTML = '<span style="color:#64748b;font-size:.85rem">Erreur chargement</span>'; }
}

// ── MODULE_SOCIETE: Company CRUD events ───────────────────────
function _bindSocieteEvents(root) {
  const panel = root.querySelector('#panel-societe');
  if (!panel) return;

  // Supprimer une société
  panel.addEventListener('click', async e => {
    const delBtn = e.target.closest('.sc-del-btn');
    if (delBtn) {
      const cid = delBtn.dataset.cid;
      if (!confirm(`Supprimer la société "${cid}" ? Cette action est irréversible.`)) return;
      try {
        const r = await fetch(`/api/societe/companies/${cid}`, { method: 'DELETE' });
        if (!r.ok) throw new Error(await r.text());
        delBtn.closest('.sc-row').remove();
        showToast(`Société "${cid}" supprimée`);
        // Update compteur
        const h3 = panel.querySelector('.s-section-title');
        if (h3 && h3.textContent.includes('enregistrées')) {
          const remaining = panel.querySelectorAll('.sc-row').length;
          h3.textContent = `Sociétés enregistrées (${remaining})`;
        }
      } catch (err) { showToast('Erreur : ' + err.message); }
    }
  });

  // Modifier une société (édition inline)
  panel.addEventListener('click', async e => {
    const editBtn = e.target.closest('.sc-edit-btn');
    if (!editBtn) return;
    const cid = editBtn.dataset.cid;
    const row = editBtn.closest('.sc-row');
    if (!row || row.classList.contains('editing')) return;
    let company;
    try {
      const r = await fetch(`/api/societe/companies/${cid}`);
      if (!r.ok) throw new Error(await r.text());
      company = await r.json();
    } catch(err) { showToast('Erreur chargement : ' + err.message); return; }

    const origHtml = row.innerHTML;
    row.classList.add('editing');
    const typeOpts = ['SARL','SAS','EI','SCI','Holding','Autre']
      .map(t => `<option value="${t}"${company.type===t?' selected':''}>${t}</option>`).join('');
    const statusOpts = ['active','archive']
      .map(s => `<option value="${s}"${company.status===s?' selected':''}>${s}</option>`).join('');

    row.innerHTML = `
      <div class="sc-edit-inline">
        <div class="sc-form" style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:8px">
          <label class="sc-form-row"><span>Nom</span><input class="s-input sc-e-name" value="${company.name}"></label>
          <label class="sc-form-row"><span>Forme</span><select class="s-input sc-e-type">${typeOpts}</select></label>
          <label class="sc-form-row"><span>Statut</span><select class="s-input sc-e-status">${statusOpts}</select></label>
          <label class="sc-form-row"><span>Email</span><input class="s-input sc-e-email" value="${company.email||''}"></label>
          <label class="sc-form-row"><span>Tél</span><input class="s-input sc-e-phone" value="${company.phone||''}"></label>
          <label class="sc-form-row"><span>Site</span><input class="s-input sc-e-website" value="${company.website||''}"></label>
        </div>
        <div style="display:flex;gap:8px;align-items:center;margin-top:8px;flex-wrap:wrap">
          <label class="sc-form-row" style="flex:0 0 auto">
            <span>Logo</span><input class="s-input sc-e-logo" value="${company.logo||'🏢'}" style="width:64px">
          </label>
          <label class="sc-form-row" style="flex:0 0 auto">
            <span>Couleur</span><input type="color" class="sc-e-color sc-color" value="${company.color||'#5E6AD2'}">
          </label>
          <label class="sc-form-row" style="flex:1">
            <span>Notes</span><input class="s-input sc-e-notes" value="${company.notes||''}">
          </label>
          <button class="s-btn primary sc-e-save" data-cid="${cid}">✓ Sauvegarder</button>
          <button class="s-btn sc-e-cancel">✕ Annuler</button>
        </div>
      </div>`;

    row.querySelector('.sc-e-cancel').addEventListener('click', () => {
      row.innerHTML = origHtml;
      row.classList.remove('editing');
    });

    row.querySelector('.sc-e-save').addEventListener('click', async () => {
      const get = cls => row.querySelector(cls)?.value?.trim() || '';
      const payload = {
        name:    get('.sc-e-name'),
        type:    row.querySelector('.sc-e-type')?.value || 'SARL',
        status:  row.querySelector('.sc-e-status')?.value || 'active',
        email:   get('.sc-e-email'),
        phone:   get('.sc-e-phone'),
        website: get('.sc-e-website'),
        logo:    get('.sc-e-logo') || '🏢',
        color:   get('.sc-e-color') || '#5E6AD2',
        notes:   get('.sc-e-notes'),
      };
      try {
        const r = await fetch(`/api/societe/companies/${cid}`, {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload),
        });
        if (!r.ok) {
          const err = await r.json().catch(() => ({ detail: r.statusText }));
          throw new Error(err.detail || r.statusText);
        }
        const updated = await r.json();
        row.classList.remove('editing');
        row.innerHTML = `
          <span class="sc-logo">${updated.logo || '🏢'}</span>
          <span class="sc-name">${updated.name}</span>
          <span class="sc-tag sc-tag--${updated.type}">${updated.type}</span>
          <span class="sc-tag sc-tag--${updated.status}">${updated.status}</span>
          <button class="s-btn sc-edit-btn" data-cid="${updated.id}" title="Modifier">✏️</button>
          <button class="s-btn danger sc-del-btn" data-cid="${updated.id}" title="Supprimer">✕</button>`;
        showToast(`"${updated.name}" mis à jour`);
      } catch(err) { showToast('Erreur : ' + err.message); }
    });
  });

  // Ajouter une société
  const addBtn = panel.querySelector('#sc-add-btn');
  if (!addBtn) return;
  addBtn.addEventListener('click', async () => {
    const get = id => panel.querySelector(id)?.value?.trim() || '';
    const id   = get('#sc-f-id');
    const name = get('#sc-f-name');
    if (!id || !name) { showToast('ID et Nom sont obligatoires'); return; }

    const payload = {
      id,
      name,
      logo:    get('#sc-f-logo') || '🏢',
      color:   get('#sc-f-color') || '#5E6AD2',
      type:    panel.querySelector('#sc-f-type')?.value || 'SARL',
      status:  panel.querySelector('#sc-f-status')?.value || 'active',
      email:   get('#sc-f-email'),
      phone:   get('#sc-f-phone'),
      website: get('#sc-f-website'),
      notes:   panel.querySelector('#sc-f-notes')?.value?.trim() || '',
    };

    const statusEl = panel.querySelector('#sc-add-status');
    addBtn.disabled = true;
    if (statusEl) statusEl.textContent = '…';
    try {
      const r = await fetch('/api/societe/companies', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      if (!r.ok) {
        const err = await r.json().catch(() => ({ detail: r.statusText }));
        throw new Error(err.detail || r.statusText);
      }
      const created = await r.json();

      // Injecter dans la liste
      const list = panel.querySelector('#sc-list');
      if (list) {
        // Retirer le message "Aucune société"
        const empty = list.querySelector('div[style]');
        if (empty) empty.remove();
        const row = document.createElement('div');
        row.className = 'sc-row';
        row.dataset.cid = created.id;
        row.innerHTML = `
          <span class="sc-logo">${created.logo || '🏢'}</span>
          <span class="sc-name">${created.name}</span>
          <span class="sc-tag sc-tag--${created.type}">${created.type}</span>
          <span class="sc-tag sc-tag--${created.status}">${created.status}</span>
          <button class="s-btn sc-edit-btn" data-cid="${created.id}" title="Modifier">✏️</button>
          <button class="s-btn danger sc-del-btn" data-cid="${created.id}" title="Supprimer">✕</button>`;
        list.appendChild(row);
      }
      // Update compteur
      const h3 = panel.querySelector('.s-section-title');
      if (h3 && h3.textContent.includes('enregistrées')) {
        const total = panel.querySelectorAll('.sc-row').length;
        h3.textContent = `Sociétés enregistrées (${total})`;
      }
      // Reset form
      ['#sc-f-id','#sc-f-name','#sc-f-email','#sc-f-phone','#sc-f-website'].forEach(sel => {
        const el = panel.querySelector(sel);
        if (el) el.value = '';
      });
      panel.querySelector('#sc-f-logo').value = '🏢';
      panel.querySelector('#sc-f-color').value = '#5E6AD2';
      panel.querySelector('#sc-f-notes').value = '';

      if (statusEl) statusEl.textContent = '✓ Ajoutée';
      setTimeout(() => { if (statusEl) statusEl.textContent = ''; }, 2500);
      showToast(`Société "${created.name}" créée`);
    } catch (err) {
      if (statusEl) statusEl.textContent = '✗ ' + err.message;
      showToast('Erreur : ' + err.message);
    } finally {
      addBtn.disabled = false;
    }
  });
}

// ── mount / unmount ───────────────────────────────────────────
let _root = null;

export async function mount(container) {
  _ensureCSS();
  setInputBarVisible(false);

  // Load settings + models in parallel
  container.innerHTML = `<div class="s-loading">Chargement des paramètres…</div>`;
  try {
    const [cfgRes, modRes] = await Promise.all([
      fetch('/api/settings'),
      fetch('/api/ollama/models'),
    ]);
    _cfg = await cfgRes.json();
    const rawModels = await modRes.json();
    _models = Array.isArray(rawModels) ? rawModels : [];
  } catch (e) {
    container.innerHTML = `<div class="s-loading">Erreur : ${e.message}</div>`;
    return;
  }

  container.innerHTML = await _buildHTML();
  _root = container;
  _bindEvents(container);
  _bindAuthEvents(container);
  _bindSocieteEvents(container);
  _bindDocumentsEvents(container);
  // Appliquer la visibilité des onglets config selon modules actifs
  applyModuleVisibility();

  // Show models count
  const countEl = container.querySelector('#models-count');
  if (countEl) countEl.textContent = `${_models.length} modèle(s) disponible(s)`;

  // Load own devices in auth panel
  _loadMyDevices(container);

  // Populate installed models list
  _loadModels(container);
}

export function unmount() {
  _root = null;
}
