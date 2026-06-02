/* ================================================================
   Vue Planificateur — Tâches · Timers · Alarmes
   ================================================================ */
import { showToast, setInputBarVisible } from '/static/core/core.js';

const _CSS = '/static/views/planner/style.css';
function _ensureCSS() {
  if (!document.getElementById('css-planner')) {
    const l = document.createElement('link');
    l.id = 'css-planner'; l.rel = 'stylesheet'; l.href = _CSS;
    document.head.appendChild(l);
  }
}

// ── HTML skeleton ─────────────────────────────────────────────
const _HTML = `
<div class="pl-wrap">

  <!-- Tâches -->
  <div class="pl-col">
    <div class="pl-col-header">
      <span class="pl-col-title">📋 Tâches</span>
    </div>
    <form class="pl-add-form" id="pl-task-form">
      <input class="pl-add-input" id="pl-task-input" type="text" placeholder="Ajouter une tâche…" autocomplete="off">
      <button class="pl-add-btn" type="submit">+</button>
    </form>
    <div class="pl-list" id="pl-task-list"><p class="pl-empty">Chargement…</p></div>
  </div>

  <!-- Timers -->
  <div class="pl-col">
    <div class="pl-col-header">
      <span class="pl-col-title">⏱️ Timers</span>
    </div>
    <form class="pl-add-form" id="pl-timer-form">
      <input class="pl-add-input" id="pl-timer-label" type="text" placeholder="Étiquette (ex: Pâtes)" autocomplete="off" style="flex:1.2">
      <input class="pl-add-input" id="pl-timer-dur" type="text" placeholder="Durée (ex: 10 min)" autocomplete="off">
      <button class="pl-add-btn" type="submit">+</button>
    </form>
    <div class="pl-list" id="pl-timer-list"><p class="pl-empty">Aucun timer actif</p></div>
  </div>

  <!-- Alarmes -->
  <div class="pl-col">
    <div class="pl-col-header">
      <span class="pl-col-title">🔔 Alarmes</span>
    </div>
    <form class="pl-add-form" id="pl-alarm-form">
      <input class="pl-add-input" id="pl-alarm-time" type="time" style="width:90px;flex:none">
      <input class="pl-add-input" id="pl-alarm-label" type="text" placeholder="Étiquette (opt.)" autocomplete="off">
      <button class="pl-add-btn" type="submit">+</button>
    </form>
    <div class="pl-list" id="pl-alarm-list"><p class="pl-empty">Chargement…</p></div>
  </div>

</div>`;

// ── Utils ─────────────────────────────────────────────────────
function _esc(s) {
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}
function _fmt(secs) {
  const h = Math.floor(secs / 3600);
  const m = Math.floor((secs % 3600) / 60);
  const s = secs % 60;
  if (h > 0) return `${h}:${String(m).padStart(2,'0')}:${String(s).padStart(2,'0')}`;
  return `${String(m).padStart(2,'0')}:${String(s).padStart(2,'0')}`;
}

// ── Tasks ─────────────────────────────────────────────────────
async function _loadTasks(root) {
  const list = root.querySelector('#pl-task-list');
  try {
    const tasks = await fetch('/api/tasks').then(r => r.json());
    if (!tasks.length) { list.innerHTML = '<p class="pl-empty">Aucune tâche. Ajoutez-en une !</p>'; return; }

    const pending   = tasks.filter(t => !t.completed);
    const completed = tasks.filter(t =>  t.completed);

    list.innerHTML = [
      ...pending.map(t => _taskHTML(t, false)),
      completed.length ? `<div class="pl-sep">Terminées (${completed.length})</div>` : '',
      ...completed.map(t => _taskHTML(t, true)),
    ].join('');

    list.querySelectorAll('.pl-task-check').forEach(cb => {
      cb.addEventListener('change', async () => {
        await fetch(`/api/tasks/${cb.dataset.id}`, {
          method: 'PATCH',
          headers: {'Content-Type':'application/json'},
          body: JSON.stringify({completed: cb.checked}),
        });
        _loadTasks(root);
      });
    });
    list.querySelectorAll('.pl-del-btn').forEach(btn => {
      btn.addEventListener('click', async () => {
        await fetch(`/api/tasks/${btn.dataset.id}`, { method: 'DELETE' });
        _loadTasks(root);
      });
    });
  } catch (e) {
    list.innerHTML = '<p class="pl-empty">Erreur chargement tâches.</p>';
  }
}
function _taskHTML(t, done) {
  return `<div class="pl-item ${done ? 'pl-item--done' : ''}">
    <input class="pl-task-check" type="checkbox" data-id="${_esc(t.id)}" ${done ? 'checked' : ''}>
    <span class="pl-item-text">${_esc(t.text)}</span>
    <button class="pl-del-btn" data-id="${_esc(t.id)}" title="Supprimer">×</button>
  </div>`;
}

// ── Alarms ────────────────────────────────────────────────────
async function _loadAlarms(root) {
  const list = root.querySelector('#pl-alarm-list');
  try {
    const alarms = await fetch('/api/planner/alarms').then(r => r.json());
    if (!alarms.length) { list.innerHTML = '<p class="pl-empty">Aucune alarme.</p>'; return; }
    list.innerHTML = alarms.map(a => `
      <div class="pl-item pl-alarm-item">
        <span class="pl-alarm-time">${_esc(a.time)}</span>
        <span class="pl-item-text">${_esc(a.label || '')}</span>
        <button class="pl-del-btn" data-id="${_esc(a.id)}" title="Supprimer">×</button>
      </div>`).join('');
    list.querySelectorAll('.pl-del-btn').forEach(btn => {
      btn.addEventListener('click', async () => {
        await fetch(`/api/planner/alarms/${btn.dataset.id}`, { method: 'DELETE' });
        _loadAlarms(root);
      });
    });
  } catch {
    list.innerHTML = '<p class="pl-empty">Erreur chargement alarmes.</p>';
  }
}

// ── Timers ────────────────────────────────────────────────────
let _timerPoll = null;
let _timerData = [];  // [{label, remaining_seconds, duration_seconds, is_expired}]

async function _fetchTimers() { try { _timerData = await fetch('/api/planner/timers').then(r => r.json()); } catch { _timerData = []; } }

function _renderTimers(root) {
  const list = root.querySelector('#pl-timer-list');
  if (!list) return;
  if (!_timerData.length) { list.innerHTML = '<p class="pl-empty">Aucun timer actif.<br><small>Créez-en un ou demandez au chat !</small></p>'; return; }

  // Keep existing items for smooth update
  const existing = new Set([...list.querySelectorAll('.pl-timer-item')].map(el => el.dataset.label));
  const incoming = new Set(_timerData.map(t => t.label));

  // Remove stale
  list.querySelectorAll('.pl-timer-item').forEach(el => {
    if (!incoming.has(el.dataset.label)) el.remove();
  });

  _timerData.forEach(t => {
    let el = list.querySelector(`.pl-timer-item[data-label="${CSS.escape(t.label)}"]`);
    if (!el) {
      el = document.createElement('div');
      el.className = 'pl-item pl-timer-item';
      el.dataset.label = t.label;
      el.innerHTML = `
        <div class="pl-timer-info">
          <span class="pl-item-text">${_esc(t.label)}</span>
          <span class="pl-timer-count"></span>
        </div>
        <div class="pl-timer-bar-wrap"><div class="pl-timer-bar"></div></div>
        <button class="pl-del-btn" title="Supprimer">×</button>`;
      el.querySelector('.pl-del-btn').addEventListener('click', async () => {
        await fetch(`/api/planner/timers/${encodeURIComponent(t.label)}`, { method: 'DELETE' });
        _timerData = _timerData.filter(x => x.label !== t.label);
        _renderTimers(root);
      });
      list.appendChild(el);
    }
    // Update countdown
    const rem = t.remaining_seconds;
    const pct = t.duration_seconds > 0 ? Math.max(0, (rem / t.duration_seconds) * 100) : 0;
    el.querySelector('.pl-timer-count').textContent = t.is_expired ? '✓ Terminé' : _fmt(rem);
    el.querySelector('.pl-timer-bar').style.width = pct + '%';
    el.classList.toggle('pl-timer--expired', t.is_expired);
  });

  // Fix empty message
  if (list.querySelector('.pl-empty') && _timerData.length) list.querySelector('.pl-empty')?.remove();
}

async function _startTimerPoll(root) {
  await _fetchTimers();
  _renderTimers(root);
  _timerPoll = setInterval(async () => {
    // Decrement locally for smooth display
    _timerData = _timerData.map(t => ({
      ...t,
      remaining_seconds: Math.max(0, t.remaining_seconds - 1),
      is_expired: t.remaining_seconds <= 1,
    }));
    _renderTimers(root);
    // Re-sync with server every 10s
    if (Date.now() % 10000 < 1100) await _fetchTimers();
  }, 1000);
}

// ── Events ────────────────────────────────────────────────────
function _bindEvents(root) {
  // Add task
  root.querySelector('#pl-task-form').addEventListener('submit', async e => {
    e.preventDefault();
    const inp = root.querySelector('#pl-task-input');
    const text = inp.value.trim();
    if (!text) return;
    inp.value = '';
    await fetch('/api/tasks', {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify({text}),
    });
    _loadTasks(root);
  });

  // Add timer
  root.querySelector('#pl-timer-form').addEventListener('submit', async e => {
    e.preventDefault();
    const label = root.querySelector('#pl-timer-label').value.trim() || 'Timer';
    const dur   = root.querySelector('#pl-timer-dur').value.trim();
    if (!dur) return;
    try {
      const r = await fetch('/api/planner/timers', {
        method: 'POST',
        headers: {'Content-Type':'application/json'},
        body: JSON.stringify({label, duration: dur}),
      });
      if (!r.ok) {
        const err = await r.json().catch(() => ({}));
        showToast(err.detail || 'Durée invalide');
        return;
      }
      root.querySelector('#pl-timer-label').value = '';
      root.querySelector('#pl-timer-dur').value   = '';
      await _fetchTimers();
      _renderTimers(root);
    } catch { showToast('Erreur création timer'); }
  });

  // Add alarm
  root.querySelector('#pl-alarm-form').addEventListener('submit', async e => {
    e.preventDefault();
    const timeVal  = root.querySelector('#pl-alarm-time').value;
    const labelVal = root.querySelector('#pl-alarm-label').value.trim();
    if (!timeVal) { showToast('Choisissez une heure'); return; }
    await fetch('/api/planner/alarms', {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify({time: timeVal, label: labelVal}),
    });
    root.querySelector('#pl-alarm-time').value  = '';
    root.querySelector('#pl-alarm-label').value = '';
    _loadAlarms(root);
  });
}

// ── mount / unmount ───────────────────────────────────────────
let _root = null;

export async function mount(container) {
  _ensureCSS();
  setInputBarVisible(false);
  container.innerHTML = _HTML;
  _root = container;

  _bindEvents(container);
  await Promise.all([
    _loadTasks(container),
    _loadAlarms(container),
    _startTimerPoll(container),
  ]);
}

export function unmount() {
  clearInterval(_timerPoll);
  _timerPoll = null;
  _timerData = [];
  _root = null;
}
