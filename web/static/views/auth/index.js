/* ================================================================
   ADA — Vue Auth : connexion QR code + code de récupération
   ================================================================ */
import { showToast } from '/static/core/core.js';

const _CSS = '/static/views/auth/style.css';

let _pollInterval  = null;
let _sessionToken  = null;
let _expireTimeout = null;

export async function mount(container) {
  if (!document.getElementById('css-auth')) {
    const l = document.createElement('link');
    l.id = 'css-auth'; l.rel = 'stylesheet'; l.href = _CSS;
    document.head.appendChild(l);
  }

  container.innerHTML = `
<div class="auth-wrap">
  <div class="auth-card">
    <div class="auth-logo">A</div>
    <h1 class="auth-title">ADA</h1>
    <p  class="auth-subtitle">Scannez le QR avec un appareil déjà connecté</p>

    <div id="auth-qr-area" class="auth-qr-area">
      <div class="auth-spinner"></div>
    </div>

    <div id="auth-status" class="auth-status"></div>

    <div class="auth-sep">ou</div>

    <button id="auth-rec-toggle" class="auth-link">
      Utiliser un code de récupération
    </button>

    <div id="auth-recovery" class="auth-recovery hidden">
      <input id="auth-rec-user"  type="text" placeholder="Nom d'utilisateur" class="auth-input" autocomplete="username" />
      <input id="auth-rec-code"  type="text" placeholder="Exemple : A1B2C3D4-E5F6A7B8"  class="auth-input" autocomplete="one-time-code" />
      <button id="auth-rec-btn" class="auth-btn">Valider</button>
    </div>
  </div>
</div>`;

  document.getElementById('auth-rec-toggle').addEventListener('click', () => {
    document.getElementById('auth-recovery').classList.toggle('hidden');
  });
  document.getElementById('auth-rec-btn').addEventListener('click', _submitRecovery);

  await _loadQR(container);
}

export function unmount() {
  _stopPoll();
  clearTimeout(_expireTimeout);
  _sessionToken = null;
}

// ── QR loading ────────────────────────────────────────────────────────────────

async function _loadQR(container) {
  const area = document.getElementById('auth-qr-area');
  if (!area) return;
  area.innerHTML = '<div class="auth-spinner"></div>';

  try {
    const ua = navigator.userAgent.substring(0, 80);
    const r  = await fetch(`/api/auth/qr?device_name=${encodeURIComponent(ua)}`);
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    const data = await r.json();

    _sessionToken = data.session_token;

    if (data.bootstrap_required) {
      // Mode bootstrap : lien direct vers la page d'inscription admin
      area.innerHTML = `
        <p class="auth-bootstrap-msg">
          ⚙️ Premier lancement — aucun compte configuré.<br>
          Scannez ce QR ou cliquez sur le lien ci-dessous<br>
          (également affiché dans le terminal du serveur).
        </p>
        ${data.qr_png_b64
          ? `<img src="data:image/png;base64,${data.qr_png_b64}" class="auth-qr-img" alt="QR Bootstrap"/>`
          : '<p class="auth-qr-unavail">QR indisponible — voir le terminal</p>'}
        <a href="${data.qr_url}" target="_blank" class="auth-bootstrap-link">
          Ouvrir le lien de configuration →
        </a>`;
    } else {
      area.innerHTML = `
        <p class="auth-scan-hint">Scannez avec un appareil déjà connecté à ADA</p>
        ${data.qr_png_b64
          ? `<img src="data:image/png;base64,${data.qr_png_b64}" class="auth-qr-img" alt="QR Code"/>`
          : '<p class="auth-qr-unavail">QR indisponible</p>'}
        <p class="auth-expire-hint" id="auth-expire">Expire dans 5 min</p>`;
    }

    _startPoll();

    // Régénère le QR 10 s avant expiration
    const msLeft = data.expires_at * 1000 - Date.now() - 10_000;
    if (msLeft > 0) {
      _expireTimeout = setTimeout(() => {
        if (_sessionToken === data.session_token) _loadQR(container);
      }, msLeft);
    }
  } catch (e) {
    if (area) area.innerHTML = `<p class="auth-error">Impossible de charger le QR : ${e.message}</p>`;
  }
}

// ── Polling ───────────────────────────────────────────────────────────────────

function _startPoll() {
  _stopPoll();
  _pollInterval = setInterval(_poll, 2000);
}

function _stopPoll() {
  if (_pollInterval) { clearInterval(_pollInterval); _pollInterval = null; }
}

async function _poll() {
  if (!_sessionToken) return;
  try {
    const r    = await fetch(`/api/auth/qr/status?session_token=${_sessionToken}`);
    const data = await r.json();
    const msg  = document.getElementById('auth-status');

    if (data.status === 'confirmed') {
      _stopPoll();
      _setToken(data.token);
      if (msg) { msg.textContent = '✅ Connecté — chargement…'; msg.className = 'auth-status ok'; }
      setTimeout(() => location.reload(), 800);

    } else if (data.status === 'expired') {
      _stopPoll();
      if (msg) { msg.textContent = 'QR expiré — régénération…'; msg.className = 'auth-status warn'; }
      setTimeout(() => _loadQR(document.querySelector('.auth-wrap')?.parentElement), 1200);
    }
  } catch { /* silencieux */ }
}

// ── Recovery ──────────────────────────────────────────────────────────────────

async function _submitRecovery() {
  const username = document.getElementById('auth-rec-user').value.trim();
  const code     = document.getElementById('auth-rec-code').value.trim();
  const btn      = document.getElementById('auth-rec-btn');
  if (!username || !code) { showToast('Remplissez les deux champs'); return; }
  btn.disabled = true;
  try {
    const r = await fetch('/api/auth/recovery/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, code, device_name: `Récupération — ${navigator.platform}` }),
    });
    const data = await r.json();
    if (r.ok) {
      _setToken(data.token);
      location.reload();
    } else {
      showToast(data.detail || 'Code invalide');
      btn.disabled = false;
    }
  } catch { showToast('Erreur réseau'); btn.disabled = false; }
}

// ── Token helpers ─────────────────────────────────────────────────────────────

function _setToken(token) {
  localStorage.setItem('ada_token', token);
  document.cookie = `ada_token=${token}; path=/; SameSite=Strict; Max-Age=${30 * 86_400}`;
}
