/* ================================================================
   Vue Chat — mount / unmount
   Gère : conversation SSE, STT (Web Speech), TTS, textarea.
   L'input bar (#input-bar) est globale — ce module l'active/désactive.
   ================================================================ */
import { showToast, setInputBarVisible, switchView } from '/static/core/core.js';

const _CSS = '/static/views/chat/style.css';

function _ensureCSS() {
  if (!document.getElementById('css-chat')) {
    const l = document.createElement('link');
    l.id = 'css-chat'; l.rel = 'stylesheet'; l.href = _CSS;
    document.head.appendChild(l);
  }
}

// ── État persistant du module (singleton) ───────────────────────
const _history = [];
let _isStreaming = false;
let _ttsEnabled  = localStorage.getItem('ada-tts') !== 'false';
let _recognition = null;
let _sttInited   = false;

// ── Références DOM globales (input bar) ─────────────────────────
const _textInput = document.getElementById('text-input');
const _sendBtn   = document.getElementById('send-btn');
const _micBtn    = document.getElementById('mic-btn');
const _ttsBtn    = document.getElementById('tts-btn');
const _ttsOn     = document.getElementById('tts-on');
const _ttsOff    = document.getElementById('tts-off');

// ── Références DOM locales (recréées à chaque mount) ────────────
let _root     = null;
let _messages = null;
let _typing   = null;

// ── Bubble ──────────────────────────────────────────────────────
function _bubble(role, content = '') {
  const d = document.createElement('div');
  d.className = `msg ${role}`;
  d.textContent = content;
  _messages.appendChild(d);
  _messages.scrollTop = _messages.scrollHeight;
  return d;
}

// ── Textarea auto-resize ────────────────────────────────────────
function _resize() {
  _textInput.style.height = 'auto';
  _textInput.style.height = Math.min(_textInput.scrollHeight, 120) + 'px';
}

// ── Envoi / SSE ─────────────────────────────────────────────────
export async function sendMessage(text) {
  text = text.trim();
  if (!text || _isStreaming) return;

  // Basculer vers chat si on vient d'une autre vue
  if (!_root || !_root.isConnected) {
    await switchView('chat', { send: text });
    return;
  }

  _isStreaming = true;
  _sendBtn.disabled = true;
  _textInput.value = '';
  _resize();

  _bubble('user', text);
  _history.push({ role: 'user', content: text });

  _typing.classList.add('show');
  _messages.scrollTop = _messages.scrollHeight;

  let ada = null;
  let acc = '';

  try {
    const resp = await fetch('/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: text, history: _history.slice(-20) }),
    });
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);

    _typing.classList.remove('show');
    // ada bubble créée au premier token texte (peut être précédée d'une image)

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
          const obj = JSON.parse(raw);
          if (obj.error) { showToast('Erreur : ' + obj.error); break; }
          if (obj.img_url) {
            // Afficher la capture caméra dans une bulle dédiée
            const imgBubble = document.createElement('div');
            imgBubble.className = 'msg ada msg-snap';
            const img = document.createElement('img');
            img.src = obj.img_url + '?t=' + Date.now();
            img.alt = 'Capture caméra';
            img.style.cssText = 'max-width:100%;max-height:260px;border-radius:10px;display:block;';
            imgBubble.appendChild(img);
            _messages.appendChild(imgBubble);
            _messages.scrollTop = _messages.scrollHeight;
          }
          if (obj.text) {
            if (!ada) { ada = _bubble('ada', ''); ada.classList.add('streaming'); }
            acc += obj.text; ada.textContent = acc; _messages.scrollTop = _messages.scrollHeight;
          }
        } catch { /* ignore */ }
      }
    }
  } catch (err) {
    _typing.classList.remove('show');
    showToast('Connexion perdue');
    console.error(err);
  } finally {
    if (ada) {
      ada.classList.remove('streaming');
      if (acc) {
        _history.push({ role: 'assistant', content: acc });
        _speakIfEnabled(acc);
      }
    }
    _isStreaming = false;
    _sendBtn.disabled = false;
    if (_root?.isConnected) _textInput.focus();
  }
}

// ── TTS ─────────────────────────────────────────────────────────
function _speakIfEnabled(text) {
  if (!_ttsEnabled || !window.speechSynthesis) return;
  window.speechSynthesis.cancel();
  const sentences = text.match(/[^.!?]+[.!?]*/g) || [text];
  for (const s of sentences) {
    const u = new SpeechSynthesisUtterance(s.trim());
    u.lang = navigator.language || 'fr-FR';
    u.rate = 1.05;
    window.speechSynthesis.speak(u);
  }
}

function _updateTtsBtn() {
  _ttsBtn.classList.toggle('active', _ttsEnabled);
  _ttsOn.style.display  = _ttsEnabled ? 'inline' : 'none';
  _ttsOff.style.display = _ttsEnabled ? 'none'   : 'inline';
  _ttsBtn.title = _ttsEnabled ? 'Désactiver la voix' : 'Activer la voix';
}

// ── STT ─────────────────────────────────────────────────────────
function _initSTT() {
  if (_sttInited) return;
  _sttInited = true;
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SR) { _micBtn.disabled = true; _micBtn.title = 'Web Speech non supporté'; return; }

  _recognition = new SR();
  _recognition.lang = navigator.language || 'fr-FR';
  _recognition.interimResults = false;
  _recognition.maxAlternatives = 1;

  _recognition.onresult = (e) => {
    const t = e.results[0][0].transcript;
    _textInput.value = t;
    _resize();
    sendMessage(t);
  };
  _recognition.onerror = (e) => {
    _micBtn.classList.remove('listening');
    if (e.error === 'not-allowed') showToast('⛔ Accès micro refusé');
    else if (e.error !== 'no-speech') showToast('Micro : ' + e.error);
  };
  _recognition.onend = () => _micBtn.classList.remove('listening');
}

// ── Handlers (stockés pour suppression propre) ──────────────────
const _h = {};

export async function mount(vp, opts = {}) {
  _ensureCSS();

  _root = document.createElement('div');
  _root.className = 'view-root chat-view';
  _root.innerHTML = `
    <div id="messages" role="log" aria-live="polite" aria-label="Conversation"></div>
    <div id="typing" role="status" aria-label="ADA réfléchit">
      <span></span><span></span><span></span>
    </div>`;
  vp.appendChild(_root);

  _messages = _root.querySelector('#messages');
  _typing   = _root.querySelector('#typing');

  setInputBarVisible(true);
  _initSTT();
  _updateTtsBtn();

  // Restaurer l'historique ou afficher le message de bienvenue
  if (_history.length > 0) {
    for (const e of _history) _bubble(e.role === 'user' ? 'user' : 'ada', e.content);
    _messages.scrollTop = _messages.scrollHeight;
  } else if (!opts.send) {
    _bubble('ada', 'Bonjour ! Je suis ADA. Comment puis-je vous aider ?');
  }

  // Câblage events
  _h.input   = () => _resize();
  _h.keydown = (e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage(_textInput.value); } };
  _h.send    = () => sendMessage(_textInput.value);
  _h.tts     = () => { _ttsEnabled = !_ttsEnabled; localStorage.setItem('ada-tts', _ttsEnabled); _updateTtsBtn(); showToast(_ttsEnabled ? '🔊 Voix activée' : '🔇 Voix désactivée'); };
  _h.mic     = () => {
    if (_micBtn.classList.contains('listening')) { _recognition?.stop(); }
    else { _micBtn.classList.add('listening'); try { _recognition?.start(); } catch { _micBtn.classList.remove('listening'); } }
  };

  _textInput.addEventListener('input',   _h.input);
  _textInput.addEventListener('keydown', _h.keydown);
  _sendBtn.addEventListener('click',     _h.send);
  _ttsBtn.addEventListener('click',      _h.tts);
  _micBtn.addEventListener('click',      _h.mic);

  _textInput.focus();

  if (opts.send) {
    sendMessage(opts.send);
  } else if (opts.prefill) {
    _textInput.value = opts.prefill;
    _resize();
    _textInput.focus();
    _textInput.setSelectionRange(opts.prefill.length, opts.prefill.length);
  }
}

export function unmount() {
  _recognition?.stop();
  _textInput.removeEventListener('input',   _h.input);
  _textInput.removeEventListener('keydown', _h.keydown);
  _sendBtn.removeEventListener('click',     _h.send);
  _ttsBtn.removeEventListener('click',      _h.tts);
  _micBtn.removeEventListener('click',      _h.mic);
  _root?.remove();
  _root = null; _messages = null; _typing = null;
}
