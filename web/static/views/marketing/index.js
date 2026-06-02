/* ================================================================
   Vue Marketing — génération de contenus marketing via Ollama
   ================================================================ */
import { showToast } from '/static/core/core.js';

const _CSS = '/static/views/marketing/style.css';

function _ensureCSS() {
  if (!document.getElementById('css-marketing')) {
    const l = document.createElement('link');
    l.id = 'css-marketing'; l.rel = 'stylesheet'; l.href = _CSS;
    document.head.appendChild(l);
  }
}

// ── État du module ──────────────────────────────────────────────
let _root        = null;
let _generating  = false;
let _abortCtrl   = null;
let _histOpen    = false;

// ── Helpers ─────────────────────────────────────────────────────
function _escHtml(s) {
  return String(s)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');
}

function _buildSelect(id, options, selectedVal) {
  const sel = document.createElement('select');
  sel.id = id;
  sel.className = 'mkt-select';
  for (const opt of options) {
    const o = document.createElement('option');
    o.value = opt;
    o.textContent = opt;
    if (opt === selectedVal) o.selected = true;
    sel.appendChild(o);
  }
  return sel;
}

// ── Chargement des méta-données depuis l'API ─────────────────────
async function _loadMeta(root) {
  try {
    const [metaResp, skillsResp, modelsResp] = await Promise.all([
      fetch('/api/marketing/meta'),
      fetch('/api/marketing/skills'),
      fetch('/api/marketing/models'),
    ]);
    const meta   = await metaResp.json();
    const skills = await skillsResp.json();
    const models = await modelsResp.json();

    // Modèles
    const modelSel = root.querySelector('#mkt-model');
    modelSel.innerHTML = '<option value="">(défaut config)</option>';
    for (const m of models) {
      const o = document.createElement('option');
      o.value = m;
      o.textContent = m;
      modelSel.appendChild(o);
    }

    // Skills
    const skillSel = root.querySelector('#mkt-skill');
    skillSel.innerHTML = '';
    for (const s of skills) {
      const o = document.createElement('option');
      o.value = s.name;
      o.textContent = s.description || s.name;
      skillSel.appendChild(o);
    }
    if (skills.length === 0) {
      const o = document.createElement('option');
      o.value = 'margepro';
      o.textContent = 'margepro';
      skillSel.appendChild(o);
    }

    // Content types
    const ctSel = root.querySelector('#mkt-content-type');
    ctSel.innerHTML = '';
    for (const ct of meta.content_types) {
      const o = document.createElement('option');
      o.value = ct;
      o.textContent = ct;
      ctSel.appendChild(o);
    }

    // Réseaux
    const resSel = root.querySelector('#mkt-reseau');
    resSel.innerHTML = '';
    for (const r of meta.reseaux) {
      const o = document.createElement('option');
      o.value = r;
      o.textContent = r;
      resSel.appendChild(o);
    }

    // Secteurs — datalist pour saisie libre
    const secList = root.querySelector('#mkt-secteur-list');
    secList.innerHTML = '';
    for (const s of meta.secteurs) {
      const o = document.createElement('option');
      o.value = s;
      secList.appendChild(o);
    }
    // Pré-remplir avec le premier secteur
    const secInput = root.querySelector('#mkt-secteur');
    if (meta.secteurs.length > 0 && !secInput.value) {
      secInput.value = meta.secteurs[0];
    }

    // Tons
    const tonSel = root.querySelector('#mkt-ton');
    tonSel.innerHTML = '';
    for (const t of meta.tons) {
      const o = document.createElement('option');
      o.value = t;
      o.textContent = t;
      tonSel.appendChild(o);
    }

  } catch (e) {
    console.error('Marketing meta load error:', e);
    showToast('Erreur chargement options marketing');
  }
}

// ── Génération SSE ──────────────────────────────────────────────
async function _generate(root) {
  if (_generating) return;

  const skillName   = root.querySelector('#mkt-skill').value;
  const contentType = root.querySelector('#mkt-content-type').value;
  const reseau      = root.querySelector('#mkt-reseau').value;
  const secteur     = root.querySelector('#mkt-secteur').value;
  const ton         = root.querySelector('#mkt-ton').value;
  const brief       = root.querySelector('#mkt-brief').value.trim();
  const model       = root.querySelector('#mkt-model').value;

  if (!contentType || !reseau || !secteur || !ton) {
    showToast('Remplis tous les champs requis');
    return;
  }

  const resultEl  = root.querySelector('#mkt-result');
  const countEl   = root.querySelector('#mkt-char-count');
  const genBtn    = root.querySelector('#mkt-gen-btn');
  const stopBtn   = root.querySelector('#mkt-stop-btn');

  _generating = true;
  _abortCtrl  = new AbortController();
  genBtn.disabled  = true;
  stopBtn.disabled = false;
  resultEl.classList.add('generating');
  resultEl.innerHTML = '<span class="mkt-cursor"></span>';
  countEl.textContent = '0 car.';

  let fullText = '';

  try {
    const resp = await fetch('/api/marketing/generate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ skill_name: skillName, content_type: contentType, reseau, secteur, ton, brief, model }),
      signal: _abortCtrl.signal,
    });

    if (!resp.ok) {
      const err = await resp.json().catch(() => ({ detail: resp.statusText }));
      throw new Error(err.detail || resp.statusText);
    }

    const reader  = resp.body.getReader();
    const decoder = new TextDecoder();
    let   buffer  = '';

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      const lines = buffer.split('\n');
      buffer = lines.pop(); // garde la ligne incomplète

      for (const line of lines) {
        if (!line.startsWith('data: ')) continue;
        const raw = line.slice(6).trim();
        if (raw === '[DONE]') break;
        try {
          const msg = JSON.parse(raw);
          if (msg.text) {
            fullText += msg.text;
            resultEl.textContent = fullText;
            resultEl.appendChild(_cursor());
            countEl.textContent = `${fullText.length} car.`;
          } else if (msg.error) {
            showToast('Erreur : ' + msg.error);
          }
        } catch { /* ignore */ }
      }
    }

  } catch (e) {
    if (e.name !== 'AbortError') {
      showToast('Erreur génération : ' + e.message);
    }
  } finally {
    _generating = false;
    genBtn.disabled  = false;
    stopBtn.disabled = true;
    resultEl.classList.remove('generating');
    // Retire le curseur clignotant
    const cur = resultEl.querySelector('.mkt-cursor');
    if (cur) cur.remove();
    if (!fullText) {
      resultEl.innerHTML = '<span class="mkt-result-placeholder">Le résultat apparaîtra ici…</span>';
    }
    // Rafraîchir l'historique
    _loadHistory(root);
  }
}

function _cursor() {
  const s = document.createElement('span');
  s.className = 'mkt-cursor';
  return s;
}

// ── Historique ──────────────────────────────────────────────────
async function _loadHistory(root) {
  const list = root.querySelector('#mkt-hist-list');
  if (!list) return;
  try {
    const items = await (await fetch('/api/marketing/history')).json();
    if (!items.length) {
      list.innerHTML = '<div class="mkt-hist-empty">Aucun contenu généré pour l\'instant</div>';
      return;
    }
    list.innerHTML = '';
    for (const item of items) {
      const div = document.createElement('div');
      div.className = 'mkt-hist-item';
      div.dataset.id = item.id;
      const ts = item.created_at.replace('T', ' ').slice(0, 16);
      const snippet = (item.result || '').replace(/\n/g, ' ').slice(0, 80);
      const itemTags = Array.isArray(item.tags) ? item.tags : ['local'];
      const tagsChips = itemTags.filter(t => t !== 'local').map(t =>
        `<span class="mkt-hist-tag mkt-tag-company">${_escHtml(t)}</span>`
      ).join('');
      div.innerHTML = `
        <div class="mkt-hist-item-header">
          <div class="mkt-hist-item-tags">
            <span class="mkt-hist-tag">${_escHtml(item.skill_name)}</span>
            <span class="mkt-hist-tag">${_escHtml(item.content_type)}</span>
            <span class="mkt-hist-tag">${_escHtml(item.reseau)}</span>
            ${tagsChips}
            <button class="mkt-tag-edit" data-id="${item.id}" title="Gérer les tags société">🏷</button>
          </div>
          <span class="mkt-hist-item-ts">${_escHtml(ts)}</span>
          <button class="mkt-hist-del" data-id="${item.id}" title="Supprimer">✕</button>
        </div>
        <div class="mkt-hist-snippet">${_escHtml(snippet)}…</div>
        <div class="mkt-tag-panel" id="mkt-tag-panel-${item.id}" style="display:none;padding:6px 0"></div>`;
      // Clic sur item = restaurer dans la zone résultat
      div.addEventListener('click', (e) => {
        if (e.target.classList.contains('mkt-hist-del')) return;
        if (e.target.classList.contains('mkt-tag-edit')) return;
        _restoreItem(root, item);
      });
      // Suppression
      div.querySelector('.mkt-hist-del').addEventListener('click', async (e) => {
        e.stopPropagation();
        await fetch(`/api/marketing/history/${item.id}`, { method: 'DELETE' });
        _loadHistory(root);
      });
      // Tag edit
      div.querySelector('.mkt-tag-edit').addEventListener('click', async (e) => {
        e.stopPropagation();
        const panel = div.querySelector(`#mkt-tag-panel-${item.id}`);
        if (panel.style.display !== 'none') { panel.style.display = 'none'; return; }
        let avail = ['local'];
        try { avail = await (await fetch('/api/tags/available')).json(); } catch {}
        const current = Array.isArray(item.tags) ? item.tags : ['local'];
        panel.innerHTML = `<select id="mkt-tsel-${item.id}" multiple style="background:#111820;border:1px solid rgba(255,255,255,0.1);border-radius:4px;color:#e8edf2;font-size:11px;padding:3px;height:56px">
          ${avail.map(t => `<option value="${_escHtml(t)}" ${current.includes(t)?'selected':''}>${_escHtml(t)}</option>`).join('')}
        </select>
        <button id="mkt-tsave-${item.id}" style="margin-left:6px;padding:3px 10px;background:rgba(0,212,255,0.1);border:1px solid rgba(0,212,255,0.4);border-radius:4px;color:#00d4ff;font-size:11px;cursor:pointer">Sauvegarder</button>`;
        panel.style.display = 'flex';
        panel.querySelector(`#mkt-tsave-${item.id}`).addEventListener('click', async () => {
          const sel = panel.querySelector(`#mkt-tsel-${item.id}`);
          const tags = Array.from(sel.selectedOptions).map(o => o.value);
          await fetch(`/api/marketing/history/${item.id}/tags`, {
            method:'PATCH', headers:{'Content-Type':'application/json'},
            body: JSON.stringify({tags})
          });
          item.tags = tags;
          panel.style.display = 'none';
          _loadHistory(root);
        });
      });
      list.appendChild(div);
    }
  } catch (e) {
    list.innerHTML = '<div class="mkt-hist-empty">Erreur chargement historique</div>';
  }
}

function _restoreItem(root, item) {
  // Restaurer les sélecteurs
  const s = (id, val) => { const el = root.querySelector(id); if (el) el.value = val; };
  s('#mkt-skill',        item.skill_name);
  s('#mkt-content-type', item.content_type);
  s('#mkt-reseau',       item.reseau);
  s('#mkt-secteur',      item.secteur);
  s('#mkt-ton',          item.ton);
  if (item.brief) root.querySelector('#mkt-brief').value = item.brief;

  const resultEl = root.querySelector('#mkt-result');
  resultEl.textContent = item.result;
  root.querySelector('#mkt-char-count').textContent = `${item.result.length} car.`;

  // Scroller vers le résultat
  resultEl.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

// ── HTML template ───────────────────────────────────────────────
const _HTML = `
<div id="mkt-root">
  <div id="mkt-scroll">

    <!-- Paramètres -->
    <div class="mkt-card">
      <div class="mkt-card-title">Paramètres</div>

      <div class="mkt-row">
        <div class="mkt-field">
          <label class="mkt-label" for="mkt-skill">Produit / Skill</label>
          <select id="mkt-skill" class="mkt-select">
            <option value="">Chargement…</option>
          </select>
        </div>
        <div class="mkt-field">
          <label class="mkt-label" for="mkt-model">Modèle IA</label>
          <select id="mkt-model" class="mkt-select">
            <option value="">(défaut config)</option>
          </select>
        </div>
      </div>

      <div class="mkt-row">
        <div class="mkt-field">
          <label class="mkt-label" for="mkt-content-type">Type de contenu</label>
          <select id="mkt-content-type" class="mkt-select">
            <option value="">…</option>
          </select>
        </div>
        <div class="mkt-field">
          <label class="mkt-label" for="mkt-reseau">Réseau social</label>
          <select id="mkt-reseau" class="mkt-select">
            <option value="">…</option>
          </select>
        </div>
      </div>

      <div class="mkt-row">
        <div class="mkt-field">
          <label class="mkt-label" for="mkt-secteur">Secteur cible</label>
          <input type="text" id="mkt-secteur" class="mkt-select" list="mkt-secteur-list"
                 placeholder="Choisir ou saisir…" autocomplete="off">
          <datalist id="mkt-secteur-list"></datalist>
        </div>
        <div class="mkt-field">
          <label class="mkt-label" for="mkt-ton">Ton</label>
          <select id="mkt-ton" class="mkt-select">
            <option value="">…</option>
          </select>
        </div>
      </div>

      <div class="mkt-field">
        <label class="mkt-label" for="mkt-brief">Brief / contexte (optionnel)</label>
        <textarea id="mkt-brief" class="mkt-textarea" placeholder="Précisions, contraintes, exemple…" rows="3"></textarea>
      </div>

      <div class="mkt-btn-row">
        <button id="mkt-gen-btn" class="mkt-btn mkt-btn-primary">✦ Générer</button>
        <button id="mkt-stop-btn" class="mkt-btn mkt-btn-secondary" disabled>■ Stop</button>
      </div>
    </div>

    <!-- Résultat -->
    <div class="mkt-card">
      <div class="mkt-card-title">Résultat</div>
      <div class="mkt-result-wrap">
        <div id="mkt-result" class="mkt-result">
          <span class="mkt-result-placeholder">Le résultat apparaîtra ici…</span>
        </div>
      </div>
      <div class="mkt-result-meta">
        <span id="mkt-char-count" class="mkt-char-count">0 car.</span>
        <button id="mkt-copy-btn" class="mkt-copy-btn">Copier</button>
      </div>
    </div>

    <!-- Historique -->
    <div class="mkt-card">
      <div class="mkt-hist-header" id="mkt-hist-toggle">
        <div class="mkt-card-title" style="margin-bottom:0">Historique</div>
        <span class="mkt-hist-toggle" id="mkt-hist-arrow">▲</span>
      </div>
      <div id="mkt-hist-list" class="hidden">
        <div class="mkt-hist-empty">Chargement…</div>
      </div>
    </div>

  </div>
</div>`;

// ── mount / unmount ─────────────────────────────────────────────
export async function mount(vp) {
  _ensureCSS();
  vp.innerHTML = _HTML;
  _root = vp.querySelector('#mkt-root');

  // Charger les méta-données
  await _loadMeta(_root);

  // Bouton Générer
  _root.querySelector('#mkt-gen-btn').addEventListener('click', () => _generate(_root));

  // Bouton Stop
  _root.querySelector('#mkt-stop-btn').addEventListener('click', () => {
    if (_abortCtrl) _abortCtrl.abort();
  });

  // Bouton Copier
  _root.querySelector('#mkt-copy-btn').addEventListener('click', () => {
    const resultEl = _root.querySelector('#mkt-result');
    const text = resultEl.textContent.trim();
    if (!text || resultEl.querySelector('.mkt-result-placeholder')) {
      showToast('Rien à copier');
      return;
    }
    navigator.clipboard.writeText(text).then(
      () => showToast('Copié !'),
      () => showToast('Erreur copie'),
    );
  });

  // Toggle historique
  const histToggle = _root.querySelector('#mkt-hist-toggle');
  const histList   = _root.querySelector('#mkt-hist-list');
  const histArrow  = _root.querySelector('#mkt-hist-arrow');
  histToggle.addEventListener('click', () => {
    _histOpen = !_histOpen;
    histList.classList.toggle('hidden', !_histOpen);
    histArrow.classList.toggle('open', _histOpen);
    if (_histOpen) _loadHistory(_root);
  });
}

export function unmount() {
  if (_abortCtrl) _abortCtrl.abort();
  _generating = false;
  _abortCtrl  = null;
  _root       = null;
}
