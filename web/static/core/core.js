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
  webagent:  () => import('/static/views/webagent/index.js'),
  cameras:   () => import('/static/views/cameras/index.js'),
  marketing: () => import('/static/views/marketing/index.js'),
};

const VIEW_TITLES = {
  dashboard: 'Tableau de bord',
  chat:      'Discussion',
  memory:    'Mémoire',
  webagent:  'Agent Web',
  cameras:   'Caméras',
  marketing: 'Marketing',
};

// ── État global ─────────────────────────────────────────────────
export let currentView = '';
let _currentMod = null;

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
statusDot.addEventListener('click', (e) => {
  e.stopPropagation();
  adminMenu.classList.toggle('hidden');
});
document.addEventListener('click', () => adminMenu.classList.add('hidden'));
adminMenu.addEventListener('click', (e) => e.stopPropagation());

document.getElementById('admin-restart').addEventListener('click', async () => {
  adminMenu.classList.add('hidden');
  showToast('Redémarrage en cours…');
  try {
    await fetch('/api/admin/restart', { method: 'POST' });
    setTimeout(() => location.reload(), 2000);
  } catch { /* le process se coupe, c'est normal */ setTimeout(() => location.reload(), 2500); }
});

document.getElementById('admin-clear-cache').addEventListener('click', async () => {
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

export async function fetchJSON(url) {
  const r = await fetch(url);
  if (!r.ok) throw new Error(`HTTP ${r.status}`);
  return r.json();
}

export function setInputBarVisible(v) {
  if (v) inputBar.classList.remove('hidden');
  else   inputBar.classList.add('hidden');
}

// ── Sidebar ─────────────────────────────────────────────────────
export function closeSidebar() {
  sidebar.classList.remove('open');
  sidebarOverlay.classList.remove('open');
}
function openSidebar() {
  sidebar.classList.add('open');
  sidebarOverlay.classList.add('open');
}

menuBtn.addEventListener('click', openSidebar);
sidebarClose.addEventListener('click', closeSidebar);
sidebarOverlay.addEventListener('click', closeSidebar);

let _touchStartX = 0;
sidebar.addEventListener('touchstart', (e) => { _touchStartX = e.touches[0].clientX; }, { passive: true });
sidebar.addEventListener('touchend',   (e) => {
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
    statusDot.className = d.ollama === 'online' ? 'online' : 'offline';
  } catch { statusDot.className = 'offline'; }
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
  closeSidebar();

  // Démonte la vue courante
  try { _currentMod?.unmount?.(); } catch { /* ignore */ }
  viewport.innerHTML = '';
  inputBar.classList.add('hidden');

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

// ── Démarrage ───────────────────────────────────────────────────
switchView('dashboard');
