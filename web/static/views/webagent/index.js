/* ================================================================
   Vue Agent Web — mount / unmount
   Interface Playwright + Ollama pour la recherche web autonome.
   Champ éditable → Start/Stop → log SSE → résultat final.
   ================================================================ */
import { escapeHtml, setInputBarVisible, showToast } from '/static/core/core.js';

const _CSS = '/static/views/webagent/style.css';

function _ensureCSS() {
  if (!document.getElementById('css-webagent')) {
    const l = document.createElement('link');
    l.id = 'css-webagent'; l.rel = 'stylesheet'; l.href = _CSS;
    document.head.appendChild(l);
  }
}

let _root = null;
let _abortCtrl = null;

export function mount(vp, opts = {}) {
  _ensureCSS();
  setInputBarVisible(false);

  _root = document.createElement('div');
  _root.className = 'view-root wa-view';
  _root.innerHTML = `
    <div class="wa-shell">
      <div class="wa-top">
        <div class="wa-input-row">
          <textarea id="wa-input" class="wa-textarea" rows="2"
            placeholder="Ex : Cherche les dernières nouvelles IA en France…"
            spellcheck="true">${escapeHtml(opts.prefill || '')}</textarea>
          <div class="wa-btn-group">
            <button id="wa-start" class="wa-btn primary">▶ Lancer</button>
            <button id="wa-stop"  class="wa-btn" disabled>■ Stop</button>
          </div>
        </div>
        <div id="wa-status" class="wa-status">Inactif</div>
      </div>
      <div class="wa-panels">
        <div class="wa-panel">
          <div class="wa-panel-title">Journal d'actions</div>
          <div id="wa-log" class="wa-log"></div>
        </div>
        <div class="wa-panel">
          <div class="wa-panel-title">Résultat</div>
          <div id="wa-result" class="wa-result">La réponse finale apparaîtra ici…</div>
        </div>
      </div>
    </div>`;

  vp.appendChild(_root);

  const inputEl  = _root.querySelector('#wa-input');
  const startBtn = _root.querySelector('#wa-start');
  const stopBtn  = _root.querySelector('#wa-stop');
  const statusEl = _root.querySelector('#wa-status');
  const logEl    = _root.querySelector('#wa-log');
  const resultEl = _root.querySelector('#wa-result');

  function _log(text) {
    const line = document.createElement('div');
    line.className = 'wa-log-line';
    line.textContent = text;
    logEl.appendChild(line);
    logEl.scrollTop = logEl.scrollHeight;
  }

  startBtn.addEventListener('click', async () => {
    const instruction = inputEl.value.trim();
    if (!instruction) { showToast('Saisissez une instruction.'); return; }

    logEl.innerHTML = '';
    resultEl.textContent = '';
    resultEl.classList.remove('has-result');
    statusEl.textContent = 'En cours…';
    startBtn.disabled = true;
    stopBtn.disabled = false;

    _abortCtrl = new AbortController();
    try {
      const resp = await fetch('/api/agent/web', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ instruction }),
        signal: _abortCtrl.signal,
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
          if (raw === '[DONE]') { if (!statusEl.textContent.startsWith('Résultat')) statusEl.textContent = 'Terminé'; break; }
          try {
            const obj = JSON.parse(raw);
            if (obj.type === 'step')   { _log(obj.text); }
            if (obj.type === 'result') {
              resultEl.textContent = obj.text;
              resultEl.classList.add('has-result');
              statusEl.textContent = 'Résultat obtenu';
            }
            if (obj.type === 'error')  { _log('⚠ ' + obj.text); statusEl.textContent = 'Erreur'; }
          } catch { /* ignore */ }
        }
      }
    } catch (err) {
      if (err.name !== 'AbortError') {
        _log('Connexion perdue : ' + err.message);
        statusEl.textContent = 'Erreur';
      } else {
        statusEl.textContent = 'Arrêté';
      }
    } finally {
      startBtn.disabled = false;
      stopBtn.disabled = true;
      _abortCtrl = null;
    }
  });

  stopBtn.addEventListener('click', () => {
    _abortCtrl?.abort();
    statusEl.textContent = 'Arrêt en cours…';
    stopBtn.disabled = true;
  });

  inputEl.focus();
  if (opts.prefill) {
    const len = inputEl.value.length;
    inputEl.setSelectionRange(len, len);
  }
}

export function unmount() {
  _abortCtrl?.abort();
  _root?.remove();
  _root = null;
  _abortCtrl = null;
}
