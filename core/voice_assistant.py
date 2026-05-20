"""
Voice Assistant - Main orchestrator for Alexa-like voice interaction.
Manages: STT → Function Gemma → Qwen → TTS pipeline.
"""

import re
import threading
import json
import requests
from typing import Optional
from PySide6.QtCore import QObject, Signal

from config import (
    RESPONDER_MODEL, OLLAMA_URL, MAX_HISTORY, GRAY, RESET, CYAN, GREEN, WAKE_WORD,
    FUNCTIONS
)
from core.stt import STTListener
from core.llm import http_session
from core.model_persistence import ensure_qwen_loaded, mark_qwen_used, unload_qwen
from core.tts import tts, SentenceBuffer
from core.function_executor import executor as function_executor
from core.semantic_router import get_route as semantic_route
from core.skill_manager import skill_manager

_AREA_HINT_RE = re.compile(
    r"\b(?:au|dans\s+le|dans\s+la|dans\s+l[''']?|le|la|du|de\s+la|caméra)\s+(\w+(?:\s+\w+)?)",
    re.IGNORECASE,
)


def _extract_area_hint(text: str) -> str:
    """Extract room/area hint from a vision query. Returns '' if none found."""
    m = _AREA_HINT_RE.search(text)
    return m.group(1).strip() if m else ""


# Functions that are actions (not passthrough)
ACTION_FUNCTIONS = {
    "control_light", "set_timer", "set_alarm",
    "create_calendar_event", "add_task", "web_search"
}

# Semantic routes that bypass Function Gemma entirely
SEMANTIC_BYPASS = {"qwen_basic", "qwen_thinking"}


class VoiceAssistant(QObject):
    """Main voice assistant orchestrator."""
    
    # Signals for UI updates (optional)
    wake_word_detected = Signal()
    speech_recognized = Signal(str)
    processing_started = Signal()
    processing_finished = Signal()
    error_occurred = Signal(str)
    # GUI update signals
    timer_set = Signal(int, str)  # seconds, label
    alarm_added = Signal()
    calendar_updated = Signal()
    task_added = Signal()
    
    def __init__(self):
        super().__init__()
        self.stt_listener: Optional[STTListener] = None
        self.running = False
        self.messages = [
            {
                'role': 'system', 
                'content': 'You are a helpful assistant. Respond in short, complete sentences. Never use emojis or special characters. Keep responses concise and conversational.'
            }
        ]
        self.current_session_id = None
        
    def initialize(self) -> bool:
        """Initialize voice assistant components."""
        try:
            print(f"{CYAN}[VoiceAssistant] Initializing voice assistant components...{RESET}")
            # Initialize STT listener
            print(f"{CYAN}[VoiceAssistant] Creating STT listener...{RESET}")
            self.stt_listener = STTListener(
                wake_word_callback=self._on_wake_word,
                speech_callback=self._on_speech
            )
            print(f"{CYAN}[VoiceAssistant] ✓ STT listener created{RESET}")
            
            print(f"{CYAN}[VoiceAssistant] Initializing STT models...{RESET}")
            if not self.stt_listener.initialize():
                print(f"{GRAY}[VoiceAssistant] ✗ Failed to initialize STT.{RESET}")
                return False
            print(f"{CYAN}[VoiceAssistant] ✓ STT initialized{RESET}")
            
            # Ensure TTS is initialized
            if not tts.piper_exe:
                print(f"{CYAN}[VoiceAssistant] Initializing TTS...{RESET}")
                tts.initialize()
                print(f"{CYAN}[VoiceAssistant] ✓ TTS initialized{RESET}")
            
            print(f"{CYAN}[VoiceAssistant] ✓ Voice assistant initialized successfully{RESET}")
            return True
        except Exception as e:
            print(f"{GRAY}[VoiceAssistant] ✗ Initialization error: {e}{RESET}")
            import traceback
            traceback.print_exc()
            return False
    
    def start(self):
        """Start the voice assistant."""
        if self.running:
            return
        
        if not self.stt_listener:
            if not self.initialize():
                return
        
        self.running = True
        self.stt_listener.start()
        print(f"{CYAN}[VoiceAssistant] Voice assistant started. Say '{GREEN}{WAKE_WORD}{RESET}{CYAN}' to activate.{RESET}")
    
    def stop(self):
        """Stop the voice assistant."""
        if not self.running:
            return
        
        self.running = False
        if self.stt_listener:
            self.stt_listener.stop()
        print(f"{GRAY}[VoiceAssistant] Voice assistant stopped.{RESET}")
    
    def _on_wake_word(self):
        """Handle wake word detection."""
        print(f"{GREEN}[VoiceAssistant] ✓ Wake word callback received!{RESET}")
        print(f"{GREEN}[VoiceAssistant] Emitting wake_word_detected signal...{RESET}")
        self.wake_word_detected.emit()
        print(f"{GREEN}[VoiceAssistant] ✓ Signal emitted. Listening for speech...{RESET}")
    
    def _on_speech(self, text: str):
        """Handle recognized speech after wake word."""
        if not text.strip():
            return
        
        # Remove wake word from text if present
        text = text.lower().replace("ada", "").strip()
        if not text:
            return
        
        self.speech_recognized.emit(text)
        self.processing_started.emit()
        
        print(f"{CYAN}[VoiceAssistant] Processing: {text}{RESET}")
        
        # Process in background thread to avoid blocking
        thread = threading.Thread(
            target=self._process_query,
            args=(text,),
            daemon=True
        )
        thread.start()
    
    def _process_query(self, user_text: str):
        """Process user query through the pipeline."""
        try:
            # ── Step 1: Semantic Router (fast, ~5ms) ──────────────────
            semantic = semantic_route(user_text)

            print(f"{GRAY}[VoiceAssistant] Semantic: {semantic}{RESET}")

            # ── Step 2: Route based on semantic decision ───────────────

            if semantic == "qwen_basic":
                # Simple conversation → Qwen direct, no thinking
                self._stream_qwen_response(user_text, False)
                return

            if semantic == "qwen_thinking":
                # Complex reasoning → Qwen with thinking
                self._stream_qwen_response(user_text, True)
                return

            if semantic == "vision":
                print(f"{CYAN}[VoiceAssistant] → Vision{RESET}")
                self._handle_vision(user_text)
                return

            if semantic == "cad_generation":
                # CAD model generation → CAD Agent (future)
                print(f"{CYAN}[VoiceAssistant] → CAD Agent (not yet implemented){RESET}")
                self._stream_qwen_response(
                    f"L'utilisateur veut: {user_text}. Dis-lui que la génération 3D est en cours d'intégration.", False
                )
                return

            if semantic == "print_control":
                print(f"{CYAN}[VoiceAssistant] → Printer Agent{RESET}")
                self._handle_print_control(user_text)
                return

            # ── Step 3: function_gemma → Ollama tool-calling (no ML router) ──
            self._handle_function_call(user_text)

        except Exception as e:
            error_msg = f"Error processing query: {e}"
            print(f"{GRAY}[VoiceAssistant] {error_msg}{RESET}")
            self.error_occurred.emit(error_msg)
            self.processing_finished.emit()
    
    def _handle_function_call(self, user_text: str):
        """Dispatch via Ollama tool-calling — no ML router, no loky."""
        ollama_url = OLLAMA_URL
        model = RESPONDER_MODEL
        try:
            ensure_qwen_loaded()
            mark_qwen_used()
            resp = http_session.post(
                f"{ollama_url}/api/chat",
                json={
                    "model": model,
                    "messages": [
                        {
                            "role": "system",
                            "content": (
                                "You are a function dispatcher. You MUST call one of the available tools. "
                                "NEVER respond with plain text. "
                                "For system info (disk, RAM, CPU, processes, network): call shell_exec. "
                                "For greetings or conversational questions: call passthrough."
                            ),
                        },
                        {"role": "user", "content": user_text},
                    ],
                    "tools": FUNCTIONS,
                    "stream": False,
                    "think": False,
                },
                timeout=90,
            )
            resp.raise_for_status()
            msg = resp.json().get("message", {})
            tool_calls = msg.get("tool_calls", [])
        except Exception as e:
            print(f"{GRAY}[VoiceAssistant] Tool-call failed: {e}{RESET}")
            self._stream_qwen_response(user_text, False)
            return

        if not tool_calls:
            self._stream_qwen_response(user_text, False)
            return

        call = tool_calls[0]
        func_name = call["function"]["name"]
        params = call["function"].get("arguments", {})
        print(f"{GRAY}[VoiceAssistant] Tool call: {func_name}{RESET}")

        if func_name == "passthrough":
            self._stream_qwen_response(user_text, bool(params.get("thinking", False)))
            return

        result = function_executor.execute(func_name, params)

        if func_name == "set_timer" and result.get("success"):
            seconds = result.get("data", {}).get("seconds", 0)
            label = result.get("data", {}).get("label", "Timer")
            self.timer_set.emit(seconds, label)
        elif func_name == "set_alarm" and result.get("success"):
            self.alarm_added.emit()
        elif func_name == "create_calendar_event" and result.get("success"):
            self.calendar_updated.emit()
        elif func_name == "add_task" and result.get("success"):
            self.task_added.emit()

        self._generate_response_with_context(func_name, result, user_text)

    def _handle_vision(self, user_text: str):
        """Capture from best HA camera (or local webcam) and describe in French."""
        try:
            from core.camera_manager import camera_manager
            from core.vision import describe, describe_from_bytes
            from core.tts import tts, SentenceBuffer

            if not camera_manager.list_endpoints():
                camera_manager.refresh()

            endpoints = camera_manager.list_endpoints()
            live = [ep for ep in endpoints if ep.state != "unavailable"]

            prompt = user_text or "Décris ce que tu vois en détail en français."
            hint = _extract_area_hint(user_text)

            if not live:
                result = describe(prompt=prompt)
            else:
                match = camera_manager.find_by_area(hint) if hint else None

                if match is None and len(live) == 1:
                    match = live[0]

                if match is None and len(live) > 1:
                    names = ", ".join(ep.area_name or ep.friendly_name for ep in live)
                    description = (
                        f"J'ai {len(live)} caméras disponibles : {names}. "
                        "Laquelle souhaitez-vous utiliser ?"
                    )
                    buf = SentenceBuffer()
                    for s in buf.add(description) + [buf.flush()]:
                        if s:
                            tts.queue_sentence(s)
                    return

                if match is None:
                    result = describe(prompt=prompt)
                else:
                    print(f"{GRAY}[VoiceAssistant] Vision → {match.entity_id} ({match.area_name}){RESET}")
                    snap = camera_manager.capture_snapshot(match.entity_id)
                    if not snap.success:
                        result = {
                            "success": False,
                            "description": f"Je ne peux pas accéder à la caméra {match.area_name or match.friendly_name}.",
                        }
                    else:
                        with open(snap.path, "rb") as f:
                            jpg = f.read()
                        result = describe_from_bytes(jpg, prompt=prompt)

            description = result.get("description") or "Je ne peux pas accéder à la caméra."
            buf = SentenceBuffer()
            for s in buf.add(description) + [buf.flush()]:
                if s:
                    tts.queue_sentence(s)

        except Exception as e:
            print(f"{GRAY}[VoiceAssistant] Vision error: {e}{RESET}")
        finally:
            self.processing_finished.emit()

    def _handle_print_control(self, user_text: str):
        """Route printer-related queries to PrinterAgent via FunctionExecutor."""
        text_lower = user_text.lower()

        # Determine action from user text
        if any(w in text_lower for w in ("pause", "mets en pause", "suspends")):
            result = function_executor.execute("control_printer", {"action": "pause"})
        elif any(w in text_lower for w in ("resume", "reprends", "continue", "redémarre")):
            result = function_executor.execute("control_printer", {"action": "resume"})
        elif any(w in text_lower for w in ("cancel", "annule", "stop", "arrête")):
            result = function_executor.execute("control_printer", {"action": "cancel"})
        else:
            # Default: status query
            result = function_executor.execute("get_print_status", {})

        self._generate_response_with_context("print_control", result, user_text)

    def _generate_response_with_context(self, func_name: str, result: dict, user_text: str, enable_thinking: bool = False):
        """Generate Qwen response with function execution context."""
        try:
            # Ensure Qwen is loaded
            if not ensure_qwen_loaded():
                print(f"{GRAY}[VoiceAssistant] Failed to load Qwen model.{RESET}")
                self.processing_finished.emit()
                return
            
            mark_qwen_used()
            
            # Build context message
            success = result.get("success", False)
            message = result.get("message", "")
            
            # Enhanced context for get_system_info
            if func_name == "get_system_info" and success:
                data = result.get("data", {})
                context_parts = []
                if data.get("timers"):
                    context_parts.append(f"Active timers: {data['timers']}")
                if data.get("alarms"):
                    context_parts.append(f"Alarms: {data['alarms']}")
                if data.get("calendar_today"):
                    context_parts.append(f"Today's events: {data['calendar_today']}")
                if data.get("tasks"):
                    pending = [t for t in data['tasks'] if not t.get('completed')]
                    context_parts.append(f"Pending tasks: {len(pending)} items")
                if data.get("smart_devices"):
                    on_devices = [d['name'] for d in data['smart_devices'] if d.get('is_on')]
                    context_parts.append(f"Devices on: {on_devices if on_devices else 'none'}")
                if data.get("weather"):
                    w = data['weather']
                    context_parts.append(f"Weather: {w.get('temp')}°F, {w.get('condition')}")
                if data.get("news"):
                    news_items = data['news']
                    if news_items:
                        news_titles = [item.get('title', '')[:50] for item in news_items[:3]]
                        context_parts.append(f"Top news: {', '.join(news_titles)}")
                context_msg = "SYSTEM CONTEXT:\n" + "\n".join(context_parts) if context_parts else "No system information available."
            else:
                context_msg = f"Function {func_name} executed. Success: {success}. Result: {message}"
            
            # Manage context window
            max_hist = MAX_HISTORY
            if len(self.messages) > max_hist:
                self.messages = [self.messages[0]] + self.messages[-(max_hist-1):]
            
            # Add context as user message
            context_prompt = f"{context_msg}\n\nUser asked: {user_text}\n\nRespond naturally and concisely."
            self.messages.append({'role': 'user', 'content': context_prompt})
            
            # Prepare payload
            payload = {
                "model": RESPONDER_MODEL,
                "messages": self.messages,
                "stream": True,
                "think": enable_thinking,
                "keep_alive": "5m"
            }
            
            sentence_buffer = SentenceBuffer()
            full_response = ""
            
            # Stream response
            with http_session.post(f"{OLLAMA_URL}/chat", json=payload, stream=True) as r:
                r.raise_for_status()
                
                for line in r.iter_lines():
                    if line:
                        try:
                            chunk = json.loads(line.decode('utf-8'))
                            msg = chunk.get('message', {})
                            
                            if 'content' in msg and msg['content']:
                                content = msg['content']
                                full_response += content
                                
                                # Queue for TTS
                                sentences = sentence_buffer.add(content)
                                for s in sentences:
                                    tts.queue_sentence(s)
                        except:
                            continue
            
            # Flush remaining
            rem = sentence_buffer.flush()
            if rem:
                tts.queue_sentence(rem)
            
            # Update messages
            self.messages.append({'role': 'assistant', 'content': full_response})
            
            mark_qwen_used()  # Update usage time
            
            print(f"{GREEN}[VoiceAssistant] Response generated.{RESET}")
            self.processing_finished.emit()
            
        except Exception as e:
            print(f"{GRAY}[VoiceAssistant] Error generating response: {e}{RESET}")
            self.processing_finished.emit()
    
    def _stream_qwen_response(self, user_text: str, enable_thinking: bool):
        """Stream direct Qwen response."""
        try:
            # Ensure Qwen is loaded
            if not ensure_qwen_loaded():
                print(f"{GRAY}[VoiceAssistant] Failed to load Qwen model.{RESET}")
                self.processing_finished.emit()
                return
            
            mark_qwen_used()
            
            # Manage context window
            max_hist = MAX_HISTORY
            if len(self.messages) > max_hist:
                self.messages = [self.messages[0]] + self.messages[-(max_hist-1):]
            
            self.messages.append({'role': 'user', 'content': user_text})

            # Inject matching skill (non-destructive copy)
            messages_with_skill = skill_manager.inject(self.messages, user_text)

            # Prepare payload
            payload = {
                "model": RESPONDER_MODEL,
                "messages": messages_with_skill,
                "stream": True,
                "think": enable_thinking,
                "keep_alive": "5m"
            }

            sentence_buffer = SentenceBuffer()
            full_response = ""
            
            # Stream response
            with http_session.post(f"{OLLAMA_URL}/chat", json=payload, stream=True) as r:
                r.raise_for_status()
                
                for line in r.iter_lines():
                    if line:
                        try:
                            chunk = json.loads(line.decode('utf-8'))
                            msg = chunk.get('message', {})
                            
                            if 'content' in msg and msg['content']:
                                content = msg['content']
                                full_response += content
                                
                                # Queue for TTS
                                sentences = sentence_buffer.add(content)
                                for s in sentences:
                                    tts.queue_sentence(s)
                        except:
                            continue
            
            # Flush remaining
            rem = sentence_buffer.flush()
            if rem:
                tts.queue_sentence(rem)
            
            # Update messages
            self.messages.append({'role': 'assistant', 'content': full_response})
            
            mark_qwen_used()  # Update usage time
            
            print(f"{GREEN}[VoiceAssistant] Response generated.{RESET}")
            self.processing_finished.emit()
            
        except Exception as e:
            print(f"{GRAY}[VoiceAssistant] Error streaming response: {e}{RESET}")
            self.processing_finished.emit()


# Global voice assistant instance
voice_assistant = VoiceAssistant()
