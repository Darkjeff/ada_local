/* ================================================================
   Vue Caméras — grille de snapshots Reolink via proxy ADA
   Auto-refresh toutes les 30 s + analyse vision gemma4.
   ================================================================ */

const _CSS = '/static/views/cameras/style.css';
const REFRESH_INTERVAL = 30_000;

let _root  = null;
let _timer = null;
let _cameras = [];

function _ensureCSS() {
  if (!document.getElementById('css-cameras')) {
    const l = document.createElement('link');
    l.id = 'css-cameras'; l.rel = 'stylesheet'; l.href = _CSS;
    document.head.appendChild(l);
  }
}

function _snapshotUrl(idx) {
  return `/api/cameras/${encodeURIComponent(idx)}/snapshot?t=${Date.now()}`;
}

function _refreshAll() {
  if (!_root) return;
  _root.querySelectorAll('.cam-img').forEach(img => {
    const idx = img.dataset.idx;
    img.classList.add('cam-loading');
    const fresh = new Image();
    fresh.onload  = () => { img.src = fresh.src; img.classList.remove('cam-loading'); };
    fresh.onerror = () => { img.classList.remove('cam-loading'); img.classList.add('cam-error'); };
    fresh.src = _snapshotUrl(idx);
  });
  const ts = _root.querySelector('#cam-ts');
  if (ts) ts.textContent = new Date().toLocaleTimeString('fr-FR');
}

async function _analyzeCamera(idx, question, resultEl, btnEl) {
  btnEl.disabled = true;
  resultEl.classList.remove('cam-result--hidden');
  resultEl.innerHTML = '<span class="cam-result-thinking">Analyse en cours…</span>';
  try {
    const resp = await fetch(`/api/cameras/${encodeURIComponent(idx)}/analyze`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question }),
    });
    if (!resp.ok) {
      const e = await resp.json().catch(() => ({ detail: resp.statusText }));
      resultEl.textContent = `Erreur : ${e.detail || resp.statusText}`;
      return;
    }
    const reader = resp.body.getReader();
    const dec = new TextDecoder();
    let text = '';
    resultEl.textContent = '';
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      for (const line of dec.decode(value).split('\n')) {
        if (!line.startsWith('data:')) continue;
        const raw = line.slice(5).trim();
        if (raw === '[DONE]') { btnEl.disabled = false; return; }
        try {
          const chunk = JSON.parse(raw);
          if (chunk.error) { resultEl.textContent = `Erreur : ${chunk.error}`; return; }
          if (chunk.text)  { text += chunk.text; resultEl.textContent = text; }
        } catch { /* skip */ }
      }
    }
  } catch (err) {
    resultEl.textContent = `Erreur réseau : ${err.message}`;
  } finally {
    btnEl.disabled = false;
  }
}

function _buildGrid() {
  if (!_cameras.length) {
    return '<p class="cam-empty">Aucune caméra disponible.<br>Vérifiez la configuration Domoticz.</p>';
  }
  return _cameras.map(c => `
    <div class="cam-card" data-cam-idx="${c.idx}">
      <div class="cam-frame">
        <img class="cam-img cam-loading"
             data-idx="${c.idx}"
             src="${_snapshotUrl(c.idx)}"
             alt="${c.name}" loading="lazy" />
        <div class="cam-overlay-name">${c.name}</div>
      </div>
      <div class="cam-analyze-bar">
        <input class="cam-question" type="text"
               placeholder="Que veux-tu savoir ?"
               value="Décris la scène. Compte les véhicules et personnes visibles." />
        <button class="cam-analyze-btn" type="button">
          <svg viewBox="0 0 24 24" width="15" height="15" fill="currentColor">
            <path d="M12 4.5C7 4.5 2.73 7.61 1 12c1.73 4.39 6 7.5 11 7.5s9.27-3.11 11-7.5
                     c-1.73-4.39-6-7.5-11-7.5zm0 12.5c-2.76 0-5-2.24-5-5s2.24-5 5-5 5 2.24 5 5
                     -2.24 5-5 5zm0-8c-1.66 0-3 1.34-3 3s1.34 3 3 3 3-1.34 3-3-1.34-3-3-3z"/>
          </svg>
          Analyser
        </button>
      </div>
      <div class="cam-result cam-result--hidden"></div>
    </div>`).join('');
}

export async function mount(vp) {
  _ensureCSS();

  _root = document.createElement('div');
  _root.className = 'view-root cam-root';
  _root.innerHTML = `
    <div class="cam-toolbar">
      <span class="cam-title">Caméras</span>
      <span class="cam-ts-label">Mis à jour : <b id="cam-ts">—</b></span>
      <button class="cam-refresh-btn" id="cam-refresh" type="button">
        <svg viewBox="0 0 24 24" width="16" height="16" fill="currentColor">
          <path d="M17.65 6.35A8 8 0 1 0 19.73 14H17.6a6 6 0 1 1-1.74-5.27L13 11h7V4l-2.35 2.35z"/>
        </svg>
        Rafraîchir
      </button>
    </div>
    <div class="cam-grid" id="cam-grid"><p class="cam-empty">Chargement…</p></div>`;

  vp.appendChild(_root);

  try {
    const data = await fetch('/api/cameras').then(r => r.json());
    _cameras = (data.cameras || []).filter(c => c.enabled !== false);
  } catch { _cameras = []; }

  const grid = _root.querySelector('#cam-grid');
  grid.innerHTML = _buildGrid();

  _root.querySelectorAll('.cam-img').forEach(img => {
    img.addEventListener('load',  () => img.classList.remove('cam-loading', 'cam-error'));
    img.addEventListener('error', () => { img.classList.remove('cam-loading'); img.classList.add('cam-error'); });
  });

  _root.querySelectorAll('.cam-card').forEach(card => {
    const idx    = card.dataset.camIdx;
    const btn    = card.querySelector('.cam-analyze-btn');
    const input  = card.querySelector('.cam-question');
    const result = card.querySelector('.cam-result');
    btn.addEventListener('click', () => _analyzeCamera(idx, input.value.trim() || input.placeholder, result, btn));
    input.addEventListener('keydown', e => { if (e.key === 'Enter') btn.click(); });
  });

  const ts = _root.querySelector('#cam-ts');
  if (ts) ts.textContent = new Date().toLocaleTimeString('fr-FR');

  _root.querySelector('#cam-refresh').addEventListener('click', _refreshAll);
  _timer = setInterval(_refreshAll, REFRESH_INTERVAL);
}

export function unmount() {
  clearInterval(_timer);
  _timer = null;
  _cameras = [];
  if (_root) { _root.remove(); _root = null; }
}
