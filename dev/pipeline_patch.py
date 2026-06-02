"""
PATCH web/pipeline.py — Intégration plugins
Appliquer ces 4 modifications dans l'ordre.
"""

# ════════════════════════════════════════════════════════════════════════
# PATCH 1 — _system_prompt()
# Remplacer la fonction existante par celle-ci
# ════════════════════════════════════════════════════════════════════════

def _system_prompt(plugin_context_id: str | None = None) -> str:
    """System prompt de base, enrichi des capacités des plugins actifs."""
    base = (
        "Tu es ADA, une assistante IA locale. "
        "Réponds TOUJOURS en français. "
        "RÈGLE ABSOLUE : réponses courtes, 1 à 3 phrases max. "
        "Pas d'intro, pas de conclusion, pas de présentation de toi-même. "
        "Va directement à la réponse."
    )
    try:
        from core.plugin_registry import plugin_registry as _pr
        injection = _pr.combined_system_prompt_injection(context_id=plugin_context_id)
        if injection:
            base += f"\n\n### Capacités disponibles ###\n{injection}"
    except Exception:
        pass
    return base


# ════════════════════════════════════════════════════════════════════════
# PATCH 2 — _call_with_tools()
# Remplacer la fonction existante entièrement
# ════════════════════════════════════════════════════════════════════════

async def _call_with_tools(
    text: str,
    conversation_messages: list[dict],
    plugin_context_id: str | None = None,
) -> str:
    """
    Tool-calling avec fonctions natives + fonctions des plugins actifs.
    Pipeline : LLM → plugin_registry.dispatch_action() → n8n_executor → function_executor.
    Les actions x_confirm_required retournent un token __confirm__ au lieu d'exécuter.
    """
    import json
    import httpx
    from config import FUNCTIONS
    from core.plugin_registry import plugin_registry as _pr
    from core.n8n_executor import n8n_executor

    # Fonctions effectives = natives + plugins actifs
    plugin_functions  = _pr.combined_function_definitions()
    effective_functions = FUNCTIONS + plugin_functions

    # System prompt dispatcher incluant les capacités plugins
    plugin_sys = _pr.combined_system_prompt_injection(context_id=plugin_context_id)
    dispatcher_system = (
        "You are a function dispatcher. You MUST call one of the available tools. "
        "NEVER respond with plain text. "
        "For greetings or conversational questions: call passthrough.\n\n"
        "Tool selection rules:\n"
        "- control_light: ANY light/lamp/room lighting request\n"
        "- set_timer: countdown timers\n"
        "- shell_exec: system commands\n"
        "- web_search: internet searches\n"
        "- passthrough: ONLY for greetings, chitchat, or questions needing no action."
    )
    if plugin_sys:
        dispatcher_system += f"\n\nActive plugin capabilities:\n{plugin_sys}"

    # ── Appel LLM tool-calling ────────────────────────────────────────────────
    try:
        async with httpx.AsyncClient(timeout=150.0) as client:
            r = await client.post(
                _chat_url(),
                json={
                    "model":      _chat_model(),
                    "messages":   [
                        {"role": "system", "content": dispatcher_system},
                        {"role": "user",   "content": text},
                    ],
                    "tools":      effective_functions,
                    "stream":     False,
                    "think":      False,
                    "keep_alive": "5m",
                },
            )
            r.raise_for_status()
            tool_calls = r.json().get("message", {}).get("tool_calls", [])
    except Exception:
        return await _call_llm(conversation_messages, thinking=False)

    if not tool_calls:
        return await _call_llm(conversation_messages, thinking=False)

    call      = tool_calls[0]
    func_name = call.get("function", {}).get("name", "")
    params    = call.get("function", {}).get("arguments", {}) or {}

    # Passthrough → réponse conversationnelle directe
    if func_name == "passthrough":
        thinking = bool(params.get("thinking", False))
        return await _call_llm(conversation_messages, thinking=thinking)

    # ── Vérification confirmation requise ─────────────────────────────────────
    func_def = next(
        (f for f in effective_functions if f["function"]["name"] == func_name),
        None,
    )
    if func_def and func_def["function"].get("x_confirm_required"):
        confirm_msg = func_def["function"].get(
            "x_confirm_message", f"Confirmer {func_name} ?"
        )
        # Token spécial intercepté par process_message → frontend
        return f"__confirm__{func_name}|{confirm_msg}|{json.dumps(params)}"

    # ── Dispatch : plugin → n8n → function_executor ───────────────────────────
    plugin_result = _pr.dispatch_action(func_name, params)
    if plugin_result is not None:
        result = plugin_result
    else:
        action = func_name.replace("_", "-")
        result = n8n_executor.call(action, params)

    success    = result.get("success", False)
    result_msg = result.get("message", "")

    # Réponse naturelle LLM avec résultat en contexte
    followup = list(conversation_messages)
    hint = f"[Résultat: {'succès' if success else 'échec'}. {result_msg}]"
    followup[-1] = {
        "role":    "user",
        "content": (
            f"{text}\n{hint}\n"
            "Réponds en français de façon naturelle et concise."
        ),
    }
    return await _call_llm(followup, thinking=False)


# ════════════════════════════════════════════════════════════════════════
# PATCH 3 — process_message() — signature
# Remplacer la signature existante
# ════════════════════════════════════════════════════════════════════════

# AVANT :
# async def process_message(
#     message: str,
#     history: list[dict],
#     company_context: str | None = None,
# ) -> AsyncGenerator[str, None]:

# APRÈS :
async def process_message(
    message: str,
    history: list[dict],
    company_context: str | None = None,   # compat existant — filtre infra
    plugin_context:  str | None = None,   # NOUVEAU : univers actif ("home","opent"…)
    context_id:      str | None = None,   # NOUVEAU : sous-contexte (company_id, etc.)
) -> ...:  # AsyncGenerator[str, None]
    pass


# ════════════════════════════════════════════════════════════════════════
# PATCH 4 — process_message() — corps
# Dans le corps de process_message(), appliquer ces remplacements ciblés
# ════════════════════════════════════════════════════════════════════════

# ── 4a : résoudre le context_id effectif (au début de process_message, après user_text) ──
# Ajouter après : user_text = (message or "").strip()

_effective_ctx = context_id or company_context or None

# ── 4b : system prompt dynamique ──
# Remplacer :
#   messages: list[dict] = [{"role": "system", "content": _system_prompt()}]
# Par :
#   messages: list[dict] = [{"role": "system", "content": _system_prompt(_effective_ctx)}]

# ── 4c : appel _call_with_tools avec context ──
# Remplacer :
#   response = await _call_with_tools(user_text, messages)
# Par :
#   response = await _call_with_tools(user_text, messages, plugin_context_id=_effective_ctx)

# ── 4d : gestion token confirmation après _call_with_tools, avant yield ──
# Insérer ce bloc AVANT le yield response :

"""
    if response and response.startswith("__confirm__"):
        _, payload = response.split("__confirm__", 1)
        parts           = payload.split("|", 2)
        confirm_func    = parts[0] if len(parts) > 0 else ""
        confirm_message = parts[1] if len(parts) > 1 else "Confirmer ?"
        confirm_params  = parts[2] if len(parts) > 2 else "{}"
        yield json.dumps({
            "__type":  "confirm_required",
            "func":    confirm_func,
            "message": confirm_message,
            "params":  confirm_params,
        })
        return
"""

# ════════════════════════════════════════════════════════════════════════
# PATCH 5 — server.py — ChatRequest + /api/chat + router
# ════════════════════════════════════════════════════════════════════════

# ── 5a : ChatRequest étendu ──
# Remplacer :
# class ChatRequest(BaseModel):
#     message: str
#     history: list[dict] = []
#     company_context: str | None = None
#
# Par :
# class ChatRequest(BaseModel):
#     message:         str
#     history:         list[dict] = []
#     company_context: str | None = None   # compat existant
#     plugin_context:  str | None = None   # NOUVEAU
#     context_id:      str | None = None   # NOUVEAU

# ── 5b : appel process_message dans /api/chat ──
# Remplacer :
#   async for chunk in process_message(req.message, req.history, company_context=req.company_context):
# Par :
#   async for chunk in process_message(
#       req.message, req.history,
#       company_context=req.company_context,
#       plugin_context=req.plugin_context,
#       context_id=req.context_id,
#   ):

# ── 5c : branchement router_plugins ──
# Ajouter après les autres include_router dans server.py :
# from web.router_plugins import router as _plugins_router
# app.include_router(_plugins_router)
