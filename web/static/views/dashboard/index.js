/* ================================================================
   Vue Dashboard — Accueil ADA
   ================================================================ */
import { showToast, setInputBarVisible, fetchJSON } from '/static/core/core.js';

const _CSS = '/static/views/dashboard/style.css';
function _ensureCSS() {
  if (!document.getElementById('css-dashboard')) {
    const l = document.createElement('link');
    l.id = 'css-dashboard'; l.rel = 'stylesheet'; l.href = _CSS;
    document.head.appendChild(l);
  }
}

// ── Helpers ───────────────────────────────────────────────────
function _greeting() {
  const h = new Date().getHours();
  if (h <  5) return 'Bonne nuit';
  if (h < 12) return 'Bonjour';
  if (h < 18) return 'Bon après-midi';
  return 'Bonsoir';
}

const _WMO_ICON = (c) => {
  if (c === 0)  return '☀️';
  if (c <= 2)   return '⛅';
  if (c <= 3)   return '☁️';
  if (c <= 48)  return '🌫️';
  if (c <= 55)  return '🌦️';
  if (c <= 67)  return '🌧️';
  if (c <= 77)  return '❄️';
  if (c <= 82)  return '🌦️';
  return '⛈️';
};

function _timeStr() {
  return new Date().toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit' });
}
function _dateStr() {
  return new Date().toLocaleDateString('fr-FR', { weekday: 'long', day: 'numeric', month: 'long' });
}

// ── Template ──────────────────────────────────────────────────
function _html() {
  return `
<div class="dh-wrap">

  <!-- Top bar -->
  <div class="dh-topbar">
    <div class="dh-welcome">
      <div class="dh-welcome-sub">Bienvenue, <span id="dh-username">…</span></div>
      <div class="dh-greeting">${_greeting()}</div>
      <div class="dh-date">${_dateStr()}</div>
    </div>
    <div class="dh-topbar-right">
      <div class="dh-clock-card">
        <span id="dh-clock">${_timeStr()}</span>
      </div>
      <div class="dh-weather-card">
        <div class="dh-weather-icon" id="dh-wicon">⏳</div>
        <div class="dh-weather-info">
          <div class="dh-weather-temp" id="dh-wtemp">—</div>
          <div class="dh-weather-desc" id="dh-wdesc">Chargement…</div>
        </div>
      </div>
    </div>
  </div>

  <!-- Body -->
  <div class="dh-body">

    <!-- Colonne gauche : stat cards -->
    <div class="dh-left">
      <div class="dh-stat-card dh-nav" data-nav="planner">
        <div class="dh-stat-icon"><img src="/static/icons/Calendar_white.svg" width="26" height="26" alt=""></div>
        <div class="dh-stat-count" id="dh-tasks-count">—</div>
        <div class="dh-stat-label">Tâches en attente</div>
      </div>
      <div class="dh-stat-card dh-nav" data-nav="page" data-nav-page="home">
        <div class="dh-stat-icon"><img src="/static/icons/IOT_white.svg" width="26" height="26" alt=""></div>
        <div class="dh-stat-count" id="dh-devices-count">—</div>
        <div class="dh-stat-label">Appareils actifs</div>
      </div>
      <div class="dh-stat-card dh-nav" data-nav="page" data-nav-page="briefing" data-nav-hint="Fais-moi un briefing de la journée : météo, actualités, agenda.">
        <div class="dh-stat-icon"><img src="/static/icons/Layout_white.svg" width="26" height="26" alt=""></div>
        <div class="dh-stat-count" id="dh-news-count">—</div>
        <div class="dh-stat-label">Actualités</div>
      </div>
      <div class="dh-scenes-card">
        <div class="dh-scenes-title">Scènes rapides</div>
        <div class="dh-scenes-row">
          <button class="dh-scene-btn" data-scene="focus">🎯 Focus</button>
          <button class="dh-scene-btn" data-scene="relax">🛋️ Relax</button>
          <button class="dh-scene-btn" data-scene="night">🌙 Nuit</button>
        </div>
      </div>
    </div>

    <!-- Colonne droite : System Intelligence -->
    <div class="dh-right">
      <div class="dh-intel-header">
        <span class="dh-intel-title">Veille Système</span>
        <span class="dh-intel-live">● Live</span>
      </div>
      <div class="dh-intel-feed" id="dh-feed">
        <div class="dh-feed-item skeleton"><div class="dh-feed-body"><div class="sk-line"></div><div class="sk-line short"></div></div></div>
        <div class="dh-feed-item skeleton"><div class="dh-feed-body"><div class="sk-line"></div><div class="sk-line short"></div></div></div>
        <div class="dh-feed-item skeleton"><div class="dh-feed-body"><div class="sk-line"></div><div class="sk-line short"></div></div></div>
      </div>
    </div>

  </div>

  <!-- Upcoming priority -->
  <div class="dh-upcoming">
    <div class="dh-upcoming-left">
      <div class="dh-upcoming-title">Prochaine priorité</div>
      <div class="dh-upcoming-text" id="dh-upcoming-text">Aucun événement à venir</div>
      <div class="dh-upcoming-sub" id="dh-upcoming-sub">Profitez de votre temps libre !</div>
    </div>
    <button class="dh-upcoming-btn" id="dh-planner-btn">Détails</button>
  </div>

</div>`;
}

// ── Feed item builder ─────────────────────────────────────────
function _feedItem(icon, title, msg, when = 'MAINTENANT', nav = null, navPage = null, navHint = null) {
  const navAttrs = nav
    ? ` class="dh-feed-item dh-nav" data-nav="${nav}"${navPage ? ` data-nav-page="${navPage}"` : ''}${navHint ? ` data-nav-hint="${navHint}"` : ''}`
    : ' class="dh-feed-item"';
  return `
  <div${navAttrs}>
    <div class="dh-feed-icon">${icon}</div>
    <div class="dh-feed-body">
      <div class="dh-feed-head">
        <span class="dh-feed-title">${title}</span>
        <span class="dh-feed-when">${when}</span>
      </div>
      <div class="dh-feed-msg">${msg}</div>
    </div>
  </div>`;
}

// ── Data load ─────────────────────────────────────────────────
async function _load(root) {
  try {
    const d = await fetchJSON('/api/dashboard/home');

    root.querySelector('#dh-username').textContent = d.user_name || 'vous';

    // Météo
    const w = d.weather || {};
    if (w.temp !== null && w.temp !== undefined) {
      root.querySelector('#dh-wicon').textContent = _WMO_ICON(w.code || 0);
      root.querySelector('#dh-wtemp').textContent = `${w.temp}${w.unit || '°C'}`;
      root.querySelector('#dh-wdesc').textContent = w.desc || '—';
    } else {
      root.querySelector('#dh-wdesc').textContent = w.city || '—';
    }

    // Compteurs
    root.querySelector('#dh-tasks-count').textContent   = d.tasks?.pending   ?? 0;
    root.querySelector('#dh-devices-count').textContent = d.active_devices   ?? 0;
    root.querySelector('#dh-news-count').textContent    = d.news_count       ?? 0;

    // Feed Veille Système
    const taskMsg = (d.tasks?.pending === 0)
      ? 'Toutes les tâches sont complétées. Bravo !'
      : `${d.tasks.pending} tâche(s) en attente — "${d.tasks.next || ''}"`;

    const newsMsg = d.latest_news
      ? `${d.latest_news.title} — <em>${d.latest_news.source}</em>`
      : 'Aucune actualité récente disponible.';

    // Maison connectée : derniers capteurs Domoticz modifiés
    let smartMsg;
    if (d.recent_devices && d.recent_devices.length > 0) {
      smartMsg = d.recent_devices
        .map(dev => `<span class="dh-device-chip"><b>${dev.name}</b> ${dev.value}</span>`)
        .join('');
    } else {
      smartMsg = d.kasa_status || 'Domoticz non connecté.';
    }
    const smartSub = d.recent_devices && d.recent_devices.length > 0
      ? `${d.active_devices} capteur(s) · dernière mise à jour`
      : '';
    const smartWhen = d.recent_devices && d.recent_devices.length > 0
      ? (d.recent_devices[0].last_update || 'MAINTENANT')
      : 'MAINTENANT';

    root.querySelector('#dh-feed').innerHTML =
      _feedItem('🎯', 'Focus du jour',   taskMsg,   'MAINTENANT',  'planner') +
      _feedItem('📡', 'Alerte info',     newsMsg,   'À L\'INSTANT', 'page', 'briefing', 'Fais-moi un briefing de la journée : météo, actualités, agenda.') +
      _feedItem('🏠', 'Maison connectée', smartMsg, smartWhen,      'page', 'home');

    // Upcoming
    if (d.tasks?.next) {
      root.querySelector('#dh-upcoming-text').textContent = d.tasks.next;
      root.querySelector('#dh-upcoming-sub').textContent  = 'Tâche la plus prioritaire';
    }

  } catch (e) {
    showToast('Erreur tableau de bord : ' + e.message);
  }
}

// ── Clock ─────────────────────────────────────────────────────
let _clockTimer = null;
function _startClock(root) {
  const el = root.querySelector('#dh-clock');
  if (!el) return;
  _clockTimer = setInterval(() => { el.textContent = _timeStr(); }, 30_000);
}

// ── Labels de page pour la navigation ─────────────────────────
const _PAGE_LABELS = {
  home:     'Domotique',
  briefing: 'Briefing',
  cameras:  'Caméras',
  skills:   'Skills',
};

// ── mount / unmount ───────────────────────────────────────────
let _root = null;

export async function mount(container) {
  _ensureCSS();
  setInputBarVisible(false);
  container.innerHTML = _html();
  _root = container;

  _startClock(container);

  // Navigation par délégation sur tous les éléments [data-nav]
  container.addEventListener('click', e => {
    const card = e.target.closest('[data-nav]');
    if (!card || e.target.closest('.dh-scene-btn') || e.target.closest('#dh-planner-btn')) return;
    import('/static/core/core.js').then(({ switchView }) => {
      const view = card.dataset.nav;
      const page = card.dataset.navPage;
      const hint = card.dataset.navHint;
      if (page) switchView(view, { page, label: _PAGE_LABELS[page] || page, hint });
      else      switchView(view);
    });
  });

  container.querySelector('#dh-planner-btn')?.addEventListener('click', () => {
    import('/static/core/core.js').then(({ switchView }) => switchView('planner'));
  });

  container.querySelectorAll('.dh-scene-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      showToast(`Scène "${btn.dataset.scene}" envoyée`);
      fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: `Active la scène ${btn.dataset.scene}`, conversation_id: 'scene' }),
      }).catch(() => {});
    });
  });

  await _load(container);
}

export function unmount() {
  clearInterval(_clockTimer);
  _clockTimer = null;
  _root = null;
}
