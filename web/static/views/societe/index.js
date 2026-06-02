/* ================================================================
   ADA — Vue Sociétés (MODULE_SOCIETE)
   Design : ada-dashboard-societe.html de référence
   ================================================================ */
import { showToast } from '/static/core/core.js';

// ── Helpers ──────────────────────────────────────────────────────────
function _escHtml(s) {
  return String(s ?? '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

// ── État ─────────────────────────────────────────────────────────
let _companies = [];
let _metrics   = {};
let _activeId  = null;

// ── État chat inline ─────────────────────────────────────────────
let _chatCtxId      = null;   // company id actif dans le chat
let _chatCtxText    = '';     // texte de contexte injecté
let _chatHistory    = [];     // historique local
let _chatStreaming   = false;
let _contentEl      = null;   // div gauche (dashboard/détail)

// ── CSS (fidèle à la référence) ───────────────────────────────────
const _CSS = `

.soc-wrap { padding: 20px; display: flex; flex-direction: column; gap: 16px; font-family: system-ui, -apple-system, sans-serif; }

/* ── Section header ── */
.soc-section-hdr { display: flex; align-items: center; gap: 10px; }
.soc-section-title {
  font-size: 11px; text-transform: uppercase;
  letter-spacing: 0.15em; color: #5a6a7a; font-weight: 700;
}
.soc-section-line { flex: 1; height: 1px; background: rgba(255,255,255,0.06); }
.soc-section-action {
  font-size: 10px; color: #5a6a7a; cursor: pointer;
  padding: 2px 8px; border-radius: 4px; border: 1px solid rgba(255,255,255,0.06);
  font-family: ui-monospace, monospace; transition: all .12s;
}
.soc-section-action:hover { color: #00d4ff; border-color: #00d4ff; }

/* ── Companies grid ── */
.soc-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 10px;
}

/* ── Company card ── */
.soc-card {
  background: #0d1219;
  border: 1px solid rgba(255,255,255,0.06);
  border-radius: 12px;
  padding: 14px 16px;
  cursor: pointer;
  transition: border-color .15s, box-shadow .15s, transform .15s;
  position: relative; overflow: hidden;
}
.soc-card::before {
  content: '';
  position: absolute; top: 0; left: 0; bottom: 0;
  width: 3px; border-radius: 12px 0 0 12px;
  background: var(--co-color, #00d4ff);
}
.soc-card:hover {
  border-color: var(--co-color, #00d4ff);
  box-shadow: 0 0 20px rgba(0,0,0,0.3);
  transform: translateY(-1px);
}

.co-header { display: flex; align-items: center; gap: 10px; margin-bottom: 10px; }
.co-logo {
  width: 32px; height: 32px; border-radius: 8px;
  display: flex; align-items: center; justify-content: center;
  font-size: 13px; font-weight: 800; flex-shrink: 0;
  background: rgba(255,255,255,0.05);
  border: 1px solid rgba(255,255,255,0.12);
  color: var(--co-color, #00d4ff);
  letter-spacing: 0.05em;
  font-family: system-ui, -apple-system, sans-serif;
}
.co-info { flex: 1; min-width: 0; }
.co-name { font-size: 13px; font-weight: 800; margin-bottom: 1px; color: #e8edf2; }
.co-type-sub { font-size: 10px; color: #5a6a7a; font-family: ui-monospace, monospace; }
.co-status {
  font-size: 9px; padding: 2px 7px; border-radius: 10px;
  font-weight: 700; letter-spacing: 0.08em;
  border: 1px solid; flex-shrink: 0;
}
.co-status-ok   { color: #00ff9d; border-color: rgba(0,255,157,0.3); background: rgba(0,255,157,0.08); }
.co-status-warn { color: #ff9500; border-color: rgba(255,149,0,0.3); background: rgba(255,149,0,0.08); }

.co-metrics { display: grid; grid-template-columns: repeat(3, 1fr); gap: 6px; margin-bottom: 10px; }
.co-metric {
  background: #111820;
  border-radius: 6px; padding: 6px 8px;
}
.co-metric-label { font-size: 9px; color: #5a6a7a; text-transform: uppercase; letter-spacing: 0.1em; margin-bottom: 2px; }
.co-metric-value { font-size: 14px; font-weight: 800; font-family: ui-monospace, monospace; }
.co-metric-sub   { font-size: 9px; color: #5a6a7a; margin-top: 1px; }

.co-connectors { display: flex; gap: 5px; flex-wrap: wrap; }
.co-connector {
  font-size: 9px; padding: 2px 7px; border-radius: 4px;
  background: rgba(255,255,255,0.04); border: 1px solid rgba(255,255,255,0.12);
  color: #5a6a7a; font-family: ui-monospace, monospace;
  display: flex; align-items: center; gap: 4px;
}
.co-connector .conn-dot { width: 4px; height: 4px; border-radius: 50%; background: #5a6a7a; }
.co-connector.conn-on   { color: #e8edf2; }
.co-connector.conn-on .conn-dot   { background: #00ff9d; box-shadow: 0 0 4px #00ff9d; }
.co-connector.conn-warn .conn-dot { background: #ff9500; }
.co-connector.conn-warn           { color: #ff9500; }

/* ── Cross alerts ── */
.soc-alert-row {
  background: #0d1219; border: 1px solid rgba(255,255,255,0.06);
  border-left: 2px solid #ff9500; border-radius: 8px;
  padding: 10px 14px; display: flex; align-items: center; gap: 12px;
  cursor: pointer; transition: background .12s;
}
.soc-alert-row:hover { background: #111820; }
.soc-alert-body { flex: 1; }
.soc-alert-title { font-size: 12px; font-weight: 700; color: #e8edf2; margin-bottom: 2px; }
.soc-alert-sub { font-size: 10px; color: #5a6a7a; font-family: ui-monospace, monospace; }
.soc-alert-co {
  font-size: 9px; padding: 2px 6px; border-radius: 3px;
  font-weight: 700; font-family: ui-monospace, monospace;
  background: rgba(0,212,255,0.08); border: 1px solid rgba(0,212,255,0.2);
  flex-shrink: 0;
}
.soc-alert-time { font-size: 10px; color: #5a6a7a; font-family: ui-monospace, monospace; flex-shrink: 0; }

/* ── Detail view ── */
.soc-detail-wrap { padding: 20px; display: flex; flex-direction: column; gap: 16px; font-family: system-ui, -apple-system, sans-serif; }

.detail-header {
  display: flex; align-items: center; gap: 12px;
  padding: 14px 16px;
  background: #0d1219;
  border: 1px solid rgba(255,255,255,0.06);
  border-radius: 12px;
}
.detail-back {
  font-size: 11px; color: #5a6a7a; cursor: pointer;
  padding: 4px 10px; border-radius: 5px; border: 1px solid rgba(255,255,255,0.12);
  font-family: ui-monospace, monospace; transition: all .12s;
  background: none;
}
.detail-back:hover { color: #e8edf2; }
.detail-co-logo {
  width: 40px; height: 40px; border-radius: 10px;
  display: flex; align-items: center; justify-content: center;
  font-size: 15px; font-weight: 800;
  border: 1px solid rgba(255,255,255,0.12);
  background: rgba(255,255,255,0.05);
  font-family: system-ui, -apple-system, sans-serif;
}
.detail-co-name { font-size: 18px; font-weight: 800; color: #e8edf2; }
.detail-co-sub  { font-size: 11px; color: #5a6a7a; font-family: ui-monospace, monospace; }

.detail-kpi-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 8px; }
.detail-kpi {
  background: #0d1219; border: 1px solid rgba(255,255,255,0.06);
  border-radius: 10px; padding: 12px 14px;
  position: relative; overflow: hidden;
}
.detail-kpi::before {
  content: ''; position: absolute; top: 0; left: 0; right: 0; height: 2px;
  background: var(--co-color, #00d4ff); opacity: 0.7;
}
.dk-label { font-size: 9px; text-transform: uppercase; letter-spacing: 0.12em; color: #5a6a7a; margin-bottom: 6px; font-weight: 700; }
.dk-value { font-size: 22px; font-weight: 800; line-height: 1; margin-bottom: 3px; font-family: ui-monospace, monospace; }
.dk-sub   { font-size: 10px; color: #5a6a7a; font-family: ui-monospace, monospace; }

.detail-cols { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
@media(max-width: 600px) { .detail-cols { grid-template-columns: 1fr; } }

/* Timeline */
.tl-list { display: flex; flex-direction: column; gap: 0; }
.tl-item-r {
  display: flex; gap: 12px; padding: 10px 0;
  border-bottom: 1px solid rgba(255,255,255,0.06);
}
.tl-item-r:last-child { border-bottom: none; }
.tl-left { display: flex; flex-direction: column; align-items: center; gap: 4px; flex-shrink: 0; width: 32px; }
.tl-dot-r { width: 8px; height: 8px; border-radius: 50%; margin-top: 3px; flex-shrink: 0; }
.tl-line  { width: 1px; flex: 1; background: rgba(255,255,255,0.06); }
.tl-body-r { flex: 1; min-width: 0; }
.tl-title-r { font-size: 12px; font-weight: 700; color: #e8edf2; margin-bottom: 2px; }
.tl-desc-r  { font-size: 11px; color: #5a6a7a; font-family: ui-monospace, monospace; margin-bottom: 4px; }
.tl-meta-r  { display: flex; align-items: center; gap: 8px; }
.tl-tag-r   { font-size: 9px; padding: 1px 6px; border-radius: 3px; font-weight: 700; letter-spacing: 0.06em; }
.tl-time-r  { font-size: 10px; color: #5a6a7a; font-family: ui-monospace, monospace; margin-left: auto; }

/* Documents */
.docs-list-r { display: flex; flex-direction: column; gap: 6px; }
.doc-item-r {
  background: #0d1219; border: 1px solid rgba(255,255,255,0.06);
  border-radius: 8px; padding: 10px 14px;
  display: flex; align-items: center; gap: 12px;
  cursor: pointer; transition: border-color .12s;
}
.doc-item-r:hover { border-color: rgba(255,255,255,0.12); }
.doc-icon-r { font-size: 16px; flex-shrink: 0; }
.doc-info-r { flex: 1; min-width: 0; }
.doc-name-r { font-size: 12px; font-weight: 700; color: #e8edf2; margin-bottom: 2px; }
.doc-meta-r { font-size: 10px; color: #5a6a7a; font-family: ui-monospace, monospace; }
.doc-status-r {
  font-size: 10px; padding: 2px 8px; border-radius: 4px;
  font-weight: 700; flex-shrink: 0;
}
.doc-sent     { color: #00d4ff; background: rgba(0,212,255,0.08); border: 1px solid rgba(0,212,255,0.2); }
.doc-accepted { color: #00ff9d; background: rgba(0,255,157,0.08); border: 1px solid rgba(0,255,157,0.2); }
.doc-pending  { color: #ff9500; background: rgba(255,149,0,0.08); border: 1px solid rgba(255,149,0,0.2); }

.soc-empty { color: #5a6a7a; font-size: 12px; font-family: ui-monospace, monospace; padding: 8px 0; }

/* ── Page layout ── */
.soc-page-layout { display: flex; gap: 10px; min-height: 0; }
.soc-content { flex: 1; min-width: 0; overflow-y: auto; }

/* ── Chat panel ── */
.soc-chat-panel {
  width: 300px; flex-shrink: 0;
  background: #0d1219;
  border: 1px solid rgba(255,255,255,0.06);
  border-radius: 12px;
  display: flex; flex-direction: column;
  height: calc(100vh - 110px);
  position: sticky; top: 0;
}
.scp-header {
  display: flex; align-items: center; gap: 8px;
  padding: 11px 14px; flex-shrink: 0;
  border-bottom: 1px solid rgba(255,255,255,0.06);
}
.scp-pulse {
  width: 6px; height: 6px; border-radius: 50%;
  background: #00ff9d; animation: soc-pulse 2s infinite;
}
@keyframes soc-pulse { 0%,100%{opacity:1} 50%{opacity:.3} }
.scp-title { font-size: 13px; font-weight: 800; color: #e8edf2; flex: 1; }
.scp-model { font-size: 9px; color: #5a6a7a; font-family: ui-monospace, monospace; }

.scp-ctx-bar { padding: 8px 10px; border-bottom: 1px solid rgba(255,255,255,0.06); flex-shrink: 0; }
.scp-ctx-label { font-size: 9px; color: #5a6a7a; text-transform: uppercase; letter-spacing: 0.1em; margin-bottom: 5px; font-weight: 700; }
.scp-ctx-btns { display: flex; gap: 4px; flex-wrap: wrap; }
.scp-ctx-btn {
  font-size: 9px; padding: 2px 8px; border-radius: 10px;
  border: 1px solid rgba(255,255,255,0.1); background: transparent;
  color: #5a6a7a; cursor: pointer; display: flex; align-items: center; gap: 4px;
  transition: all .12s;
}
.scp-ctx-btn .cb-dot { width: 5px; height: 5px; border-radius: 50%; }
.scp-ctx-btn.active { border-color: var(--co-color, #00d4ff); color: #e8edf2; background: rgba(0,212,255,0.06); }

.scp-msgs {
  flex: 1; overflow-y: auto; padding: 10px 12px;
  display: flex; flex-direction: column; gap: 8px;
  scroll-behavior: smooth;
}
.scp-msg {
  max-width: 92%; padding: 8px 10px; border-radius: 10px;
  font-size: 12px; line-height: 1.5; word-break: break-word;
}
.scp-msg-user { background: #111820; color: #e8edf2; align-self: flex-end; border: 1px solid rgba(255,255,255,0.08); }
.scp-msg-ada  { background: rgba(0,212,255,0.05); border: 1px solid rgba(0,212,255,0.12); color: #e8edf2; align-self: flex-start; }
.scp-msg-ada.streaming::after { content: '▋'; animation: soc-blink 1s infinite; color: #00d4ff; }
@keyframes soc-blink { 0%,100%{opacity:1} 50%{opacity:0} }

.scp-qp { padding: 6px 10px; border-top: 1px solid rgba(255,255,255,0.06); flex-shrink: 0; display: flex; gap: 4px; flex-wrap: wrap; }
.scp-qp-btn {
  font-size: 10px; padding: 3px 8px; border-radius: 6px;
  border: 1px solid rgba(255,255,255,0.07); background: transparent;
  color: #5a6a7a; cursor: pointer; transition: all .12s; text-align: left;
}
.scp-qp-btn:hover { color: #e8edf2; border-color: rgba(255,255,255,0.2); }

.scp-input-row {
  display: flex; gap: 6px; align-items: flex-end;
  padding: 10px 12px; border-top: 1px solid rgba(255,255,255,0.06); flex-shrink: 0;
}
.scp-textarea {
  flex: 1; background: #111820; border: 1px solid rgba(255,255,255,0.1);
  border-radius: 8px; padding: 7px 10px; color: #e8edf2; font-size: 12px;
  resize: none; min-height: 34px; max-height: 80px; overflow-y: auto;
  outline: none; font-family: inherit; line-height: 1.4;
}
.scp-textarea:focus { border-color: rgba(0,212,255,0.4); }
.scp-textarea::placeholder { color: #5a6a7a; }
.scp-send {
  width: 32px; height: 32px; border-radius: 8px;
  background: #00d4ff; border: none; cursor: pointer;
  display: flex; align-items: center; justify-content: center;
  color: #080c10; flex-shrink: 0; font-size: 14px; transition: opacity .12s;
}
.scp-send:hover { opacity: 0.85; }
.scp-send:disabled { opacity: 0.35; cursor: default; }

/* ── Connector panel ── */
.soc-conn-panel { display: flex; flex-direction: column; gap: 8px; }
.conn-row {
  display: flex; align-items: center; gap: 8px;
  padding: 10px 12px; border-radius: 10px;
  background: rgba(255,255,255,0.02); border: 1px solid rgba(255,255,255,0.06);
}
.conn-logo { font-size: 16px; flex-shrink: 0; }
.conn-name { font-size: 12px; font-weight: 700; color: #e8edf2; }
.conn-url  { font-size: 9px; color: #5a6a7a; font-family: ui-monospace, monospace; margin-top: 1px; }
.conn-last-sync { font-size: 9px; color: #5a6a7a; font-family: ui-monospace, monospace; }
.conn-badge {
  font-size: 9px; padding: 2px 8px; border-radius: 10px;
  font-family: ui-monospace, monospace; white-space: nowrap; flex-shrink: 0;
}
.conn-badge-ok   { background: rgba(0,255,157,0.1);  color: #00ff9d; border: 1px solid rgba(0,255,157,0.3); }
.conn-badge-err  { background: rgba(255,59,92,0.1);   color: #ff3b5c; border: 1px solid rgba(255,59,92,0.3); }
.conn-badge-none { background: rgba(90,106,122,0.1);  color: #5a6a7a; border: 1px solid rgba(90,106,122,0.3); }
.conn-btn {
  font-size: 10px; padding: 4px 10px; border-radius: 6px;
  border: 1px solid rgba(255,255,255,0.12); background: transparent;
  color: #e8edf2; cursor: pointer; transition: all .12s; white-space: nowrap; flex-shrink: 0;
}
.conn-btn:hover { border-color: #00d4ff; color: #00d4ff; }
.conn-btn.primary { background: rgba(0,212,255,0.1); border-color: rgba(0,212,255,0.4); color: #00d4ff; }
.conn-btn:disabled { opacity: 0.4; cursor: default; }
.conn-form {
  padding: 10px 12px; background: rgba(0,0,0,0.25); border-radius: 8px;
  border: 1px solid rgba(255,255,255,0.06); display: flex; flex-direction: column; gap: 8px;
}
.conn-input {
  background: #111820; border: 1px solid rgba(255,255,255,0.1);
  border-radius: 6px; padding: 7px 10px; color: #e8edf2; font-size: 12px;
  outline: none; font-family: inherit;
}
.conn-input:focus { border-color: rgba(0,212,255,0.4); }
.conn-input::placeholder { color: #5a6a7a; }
.conn-form-row { display: flex; gap: 8px; align-items: center; }
`;

// ── Helpers ───────────────────────────────────────────────────────
const _fmtEur  = v => v != null ? `${parseFloat(v).toLocaleString('fr-FR', {maximumFractionDigits:0})} €` : '—';
const _fmtDate = ts => ts ? new Date(ts * 1000).toLocaleDateString('fr-FR') : '—';
const _initials = name => {
  const parts = name.trim().split(/\s+/);
  if (parts.length >= 2) return (parts[0][0] + parts[1][0]).toUpperCase();
  return name.slice(0, 2).toUpperCase();
};

const _TL_COLOR = {
  invoice:'#00ff9d',         meeting:'#00d4ff',         call:'#0ea5e9',
  note:'#5a6a7a',            ticket:'#ff9500',          quote:'#a78bfa',
  dolibarr_invoice:'#00ff9d', dolibarr_ticket:'#ff9500', dolibarr_devis:'#a78bfa',
};
const _TL_BG = {
  invoice:'rgba(0,255,157,0.08)',  meeting:'rgba(0,212,255,0.08)',
  call:'rgba(14,165,233,0.08)',    note:'rgba(90,106,122,0.1)',
  ticket:'rgba(255,149,0,0.08)',   quote:'rgba(167,139,250,0.08)',
  dolibarr_invoice:'rgba(0,255,157,0.08)', dolibarr_ticket:'rgba(255,149,0,0.08)',
};
const _DOC_ICON = { invoice:'🧾', quote:'📄', contract:'📋', report:'📊', other:'📎', dolibarr_devis:'📄' };

async function _api(path) {
  const r = await fetch(`/api/societe${path}`);
  if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
  return r.json();
}

// ── Dashboard ─────────────────────────────────────────────────────
async function _renderDashboard(container) {
  container.innerHTML = '<div class="soc-wrap"><div style="color:#5a6a7a;font-size:12px">Chargement…</div></div>';

  try { _companies = await _api('/companies'); }
  catch(e) {
    container.innerHTML = `<div class="soc-wrap"><p style="color:#ff3b5c;font-size:12px">Erreur : ${e.message}</p></div>`;
    return;
  }

  // Charger toutes les métriques en parallèle
  _metrics = {};
  await Promise.all(_companies.map(async c => {
    try { _metrics[c.id] = await _api(`/companies/${c.id}/metrics`); }
    catch { _metrics[c.id] = {}; }
  }));

  // Alertes croisées
  const alerts = [];
  for (const c of _companies) {
    const m = _metrics[c.id] || {};
    if ((m.unpaid || 0) > 0)
      alerts.push({ cid: c.id, name: c.name, color: c.color, text: `Impayés : ${_fmtEur(m.unpaid)}`, sub: 'Montant non encaissé' });
    if ((m.open_tickets || 0) > 0)
      alerts.push({ cid: c.id, name: c.name, color: c.color, text: `${Math.round(m.open_tickets)} ticket(s) ouvert(s)`, sub: 'À traiter' });
  }

  const cardsHtml = _companies.map(c => _cardHtml(c)).join('');

  const alertsHtml = alerts.length
    ? alerts.map(a => `
      <div class="soc-alert-row" data-alert-cid="${a.cid}">
        <span style="font-size:13px">⚠</span>
        <div class="soc-alert-body">
          <div class="soc-alert-title">${a.name} — ${a.text}</div>
          <div class="soc-alert-sub">${a.sub}</div>
        </div>
        <span class="soc-alert-co" style="color:${a.color};border-color:${a.color}33">${a.name}</span>
      </div>`).join('')
    : '<div class="soc-empty">Aucune alerte croisée.</div>';

  container.innerHTML = `
  <div class="soc-wrap">
    <div class="soc-section-hdr">
      <div class="soc-section-title">Sociétés actives</div>
      <div class="soc-section-line"></div>
      <div class="soc-section-action" id="soc-refresh-btn">↻ Actualiser</div>
    </div>
    <div class="soc-grid" id="soc-grid">${cardsHtml}</div>
    <div class="soc-section-hdr">
      <div class="soc-section-title">Alertes croisées</div>
      <div class="soc-section-line"></div>
    </div>
    <div id="soc-alerts" style="display:flex;flex-direction:column;gap:6px">${alertsHtml}</div>
  </div>`;

  container.querySelectorAll('.soc-card[data-id]').forEach(card =>
    card.addEventListener('click', () => _renderDetail(container, card.dataset.id))
  );
  container.querySelectorAll('.soc-alert-row[data-alert-cid]').forEach(row =>
    row.addEventListener('click', () => _renderDetail(container, row.dataset.alertCid))
  );
  container.querySelector('#soc-refresh-btn')?.addEventListener('click', () => _renderDashboard(container));
}

function _cardHtml(c) {
  const m = _metrics[c.id] || {};
  const hasAlert = (m.unpaid || 0) > 0 || (m.open_tickets || 0) > 0;
  const alertCount = [(m.unpaid||0) > 0, (m.open_tickets||0) > 0].filter(Boolean).length;

  const statusHtml = hasAlert
    ? `<div class="co-status co-status-warn">${alertCount} alerte${alertCount > 1 ? 's' : ''}</div>`
    : `<div class="co-status co-status-ok">Nominal</div>`;

  const caVal     = m.ca_ytd || 0;
  const unpaidVal = m.unpaid || 0;
  const ticketsVal = m.open_tickets || 0;
  const devisVal  = m.quotes_pending || 0;

  const metricsHtml = `
    <div class="co-metric">
      <div class="co-metric-label">CA YTD</div>
      <div class="co-metric-value" style="color:${caVal > 0 ? '#00d4ff' : '#5a6a7a'}">${caVal > 0 ? _fmtEur(caVal) : '—'}</div>
      <div class="co-metric-sub">année en cours</div>
    </div>
    <div class="co-metric">
      <div class="co-metric-label">Impayés</div>
      <div class="co-metric-value" style="color:${unpaidVal > 0 ? '#ff3b5c' : '#00ff9d'}">${unpaidVal > 0 ? _fmtEur(unpaidVal) : '0 €'}</div>
      <div class="co-metric-sub">${unpaidVal > 0 ? 'à encaisser' : 'à jour'}</div>
    </div>
    <div class="co-metric">
      <div class="co-metric-label">Tickets</div>
      <div class="co-metric-value" style="color:${ticketsVal > 0 ? '#ff9500' : '#5a6a7a'}">${Math.round(ticketsVal) || '—'}</div>
      <div class="co-metric-sub">${devisVal > 0 ? `${Math.round(devisVal)} devis` : 'ouverts'}</div>
    </div>`;

  let connectors = {};
  try { connectors = JSON.parse(c.connectors_json || '{}'); } catch {}
  const connHtml = Object.entries(connectors).map(([name, cfg]) => `
    <div class="co-connector ${cfg.enabled ? 'conn-on' : ''}">
      <div class="conn-dot"></div>${name}
    </div>`).join('') || `<div class="co-connector"><div class="conn-dot"></div>aucun connecteur</div>`;

  return `
  <div class="soc-card" data-id="${c.id}" style="--co-color:${c.color}">
    <div class="co-header">
      <div class="co-logo">${_initials(c.name)}</div>
      <div class="co-info">
        <div class="co-name">${c.name}</div>
        <div class="co-type-sub">${c.type}${c.notes ? ' · ' + c.notes.slice(0,35) : ''}</div>
      </div>
      ${statusHtml}
    </div>
    <div class="co-metrics">${metricsHtml}</div>
    <div class="co-connectors">${connHtml}</div>
  </div>`;
}

// ── Détail société ────────────────────────────────────────────────
async function _renderDetail(container, companyId) {
  _activeId = companyId;
  container.innerHTML = '<div class="soc-detail-wrap"><div style="color:#5a6a7a;font-size:12px">Chargement…</div></div>';

  let company, metrics = {}, timeline = [], taggedItems = { endpoints: [], marketing: [] };
  try {
    [company, metrics, timeline, taggedItems] = await Promise.all([
      _api(`/companies/${companyId}`),
      _api(`/companies/${companyId}/metrics`),
      _api(`/companies/${companyId}/timeline`),
      _api(`/companies/${companyId}/tagged-items`).catch(() => ({ endpoints: [], marketing: [] })),
    ]);
  } catch(e) {
    showToast('Erreur : ' + e.message);
    _renderDashboard(container);
    return;
  }

  let connectors = {};
  try { connectors = company.connectors || {}; } catch {}
  const connBar = Object.entries(connectors).map(([name, cfg]) => `
    <div style="display:flex;align-items:center;gap:6px;padding:5px 12px;border-radius:20px;
      border:1px solid ${cfg.enabled ? 'rgba(0,255,157,0.3)' : 'rgba(255,255,255,0.12)'};
      font-size:11px;font-family:ui-monospace,monospace;
      color:${cfg.enabled ? '#00ff9d' : '#5a6a7a'}">
      <div style="width:5px;height:5px;border-radius:50%;background:${cfg.enabled ? '#00ff9d' : '#5a6a7a'};${cfg.enabled ? 'box-shadow:0 0 5px #00ff9d' : ''}"></div>
      ${name}
    </div>`).join('') || '';

  const kpiDefs = [
    { key:'ca_ytd',         label:'CA Année',  colorFn: v => v > 0 ? '#00d4ff' : '#5a6a7a', sub:'EUR' },
    { key:'unpaid',         label:'Impayés',   colorFn: v => v > 0 ? '#ff3b5c' : '#00ff9d', sub:'EUR' },
    { key:'open_tickets',   label:'Tickets',   colorFn: v => v > 0 ? '#ff9500' : '#5a6a7a', sub:'ouverts' },
    { key:'quotes_pending', label:'Devis',     colorFn: v => v > 0 ? '#a78bfa' : '#5a6a7a', sub:'en attente' },
  ];
  const kpisHtml = kpiDefs.map(d => {
    const val = metrics[d.key] || 0;
    const isEur = d.sub === 'EUR';
    const fmt = isEur ? _fmtEur(val) : String(Math.round(val));
    return `<div class="detail-kpi" style="--co-color:${company.color}">
      <div class="dk-label">${d.label}</div>
      <div class="dk-value" style="color:${d.colorFn(val)}">${fmt}</div>
      <div class="dk-sub">${d.sub}</div>
    </div>`;
  }).join('');

  const tlEvents = timeline.slice(0, 5);
  const tlHtml = tlEvents.length
    ? `<div class="tl-list">${tlEvents.map((ev, i) => `
      <div class="tl-item-r">
        <div class="tl-left">
          <div class="tl-dot-r" style="background:${_TL_COLOR[ev.event_type]||'#5a6a7a'}"></div>
          ${i < tlEvents.length - 1 ? '<div class="tl-line"></div>' : ''}
        </div>
        <div class="tl-body-r">
          <div class="tl-title-r">${ev.title}</div>
          ${ev.description ? `<div class="tl-desc-r">${ev.description}</div>` : ''}
          <div class="tl-meta-r">
            <span class="tl-tag-r" style="background:${_TL_BG[ev.event_type]||'rgba(90,106,122,0.1)'};color:${_TL_COLOR[ev.event_type]||'#5a6a7a'}">${ev.event_type}</span>
            ${ev.amount ? `<span style="font-size:10px;color:#e8edf2;font-family:ui-monospace,monospace">${_fmtEur(ev.amount)}</span>` : ''}
            <span class="tl-time-r">${_fmtDate(ev.event_date)}</span>
          </div>
        </div>
      </div>`).join('')}</div>`
    : '<div class="soc-empty">Aucun événement.</div>';

  // ── Infrastructure & marketing associés ──────────────────────────────────
  const _eps = Array.isArray((taggedItems||{}).endpoints) ? taggedItems.endpoints : [];
  const _mkt = Array.isArray((taggedItems||{}).marketing) ? taggedItems.marketing : [];
  let infraHtml = '';
  if (_eps.length) {
    infraHtml += `<div style="margin-bottom:10px">
      <div style="font-size:9px;text-transform:uppercase;letter-spacing:.1em;color:#5a6a7a;margin-bottom:6px">Endpoints (${_eps.length})</div>
      ${_eps.map(ep => {
        const _stC = {online:'#00ff9d', offline:'#ff3b5c', unknown:'#ffa500'};
        const _st  = ep.status || 'unknown';
        return `<div style="display:flex;align-items:center;gap:8px;padding:4px 0;border-bottom:1px solid rgba(255,255,255,0.04)">
          <span style="display:inline-block;width:7px;height:7px;border-radius:50%;background:${_stC[_st]||'#888'};flex-shrink:0" title="${_escHtml(_st)}${ep.details?' · '+_escHtml(ep.details):''}"></span>
          <span style="font-size:11px;font-weight:700;color:#e8edf2">${_escHtml(ep.name)}</span>
          <a href="${_escHtml(ep.url)}" target="_blank" style="font-size:10px;color:#5a6a7a;text-decoration:none;flex:1;overflow:hidden;text-overflow:ellipsis">${_escHtml(ep.url)}</a>
          <span style="font-size:9px;color:${_stC[_st]||'#888'};font-family:ui-monospace,monospace;flex-shrink:0">${_escHtml(_st)}</span>
        </div>`;
      }).join('')}
    </div>`;
  }
  if (_mkt.length) {
    infraHtml += `<div>
      <div style="font-size:9px;text-transform:uppercase;letter-spacing:.1em;color:#5a6a7a;margin-bottom:6px">Marketing (${_mkt.length})</div>
      ${_mkt.map(m => `<div style="display:flex;align-items:center;gap:6px;padding:4px 0;border-bottom:1px solid rgba(255,255,255,0.04)">
        <span style="font-size:10px">📄</span>
        <span style="font-size:10px;font-weight:700;color:#e8edf2">${_escHtml(m.content_type)} · ${_escHtml(m.reseau)}</span>
        <span style="font-size:9px;color:#5a6a7a;flex:1">${_escHtml((m.result||'').slice(0,50))}…</span>
      </div>`).join('')}
    </div>`;
  }
  if (!infraHtml) {
    infraHtml = `<div class="soc-empty">Aucun élément associé.<br><span style="font-size:10px">Taguez des endpoints ou contenus marketing avec <b>${_escHtml(companyId)}</b>.</span></div>`;
  }

  const connPanelHtml = _renderConnPanel(company);

  const meta = [company.website, company.email, company.phone].filter(Boolean).join(' · ');

  container.innerHTML = `
  <div class="soc-detail-wrap">
    <div class="detail-header">
      <button class="detail-back" id="soc-back">← Retour</button>
      <div class="detail-co-logo" style="color:${company.color}">${_initials(company.name)}</div>
      <div>
        <div class="detail-co-name">${company.name}</div>
        <div class="detail-co-sub">${company.type}${meta ? ' · ' + meta : ''}</div>
      </div>
      <div style="display:flex;gap:6px;margin-left:auto;flex-wrap:wrap">${connBar}</div>
    </div>
    <div class="soc-section-hdr">
      <div class="soc-section-title">Indicateurs clés</div>
      <div class="soc-section-line"></div>
    </div>
    <div class="detail-kpi-grid">${kpisHtml}</div>
    <div class="detail-cols">
      <div>
        <div class="soc-section-hdr" style="margin-bottom:8px">
          <div class="soc-section-title">Fil des événements</div>
          <div class="soc-section-line"></div>
        </div>
        ${tlHtml}
      </div>
      <div>
        <div class="soc-section-hdr" style="margin-bottom:8px">
          <div class="soc-section-title">Infrastructure &amp; Marketing</div>
          <div class="soc-section-line"></div>
        </div>
        <div>${infraHtml}</div>
      </div>
    </div>
    <div class="soc-section-hdr" style="margin-top:4px">
      <div class="soc-section-title">Connecteurs</div>
      <div class="soc-section-line"></div>
    </div>
    <div class="soc-conn-panel" id="conn-section">${connPanelHtml}</div>
  </div>`;

  container.querySelector('#soc-back')?.addEventListener('click', () => {
    _activeId = null;
    _renderDashboard(container);
  });
  _bindConnectorEvents(container, companyId);
}

async function _loadTaggedItems(container, companyId) {
  const wrap = container.querySelector('#tagged-items-section');
  if (!wrap) return;
  try {
    const data = await _api(`/companies/${companyId}/tagged-items`);
    const eps = Array.isArray(data.endpoints) ? data.endpoints : [];
    const mkt = Array.isArray(data.marketing) ? data.marketing : [];
    if (!eps.length && !mkt.length) {
      wrap.innerHTML = '<p class="soc-empty">Aucun élément tagué avec cette société. Taguez des endpoints ou des contenus marketing avec <b>' + companyId + '</b>.</p>';
      return;
    }
    const epsHtml = eps.length ? `
      <div style="margin-bottom:10px">
        <div style="font-size:10px;text-transform:uppercase;letter-spacing:.1em;color:#5a6a7a;margin-bottom:6px">Endpoints infrastructure (${eps.length})</div>
        ${eps.map(ep => `<div style="display:flex;align-items:center;gap:8px;padding:5px 0;border-bottom:1px solid rgba(255,255,255,0.04)">
          <span style="font-size:11px;color:#00d4ff">⬡</span>
          <span style="font-size:12px;font-weight:700;color:#e8edf2">${_escHtml(ep.name)}</span>
          <a href="${_escHtml(ep.url)}" target="_blank" style="font-size:11px;color:#5a6a7a;text-decoration:none;flex:1">${_escHtml(ep.url)}</a>
        </div>`).join('')}
      </div>` : '';
    const mktHtml = mkt.length ? `
      <div>
        <div style="font-size:10px;text-transform:uppercase;letter-spacing:.1em;color:#5a6a7a;margin-bottom:6px">Contenus marketing (${mkt.length})</div>
        ${mkt.map(m => `<div style="display:flex;align-items:center;gap:8px;padding:5px 0;border-bottom:1px solid rgba(255,255,255,0.04)">
          <span style="font-size:11px">📄</span>
          <span style="font-size:11px;font-weight:700;color:#e8edf2">${_escHtml(m.content_type)} · ${_escHtml(m.reseau)}</span>
          <span style="font-size:10px;color:#5a6a7a;flex:1">${_escHtml((m.result||'').slice(0,60))}…</span>
          <span style="font-size:9px;color:#5a6a7a">${_escHtml((m.created_at||'').slice(0,10))}</span>
        </div>`).join('')}
      </div>` : '';
    wrap.innerHTML = `<div style="padding:4px 0">${epsHtml}${mktHtml}</div>`;
  } catch {
    wrap.innerHTML = '<p class="soc-empty">Impossible de charger les éléments associés.</p>';
  }
}

// ── Connector panel ──────────────────────────────────────────────
function _renderConnPanel(company) {
  const dol = (company.connectors || {}).dolibarr || {};
  const isCfg = !!(dol.url && dol.api_key);
  const lastSync = dol.last_sync
    ? `Sync : ${_fmtDate(new Date(dol.last_sync).getTime() / 1000)}`
    : 'Jamais synchronisé';
  return `
    <div class="conn-row">
      <div class="conn-logo">🔌</div>
      <div style="flex:1;min-width:0">
        <div class="conn-name">Dolibarr ERP</div>
        ${isCfg
          ? `<div class="conn-url">${dol.url}</div><div class="conn-last-sync">${lastSync}</div>`
          : `<div class="conn-url" style="color:#ff9500">Non configuré</div>`}
      </div>
      <div class="conn-badge conn-badge-none" id="conn-dol-badge">${isCfg ? 'non testé' : 'inactif'}</div>
      ${isCfg ? `
        <button class="conn-btn" id="conn-dol-test">Tester</button>
        <button class="conn-btn primary" id="conn-dol-sync">↻ Sync</button>` : ''}
      <button class="conn-btn" id="conn-dol-cfg">${isCfg ? '⚙' : '+ Configurer'}</button>
    </div>
    <div class="conn-form" id="conn-dol-form" style="display:none">
      <input class="conn-input" id="conn-dol-url"   placeholder="URL Dolibarr (https://...)"              value="${dol.url || ''}" />
      <input class="conn-input" id="conn-dol-key"   placeholder="API Key Dolibarr"  type="password"       value="" />
      <input class="conn-input" id="conn-dol-field" placeholder="Champ ID client Dolibarr (code_client)"  value="${dol.company_id_field || 'code_client'}" />
      <input class="conn-input" id="conn-dol-dolid" placeholder="ID société dans Dolibarr (optionnel)"    value="${dol.dolibarr_company_id || ''}" />
      <div class="conn-form-row">
        <button class="conn-btn primary" id="conn-dol-save">💾 Enregistrer</button>
        ${isCfg ? `<span style="font-size:10px;color:#5a6a7a">Laisser API Key vide pour conserver l'existante</span>` : ''}
      </div>
    </div>`;
}

function _bindConnectorEvents(container, companyId) {
  const cfgBtn  = container.querySelector('#conn-dol-cfg');
  const form    = container.querySelector('#conn-dol-form');
  const testBtn = container.querySelector('#conn-dol-test');
  const syncBtn = container.querySelector('#conn-dol-sync');
  const saveBtn = container.querySelector('#conn-dol-save');
  const badge   = container.querySelector('#conn-dol-badge');

  cfgBtn?.addEventListener('click', () => {
    if (form) form.style.display = form.style.display === 'none' ? 'flex' : 'none';
  });

  testBtn?.addEventListener('click', async () => {
    if (!badge) return;
    badge.textContent = '…';
    badge.className = 'conn-badge conn-badge-none';
    try {
      const res = await _api(`/companies/${companyId}/connectors/dolibarr/status`);
      badge.textContent = res.connected ? 'connecté ✓' : 'erreur ✗';
      badge.className   = res.connected ? 'conn-badge conn-badge-ok' : 'conn-badge conn-badge-err';
    } catch {
      badge.textContent = 'erreur ✗';
      badge.className   = 'conn-badge conn-badge-err';
    }
  });

  saveBtn?.addEventListener('click', async () => {
    const url   = container.querySelector('#conn-dol-url')?.value.trim();
    const key   = container.querySelector('#conn-dol-key')?.value.trim();
    const field = container.querySelector('#conn-dol-field')?.value.trim() || 'code_client';
    const dolId = container.querySelector('#conn-dol-dolid')?.value.trim() || '';
    if (!url) { showToast('URL Dolibarr requise'); return; }
    const orig = saveBtn.textContent;
    saveBtn.textContent = '…';
    saveBtn.disabled = true;
    try {
      const r = await fetch(`/api/societe/companies/${companyId}/connectors/dolibarr`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url, api_key: key, company_id_field: field, dolibarr_company_id: dolId }),
      });
      if (!r.ok) throw new Error((await r.json()).detail || `HTTP ${r.status}`);
      showToast('Connecteur Dolibarr enregistré ✓');
      await _renderDetail(container, companyId);
    } catch(e) {
      showToast('Erreur : ' + e.message);
      saveBtn.textContent = orig;
      saveBtn.disabled = false;
    }
  });

  syncBtn?.addEventListener('click', async () => {
    const orig = syncBtn.textContent;
    syncBtn.textContent = '…';
    syncBtn.disabled = true;
    try {
      const r = await fetch(`/api/societe/companies/${companyId}/sync/dolibarr`, { method: 'POST' });
      const data = await r.json();
      if (!r.ok) throw new Error(data.detail || `HTTP ${r.status}`);
      const s = data.synced;
      showToast(`Sync OK · ${s.invoices} factures · ${s.quotes} devis · ${s.tickets} tickets`);
      await _renderDetail(container, companyId);
    } catch(e) {
      showToast('Sync échoué : ' + e.message);
      syncBtn.textContent = orig;
      syncBtn.disabled = false;
    }
  });
}

// ── Chat panel ───────────────────────────────────────────────────
function _renderChatPanel(pane) {
  // Boutons contexte
  const ctxBtns = [
    { id: null, label: 'Tout', color: 'rgba(255,255,255,0.4)' },
    ..._companies.map(c => ({ id: c.id, label: c.name, color: c.color })),
  ];
  const ctxHtml = ctxBtns.map(b => `
    <button class="scp-ctx-btn${b.id === _chatCtxId ? ' active' : ''}"
            data-ctx="${b.id || ''}"
            style="--co-color:${b.color}">
      <span class="cb-dot" style="background:${b.color}"></span>${b.label}
    </button>`).join('');

  const quickPrompts = _chatCtxId
    ? ['Résume la situation', 'Quels impayés ?', 'Tickets ouverts ?', 'Prochain devis ?']
    : ['État des sociétés', 'Alertes en cours ?', 'Total impayés ?', 'Tickets ouverts ?'];

  const qpHtml = quickPrompts.map(p =>
    `<button class="scp-qp-btn" data-qp="${p}">${p}</button>`).join('');

  pane.innerHTML = `
    <div class="scp-header">
      <div class="scp-pulse"></div>
      <div class="scp-title">ADA</div>
      <div class="scp-model">mistral · local</div>
    </div>
    <div class="scp-ctx-bar">
      <div class="scp-ctx-label">Contexte actif</div>
      <div class="scp-ctx-btns">${ctxHtml}</div>
    </div>
    <div class="scp-msgs" id="scp-msgs"></div>
    <div class="scp-qp">${qpHtml}</div>
    <div class="scp-input-row">
      <textarea class="scp-textarea" id="scp-input" rows="1" placeholder="Posez une question…"></textarea>
      <button class="scp-send" id="scp-send" title="Envoyer">
        <svg viewBox="0 0 24 24" width="16" height="16" fill="currentColor"><path d="M2.01 21L23 12 2.01 3 2 10l15 2-15 2z"/></svg>
      </button>
    </div>`;

  // Contexte
  pane.querySelectorAll('.scp-ctx-btn').forEach(btn => {
    btn.addEventListener('click', async () => {
      const cid = btn.dataset.ctx || null;
      _chatCtxId = cid;
      _chatCtxText = '';
      if (cid) {
        try {
          const ctx = await _api(`/companies/${cid}/context`);
          _chatCtxText = typeof ctx === 'string' ? ctx : JSON.stringify(ctx);
        } catch {}
      }
      pane.querySelectorAll('.scp-ctx-btn').forEach(b => {
        b.classList.toggle('active', (b.dataset.ctx || null) === _chatCtxId);
      });
      // Rafraîchir les quick prompts
      const qpDiv = pane.querySelector('.scp-qp');
      if (qpDiv) {
        const qps = _chatCtxId
          ? ['Résume la situation', 'Quels impayés ?', 'Tickets ouverts ?', 'Prochain devis ?']
          : ['État des sociétés', 'Alertes en cours ?', 'Total impayés ?', 'Tickets ouverts ?'];
        qpDiv.innerHTML = qps.map(p => `<button class="scp-qp-btn" data-qp="${p}">${p}</button>`).join('');
        _bindQP(pane);
      }
    });
  });

  _bindQP(pane);

  // Envoi
  const input  = pane.querySelector('#scp-input');
  const sendBtn = pane.querySelector('#scp-send');

  sendBtn.addEventListener('click', () => _chatSend(pane, input));
  input.addEventListener('keydown', e => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); _chatSend(pane, input); }
  });
  input.addEventListener('input', () => {
    input.style.height = 'auto';
    input.style.height = Math.min(input.scrollHeight, 80) + 'px';
  });
}

function _bindQP(pane) {
  pane.querySelectorAll('.scp-qp-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      const input = pane.querySelector('#scp-input');
      if (input) { input.value = btn.dataset.qp; input.focus(); }
    });
  });
}

async function _chatSend(pane, input) {
  const text = input.value.trim();
  if (!text || _chatStreaming) return;
  input.value = '';
  input.style.height = 'auto';

  const msgs = pane.querySelector('#scp-msgs');
  const sendBtn = pane.querySelector('#scp-send');

  // Bulle user
  const userBubble = document.createElement('div');
  userBubble.className = 'scp-msg scp-msg-user';
  userBubble.textContent = text;
  msgs.appendChild(userBubble);
  msgs.scrollTop = msgs.scrollHeight;

  _chatHistory.push({ role: 'user', content: text });
  _chatStreaming = true;
  sendBtn.disabled = true;

  // Bulle ADA
  const adaBubble = document.createElement('div');
  adaBubble.className = 'scp-msg scp-msg-ada streaming';
  msgs.appendChild(adaBubble);
  msgs.scrollTop = msgs.scrollHeight;

  // Construire l'historique avec contexte injecté
  const histWithCtx = _chatCtxText
    ? [
        { role: 'user',      content: `Contexte société actif :\n${_chatCtxText}` },
        { role: 'assistant', content: 'Contexte pris en compte.' },
        ..._chatHistory.slice(-18),
      ]
    : _chatHistory.slice(-20);

  let acc = '';
  try {
    const resp = await fetch('/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: text, history: histWithCtx.slice(0, -1), company_context: _chatCtxId || null }),
    });
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);

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
          if (d.text) { acc += d.text; adaBubble.textContent = acc; msgs.scrollTop = msgs.scrollHeight; }
        } catch {}
      }
    }
    _chatHistory.push({ role: 'assistant', content: acc });
  } catch(e) {
    adaBubble.textContent = 'Erreur : ' + e.message;
  } finally {
    adaBubble.classList.remove('streaming');
    _chatStreaming = false;
    sendBtn.disabled = false;
    msgs.scrollTop = msgs.scrollHeight;
  }
}

// ── mount / unmount ───────────────────────────────────────────────
export async function mount(container) {
  if (!document.getElementById('css-societe')) {
    const s = document.createElement('style');
    s.id = 'css-societe';
    s.textContent = _CSS;
    document.head.appendChild(s);
  }

  // Layout pleine largeur — le chat est géré par le shell principal
  container.innerHTML = `
    <div class="soc-page-layout">
      <div class="soc-content" id="soc-content"></div>
    </div>`;

  _contentEl = container.querySelector('#soc-content');

  // Charger les sociétés puis notifier le shell
  await _renderDashboard(_contentEl);
  window.adaSocSetCompanies?.(_companies);
}

export function unmount() {
  _activeId = null;
  _chatCtxId = null;
  _chatCtxText = '';
  window.adaSocSetCompanies?.([]);
}

// ── API publique chat context (MODULE_SOCIETE) ────────────────────
export async function getSocieteContext(companyId) {
  return _api(companyId ? `/companies/${companyId}/context` : '/context');
}
export function getActiveCompanyId() { return _activeId; }
export function getCompanies()       { return _companies; }
