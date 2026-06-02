"""
Telegram Adapter — long-polling bot that routes messages through the ADA pipeline.

Architecture:
  - Daemon thread runs the polling loop (no asyncio, pure requests)
  - Each Telegram chat_id gets its own isolated session (memory, history)
  - Text messages → semantic router → tool-calling (function_gemma) or Ollama conversation
  - Photos → vision pipeline (llava-phi3)
  - /help, /status, /clear slash commands
"""

import base64
import json
import threading
import time
from datetime import datetime
from typing import Optional

import requests

from config import OLLAMA_URL, RESPONDER_MODEL, FUNCTIONS
from core.memory_store import memory_store
from core.skill_manager import skill_manager
from core.settings_store import settings
from core.function_executor import executor as function_executor
from core.semantic_router import get_route as semantic_route

_API_BASE = "https://api.telegram.org/bot{token}"

def _system_prompt() -> str:
    try:
        from core.i18n import ai_lang_instruction
        lang_instr = ai_lang_instruction()
    except Exception:
        lang_instr = "Réponds en français. Sois concis et précis."
    return (
        f"Tu es ADA, une assistante IA locale tournant sur l'ordinateur de {settings.get('user.name', 'ton utilisateur')}. "
        f"{lang_instr} "
        f"Tu es accessible via Telegram — sois utile, précise et naturelle."
    )

_HELP_TEXT = """\
🤖 *ADA via Telegram*

Commandes disponibles :
/help — afficher ce message
/myid — afficher ton chat ID (pour les briefings)
/status — état du système
/clear — effacer l'historique de cette conversation

Envoie n'importe quel message texte ou une photo pour interagir avec ADA."""

# Triggers déterministes — répondent sans passer par le LLM
_INFRA_TRIGGERS = frozenset({
    "état infra", "etat infra", "status infra", "infrastructure status",
    "état de l'infra", "etat de l infra",
})


class TelegramAdapter:
    """
    Long-polling Telegram bot that bridges to the ADA pipeline.
    Call start() once at application launch; it spawns a daemon thread.
    """

    def __init__(self):
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._offset = 0
        # Per-chat history: {chat_id: [{"role": ..., "content": ...}, ...]}
        self._histories: dict[int, list] = {}
        self._lock = threading.Lock()

    # ── Public ────────────────────────────────────────────────────────────────

    def start(self):
        token = settings.get("telegram.token", "").strip()
        if not token:
            print("[Telegram] No token configured — adapter disabled.")
            return
        if not settings.get("telegram.enabled", False):
            print("[Telegram] Adapter disabled in settings.")
            return
        if self._running:
            return

        self._running = True
        self._thread = threading.Thread(
            target=self._run, daemon=True, name="TelegramAdapter"
        )
        self._thread.start()
        print("[Telegram] Adapter started.")

    def stop(self):
        self._running = False

    def restart(self):
        """Call after settings change (new token or toggle)."""
        self.stop()
        time.sleep(0.5)
        self.start()

    # ── Internal ──────────────────────────────────────────────────────────────

    def _api(self, method: str, **kwargs) -> Optional[dict]:
        token = settings.get("telegram.token", "").strip()
        url = f"https://api.telegram.org/bot{token}/{method}"
        try:
            r = requests.post(url, json=kwargs, timeout=15)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            print(f"[Telegram] API error ({method}): {e}")
            return None

    def _get_updates(self) -> list:
        token = settings.get("telegram.token", "").strip()
        url = f"https://api.telegram.org/bot{token}/getUpdates"
        try:
            r = requests.post(
                url,
                json={"offset": self._offset, "timeout": 30,
                      "allowed_updates": ["message"]},
                timeout=40,
            )
            r.raise_for_status()
            data = r.json()
            return data.get("result", [])
        except requests.exceptions.ReadTimeout:
            return []
        except Exception as e:
            print(f"[Telegram] getUpdates error: {e}")
            time.sleep(5)
            return []

    def _send(self, chat_id: int, text: str):
        """Send a message, splitting at 4096 chars if needed."""
        max_len = 4096
        while text:
            chunk, text = text[:max_len], text[max_len:]
            self._api("sendMessage", chat_id=chat_id, text=chunk,
                      parse_mode="Markdown")

    def notify_owner(self, text: str) -> None:
        """Send a plain-text notification to the owner chat ID (no Markdown parsing).

        No-op if Telegram is disabled or owner_chat_id is not configured.
        Suitable for user-editable content (e.g., door alert messages) containing
        special chars like _, *, `, [ that would break Markdown mode.
        """
        if not settings.get("telegram.enabled", False):
            return
        owner_id = settings.get("telegram.owner_chat_id", "")
        if not owner_id:
            return
        try:
            self._api("sendMessage", chat_id=int(owner_id), text=text)
        except Exception as e:
            print(f"[Telegram] notify_owner failed: {e}")

    def _send_typing(self, chat_id: int):
        self._api("sendChatAction", chat_id=chat_id, action="typing")

    def _run(self):
        print("[Telegram] Polling started.")
        while self._running:
            updates = self._get_updates()
            for update in updates:
                self._offset = update["update_id"] + 1
                try:
                    self._handle_update(update)
                except Exception as e:
                    print(f"[Telegram] Handler error: {e}")
        print("[Telegram] Polling stopped.")

    def _handle_update(self, update: dict):
        msg = update.get("message")
        if not msg:
            return

        chat_id = msg["chat"]["id"]
        text = msg.get("text", "")
        photo = msg.get("photo")

        # Check allowed users (if configured)
        allowed = settings.get("telegram.allowed_users", [])
        if allowed and chat_id not in allowed:
            return

        # Slash commands (strip @botname suffix e.g. /myid@ada_jeff_bot)
        if text.startswith("/"):
            cmd = text.split()[0].lower()
            cmd = cmd.split("@")[0]  # strip @botname if present
            self._handle_command(chat_id, cmd)
            return

        self._send_typing(chat_id)

        if photo:
            self._handle_photo(chat_id, photo, msg.get("caption", ""))
        elif text:
            self._handle_text(chat_id, text)

    def _handle_command(self, chat_id: int, cmd: str):
        if cmd in ("/help", "/start"):
            self._send(chat_id, _HELP_TEXT)

        elif cmd == "/myid":
            self._send(chat_id,
                f"🆔 Ton chat ID Telegram : `{chat_id}`\n"
                f"Copie cette valeur dans Settings → Telegram Bot → Owner Chat ID "
                f"pour recevoir les briefings matinaux."
            )

        elif cmd == "/status":
            from datetime import datetime
            now = datetime.now().strftime("%d/%m/%Y %H:%M")
            stats = memory_store.stats()
            reply = (
                f"✅ *ADA opérationnelle*\n"
                f"📅 {now}\n"
                f"🧠 {stats.get('total', 0)} souvenirs · "
                f"{stats.get('sessions', 0)} sessions\n"
                f"💬 Historique actif : "
                f"{len(self._histories.get(chat_id, []))} messages"
            )
            self._send(chat_id, reply)

        elif cmd == "/clear":
            with self._lock:
                self._histories.pop(chat_id, None)
            session_id = f"telegram_{chat_id}"
            memory_store.clear_session(session_id)
            self._send(chat_id, "🗑️ Historique effacé.")

    def _handle_text(self, chat_id: int, text: str):
        session_id = f"telegram_{chat_id}"

        # --- Routing déterministe : état infra ---
        text_lower = text.lower().strip()
        if any(trigger in text_lower for trigger in _INFRA_TRIGGERS):
            from core.runtime_state import runtime_state
            runtime_state.refresh()
            self._send(chat_id, runtime_state.format_infra_status_fr())
            return

        with self._lock:
            history = self._histories.setdefault(chat_id, [])

        # Build messages list
        messages = [{"role": "system", "content": _system_prompt()}]
        messages += history[-20:]  # Last 20 turns max

        # Skill injection
        messages = skill_manager.inject(messages, text)

        # Memory context injection into system message
        mem = memory_store.build_context(text, current_session_id=session_id)
        if mem:
            messages[0] = {
                "role": "system",
                "content": messages[0]["content"] + "\n\n" + mem,
            }

        messages.append({"role": "user", "content": text})

        route = semantic_route(text)
        print(f"[Telegram] Route: {route}")

        if route == "function_gemma":
            response = self._call_with_tools(text, messages)
        elif route == "vision":
            response = self._handle_vision(text, chat_id)
        else:
            response = self._call_llm(messages)

        # Save to history and memory
        with self._lock:
            history.append({"role": "user", "content": text})
            history.append({"role": "assistant", "content": response})

        memory_store.save(session_id, "user", text)
        memory_store.save(session_id, "assistant", response)

        self._send(chat_id, response)

    def _handle_photo(self, chat_id: int, photo: list, caption: str):
        # Get highest-resolution photo
        file_info = self._api("getFile", file_id=photo[-1]["file_id"])
        if not file_info:
            self._send(chat_id, "❌ Impossible de récupérer la photo.")
            return

        file_path = file_info["result"]["file_path"]
        token = settings.get("telegram.token", "").strip()
        file_url = f"https://api.telegram.org/file/bot{token}/{file_path}"

        try:
            img_data = requests.get(file_url, timeout=30).content
            img_b64 = base64.b64encode(img_data).decode()
        except Exception as e:
            print(f"[Telegram] Photo download error: {e}")
            self._send(chat_id, "❌ Erreur lors du téléchargement de la photo.")
            return

        prompt = caption if caption else "Décris cette image en détail en français."

        from core.vision import describe_from_bytes
        result = describe_from_bytes(img_data, prompt=prompt)
        description = result.get("description", "❌ Impossible d'analyser l'image.")

        session_id = f"telegram_{chat_id}"
        memory_store.save(session_id, "user", f"[Photo] {caption or '(sans légende)'}")
        memory_store.save(session_id, "assistant", description)

        self._send(chat_id, description)

    def _handle_vision(self, text: str, chat_id: int) -> str:
        """Camera-aware vision handler for Telegram. Returns French description."""
        try:
            from core.camera_manager import camera_manager
            from core.vision import describe, describe_from_bytes
            from core.voice_assistant import _extract_area_hint

            if not camera_manager.list_endpoints():
                camera_manager.refresh()

            endpoints = camera_manager.list_endpoints()
            live = [ep for ep in endpoints if ep.state != "unavailable"]

            try:
                from core.i18n import ai_lang_instruction
                lang_instr = ai_lang_instruction()
            except Exception:
                lang_instr = "Réponds en français. Sois concis et précis."
            prompt = f"Décris précisément tout ce que tu vois dans cette image. {lang_instr}"

            hint = _extract_area_hint(text)

            if not live:
                result = describe(prompt=prompt)
            else:
                match = camera_manager.find_by_area(hint) if hint else None
                if match is None and len(live) == 1:
                    match = live[0]
                if match is None and len(live) > 1:
                    names = ", ".join(ep.area_name or ep.friendly_name for ep in live)
                    return f"J'ai {len(live)} caméras disponibles : {names}. Laquelle souhaitez-vous ?"
                if match is None:
                    result = describe(prompt=prompt)
                else:
                    print(f"[Telegram] Vision → {match.entity_id} ({match.area_name})")
                    snap = camera_manager.capture_snapshot(match.entity_id)
                    if not snap.success:
                        return f"Je ne peux pas accéder à la caméra {match.area_name or match.friendly_name}."
                    with open(snap.path, "rb") as f:
                        jpg = f.read()
                    result = describe_from_bytes(jpg, prompt=prompt)

            return result.get("description") or "Je ne peux pas accéder à la caméra."

        except Exception as e:
            print(f"[Telegram] Vision error: {e}")
            return "Erreur lors de l'accès à la caméra."

    def _call_with_tools(self, text: str, conversation_messages: list) -> str:
        """Route through Ollama tool-calling, like voice_assistant._handle_function_call."""
        try:
            resp = requests.post(
                f"{OLLAMA_URL}/chat",
                json={
                    "model": RESPONDER_MODEL,
                    "messages": [
                        {
                            "role": "system",
                            "content": (
                                "You are a function dispatcher. You MUST call one of the available tools. "
                                "NEVER respond with plain text. "
                                "For greetings or conversational questions: call passthrough."
                            ),
                        },
                        {"role": "user", "content": text},
                    ],
                    "tools": FUNCTIONS,
                    "stream": False,
                    "think": False,
                    "keep_alive": "5m",
                },
                timeout=150,
            )
            resp.raise_for_status()
            tool_calls = resp.json().get("message", {}).get("tool_calls", [])
        except Exception as e:
            print(f"[Telegram] Tool-call failed: {e}")
            return self._call_llm(conversation_messages)

        if not tool_calls:
            return self._call_llm(conversation_messages)

        call = tool_calls[0]
        func_name = call["function"]["name"]
        params = call["function"].get("arguments", {})
        print(f"[Telegram] Tool call: {func_name}({params})")

        if func_name == "passthrough":
            return self._call_llm(conversation_messages)

        result = function_executor.execute(func_name, params)
        success = result.get("success", False)
        result_msg = result.get("message", "")

        # Inject result context into the last user message so Qwen can confirm naturally
        followup = list(conversation_messages)
        hint = f"[Résultat: {'succès' if success else 'échec'}. {result_msg}]"
        followup[-1] = {"role": "user", "content": f"{text}\n{hint}\nRéponds en français de façon naturelle et concise."}
        return self._call_llm(followup)

    def _call_llm(self, messages: list) -> str:
        payload = {
            "model": RESPONDER_MODEL,
            "messages": messages,
            "stream": False,
            "think": False,
            "keep_alive": "5m",
        }
        try:
            r = requests.post(
                f"{OLLAMA_URL}/chat",
                json=payload,
                timeout=150,
            )
            r.raise_for_status()
            return r.json().get("message", {}).get("content", "").strip()
        except Exception as e:
            print(f"[Telegram] LLM error: {e}")
            return "❌ Erreur lors de la génération de la réponse."


# Global singleton
telegram_adapter = TelegramAdapter()
