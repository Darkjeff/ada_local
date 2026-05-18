from PySide6.QtCore import QObject, Signal, QThread, QTimer
import json
import re

from config import RESPONDER_MODEL, OLLAMA_URL, MAX_HISTORY, FUNCTIONS
from core.llm import http_session
from core.tts import tts, SentenceBuffer
from core.history import history_manager
from core.model_manager import ensure_exclusive_qwen
from core.model_persistence import ensure_qwen_loaded, mark_qwen_used
from core.settings_store import settings as app_settings
from core.function_executor import executor as function_executor
from core.pattern_dispatcher import pattern_dispatcher
from core.n8n_executor import n8n_executor
from core.skill_manager import skill_manager
from core.memory_store import memory_store

# Functions that are actions (not passthrough)
ACTION_FUNCTIONS = {"control_light", "set_timer", "set_alarm", "create_calendar_event", "add_task", "web_search", "shell_exec"}


# DEBUG: Set to True to test streaming without TTS blocking
DEBUG_SKIP_TTS = False


class ChatWorker(QObject):
    """Background worker for LLM processing with Qt signals."""
    
    # Signals for thread-safe UI updates
    thought_chunk = Signal(str)
    response_chunk = Signal(str)
    think_start = Signal(bool)  # Pass whether thinking is enabled
    think_end = Signal()
    simple_response = Signal(str)
    error = Signal(str)
    status = Signal(str)
    done = Signal()
    ui_update = Signal()
    toast = Signal(str, bool)  # message, success
    set_timer_signal = Signal(int, str)  # seconds, label
    reload_alarms = Signal()  # trigger alarm list reload
    reload_calendar = Signal()  # trigger calendar refresh
    search_start = Signal(str)  # query
    search_end = Signal()
    navigate_to_cad = Signal(str)  # prompt to send to CAD tab
    
    def __init__(self, user_text: str, messages: list, is_tts_enabled: bool, 
                 current_session_id: str, stop_event):
        super().__init__()
        self.user_text = user_text
        self.messages = messages
        self.is_tts_enabled = is_tts_enabled
        self.current_session_id = current_session_id
        self.stop_event = stop_event
        self.full_response = ""
        
    def process(self):
        """Background processing method."""
        try:
            from core.semantic_router import get_route
            self.status.emit("Routing...")
            route = get_route(self.user_text)

            if route == "qwen_basic":
                self._stream_qwen_response(False)
            elif route == "qwen_thinking":
                self._stream_qwen_response(True)
            elif route == "function_gemma":
                self._handle_function_gemma()
            elif route == "youtube":
                self._handle_youtube()
            elif route == "vision":
                self._stream_qwen_response(False)
            elif route == "cad_generation":
                self._handle_cad_generation()
            else:
                self._stream_qwen_response(False)

        except Exception as e:
            self.error.emit(str(e))

        finally:
            self.done.emit()

    def _handle_cad_generation(self):
        """Route CAD requests to the CAD tab and confirm in chat."""
        # Extract the model description (strip known trigger words)
        import re
        desc = re.sub(
            r"(?i)(crée?|génère?|dessine?|modélise?|make|create|generate|design|build)\s+(un|une|a|an)?\s*"
            r"(modèle?|model|3d|stl|cad|pièce?|piece|objet?|object)?\s*",
            "", self.user_text
        ).strip() or self.user_text

        self.navigate_to_cad.emit(desc)
        self.simple_response.emit(
            f"Je génère le modèle 3D : **{desc}**\n"
            "Allez dans l'onglet **CAD Agent** pour voir la progression et le résultat."
        )

    def _handle_youtube(self):
        """
        Full YouTube summarization pipeline:
          1. Ingest (extract → retrieve → validate → chunk) — no LLM
          2. Map  — summarize each chunk individually
          3. Reduce — stream final structured synthesis to UI

        The LLM is NEVER called if transcript retrieval or validation fails.
        The raw transcript is NEVER added to the persistent chat history.
        """
        from core.youtube_transcript import run_pipeline

        # ── Step 1: Ingestion ────────────────────────────────────────────────
        self.status.emit("Récupération du transcript...")
        pipeline = run_pipeline(self.user_text)

        if not pipeline.success:
            self.simple_response.emit(pipeline.error)
            return

        meta = pipeline.metadata()
        lang = meta["language"]
        chunks_n = meta["chunks"]
        confidence_pct = f"{meta['confidence']:.0%}"

        import re as _re
        question = _re.sub(r"https?://\S+", "", self.user_text).strip()
        if not question:
            question = "Résume cette vidéo en français de façon structurée."

        model = app_settings.get("models.chat", RESPONDER_MODEL)
        ollama_url = app_settings.get("ollama_url", OLLAMA_URL)
        base = ollama_url.rstrip("/")
        if base.endswith("/api"):
            base = base[:-4]
        generate_url = f"{base}/api/generate"
        chat_url = f"{base}/api/chat"

        ensure_qwen_loaded()
        mark_qwen_used()
        ensure_exclusive_qwen(model)

        # ── Step 2: Map — summarize each chunk (non-streaming) ───────────────
        if chunks_n == 1:
            chunk_summaries = pipeline.chunks[:]
        else:
            chunk_summaries = []
            for i, chunk in enumerate(pipeline.chunks, 1):
                if self.stop_event.is_set():
                    return
                self.status.emit(f"Analyse du segment {i}/{chunks_n}...")
                summary = self._yt_summarize_chunk(
                    generate_url, model, chunk, i, chunks_n, lang
                )
                chunk_summaries.append(summary if summary else chunk[:600])

        if not chunk_summaries:
            self.simple_response.emit(
                "Impossible de récupérer une transcription exploitable pour cette vidéo."
            )
            return

        # ── Step 3: Reduce — build combined context, stream final answer ─────
        self.status.emit("Synthèse en cours...")

        if len(chunk_summaries) == 1:
            combined = chunk_summaries[0]
        else:
            combined = "\n\n".join(
                f"[Segment {i + 1}/{chunks_n}]\n{s}"
                for i, s in enumerate(chunk_summaries)
            )

        synthesis_system = (
            "Tu es un assistant d'analyse de vidéos YouTube. "
            "Tu analyses UNIQUEMENT le transcript fourni dans le message utilisateur. "
            "Tu n'inventes rien et tu ne complètes pas avec tes propres connaissances. "
            "Si une information ne figure pas dans le transcript, tu l'ignores. "
            "Réponds en français avec des titres en gras (**Titre**)."
        )

        synthesis_user = (
            f"[TRANSCRIPT YouTube — langue: {lang}, {chunks_n} segment(s), "
            f"confiance: {confidence_pct}]\n\n"
            f"{combined}\n\n"
            f"Question: {question}\n\n"
            "Fournis une analyse structurée:\n"
            "- **Sujet principal** de la vidéo\n"
            "- **Points clés** (3 à 5 points)\n"
            "- **Conclusions** ou enseignements\n"
            "- **Insights actionnables** si pertinents\n\n"
            "Base-toi UNIQUEMENT sur le transcript ci-dessus."
        )

        synthesis_messages = [
            {"role": "system", "content": synthesis_system},
            {"role": "user", "content": synthesis_user},
        ]

        header = (
            f"📊 *Transcript · {lang} · {chunks_n} segment{'s' if chunks_n > 1 else ''} "
            f"· confiance {confidence_pct}*\n\n"
        )

        self.ui_update.emit()
        self.think_start.emit(False)
        self.response_chunk.emit(header)

        self._yt_stream_synthesis(synthesis_messages, model, chat_url)

        # Save original user message + final summary to history and semantic memory
        self.messages.append({"role": "user", "content": self.user_text})
        self.messages.append({"role": "assistant", "content": self.full_response})
        if self.current_session_id:
            history_manager.add_message(self.current_session_id, "user", self.user_text)
            history_manager.add_message(self.current_session_id, "assistant", self.full_response)
        sid = self.current_session_id or "default"
        memory_store.save(sid, "user", self.user_text)
        if self.full_response:
            memory_store.save(sid, "assistant", self.full_response)

    def _yt_summarize_chunk(
        self, url: str, model: str, chunk: str, idx: int, total: int, lang: str
    ) -> str:
        """Non-streaming chunk summary for the map step. Returns empty string on failure."""
        try:
            resp = http_session.post(
                url,
                json={
                    "model": model,
                    "system": (
                        "Tu résumes des segments de transcript YouTube. "
                        "Tu utilises UNIQUEMENT le texte fourni. "
                        "Tu n'inventes rien et tu ne complètes pas avec tes connaissances."
                    ),
                    "prompt": (
                        f"[Segment {idx}/{total} — langue: {lang}]\n\n{chunk}\n\n"
                        "Résume ce segment en 3 à 5 phrases clés. "
                        "Utilise uniquement le texte ci-dessus."
                    ),
                    "stream": False,
                    "think": False,
                    "options": {"num_predict": 400, "temperature": 0.1},
                },
                timeout=90,
            )
            resp.raise_for_status()
            return resp.json().get("response", "").strip()
        except Exception as e:
            print(f"[YouTube] Chunk {idx}/{total} summary error: {e}")
            return ""

    def _yt_stream_synthesis(self, messages: list, model: str, chat_url: str):
        """Stream the final synthesis to the UI without touching self.messages."""
        sentence_buffer = SentenceBuffer()
        self.full_response = ""

        try:
            with http_session.post(
                chat_url,
                json={
                    "model": model,
                    "messages": messages,
                    "stream": True,
                    "think": False,
                    "keep_alive": "5m",
                },
                stream=True,
                timeout=120,
            ) as r:
                r.raise_for_status()
                for line in r.iter_lines():
                    if self.stop_event.is_set():
                        break
                    if not line:
                        continue
                    try:
                        tok = json.loads(line.decode("utf-8"))
                        content = tok.get("message", {}).get("content", "")
                        if content:
                            self.full_response += content
                            self.response_chunk.emit(content)
                            if self.is_tts_enabled and not DEBUG_SKIP_TTS:
                                for s in sentence_buffer.add(content):
                                    tts.queue_sentence(s)
                    except Exception:
                        continue
        except Exception as e:
            self.response_chunk.emit(f"\n\n*Erreur de génération : {e}*")

        self.think_end.emit()

        if self.is_tts_enabled and not DEBUG_SKIP_TTS and not self.stop_event.is_set():
            rem = sentence_buffer.flush()
            if rem:
                tts.queue_sentence(rem)

    def _direct_shell_dispatch(self) -> bool:
        """
        Pattern-match common system queries and call shell_exec directly,
        bypassing the LLM tool-calling step for reliability.
        Returns True if dispatched, False if no pattern matched.
        """
        import re, sys
        text = self.user_text.lower()
        # normalise apostrophes
        text = re.sub(r"[^\w\s]", " ", text)

        is_linux = sys.platform != "win32"

        patterns = [
            # disk space
            (r"\b(espace|disque|disk|space|libre|free|df|drive|stockage)\b",
             "df -h" if is_linux else "Get-PSDrive | Where-Object {$_.Used -ne $null} | Select-Object Name,@{N='Used(GB)';E={[math]::Round($_.Used/1GB,1)}},@{N='Free(GB)';E={[math]::Round($_.Free/1GB,1)}}"),
            # RAM/memory
            (r"\b(ram|m[eé]moire|memory|free)\b",
             "free -h" if is_linux else "Get-CimInstance Win32_OperatingSystem | Select-Object @{N='Total(GB)';E={[math]::Round($_.TotalVisibleMemorySize/1MB,1)}},@{N='Free(GB)';E={[math]::Round($_.FreePhysicalMemory/1MB,1)}}"),
            # CPU usage
            (r"\b(cpu|processeur|processor|charge|load|utilisation)\b",
             "top -bn1 | head -15" if is_linux else "Get-Process | Sort-Object CPU -Descending | Select-Object -First 10 Name,CPU,WorkingSet"),
            # processes
            (r"\b(processus|process|ps|pid|tâche|task)\b",
             "ps aux --sort=-%cpu | head -20" if is_linux else "Get-Process | Sort-Object CPU -Descending | Select-Object -First 15 Name,Id,CPU"),
            # network
            (r"\b(r[eé]seau|network|ip|netstat|connexion|interface)\b",
             "ip addr show" if is_linux else "ipconfig"),
            # python version
            (r"\b(python|python3)\b.*\b(version|ver)\b",
             "python3 --version" if is_linux else "python --version"),
            # uptime
            (r"\buptime\b",
             "uptime" if is_linux else "(Get-Date) - (gcim Win32_OperatingSystem).LastBootUpTime"),
            # temperature
            (r"\b(temp[eé]rature|thermal|chaleur)\b",
             "cat /sys/class/thermal/thermal_zone*/temp 2>/dev/null | awk '{print $1/1000 \"°C\"}'" if is_linux else "Get-CimInstance MSAcpi_ThermalZoneTemperature -Namespace root/wmi 2>$null"),
        ]

        for pattern, command in patterns:
            if re.search(pattern, text):
                self.status.emit("Executing shell_exec...")
                result = function_executor.execute("shell_exec", {"command": command})
                self.toast.emit(result["message"][:120], result["success"])
                self._generate_response_with_context("shell_exec", result, False)
                return True
        return False

    def _handle_function_gemma(self):
        """
        Intent dispatch pipeline:
        1. PatternDispatcher  — deterministic regex, <1 ms, no LLM
        2. N8NExecutor        — POST to n8n webhook; falls back to FunctionExecutor
        3. LLM (qwen3)        — fallback for ambiguous prompts
        """
        self.status.emit("Dispatching...")

        # --- 1. PatternDispatcher fast path ---
        matched = pattern_dispatcher.match(self.user_text)
        if matched:
            action, params = matched
            self.status.emit(f"Executing {action}...")

            if action == "web-search":
                self.search_start.emit(params.get("query", ""))

            result = n8n_executor.call(action, params)

            if action == "web-search":
                self.search_end.emit()

            self.toast.emit(result["message"][:120], result["success"])

            # Emit Qt signals for side-effects that require UI updates
            func_name = action.replace("-", "_")   # e.g. "set-timer" → "set_timer"
            if action == "set-timer" and result["success"]:
                seconds = result.get("data", {}).get("seconds", 0) if result.get("data") else 0
                label   = result.get("data", {}).get("label", "Timer") if result.get("data") else "Timer"
                self.set_timer_signal.emit(seconds, label)
            elif action == "set-alarm" and result["success"]:
                self.reload_alarms.emit()
            elif action == "calendar-event" and result["success"]:
                self.reload_calendar.emit()

            self._generate_response_with_context(func_name, result, action == "web-search")
            return

        # --- 2. LLM tool-calling path (qwen3) ---
        ollama_url = app_settings.get("ollama_url", OLLAMA_URL)
        model = app_settings.get("models.chat", RESPONDER_MODEL)

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
                                "You are a smart home function dispatcher. "
                                "You MUST always call one of the available tools — NEVER respond with plain text.\n\n"
                                "Tool selection rules:\n"
                                "- control_light: for ANY request involving lights, lamps, LEDs, or room lighting "
                                "(French: lumière, lampe, éclairage, led, allume, éteins, désactive, coupe, baisse). "
                                "Use action='off' for off/éteins/désactive/coupe/arrête, "
                                "action='on' for on/allume/active/mets, "
                                "action='dim' for dim/baisse/réduis. "
                                "Set device_name to the room or device mentioned (e.g. 'bureau', 'salon', 'chambre'), "
                                "or 'all' if no specific device is mentioned.\n"
                                "- set_timer: for countdown timers (minuterie, timer, dans X minutes).\n"
                                "- shell_exec: for system commands — disk space (df -h), RAM (free -h), "
                                "CPU (top -bn1), processes (ps aux), network (ip addr), etc.\n"
                                "- web_search: for internet searches.\n"
                                "- passthrough: ONLY for greetings, chitchat, or questions needing no action.\n\n"
                                "Examples:\n"
                                "- 'éteins la lumière' → control_light(action='off', device_name='all')\n"
                                "- 'désactive l\\'éclairage du bureau' → control_light(action='off', device_name='bureau')\n"
                                "- 'allume les lumières du salon' → control_light(action='on', device_name='salon')\n"
                                "- 'baisse la lumière' → control_light(action='dim', device_name='all', brightness=30)\n"
                                "- 'coupe tout' → control_light(action='off', device_name='all')\n"
                                "- 'set a 5 minute timer' → set_timer(duration='5 minutes')\n"
                                "- 'espace disque' → shell_exec(command='df -h')"
                            ),
                        },
                        {"role": "user", "content": self.user_text},
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
            print(f"[FunctionGemma] Tool-call failed: {e}")
            self._stream_qwen_response(False)
            return

        if not tool_calls:
            self._stream_qwen_response(False)
            return

        call = tool_calls[0]
        func_name = call["function"]["name"]
        params    = call["function"].get("arguments", {})

        if func_name == "passthrough":
            self._stream_qwen_response(bool(params.get("thinking", False)))
            return

        self.status.emit(f"Executing {func_name}...")

        # Convert LLM func_name (underscores) to n8n action (hyphens)
        action = func_name.replace("_", "-")

        if func_name == "web_search":
            self.search_start.emit(params.get("query", ""))

        result = n8n_executor.call(action, params)

        if func_name == "web_search":
            self.search_end.emit()

        if func_name in ACTION_FUNCTIONS:
            self.toast.emit(result["message"], result["success"])

        if func_name == "set_timer" and result["success"]:
            seconds = result.get("data", {}).get("seconds", 0) if result.get("data") else 0
            label   = result.get("data", {}).get("label", "Timer") if result.get("data") else "Timer"
            self.set_timer_signal.emit(seconds, label)
        elif func_name == "set_alarm" and result["success"]:
            self.reload_alarms.emit()
        elif func_name == "create_calendar_event" and result["success"]:
            self.reload_calendar.emit()

        enable_thinking = (func_name == "web_search")
        self._generate_response_with_context(func_name, result, enable_thinking)
    
    def _generate_response_with_context(self, func_name: str, result: dict, enable_thinking: bool = False):
        """Generate a Qwen response with function result as context."""
        # Build system message with context
        if func_name == "get_system_info" and result.get("success"):
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
            
            context_msg = "SYSTEM CONTEXT:\n" + "\n".join(context_parts) if context_parts else ""
        else:
            # Action function result
            status = "succeeded" if result.get("success") else "failed"
            
            # Special handling for web_search to include full results
            if func_name == "web_search" and result.get("success") and result.get("data"):
                search_data = result.get("data", {})
                query = search_data.get("query", "")
                results = search_data.get("results", [])
                
                if results:
                    context_msg = f"SEARCH RESULTS for '{query}':\n\n"
                    for i, r in enumerate(results, 1):
                        title = r.get("title", "")
                        body = r.get("body", "")
                        url = r.get("url", "")
                        context_msg += f"{i}. {title}\n"
                        context_msg += f"   {body}\n"
                        context_msg += f"   URL: {url}\n\n"
                    context_msg += "Use the above search results to answer the user's question. Include relevant URLs in your response using markdown link format [text](url)."
                else:
                    context_msg = f"ACTION RESULT: {func_name} {status}. {result.get('message', '')}"
            elif func_name == "shell_exec":
                cmd = result.get("data", {}).get("command", "")
                output = result.get("message", "")
                if result.get("success"):
                    context_msg = (
                        f"SHELL COMMAND OUTPUT (command: `{cmd}`):\n{output}\n\n"
                        "Summarise this output naturally and concisely in French."
                    )
                else:
                    context_msg = f"SHELL COMMAND FAILED (command: `{cmd}`): {output}. Explain the error in French."
            else:
                context_msg = f"ACTION RESULT: {func_name} {status}. {result.get('message', '')}"
        
        # Prepare messages with context
        max_hist = app_settings.get("general.max_history", MAX_HISTORY)
        if len(self.messages) > max_hist:
            self.messages = [self.messages[0]] + self.messages[-(max_hist-1):]
        
        # Add context as system message and user's original question
        context_prompt = f"{context_msg}\n\nUser asked: {self.user_text}\n\nRespond naturally and concisely."
        self.messages.append({'role': 'user', 'content': context_prompt})
        
        self.ui_update.emit()
        self.status.emit("Generating response...")
        
        model = app_settings.get("models.chat", RESPONDER_MODEL)
        ensure_qwen_loaded()  # Use persistence manager
        mark_qwen_used()
        ensure_exclusive_qwen(model)
        ollama_url = app_settings.get("ollama_url", OLLAMA_URL)
        
        payload = {
            "model": model,
            "messages": self.messages,
            "stream": True,
            "think": enable_thinking,  # Enable thinking for web_search
            "keep_alive": "5m"  # Longer keep-alive for voice assistant
        }
        
        sentence_buffer = SentenceBuffer()
        self.full_response = ""
        self.think_start.emit(enable_thinking)
        
        with http_session.post(f"{ollama_url}/api/chat", json=payload, stream=True) as r:
            r.raise_for_status()
            
            for line in r.iter_lines():
                if self.stop_event.is_set():
                    break
                    
                if line:
                    try:
                        chunk = json.loads(line.decode('utf-8'))
                        msg = chunk.get('message', {})
                        
                        # Handle thinking chunks (for web_search)
                        if 'thinking' in msg and msg['thinking']:
                            thought = msg['thinking']
                            self.thought_chunk.emit(thought)
                        
                        if 'content' in msg and msg['content']:
                            content = msg['content']
                            self.full_response += content
                            self.response_chunk.emit(content)
                            
                            if self.is_tts_enabled and not DEBUG_SKIP_TTS:
                                sentences = sentence_buffer.add(content)
                                for s in sentences:
                                    tts.queue_sentence(s)
                    except:
                        continue
        
        self.think_end.emit()
        
        if self.is_tts_enabled and not DEBUG_SKIP_TTS and not self.stop_event.is_set():
            rem = sentence_buffer.flush()
            if rem:
                tts.queue_sentence(rem)
        
        self.messages.append({'role': 'assistant', 'content': self.full_response})
        
        if self.current_session_id:
            history_manager.add_message(self.current_session_id, "assistant", self.full_response)
    
    def _stream_qwen_response(self, enable_thinking: bool):
        """Stream a direct Qwen response (for thinking/nonthinking)."""
        max_hist = app_settings.get("general.max_history", MAX_HISTORY)
        if len(self.messages) > max_hist:
            self.messages = [self.messages[0]] + self.messages[-(max_hist-1):]
        
        self.messages.append({'role': 'user', 'content': self.user_text})

        self.ui_update.emit()
        self.status.emit("Generating...")

        model = app_settings.get("models.chat", RESPONDER_MODEL)
        ensure_qwen_loaded()  # Use persistence manager
        mark_qwen_used()
        ensure_exclusive_qwen(model)
        ollama_url = app_settings.get("ollama_url", OLLAMA_URL)

        # Inject skill context + semantic memories into system message
        messages_with_skill = skill_manager.inject(self.messages, self.user_text)
        mem_context = memory_store.build_context(
            self.user_text, current_session_id=self.current_session_id
        )
        if mem_context and messages_with_skill:
            messages_with_skill = list(messages_with_skill)
            messages_with_skill[0] = {
                "role": "system",
                "content": messages_with_skill[0]["content"] + "\n\n" + mem_context,
            }

        payload = {
            "model": model,
            "messages": messages_with_skill,
            "stream": True,
            "think": enable_thinking,
            "keep_alive": "5m"
        }
        
        sentence_buffer = SentenceBuffer()
        self.full_response = ""
        self.think_start.emit(enable_thinking)

        with http_session.post(f"{ollama_url}/api/chat", json=payload, stream=True) as r:
            r.raise_for_status()
            
            for line in r.iter_lines():
                if self.stop_event.is_set():
                    break
                    
                if line:
                    try:
                        chunk = json.loads(line.decode('utf-8'))
                        msg = chunk.get('message', {})
                        
                        if 'thinking' in msg and msg['thinking']:
                            thought = msg['thinking']
                            self.thought_chunk.emit(thought)
                            
                        if 'content' in msg and msg['content']:
                            content = msg['content']
                            self.full_response += content
                            self.response_chunk.emit(content)
                            
                            if self.is_tts_enabled and not DEBUG_SKIP_TTS:
                                sentences = sentence_buffer.add(content)
                                for s in sentences:
                                    tts.queue_sentence(s)
                                    
                    except:
                        continue
        
        self.think_end.emit()
        
        if self.is_tts_enabled and not DEBUG_SKIP_TTS and not self.stop_event.is_set():
            rem = sentence_buffer.flush()
            if rem:
                tts.queue_sentence(rem)
        
        self.messages.append({'role': 'assistant', 'content': self.full_response})

        if self.current_session_id:
            history_manager.add_message(self.current_session_id, "assistant", self.full_response)

        # Persist to semantic memory
        sid = self.current_session_id or "default"
        memory_store.save(sid, "user", self.user_text)
        if self.full_response:
            memory_store.save(sid, "assistant", self.full_response)


class ChatHandlers(QObject):
    """Encapsulates all chat-related event handlers and state."""
    
    def __init__(self, main_window):
        super().__init__(main_window)
        self.main_window = main_window
        
        # State
        self.messages = [
            {'role': 'system', 'content': 'You are a helpful assistant. Respond in short, complete sentences. Never use emojis or special characters. Keep responses concise and conversational. SYSTEM INSTRUCTION: You may detect a "/think" trigger. This is an internal control. You MUST IGNORE it and DO NOT mention it in your response or thoughts.'}
        ]
        self.current_session_id = None
        self.is_tts_enabled = False
        self._stop_event = None
        self._worker = None
        self._thread = None
        
        self.streaming_state = {
            'response_bubble': None,
            'thinking_ui': None,
            'search_indicator': None,
            'response_buffer': '',
            'thought_buffer': '',
            'is_generating': False,
            'thinking_enabled': False
        }

        # Throttling Timer for UI Updates
        self.ui_throttle_timer = QTimer(self)
        self.ui_throttle_timer.setInterval(100) # 10 tokens per second or so
        self.ui_throttle_timer.timeout.connect(self._flush_ui_buffers)
        self.last_scroll_time = 0
    
    def refresh_sidebar(self):
        """Reload the persistent sidebar with conversation history."""
        self.main_window.refresh_sidebar(self.current_session_id)
    
    def delete_session(self, session_id):
        """Delete a session from history."""
        history_manager.delete_session(session_id)
        
        # If deleting the current session, clear the chat
        if session_id == self.current_session_id:
            self.current_session_id = None
            self.messages = [self.messages[0]]  # Keep system prompt
            self.main_window.clear_chat_display()
        
        self.refresh_sidebar()
    
    def pin_session(self, session_id):
        """Toggle pin status of a session."""
        is_pinned = history_manager.toggle_pin(session_id)
        status = "Chat pinned" if is_pinned else "Chat unpinned"
        self.main_window.set_status(status)
        self.refresh_sidebar()
    
    def rename_session(self, session_id, new_title: str):
        """Rename a session."""
        history_manager.update_session_title(session_id, new_title)
        self.refresh_sidebar()

    def load_session(self, session_id):
        """Load a specific chat session."""
        self.current_session_id = session_id
        db_messages = history_manager.get_messages(session_id)
        
        # Reset message context (keep system prompt)
        self.messages = [self.messages[0]]
        self.main_window.clear_chat_display()
        
        for msg in db_messages:
            role = msg['role']
            content = msg['content']
            
            # Reconstruct LLM context
            self.messages.append({'role': role, 'content': content})
            
            # Reconstruct UI bubbles
            self.main_window.add_message_bubble(role, content)
        
        self.refresh_sidebar()  # Update highlight

    def init_new_session(self, first_message):
        """Create a new session in DB."""
        title = first_message[:30] + "..." if len(first_message) > 30 else first_message
        self.current_session_id = history_manager.create_session(title=title)
        return self.current_session_id
    
    def _on_think_start(self, thinking_enabled: bool):
        """Called when generation starts, with thinking mode flag."""
        self.streaming_state['thinking_enabled'] = thinking_enabled
        if thinking_enabled and self.streaming_state['thinking_ui']:
            self.streaming_state['thinking_ui'].setVisible(True)
        self.ui_throttle_timer.start()

    def _on_thought_chunk(self, text):
        self.streaming_state['thought_buffer'] += text

    def _on_response_chunk(self, text):
        self.streaming_state['response_buffer'] += text
            
    def _flush_ui_buffers(self):
        """Flush accumulated text to the UI components."""
        updated = False
        
        # Update Thinking UI
        if self.streaming_state['thought_buffer'] and self.streaming_state['thinking_ui']:
            self.streaming_state['thinking_ui'].add_text(self.streaming_state['thought_buffer'])
            self.streaming_state['thought_buffer'] = ''
            updated = True
            
        # Update Response Bubble
        if self.streaming_state['response_buffer'] and self.streaming_state['response_bubble']:
            self.streaming_state['response_bubble'].append_text(self.streaming_state['response_buffer'])
            self.streaming_state['response_buffer'] = ''
            updated = True
            
        if updated:
            self.main_window.scroll_to_bottom()

    def _on_think_end(self):
        # Final flush
        self._flush_ui_buffers()
        # Only mark complete if thinking was enabled
        if self.streaming_state.get('thinking_enabled') and self.streaming_state['thinking_ui']:
            self.streaming_state['thinking_ui'].complete()
                
    def _on_simple_response(self, text):
        self.main_window.add_message_bubble("assistant", text)
        
        # Save simple response to history
        if self.current_session_id:
            history_manager.add_message(self.current_session_id, "assistant", text)
    
    def _on_toast(self, message: str, success: bool):
        """Show toast notification for function execution result."""
        from gui.components.toast import ToastNotification
        ToastNotification.show_toast(self.main_window, message, success)
    
    def _on_set_timer(self, seconds: int, label: str):
        """Update timer GUI when set via voice command."""
        try:
            # Access timer component via planner lazy tab
            if hasattr(self.main_window, 'planner_lazy') and self.main_window.planner_lazy.actual_widget:
                planner = self.main_window.planner_lazy.actual_widget
                if hasattr(planner, 'timer_component'):
                    planner.timer_component.set_and_start(seconds, label)
        except Exception as e:
            print(f"[Handlers] Timer update failed: {e}")
    
    def _on_reload_alarms(self):
        """Reload alarms GUI when added via voice command."""
        try:
            # Access alarm component via planner lazy tab
            if hasattr(self.main_window, 'planner_lazy') and self.main_window.planner_lazy.actual_widget:
                planner = self.main_window.planner_lazy.actual_widget
                if hasattr(planner, 'alarm_component'):
                    planner.alarm_component.reload()
        except Exception as e:
            print(f"[Handlers] Alarm reload failed: {e}")

    def _on_reload_calendar(self):
        """Reload calendar GUI when event added via voice command."""
        try:
            # Access schedule component via planner lazy tab
            if hasattr(self.main_window, 'planner_lazy') and self.main_window.planner_lazy.actual_widget:
                planner = self.main_window.planner_lazy.actual_widget
                if hasattr(planner, 'schedule_component'):
                    planner.schedule_component.refresh_events()
        except Exception as e:
            print(f"[Handlers] Calendar reload failed: {e}")
    
    def _on_search_start(self, query: str):
        """Called when web search starts."""
        if self.streaming_state['search_indicator']:
            self.streaming_state['search_indicator'].add_query(query)
            self.streaming_state['search_indicator'].setVisible(True)
    
    def _on_search_end(self):
        """Called when web search completes."""
        if self.streaming_state['search_indicator']:
            self.streaming_state['search_indicator'].complete()
            
    def _on_navigate_to_cad(self, prompt: str):
        """Switch to CAD tab and start generation with the given prompt."""
        win = self.main_window
        # Ensure the CAD lazy tab is initialized
        if hasattr(win, "cad_lazy"):
            cad_tab = win.cad_lazy.initialize()
            win.switchTo(win.cad_lazy)
            if hasattr(cad_tab, "start_generation"):
                cad_tab.start_generation(prompt)

    def _on_error(self, text):
        self.main_window.add_message_bubble("system", f"Error: {text}", is_thinking=True)
            
    def _on_status(self, text):
        self.main_window.set_status(text)

    def _on_done(self):
        self.ui_throttle_timer.stop()
        self._flush_ui_buffers() # Final final flush
        self._end_generation_state()
    
    def _start_generation_state(self):
        """Switch UI to generating mode."""
        self.streaming_state['is_generating'] = True
        self.main_window.set_generating_state(True)

    def _end_generation_state(self):
        """Switch UI back to idle mode."""
        self.streaming_state['is_generating'] = False
        self.main_window.set_generating_state(False)

    def stop_generation(self):
        """Stop current generation."""
        tts.stop()
        if self.streaming_state['is_generating'] and self._stop_event:
            self._stop_event.set()
            self.main_window.set_status("Stopping...")
            self.ui_throttle_timer.stop()

    def send_message(self, text: str):
        """Handle sending a new message."""
        tts.stop()  # Interrupt previous speech
        text = text.strip()
        if not text:
            return
        
        self.main_window.clear_input()

        # Add User Message UI
        self.main_window.add_message_bubble("user", text)
        
        # Start new session if needed
        if not self.current_session_id:
            self.init_new_session(text)
            self.refresh_sidebar()

        # Save to DB
        history_manager.add_message(self.current_session_id, "user", text)
        
        self._start_generation_state()
        
        # Create stop event
        import threading
        self._stop_event = threading.Event()
        
        # Create streaming UI containers
        from gui.components import MessageBubble, ThinkingExpander, SearchIndicator
        
        thinking_ui = ThinkingExpander()
        search_indicator = SearchIndicator()
        response_bubble = MessageBubble("assistant", "")
        
        self.streaming_state['thinking_ui'] = thinking_ui
        self.streaming_state['search_indicator'] = search_indicator
        self.streaming_state['response_bubble'] = response_bubble
        self.streaming_state['response_buffer'] = ''
        self.streaming_state['thought_buffer'] = ''
        self.streaming_state['thinking_enabled'] = False  # Will be set by think_start signal
        
        # Hide indicators initially - will be shown only if their respective modes are enabled
        thinking_ui.setVisible(False)
        search_indicator.setVisible(False)
        
        # Add to UI
        self.main_window.add_streaming_widgets(thinking_ui, search_indicator, response_bubble)

        # Start background worker
        self._thread = QThread(self)
        self._worker = ChatWorker(
            text, self.messages.copy(), self.is_tts_enabled,
            self.current_session_id, self._stop_event
        )
        self._worker.moveToThread(self._thread)
        
        # Connect signals
        self._thread.started.connect(self._worker.process)
        self._worker.think_start.connect(self._on_think_start)
        self._worker.thought_chunk.connect(self._on_thought_chunk)
        self._worker.response_chunk.connect(self._on_response_chunk)
        self._worker.think_end.connect(self._on_think_end)
        self._worker.simple_response.connect(self._on_simple_response)
        self._worker.error.connect(self._on_error)
        self._worker.status.connect(self._on_status)
        self._worker.toast.connect(self._on_toast)
        self._worker.set_timer_signal.connect(self._on_set_timer)
        self._worker.reload_alarms.connect(self._on_reload_alarms)
        self._worker.reload_calendar.connect(self._on_reload_calendar)
        self._worker.search_start.connect(self._on_search_start)
        self._worker.search_end.connect(self._on_search_end)
        self._worker.navigate_to_cad.connect(self._on_navigate_to_cad)
        self._worker.done.connect(self._on_done)
        self._worker.done.connect(self._thread.quit)
        self._worker.done.connect(self._worker.deleteLater)
        self._thread.finished.connect(self._thread.deleteLater)
        
        # Update messages reference
        self._worker.messages = self.messages
        
        self._thread.start()

    def clear_chat(self):
        """Start a fresh chat (reset session)."""
        self.current_session_id = None
        self.messages = [self.messages[0]]
        self.main_window.clear_chat_display()
        self.refresh_sidebar()

    def toggle_tts(self, enabled: bool):
        """Toggle TTS on/off."""
        self.is_tts_enabled = enabled
        tts.toggle(enabled)
        self.main_window.set_status("TTS Active" if enabled else "TTS Muted")
