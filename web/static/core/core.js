/* ================================================================
   ADA Mobile — Core Module
   Sidebar, navigation, toast, status polling, view dispatcher.
   Chaque vue est un module ES importé dynamiquement.
   ================================================================ */

// ── Registre des vues ───────────────────────────────────────────
const VIEW_LOADERS = {
  dashboard: () => import('/static/views/dashboard/index.js'),
  chat:      () => import('/static/views/chat/index.js'),
  memory:    () => import('/static/views/memory/index.js'),
  page:      () => import('/static/views/page/index.js'),
  planner:   () => import('/static/views/planner/index.js'),
  briefing:  () => import('/static/views/briefing/index.js'),
  webagent:  () => import('/static/views/webagent/index.js'),
  cameras:   () => import('/static/views/cameras/index.js'),
  marketing: () => import('/static/views/marketing/index.js'),
  settings:  () => import('/static/views/settings/index.js?v=2'),
  'profile-editor': () => import('/static/views/profile-editor/index.js'),
  auth:      () => import('/static/views/auth/index.js'),
  // MODULE_SOCIETE
  societe:   () => import('/static/views/societe/index.js?v=2'),
  // MODULE_SKILLS
  skills:    () => import('/static/views/skills/index.js'),
};

const VIEW_TITLES = {
  dashboard: 'Tableau de bord',
  chat:      'Discussion',
  memory:    'Mémoire',
  planner:   'Planificateur',
  briefing:  'Briefing',
  webagent:  'Agent Web',
  cameras:   'Caméras',
  marketing: 'Marketing',
  settings:  'Paramètres',
  'profile-editor': 'Profils & Univers',
  auth:      'Connexion',
  // MODULE_SOCIETE
  societe:   'Sociétés',
  // MODULE_SKILLS
  skills:    'AutoSkills',
};

// ── État global ─────────────────────────────────────────────────
export let currentView = '';
let _currentMod = null;

// ── Gestion du token d'authentification ─────────────────────────
export function getToken() { return localStorage.getItem('ada_token'); }

export function setToken(token) {
  localStorage.setItem('ada_token', token);
  document.cookie = `ada_token=${token}; path=/; SameSite=Strict; Max-Age=${30 * 86_400}`;
}

export function clearToken() {
  localStorage.removeItem('ada_token');
  document.cookie = 'ada_token=; path=/; SameSite=Strict; Max-Age=0';
}

// ── DOM ─────────────────────────────────────────────────────────
const sidebar        = document.getElementById('sidebar');
const sidebarOverlay = document.getElementById('sidebar-overlay');
const menuBtn        = document.getElementById('menu-btn');
const sidebarClose   = document.getElementById('sidebar-close');
const navItems       = document.querySelectorAll('.nav-item');
const viewTitle      = document.getElementById('view-title');
const statusDot      = document.getElementById('status-dot');
const adminMenu      = document.getElementById('admin-menu');
const toastEl        = document.getElementById('toast');
const inputBar       = document.getElementById('input-bar');
export const viewport = document.getElementById('viewport');

// ── Menu admin ──────────────────────────────────────────────────
statusDot?.addEventListener('click', (e) => {
  e.stopPropagation();
  adminMenu?.classList.toggle('hidden');
});
document.addEventListener('click', () => adminMenu?.classList.add('hidden'));
adminMenu?.addEventListener('click', (e) => e.stopPropagation());

document.getElementById('admin-restart')?.addEventListener('click', async () => {
  adminMenu.classList.add('hidden');
  showToast('Redémarrage en cours…');
  try {
    await fetch('/api/admin/restart', { method: 'POST' });
    setTimeout(() => location.reload(), 2000);
  } catch { /* le process se coupe, c'est normal */ setTimeout(() => location.reload(), 2500); }
});

document.getElementById('admin-clear-cache')?.addEventListener('click', async () => {
  adminMenu.classList.add('hidden');
  if ('serviceWorker' in navigator && 'caches' in window) {
    const keys = await caches.keys();
    await Promise.all(keys.map((k) => caches.delete(k)));
    const reg = await navigator.serviceWorker.getRegistration();
    if (reg) await reg.unregister();
    showToast('Cache vidé — rechargement…');
    setTimeout(() => location.reload(true), 1000);
  } else {
    showToast('Cache SW non disponible.');
  }
});

// ── Utilitaires exportés ────────────────────────────────────────
let _toastTimer;
export function showToast(msg) {
  toastEl.textContent = msg;
  toastEl.classList.add('show');
  clearTimeout(_toastTimer);
  _toastTimer = setTimeout(() => toastEl.classList.remove('show'), 2500);
}

export function escapeHtml(text = '') {
  return String(text)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}

// ── Visibilité des modules nav (domotique / print3d / music) ────
export function applyModuleVisibility(modules = {}) {
  const map = {
    domotique: ['[data-page="home"]', '[data-view="cameras"]'],
    print3d:   ['[data-page="printers"]', '[data-page="cad"]'],
    music:     ['[data-page="music"]', '[data-page="library"]'],
  };
  for (const [mod, selectors] of Object.entries(map)) {
    const visible = modules[mod] !== false;
    selectors.forEach(sel => {
      document.querySelectorAll(sel).forEach(el => {
        el.style.display = visible ? '' : 'none';
      });
    });
  }
}

export async function fetchJSON(url, options = {}) {
  const token = getToken();
  const headers = {
    ...(token ? { 'Authorization': `Bearer ${token}` } : {}),
    ...(options.headers || {}),
  };
  const r = await fetch(url, { ...options, headers });
  if (r.status === 401) {
    clearToken();
    switchView('auth');
    throw new Error('Non authentifié');
  }
  if (!r.ok) throw new Error(`HTTP ${r.status}`);
  return r.json();
}

export function setInputBarVisible(v) {
  if (!inputBar) return;
  if (v) inputBar.classList.remove('hidden');
  else   inputBar.classList.add('hidden');
}

// ── Sidebar ─────────────────────────────────────────────────────
export function closeSidebar() {
  sidebar?.classList.remove('open');
  sidebarOverlay?.classList.remove('open');
}
function openSidebar() {
  sidebar?.classList.add('open');
  sidebarOverlay?.classList.add('open');
}

menuBtn?.addEventListener('click', openSidebar);
sidebarClose?.addEventListener('click', closeSidebar);
sidebarOverlay?.addEventListener('click', closeSidebar);

let _touchStartX = 0;
sidebar?.addEventListener('touchstart', (e) => { _touchStartX = e.touches[0].clientX; }, { passive: true });
sidebar?.addEventListener('touchend',   (e) => {
  if (e.changedTouches[0].clientX - _touchStartX < -60) closeSidebar();
}, { passive: true });

// ── Statut Ollama + barre hw ────────────────────────────────────
const _hwBar = {
  cpu:    document.getElementById('hw-cpu'),
  ram:    document.getElementById('hw-ram'),
  gpu:    document.getElementById('hw-gpu'),
  vram:   document.getElementById('hw-vram'),
  models: document.getElementById('hw-models'),
};

function _colorStat(el, pct) {
  if (!el) return;
  el.style.color = pct > 85 ? '#ff6b6b' : pct > 60 ? '#ffd166' : '#9de8b0';
}

async function _checkStatus() {
  try {
    const d = await (await fetch('/api/status')).json();
    if (statusDot) statusDot.className = d.ollama === 'online' ? 'online' : 'offline';
  } catch { if (statusDot) statusDot.className = 'offline'; }
}

async function _updateHwBar() {
  try {
    const d = await (await fetch('/api/dashboard')).json();
    if (_hwBar.cpu) {
      _hwBar.cpu.textContent = `${d.cpu_pct}%`;
      _colorStat(_hwBar.cpu, d.cpu_pct);
    }
    if (_hwBar.ram && d.ram) {
      _hwBar.ram.textContent = `${d.ram.pct}% (${d.ram.used_gb}/${d.ram.total_gb} GB)`;
      _colorStat(_hwBar.ram, d.ram.pct);
    }
    if (_hwBar.gpu) {
      _hwBar.gpu.textContent = d.vram ? `${Math.round((d.vram.used_gb / d.vram.total_gb) * 100)}%` : '—';
    }
    if (_hwBar.vram && d.vram) {
      _hwBar.vram.textContent = `${d.vram.used_gb}/${d.vram.total_gb} GB`;
      _colorStat(_hwBar.vram, (d.vram.used_gb / d.vram.total_gb) * 100);
    }
    if (_hwBar.models) {
      const names = (d.loaded_models || []).map((m) => m.split(':')[0]).join(', ') || (d.model ? d.model.split(':')[0] : '—');
      _hwBar.models.textContent = names;
    }
  } catch { /* silencieux */ }
}

_checkStatus();
_updateHwBar();
setInterval(_checkStatus, 30_000);
setInterval(_updateHwBar, 15_000);

// ── Navigation ──────────────────────────────────────────────────
function _updateNavActive(viewName, pageKey) {
  navItems.forEach((n) => n.classList.remove('active'));
  if (viewName === 'chat') {
    document.querySelector('[data-view="chat"]')?.classList.add('active');
  } else if (viewName === 'page' && pageKey) {
    document.querySelector(`[data-page="${pageKey}"]`)?.classList.add('active');
  } else {
    document.querySelector(`[data-view="${viewName}"]`)?.classList.add('active');
  }
}

export async function switchView(viewName, opts = {}) {
  if (window.adaNavigate) { window.adaNavigate(viewName); return; }
  closeSidebar();

  // Démonte la vue courante
  try { _currentMod?.unmount?.(); } catch { /* ignore */ }
  if (viewport) viewport.innerHTML = '';
  inputBar?.classList.add('hidden');

  // Mise à jour état + UI immédiate (feedback avant import)
  currentView = viewName;
  _updateNavActive(viewName, opts.page);
  viewTitle.textContent = VIEW_TITLES[viewName] ?? opts.label ?? '';

  const loader = VIEW_LOADERS[viewName];
  if (!loader) { console.warn('[ADA core] vue inconnue :', viewName); return; }

  const mod = await loader();
  _currentMod = mod;
  await mod.mount(viewport, opts);
}

// ── Câblage clics nav ───────────────────────────────────────────
navItems.forEach((item) => {
  item.addEventListener('click', () => {
    const view  = item.dataset.view;
    const page  = item.dataset.page || '';
    const hint  = item.dataset.hint || '';
    const label = item.querySelector('span')?.textContent || '';

    if (view === 'page' && page) {
      switchView('page', { page, hint, label });
    } else if (hint) {
      switchView(view, { prefill: hint, label });
    } else {
      switchView(view, { label });
    }
  });
});

// ── Service Worker ──────────────────────────────────────────────
if ('serviceWorker' in navigator) {
  navigator.serviceWorker.register('/sw.js').catch(() => {});
}

// ── Auth — permissions nav ───────────────────────────────────────
// Mapping nav-item → menu_tag
function _navItemTag(item) {
  const view = item.dataset.view;
  const page = item.dataset.page;
  if (page) return page;  // home, cad, printers, skills, senses, music, library, infrastructure
  return view;            // dashboard, chat, memory, planner, briefing, webagent, cameras, marketing, settings, auth
}

export function applyPermissions(accessibleTags) {
  if (!accessibleTags) return;
  navItems.forEach(item => {
    const tag = _navItemTag(item);
    item.style.display = accessibleTags.includes(tag) ? '' : 'none';
  });
}

// ── Map module → icône SVG inline (fallback nav dynamique) ──────
const _MODULE_ICON_SVG = {
  dashboard:      '<path d="M3 3h8v8H3zm0 10h8v8H3zM13 3h8v8h-8zm0 10h8v8h-8z" fill-rule="evenodd"/>',
  chat:           '<path d="M20 2H4c-1.1 0-2 .9-2 2v18l4-4h14c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2z"/>',
  planner:        '<path d="M19 3h-1V1h-2v2H8V1H6v2H5c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h14c1.1 0 2-.9 2-2V5c0-1.1-.9-2-2-2zm0 16H5V8h14v11zM7 10h5v5H7z"/>',
  briefing:       '<path d="M19 3H5c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h14c1.1 0 2-.9 2-2V5c0-1.1-.9-2-2-2zM7 7h10v2H7zm0 4h10v2H7zm0 4h7v2H7z"/>',
  home:           '<path d="M10 20v-6h4v6h5v-8h3L12 3 2 12h3v8z"/>',
  cameras:        '<path d="M17 10.5V7c0-.55-.45-1-1-1H4c-.55 0-1 .45-1 1v10c0 .55.45 1 1 1h12c.55 0 1-.45 1-1v-3.5l4 4v-11l-4 4z"/>',
  senses:         '<path d="M12 1C5.93 1 1 5.93 1 12s4.93 11 11 11 11-4.93 11-11S18.07 1 12 1zm0 20c-4.96 0-9-4.04-9-9s4.04-9 9-9 9 4.04 9 9-4.04 9-9 9zm.5-13H11v6l5.25 3.15.75-1.23-4.5-2.67z"/>',
  music:          '<path d="M12 3v10.55c-.59-.34-1.27-.55-2-.55-2.21 0-4 1.79-4 4s1.79 4 4 4 4-1.79 4-4V7h4V3h-6z"/>',
  infrastructure: '<path d="M19.14 12.94c.04-.3.06-.61.06-.94 0-.32-.02-.64-.07-.94l2.03-1.58c.18-.14.23-.41.12-.61l-1.92-3.32c-.12-.22-.37-.29-.59-.22l-2.39.96c-.5-.38-1.03-.7-1.62-.94l-.36-2.54c-.04-.24-.24-.41-.48-.41h-3.84c-.24 0-.43.17-.47.41l-.36 2.54c-.59.24-1.13.57-1.62.94l-2.39-.96c-.22-.08-.47 0-.59.22L2.74 8.87c-.12.21-.08.47.12.61l2.03 1.58c-.05.3-.09.63-.09.94s.02.64.07.94l-2.03 1.58c-.18.14-.23.41-.12.61l1.92 3.32c.12.22.37.29.59.22l2.39-.96c.5.38 1.03.7 1.62.94l.36 2.54c.05.24.24.41.48.41h3.84c.24 0 .44-.17.47-.41l.36-2.54c.59-.24 1.13-.56 1.62-.94l2.39.96c.22.08.47 0 .59-.22l1.92-3.32c.12-.22.07-.47-.12-.61l-2.01-1.58zM12 15.6c-1.98 0-3.6-1.62-3.6-3.6s1.62-3.6 3.6-3.6 3.6 1.62 3.6 3.6-1.62 3.6-3.6 3.6z"/>',
  societe:        '<path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-1 17.93c-3.95-.49-7-3.85-7-7.93 0-.62.08-1.21.21-1.79L9 15v1c0 1.1.9 2 2 2v1.93zm6.9-2.54c-.26-.81-1-1.39-1.9-1.39h-1v-3c0-.55-.45-1-1-1H8v-2h2c.55 0 1-.45 1-1V7h2c1.1 0 2-.9 2-2v-.41c2.93 1.19 5 4.06 5 7.41 0 2.08-.8 3.97-2.1 5.39z"/>',
  marketing:      '<path d="M3 17.25V21h3.75L17.81 9.94l-3.75-3.75L3 17.25zM20.71 7.04c.39-.39.39-1.02 0-1.41l-2.34-2.34c-.39-.39-1.02-.39-1.41 0l-1.83 1.83 3.75 3.75 1.83-1.83z"/>',
  webagent:       '<path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-1 17.93c-3.95-.49-7-3.85-7-7.93 0-.62.08-1.21.21-1.79L9 15v1c0 1.1.9 2 2 2v1.93zm6.9-2.54c-.26-.81-1-1.39-1.9-1.39h-1v-3c0-.55-.45-1-1-1H8v-2h2c.55 0 1-.45 1-1V7h2c1.1 0 2-.9 2-2v-.41c2.93 1.19 5 4.06 5 7.41 0 2.08-.8 3.97-2.1 5.39z"/>',
  cad:            '<path d="M7.75 2.75h-1.5c-.69 0-1.25.56-1.25 1.25v1.5C5 6.19 5.56 6.75 6.25 6.75h1.5c.69 0 1.25-.56 1.25-1.25v-1.5c0-.69-.56-1.25-1.25-1.25zm8.5 0h-1.5c-.69 0-1.25.56-1.25 1.25v1.5c0 .69.56 1.25 1.25 1.25h1.5c.69 0 1.25-.56 1.25-1.25v-1.5c0-.69-.56-1.25-1.25-1.25zM12 9l-7 4 7 4 7-4-7-4zm-7 6l7 4 7-4"/>',
  printers:       '<path d="M19 8H5c-1.66 0-3 1.34-3 3v6h4v4h12v-4h4v-6c0-1.66-1.34-3-3-3zm-3 11H8v-5h8v5zm3-7c-.55 0-1-.45-1-1s.45-1 1-1 1 .45 1 1-.45 1-1 1zm-1-9H6v4h12V3z"/>',
  skills:         '<path d="M19 3H5c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h14c1.1 0 2-.9 2-2V5c0-1.1-.9-2-2-2zM9 17H7v-7h2v7zm4 0h-2V7h2v10zm4 0h-2v-4h2v4z"/>',
  memory:         '<path d="M13 3c-4.97 0-9 4.03-9 9H1l3.89 3.89.07.14L9 12H6c0-3.87 3.13-7 7-7s7 3.13 7 7-3.13 7-7 7c-1.93 0-3.68-.79-4.94-2.06l-1.42 1.42C8.27 19.99 10.51 21 13 21c4.97 0 9-4.03 9-9s-4.03-9-9-9zm-1 5v5l4.28 2.54.72-1.21-3.5-2.08V8H12z"/>',
  library:        '<path d="M18 2H6c-1.1 0-2 .9-2 2v16c0 1.1.9 2 2 2h12c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2zM6 4h5v8l-2.5-1.5L6 12V4z"/>',
  settings:       '<path d="M19.14 12.94c.04-.3.06-.61.06-.94 0-.32-.02-.64-.07-.94l2.03-1.58c.18-.14.23-.41.12-.61l-1.92-3.32c-.12-.22-.37-.29-.59-.22l-2.39.96c-.5-.38-1.03-.7-1.62-.94l-.36-2.54c-.04-.24-.24-.41-.48-.41h-3.84c-.24 0-.43.17-.47.41l-.36 2.54c-.59.24-1.13.57-1.62.94l-2.39-.96c-.22-.08-.47 0-.59.22L2.74 8.87c-.12.21-.08.47.12.61l2.03 1.58c-.05.3-.09.63-.09.94s.02.64.07.94l-2.03 1.58c-.18.14-.23.41-.12.61l1.92 3.32c.12.22.37.29.59.22l2.39-.96c.5.38 1.03.7 1.62.94l.36 2.54c.05.24.24.41.48.41h3.84c.24 0 .44-.17.47-.41l.36-2.54c.59-.24 1.13-.56 1.62-.94l2.39.96c.22.08.47 0 .59-.22l1.92-3.32c.12-.22.07-.47-.12-.61l-2.01-1.58zM12 15.6c-1.98 0-3.6-1.62-3.6-3.6s1.62-3.6 3.6-3.6 3.6 1.62 3.6 3.6-1.62 3.6-3.6 3.6z"/>',
};

/**
 * Construit la nav sidebar dynamiquement depuis les univers du profil.
 * Remplace les nav-items existants. Si universes est vide, la nav statique reste.
 */
export function buildNav(universes, defaultUniverseId) {
  if (!universes || universes.length === 0) return;

  const navList = document.querySelector('.nav-list');
  if (!navList) return;

  // Supprimer les nav-items existants
  navList.querySelectorAll('.nav-item').forEach(el => el.remove());

  for (const universe of universes) {
    const li = document.createElement('li');
    li.className = 'nav-item';
    li.dataset.universe = universe.id;

    // Le premier module de l'univers est la vue d'entrée
    const entryModule = universe.modules[0] || 'dashboard';
    li.dataset.view = entryModule === 'planner' || entryModule === 'briefing' ||
                      entryModule === 'home' || entryModule === 'cad' ||
                      entryModule === 'printers' || entryModule === 'skills' ||
                      entryModule === 'senses' || entryModule === 'music' ||
                      entryModule === 'library' || entryModule === 'infrastructure'
                      ? 'page' : entryModule;
    if (li.dataset.view === 'page') li.dataset.page = entryModule;

    const svgPath = _MODULE_ICON_SVG[entryModule] || _MODULE_ICON_SVG['dashboard'];
    li.innerHTML = `<svg viewBox="0 0 24 24">${svgPath}</svg><span>${universe.name}</span>`;

    if (universe.id === defaultUniverseId) li.classList.add('active');

    li.addEventListener('click', () => {
      const view  = li.dataset.view;
      const page  = li.dataset.page || '';
      const label = universe.name;
      if (view === 'page' && page) {
        switchView('page', { page, label });
      } else {
        switchView(view, { label });
      }
    });

    navList.appendChild(li);
  }

  // Toujours réinjecter le bouton Paramètres épinglé en bas (margin-top: auto via CSS)
  const settingsLi = document.createElement('li');
  settingsLi.className = 'nav-item';
  settingsLi.dataset.view = 'settings';
  settingsLi.innerHTML = `<svg viewBox="0 0 24 24">${_MODULE_ICON_SVG['settings']}</svg><span>Paramètres</span>`;
  settingsLi.addEventListener('click', () => switchView('settings', { label: 'Paramètres' }));
  navList.appendChild(settingsLi);
}

/**
 * Charge le profil depuis /api/profile et applique thème, densité, nav.
 * Silencieux en cas d'échec (fallback nav statique).
 */
async function _loadAndApplyProfile() {
  try {
    const data = await fetchJSON('/api/profile');
    const profile = data.profile;
    if (!profile) return;

    // Appliquer thème
    document.documentElement.setAttribute('data-theme', profile.theme || 'dark');

    // Appliquer densité
    document.documentElement.setAttribute('data-density', profile.density || 'normal');

    // Construire la nav dynamiquement
    buildNav(profile.universes, profile.default_universe_id);
  } catch {
    // Fallback silencieux — nav statique reste en place
  }
}

// ── Auth — gate de démarrage ─────────────────────────────────────
async function _authGate() {
  try {
    const cfg = await fetch('/api/auth/config').then(r => r.json());
    if (!cfg.enabled) return; // auth désactivée → tout accès autorisé

    const token = getToken();
    if (!token) { await switchView('auth'); return; }

    const r = await fetch('/api/auth/me', {
      headers: { 'Authorization': `Bearer ${token}` },
    });

    if (r.status === 401) {
      clearToken();
      await switchView('auth');
      return;
    }

    if (r.ok) {
      const me = await r.json();
      applyPermissions(me.accessible_tags);
      await _loadAndApplyProfile();
      // Synchronise aussi le cookie pour les requêtes sans header
      document.cookie = `ada_token=${token}; path=/; SameSite=Strict; Max-Age=${30 * 86_400}`;
      // Afficher le bouton logout dans le menu admin
      const logoutBtn = document.getElementById('admin-logout');
      if (logoutBtn) logoutBtn.style.display = '';
    }
  } catch { /* erreur réseau → ne pas bloquer l'app */ }
}

// ── Auth — confirmation QR (appareil authentifié scanne le QR) ──
async function _handleQRConfirm(code) {
  const token = getToken();
  if (!token) return; // non connecté → ne peut pas confirmer

  const modal = document.createElement('div');
  modal.id = 'qr-confirm-modal';
  modal.style.cssText = [
    'position:fixed;inset:0;z-index:9999;background:rgba(0,0,0,.7)',
    'display:flex;align-items:center;justify-content:center;padding:1.5rem',
  ].join(';');
  modal.innerHTML = `
    <div style="background:#1e2330;border-radius:16px;padding:2rem;max-width:360px;width:100%;
                border:1px solid rgba(123,104,238,.3)">
      <h2 style="color:#c7d2fe;margin:0 0 .5rem;font-size:1.1rem">Nouveau appareil</h2>
      <p style="color:#94a3b8;font-size:.9rem;margin:0 0 1.25rem">
        Un nouvel appareil demande à accéder à ADA.<br>
        Voulez-vous l'autoriser ?
      </p>
      <div style="display:flex;gap:.75rem">
        <button id="qrc-cancel" style="flex:1;padding:.6rem;border:1px solid #374151;border-radius:8px;
                background:transparent;color:#94a3b8;cursor:pointer">Refuser</button>
        <button id="qrc-confirm" style="flex:1;padding:.6rem;border:none;border-radius:8px;
                background:#7b68ee;color:#fff;cursor:pointer">Autoriser</button>
      </div>
    </div>`;
  document.body.appendChild(modal);

  // Clean URL
  history.replaceState({}, '', window.location.pathname);

  document.getElementById('qrc-cancel').onclick = () => modal.remove();
  document.getElementById('qrc-confirm').onclick = async () => {
    const btn = document.getElementById('qrc-confirm');
    if (btn) btn.disabled = true;
    try {
      const r = await fetch('/api/auth/confirm', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` },
        body: JSON.stringify({ code }),
      });
      const data = await r.json();
      if (r.ok) {
        showToast('✅ ' + (data.message || 'Appareil autorisé'));
      } else {
        showToast('Erreur : ' + (data.detail || 'Code invalide'));
      }
    } catch { showToast('Erreur réseau'); }
    modal.remove();
  };
}

// ── Logout ───────────────────────────────────────────────────────
document.getElementById('admin-logout')?.addEventListener('click', async () => {
  adminMenu.classList.add('hidden');
  await fetch('/api/auth/logout', { method: 'POST' });
  clearToken();
  location.reload();
});

// ── Démarrage ────────────────────────────────────────────────────
(async () => {
  // 1. Vérifier si un QR de confirmation est dans l'URL
  const urlParams = new URLSearchParams(window.location.search);
  const confirmCode = urlParams.get('confirm');

  // 2. Auth gate
  await _authGate();

  // 3. Si la vue auth a été montée → s'arrêter
  if (currentView === 'auth') return;

  // 4. Visibilité des modules (settings)
  try {
    const cfg = await fetch('/api/settings').then(r => r.json());
    applyModuleVisibility(cfg.modules || {});
  } catch {}

  // 5. Vue initiale
  switchView('dashboard');

  // 6. Confirmation QR (si présente dans l'URL, APRÈS être authentifié)
  if (confirmCode) _handleQRConfirm(confirmCode);
})();
