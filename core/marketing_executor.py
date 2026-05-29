"""
Marketing content generator for MargePro.

Appelle Ollama directement avec un system prompt MargePro contextualisé.
Stocke l'historique dans data/marketing_history.db.
"""

import sqlite3
import datetime
from pathlib import Path
from typing import Callable, Iterator

import requests

from config import OLLAMA_URL, MARKETING_MODEL

# ---------------------------------------------------------------------------
# DB setup
# ---------------------------------------------------------------------------

_DB_PATH = Path(__file__).parent.parent / "data" / "marketing_history.db"
_DB_PATH.parent.mkdir(parents=True, exist_ok=True)


def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(_DB_PATH))
    conn.execute("""
        CREATE TABLE IF NOT EXISTS marketing_history (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at  TEXT    NOT NULL,
            skill_name  TEXT    NOT NULL DEFAULT 'margepro',
            content_type TEXT   NOT NULL,
            reseau      TEXT    NOT NULL,
            secteur     TEXT    NOT NULL,
            ton         TEXT    NOT NULL,
            brief       TEXT,
            result      TEXT    NOT NULL
        )
    """)
    # Migration : ajoute skill_name sur les DBs existantes
    try:
        conn.execute("ALTER TABLE marketing_history ADD COLUMN skill_name TEXT NOT NULL DEFAULT 'margepro'")
        conn.commit()
    except Exception:
        pass
    return conn


# ---------------------------------------------------------------------------
# Content-type prompt templates
# ---------------------------------------------------------------------------

CONTENT_TYPES: dict[str, str] = {
    "Post": (
        "Génère un post {reseau} percutant pour promouvoir {produit} auprès du secteur {secteur}. "
        "Ton : {ton}. "
        "Longueur adaptée à {reseau} (LinkedIn ~1500 car, Twitter ≤280 car, Instagram ~500 car). "
        "Inclus un appel à l'action clair. "
        "Brief complémentaire de l'utilisateur : {brief}"
    ),
    "Accroches (hooks)": (
        "Génère 5 accroches (hooks) différentes pour un post {reseau} sur {produit}, secteur {secteur}. "
        "Ton : {ton}. Chaque accroche doit donner envie de lire la suite. "
        "Format : une accroche par ligne, numérotées. "
        "Brief : {brief}"
    ),
    "Bio profil": (
        "Rédige une bio de profil {reseau} pour un commercial/fondateur qui vend {produit}. "
        "Secteur cible : {secteur}. Ton : {ton}. "
        "Longueur : 2-3 phrases impactantes. "
        "Brief : {brief}"
    ),
    "Stratégie contenu": (
        "Crée un plan de contenu sur 4 semaines pour promouvoir {produit} sur {reseau} "
        "auprès du secteur {secteur}. Ton : {ton}. "
        "Format : tableau semaine / type de contenu / angle / objectif. "
        "Brief : {brief}"
    ),
    "Réponse objection": (
        "Rédige une réponse professionnelle à cette objection client courante dans le secteur {secteur} : "
        "'{brief}'. "
        "Contexte produit : {produit}. Ton : {ton}. "
        "La réponse doit être empathique, rassurante et conclure par une invitation à aller plus loin."
    ),
    "Séquence email": (
        "Rédige une séquence de 3 emails de prospection/nurturing pour {produit}, "
        "ciblant le secteur {secteur}. Ton : {ton}. "
        "Email 1 : prise de contact. Email 2 : valeur ajoutée. Email 3 : appel à l'action. "
        "Brief : {brief}"
    ),
}

RESEAUX = ["LinkedIn", "Twitter/X", "Instagram", "Facebook", "TikTok", "Email / Newsletter"]
SECTEURS = [
    "SaaS / Tech",
    "E-commerce",
    "Consulting / Agence",
    "Immobilier",
    "Finance / Assurance",
    "RH / Recrutement",
    "Formation / Coaching",
    "Retail / Commerce",
    "Santé / Bien-être",
    "Industrie / B2B",
]
TONS = ["Professionnel", "Décontracté / Casual", "Expert / Autoritaire", "Storytelling", "Humour / Décalé", "Inspirant"]


# ---------------------------------------------------------------------------
# HTTP session (shared)
# ---------------------------------------------------------------------------

_session = requests.Session()

_FRONTMATTER_RE = __import__('re').compile(r'^---[ \t]*\r?\n.*?\r?\n---[ \t]*\r?\n(.*)', __import__('re').DOTALL)


# ---------------------------------------------------------------------------
# Skill helpers
# ---------------------------------------------------------------------------

def _skills_dir() -> Path:
    return Path(__file__).parent.parent / "skills"


def list_ollama_models() -> list[str]:
    """Retourne la liste des modèles disponibles dans Ollama."""
    try:
        base = OLLAMA_URL.rstrip("/")
        if base.endswith("/api"):
            base = base[:-4]
        resp = _session.get(f"{base}/api/tags", timeout=5)
        resp.raise_for_status()
        return [m["name"] for m in resp.json().get("models", [])]
    except Exception:
        return []


def list_marketing_skills() -> list[dict]:
    """Retourne la liste des skills disponibles sous forme [{name, description}]."""
    skills = []
    for skill_path in sorted(_skills_dir().glob("*/SKILL.md")):
        try:
            raw = skill_path.read_text(encoding="utf-8")
            # Parse frontmatter minimal (sans dépendance yaml)
            fm_match = __import__('re').match(
                r'^---[ \t]*\r?\n(.*?)\r?\n---', raw, __import__('re').DOTALL
            )
            name = skill_path.parent.name
            description = name
            if fm_match:
                for line in fm_match.group(1).splitlines():
                    if line.startswith('description:'):
                        description = line.split(':', 1)[1].strip().strip('"\'')
                        break
                    if line.startswith('name:'):
                        name = line.split(':', 1)[1].strip().strip('"\'')
            skills.append({"name": skill_path.parent.name, "description": description})
        except Exception:
            continue
    return skills


def _read_skill_body(skill_name: str) -> str:
    """Lit le corps (sans frontmatter) d'un skill. Retourne '' si introuvable."""
    skill_path = _skills_dir() / skill_name / "SKILL.md"
    if not skill_path.exists():
        return ""
    raw = skill_path.read_text(encoding="utf-8")
    m = _FRONTMATTER_RE.match(raw)
    return m.group(1).strip() if m else raw.strip()


# ---------------------------------------------------------------------------
# Core generation
# ---------------------------------------------------------------------------

def _build_system_prompt(skill_name: str) -> str:
    ctx = _read_skill_body(skill_name)
    produit = skill_name.replace('_', ' ').replace('-', ' ').title()
    return (
        f"Tu es un expert en copywriting et marketing B2B spécialisé dans {produit}. "
        "Voici tout ce que tu dois savoir sur ce produit :\n\n"
        f"{ctx}\n\n"
        "Génère uniquement le contenu demandé, sans explications ni méta-commentaires. "
        "Sois percutant, concret et orienté résultats. "
        "Adapte systématiquement le ton et le format au réseau social ciblé."
    )


def generate_stream(
    content_type: str,
    reseau: str,
    secteur: str,
    ton: str,
    brief: str,
    on_token: Callable[[str], None],
    on_done: Callable[[str], None],
    on_error: Callable[[str], None],
    skill_name: str = "margepro",
    model: str = "",
) -> None:
    """
    Génère du contenu marketing en streaming.
    Appelle `on_token(chunk)` pour chaque morceau, puis `on_done(full_text)`.
    Stocke automatiquement l'entrée en BDD.

    À appeler depuis un QThread (bloque le thread appelant).
    """
    produit = skill_name.replace('_', ' ').replace('-', ' ').title()
    template = CONTENT_TYPES.get(content_type, CONTENT_TYPES["Post"])
    user_prompt = template.format(
        reseau=reseau,
        secteur=secteur,
        ton=ton,
        brief=brief or "Aucun brief spécifique.",
        produit=produit,
    )

    payload = {
        "model": model or MARKETING_MODEL,
        "prompt": user_prompt,
        "system": _build_system_prompt(skill_name),
        "stream": True,
        "options": {
            "temperature": 0.85,
            "num_predict": 2048,
        },
    }

    full_text = ""
    try:
        with _session.post(
            f"{OLLAMA_URL}/generate",
            json=payload,
            stream=True,
            timeout=120,
        ) as resp:
            resp.raise_for_status()
            import json as _json
            for line in resp.iter_lines():
                if not line:
                    continue
                try:
                    chunk = _json.loads(line)
                except ValueError:
                    continue
                token = chunk.get("response", "")
                if token:
                    full_text += token
                    on_token(token)
                if chunk.get("done"):
                    break
    except Exception as exc:
        on_error(str(exc))
        return

    # Persist history
    try:
        conn = _get_conn()
        conn.execute(
            "INSERT INTO marketing_history (created_at, skill_name, content_type, reseau, secteur, ton, brief, result) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                datetime.datetime.now().isoformat(timespec="seconds"),
                skill_name,
                content_type,
                reseau,
                secteur,
                ton,
                brief,
                full_text,
            ),
        )
        conn.commit()
        conn.close()
    except Exception:
        pass  # Ne pas crasher si la BDD plante

    on_done(full_text)


def get_history(limit: int = 50) -> list[dict]:
    """Retourne les N dernières entrées de l'historique."""
    try:
        conn = _get_conn()
        rows = conn.execute(
            "SELECT id, created_at, skill_name, content_type, reseau, secteur, ton, brief, result "
            "FROM marketing_history ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
        conn.close()
        return [
            {
                "id": r[0],
                "created_at": r[1],
                "skill_name": r[2],
                "content_type": r[3],
                "reseau": r[4],
                "secteur": r[5],
                "ton": r[6],
                "brief": r[7],
                "result": r[8],
            }
            for r in rows
        ]
    except Exception:
        return []


def delete_history_entry(entry_id: int) -> None:
    """Supprime une entrée de l'historique par son id."""
    try:
        conn = _get_conn()
        conn.execute("DELETE FROM marketing_history WHERE id = ?", (entry_id,))
        conn.commit()
        conn.close()
    except Exception:
        pass
