"""
Semantic Router — lightweight embedding-based pre-classifier.

Routes user prompts in ~5ms using vector similarity, BEFORE Function Gemma.
Avoids loading heavy models for simple conversations.

Routes:
  qwen_basic      → simple chat, greetings, quick facts  → Qwen (no thinking)
  qwen_thinking   → complex reasoning, coding, analysis  → Qwen (thinking)
  function_gemma  → actions (lights, timer, calendar...) → Function Gemma
  cad_generation  → 3D model creation / iteration        → CAD Agent
  print_control   → printer status / print job control   → Printer Agent
"""

import os
from pathlib import Path

VALID_ROUTES = {"qwen_basic", "qwen_thinking", "function_gemma", "cad_generation", "print_control"}

_router = None


def _build_encoder():
    """Try encoders in order: FastEmbed → HuggingFace → raises."""
    cache_dir = Path(__file__).resolve().parent.parent / "data" / "fastembed_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)

    try:
        from semantic_router.encoders import FastEmbedEncoder
        encoder = FastEmbedEncoder(cache_dir=str(cache_dir))
        print("[SemanticRouter] Using FastEmbedEncoder")
        return encoder
    except (ImportError, Exception) as e:
        print(f"[SemanticRouter] FastEmbed unavailable ({e}), trying HuggingFaceEncoder...")

    try:
        from semantic_router.encoders import HuggingFaceEncoder
        encoder = HuggingFaceEncoder()
        print("[SemanticRouter] Using HuggingFaceEncoder")
        return encoder
    except (ImportError, Exception) as e:
        raise RuntimeError(
            f"No encoder available. Install one: pip install 'semantic-router[fastembed]' "
            f"or pip install 'semantic-router' sentence-transformers"
        ) from e


def _build_router():
    try:
        from semantic_router import Route
        from semantic_router.routers import SemanticRouter
    except ImportError as e:
        raise ImportError(
            "semantic-router not installed. Run: pip install semantic-router"
        ) from e

    encoder = _build_encoder()

    qwen_basic = Route(
        name="qwen_basic",
        utterances=[
            "hi", "hello", "hey", "how are you", "good morning", "good night",
            "thanks", "thank you", "bye", "see you", "ok", "got it", "sure",
            "what's up", "nice to meet you", "how's it going",
            "what is the capital of France", "what is two plus two",
            "who wrote Romeo and Juliet", "what year did World War II end",
            "how many days in a week", "what is the largest ocean",
            "name the planets", "what is the speed of light",
            "tell me a joke", "say something funny", "what time is it",
            "what is today's date", "what's the weather like",
            "what is the capital of Japan", "who is the president",
            "bonjour", "merci", "bonsoir", "salut", "ça va",
            "quelle heure est-il", "quelle est la capitale de la France",
        ],
    )

    qwen_thinking = Route(
        name="qwen_thinking",
        utterances=[
            "why does this happen", "explain the reasoning behind it",
            "what are the steps to solve this", "compare X and Y",
            "analyze this situation", "what are the pros and cons",
            "how would you approach this problem", "walk me through the logic",
            "give me a detailed explanation", "what are the implications",
            "summarize the main points", "how do these relate",
            "write a Python function", "write code to", "debug this code",
            "what's the difference between", "explain quantum computing",
            "how does machine learning work", "write an essay about",
            "create a business plan", "explain inverse kinematics",
            "explique-moi pourquoi", "comment fonctionne", "analyse cette situation",
            "écris un programme", "quelle est la différence entre",
            "résume les points principaux", "comment résoudre ce problème",
        ],
    )

    function_gemma = Route(
        name="function_gemma",
        utterances=[
            "turn on the lights", "turn off the lights", "dim the lights",
            "allume la lumière", "éteins la lumière", "mets la lumière en bleu",
            "set a timer for 5 minutes", "set an alarm for 7am",
            "minuterie 10 minutes", "réveil à 7 heures",
            "add a task", "create a calendar event", "schedule meeting tomorrow",
            "ajoute une tâche", "crée un événement", "planifie une réunion",
            "search the web for", "look up", "find information about",
            "cherche sur internet", "recherche", "what's on my schedule",
            "qu'est-ce que j'ai aujourd'hui", "what tasks do I have",
            "what's the weather in New York", "weather in Paris",
            "quel temps fait-il à Paris",
        ],
    )

    cad_generation = Route(
        name="cad_generation",
        utterances=[
            "create a 3D model", "generate a 3D model", "design a 3D object",
            "make a CAD model", "create an STL file", "generate STL",
            "design a box", "model a bracket", "create a gear",
            "make a housing for", "design a mount for", "create a case for",
            "3D model of a cube", "parametric design", "build123d",
            "make me a 3D model", "I need a 3D model of",
            "crée un modèle 3D", "génère un fichier STL", "dessine une pièce",
            "modélise un boîtier", "crée une pièce pour", "conception 3D",
            "modify the 3D model", "change the height of the model",
            "add a hole to the model", "update the design",
            "iterate on the model", "adjust the dimensions",
            "modifie le modèle", "change les dimensions",
        ],
    )

    print_control = Route(
        name="print_control",
        utterances=[
            "print the model", "start printing", "send to printer",
            "print status", "how's the print going", "what is printing",
            "pause the print", "cancel the print", "resume the print",
            "printer temperature", "bed temperature", "hotend temperature",
            "discover printers", "find my printer", "connect to printer",
            "what printers are available", "add a printer",
            "print this STL", "slice and print", "print job",
            "imprime le modèle", "lance l'impression", "statut de l'impression",
            "pause l'impression", "annule l'impression", "quelle est la progression",
            "température de la buse", "température du plateau",
            "trouve les imprimantes", "connecte l'imprimante",
            "quel est le statut de l'impression", "où en est l'impression",
            "est-ce que l'imprimante imprime", "l'impression est-elle terminée",
            "combien de temps reste-t-il pour l'impression",
            "arrête l'impression", "met en pause l'imprimante",
            "imprimante 3D", "octoprint", "klipper", "moonraker",
            "3D printer status", "is the printer done", "stop the printer",
        ],
    )

    return SemanticRouter(
        encoder=encoder,
        routes=[qwen_basic, qwen_thinking, function_gemma, cad_generation, print_control],
        auto_sync="local",
    )


def get_route(prompt: str) -> str:
    """
    Route a prompt. Returns one of the VALID_ROUTES strings.
    Falls back to 'function_gemma' on error (existing behavior).
    """
    global _router
    if not prompt or not prompt.strip():
        return "qwen_basic"
    try:
        if _router is None:
            print("[SemanticRouter] Initializing...")
            _router = _build_router()
            print("[SemanticRouter] Ready.")
        choice = _router(prompt)
        name = choice.name if choice else None
        return name if name in VALID_ROUTES else "function_gemma"
    except Exception as e:
        print(f"[SemanticRouter] Route failed: {e}")
        return "function_gemma"


def warmup():
    """Pre-load the router (call at app startup)."""
    get_route("hello")
