/* ================================================================
   Vue Dashboard — mount / unmount
   ================================================================ */
import { showToast, fetchJSON } from '/static/core/core.js';

const _CSS = '/static/views/dashboard/style.css';

function _ensureCSS() {
  if (!document.getElementById('css-dashboard')) {
    const l = document.createElement('link');
    l.id = 'css-dashboard'; l.rel = 'stylesheet'; l.href = _CSS;
    document.head.appendChild(l);
  }
}

const _HTML = `
<div id="dashboard-cards" class="dashboard-grid">
  <div class="dash-card loading" id="card-ollama">
    <div class="dash-card-icon">🤖</div>
    <div class="dash-card-label">Modèle</div>
    <div class="dash-card-value" id="dc-model">…</div>
  </div>
  <div class="dash-card loading" id="card-cpu">
    <div class="dash-card-icon">⚙️</div>
    <div class="dash-card-label">CPU</div>
    <div class="dash-card-value" id="dc-cpu">…</div>
  </div>
  <div class="dash-card loading" id="card-ram">
    <div class="dash-card-icon">💾</div>
    <div class="dash-card-label">RAM</div>
    <div class="dash-card-value" id="dc-ram">…</div>
  </div>
  <div class="dash-card loading" id="card-disk">
    <div class="dash-card-icon">🗄️</div>
    <div class="dash-card-label">Disque</div>
    <div class="dash-card-value" id="dc-disk">…</div>
  </div>
  <div class="dash-card loading" id="card-vram" style="display:none">
    <div class="dash-card-icon">🎮</div>
    <div class="dash-card-label">VRAM</div>
    <div class="dash-card-value" id="dc-vram">…</div>
  </div>
</div>
<button class="refresh-btn" id="dashboard-refresh">
  <svg viewBox="0 0 24 24" width="18" height="18"><path d="M17.65 6.35C16.2 4.9 14.21 4 12 4c-4.42 0-7.99 3.58-7.99 8s3.57 8 7.99 8c3.73 0 6.84-2.55 7.73-6h-2.08c-.82 2.33-3.04 4-5.65 4-3.31 0-6-2.69-6-6s2.69-6 6-6c1.66 0 3.14.69 4.22 1.78L13 11h7V4l-2.35 2.35z"/></svg>
  Rafraîchir
</button>`;

let _root = null;

function _setCard(root, cardId, valId, text, pct) {
  const card = root.querySelector('#' + cardId);
  card.classList.remove('loading');
  root.querySelector('#' + valId).textContent = text;
  let bar = card.querySelector('.dash-bar');
  if (!bar) {
    const wrap = document.createElement('div');
    wrap.className = 'dash-bar-wrap';
    bar = document.createElement('div');
    bar.className = 'dash-bar';
    wrap.appendChild(bar);
    card.appendChild(wrap);
  }
  bar.style.width = `${Math.min(pct, 100)}%`;
  bar.className = 'dash-bar' + (pct > 90 ? ' danger' : pct > 70 ? ' warn' : '');
}

async function _load(root) {
  root.querySelectorAll('.dash-card').forEach((c) => c.classList.add('loading'));
  try {
    const d = await fetchJSON('/api/dashboard');

    const cardOllama = root.querySelector('#card-ollama');
    cardOllama.classList.remove('loading');
    root.querySelector('#dc-model').textContent =
      d.loaded_models?.length ? d.loaded_models.join(', ') : d.model;
    cardOllama.style.borderColor =
      d.ollama === 'online' ? 'rgba(76,175,130,.4)' : 'rgba(224,85,85,.4)';

    _setCard(root, 'card-cpu',  'dc-cpu',  `${d.cpu_pct} %`, d.cpu_pct);
    _setCard(root, 'card-ram',  'dc-ram',  `${d.ram.used_gb} / ${d.ram.total_gb} Go`, d.ram.pct);
    _setCard(root, 'card-disk', 'dc-disk', `${d.disk.used_gb} / ${d.disk.total_gb} Go`, d.disk.pct);

    if (d.vram) {
      root.querySelector('#card-vram').style.display = '';
      _setCard(root, 'card-vram', 'dc-vram',
        `${d.vram.used_gb} / ${d.vram.total_gb} Go`,
        Math.round((d.vram.used_gb / d.vram.total_gb) * 100));
    }
  } catch { showToast('Impossible de charger le tableau de bord'); }
}

export async function mount(vp) {
  _ensureCSS();
  _root = document.createElement('div');
  _root.className = 'view-root dashboard-view';
  _root.innerHTML = _HTML;
  vp.appendChild(_root);

  _root.querySelector('#dashboard-refresh').addEventListener('click', () => _load(_root));
  await _load(_root);
}

export function unmount() {
  _root?.remove();
  _root = null;
}
