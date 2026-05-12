"""
Semantic Router — keyword-overlap pre-classifier (no ML, no loky, no semaphores).

Routes user prompts in <1ms using word-overlap scoring against predefined
utterances. Same interface as the previous ML-based router, drop-in replacement.

Routes:
  qwen_basic      → simple chat, greetings, quick facts  → Qwen (no thinking)
  qwen_thinking   → complex reasoning, coding, analysis  → Qwen (thinking)
  function_gemma  → actions (lights, timer, calendar...) → Function Gemma
  cad_generation  → 3D model creation / iteration        → CAD Agent
  print_control   → printer status / print job control   → Printer Agent
  vision          → webcam / image analysis              → Vision pipeline
"""

import re

VALID_ROUTES = {
    "qwen_basic", "qwen_thinking", "function_gemma",
    "cad_generation", "print_control", "vision",
}

# ── Utterances per route ───────────────────────────────────────────────────────
# Listed from most-specific to least-specific within each route.
# The scorer sums word-overlap hits; highest score wins.

_ROUTES: dict[str, list[str]] = {
    "vision": [
        "regarde", "que vois tu", "que vois-tu", "qu'est-ce que tu vois",
        "décris ce que tu vois", "regarde autour", "observe",
        "prends une photo", "capture une image", "montre ce que tu vois",
        "analyse l'image", "décris la scène", "tu vois quoi",
        "dis-moi ce que tu vois", "regarde ce qu'il y a",
        "utilise la caméra", "webcam", "caméra",
        "what do you see", "look around", "describe what you see",
        "take a picture", "capture a frame", "look at this",
        "what's in front of you", "describe the scene",
        "use the camera", "show me what you see", "camera",
        "scan the room", "look at the room",
    ],

    "cad_generation": [
        "crée un modèle 3d", "génère un fichier stl", "dessine une pièce",
        "modélise un boîtier", "crée une pièce pour", "conception 3d",
        "modifie le modèle", "change les dimensions", "crée un stl",
        "create a 3d model", "generate a 3d model", "design a 3d object",
        "make a cad model", "create an stl file", "generate stl",
        "design a box", "model a bracket", "create a gear",
        "make a housing for", "design a mount for", "create a case for",
        "parametric design", "build123d",
        "make me a 3d model", "i need a 3d model",
        "modify the 3d model", "change the height of the model",
        "add a hole to the model", "update the design",
        "iterate on the model", "adjust the dimensions",
    ],

    "print_control": [
        "imprime le modèle", "lance l'impression", "statut de l'impression",
        "pause l'impression", "annule l'impression", "progression impression",
        "température buse", "température plateau", "trouve les imprimantes",
        "connecte l'imprimante", "statut imprimante", "où en est l'impression",
        "imprimante 3d", "octoprint", "klipper", "moonraker",
        "print the model", "start printing", "send to printer",
        "print status", "how's the print going", "what is printing",
        "pause the print", "cancel the print", "resume the print",
        "printer temperature", "bed temperature", "hotend temperature",
        "discover printers", "find my printer", "connect to printer",
        "3d printer status", "is the printer done", "stop the printer",
    ],

    "function_gemma": [
        "allume la lumière", "éteins la lumière", "mets la lumière",
        "turn on the lights", "turn off the lights", "dim the lights",
        "minuterie", "timer", "set a timer", "set an alarm", "réveil",
        "ajoute une tâche", "add a task", "crée un événement",
        "create a calendar event", "schedule meeting",
        "cherche sur internet", "search the web", "look up",
        "quel temps fait-il", "weather in", "météo à",
        "qu'est-ce que j'ai aujourd'hui", "what tasks do I have",
        "what's on my schedule", "rappelle-moi",
        # shell_exec
        "exécute", "lance le script", "shell", "commande powershell",
        "liste les fichiers", "quelle version", "ping",
        "espace disque", "espace disponible", "disk space", "df",
        "utilisation cpu", "utilisation mémoire", "ram disponible",
        "processus en cours", "liste les processus", "process list",
        "quel est l'espace", "combien d'espace", "how much disk",
        "température cpu", "cpu temperature", "charge système",
        "ports ouverts", "connexions réseau", "netstat", "ipconfig", "ifconfig",
        "version de python", "version python", "version nodejs",
        "services windows", "services linux", "systemctl",
    ],

    "qwen_thinking": [
        "pourquoi", "explique", "comment fonctionne", "analyse",
        "compare", "différence entre", "pros and cons", "avantages inconvénients",
        "résume", "résumé", "synthèse", "implications",
        "écris un programme", "écris du code", "débogue", "debug",
        "write code", "write a function", "write a script",
        "explain", "how does", "what are the steps",
        "walk me through", "detailed explanation",
        "essay", "business plan", "inverse kinematics",
        "quantum", "machine learning", "algorithme",
        "implémente", "implement", "architecture",
    ],

    "qwen_basic": [
        "bonjour", "salut", "bonsoir", "merci", "ça va", "au revoir",
        "hi", "hello", "hey", "good morning", "good night",
        "thanks", "thank you", "bye", "see you", "ok", "sure",
        "what's up", "how are you", "what time is it",
        "quelle heure", "quelle date", "quel jour",
        "capitale", "capital of", "qui est", "who is",
        "blague", "joke", "say something funny",
    ],
}

# Pre-tokenize utterances: list of (route, frozenset_of_tokens)
_TOKEN_INDEX: list[tuple[str, frozenset]] = []

def _tokenize(text: str) -> frozenset:
    """Lowercase, strip punctuation, split on whitespace."""
    text = text.lower()
    text = re.sub(r"[^\w\s']", " ", text)
    return frozenset(w for w in text.split() if len(w) > 1)

def _build_index():
    global _TOKEN_INDEX
    _TOKEN_INDEX = []
    for route, utterances in _ROUTES.items():
        for utt in utterances:
            _TOKEN_INDEX.append((route, _tokenize(utt)))

_build_index()

# ── Scorer ─────────────────────────────────────────────────────────────────────

_THRESHOLD = 1  # Minimum overlapping tokens to count a hit

def get_route(prompt: str) -> str:
    """
    Route a prompt. Returns one of the VALID_ROUTES strings.
    Falls back to 'function_gemma' when no route scores above threshold.
    """
    if not prompt or not prompt.strip():
        return "qwen_basic"

    tokens = _tokenize(prompt)
    if not tokens:
        return "qwen_basic"

    scores: dict[str, float] = {r: 0.0 for r in VALID_ROUTES}

    for route, utt_tokens in _TOKEN_INDEX:
        overlap = len(tokens & utt_tokens)
        if overlap >= _THRESHOLD:
            # Normalise by utterance length to prefer specific matches
            scores[route] += overlap / max(len(utt_tokens), 1)

    best_route = max(scores, key=lambda r: scores[r])
    best_score = scores[best_route]

    if best_score < 0.3:
        return "function_gemma"

    return best_route


def warmup():
    """No-op — keyword router needs no warm-up."""
    print("[SemanticRouter] Ready (keyword router, no ML).")
