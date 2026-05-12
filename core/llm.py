"""
LLM interaction and function execution.
"""

import requests
import threading

from config import (
    RESPONDER_MODEL, OLLAMA_URL, LOCAL_ROUTER_PATH,
    GRAY, RESET
)

# Persistent Session for faster HTTP
http_session = requests.Session()

# Global Router Instance
router = None


def is_router_loaded():
    """Check if the local router model is loaded in memory."""
    return router is not None


def should_bypass_router(text):
    """Return True if text definitely doesn't need routing."""
    # All queries now go through Function Gemma router
    # This function is kept for compatibility but always returns False
    return False


def route_query(user_input):
    """Route user query using local FunctionGemmaRouter. Lazy loads the router on first use."""
    global router
    
    # Lazy Initialization
    if not router:
        try:
            from core.router import FunctionGemmaRouter
            # We load without compilation for faster initialization and stability
            router = FunctionGemmaRouter(model_path=LOCAL_ROUTER_PATH, compile_model=False)
        except Exception as e:
            print(f"{GRAY}[Router Init Error: {e}]{RESET}")
            return "nonthinking", {"prompt": user_input}

    try:
        # Route using the fine-tuned model - returns (func_name, params)
        (func_name, params), elapsed = router.route_with_timing(user_input)
        return func_name, params
            
    except Exception as e:
        print(f"{GRAY}[Router Error: {e}]{RESET}")
        return "nonthinking", {"prompt": user_input}


def execute_function(name, params):
    """Execute function and return response string."""
    if name == "control_light":
        action = params.get("action", "toggle")
        room = params.get("room", "room")
        if action == "on":
            return f"💡 Turned on the {room} lights."
        elif action == "off":
            return f"💡 Turned off the {room} lights."
        elif action == "dim":
            return f"💡 Dimmed the {room} lights."
        else:
            return f"💡 {action.capitalize()} the {room} lights."
    
    elif name == "web_search":
        query = params.get("query", "")
        return f"🔍 Searching the web for: {query}"
    
    elif name == "set_timer":
        duration = params.get("duration", "")
        label = params.get("label", "Timer")
        return f"⏱️ Timer set for {duration}" + (f" ({label})" if label else "")
    
    elif name == "create_calendar_event":
        title = params.get("title", "Event")
        date = params.get("date", "")
        time = params.get("time", "")
        return f"📅 Created event: {title} on {date}" + (f" at {time}" if time else "")
    
    elif name == "read_calendar":
        date = params.get("date", "today")
        return f"📆 Checking calendar for {date}..."
    
    else:
        return f"Unknown function: {name}"


def preload_models():
    """Preload Ollama responder model and TTS into memory at startup."""
    # NOTE: The ML FunctionGemmaRouter is intentionally NOT loaded here.
    # The chat pipeline now uses core.semantic_router (keyword-based, no ML).
    # Loading transformers/tokenizers creates a loky process pool that leaks
    # 25 POSIX semaphores at shutdown and causes a segfault (core dump).
    from core.tts import tts

    print(f"{GRAY}[System] Preloading models...{RESET}")

    def load_responder():
        try:
            print(f"{GRAY}[System] Loading responder model ({RESPONDER_MODEL})...{RESET}")
            response = http_session.post(f"{OLLAMA_URL}/generate", json={
                "model": RESPONDER_MODEL,
                "prompt": "hi",
                "stream": False,
                "keep_alive": "30m",
                "options": {"num_predict": 1}
            }, timeout=120)
            if response.status_code == 200:
                print(f"{GRAY}[System] Responder model loaded successfully.{RESET}")
            else:
                print(f"{GRAY}[System] Responder model load returned status {response.status_code}{RESET}")
        except Exception as e:
            print(f"{GRAY}[System] Failed to preload responder: {e}{RESET}")

    def load_voice():
        print(f"{GRAY}[System] Loading voice model...{RESET}")
        tts.initialize()

    threads = [
        threading.Thread(target=load_responder),
        threading.Thread(target=load_voice),
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    print(f"{GRAY}[System] Models warm and ready.{RESET}")
