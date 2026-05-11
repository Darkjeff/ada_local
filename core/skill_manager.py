"""
Skill Manager — loads SKILL.md files from the skills/ directory.

Each skill has YAML frontmatter (name, description, triggers) and a markdown
body that gets injected into the system prompt when the user's input matches
one of the skill's triggers.

Skill file format (skills/<name>/SKILL.md):

    ---
    name: cooking_expert
    description: Expert culinaire, recettes, techniques, ingrédients
    triggers:
      - recette
      - cuisine
      - ingrédient
      - cuire
    ---

    Tu es un chef cuisinier expert...
"""

import re
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional, List

try:
    import yaml
    _HAS_YAML = True
except ImportError:
    _HAS_YAML = False

SKILLS_DIR = Path(__file__).resolve().parent.parent / "skills"

_FRONTMATTER_RE = re.compile(r"^---[ \t]*\r?\n(.*?)\r?\n---[ \t]*\r?\n(.*)", re.DOTALL)


@dataclass
class Skill:
    name: str
    description: str
    triggers: List[str]
    body: str
    path: Path
    model: Optional[str] = None  # optional model override


class SkillManager:
    def __init__(self):
        self._skills: List[Skill] = []
        self._loaded = False

    # ── Loading ──────────────────────────────────────────────────────────────

    def load(self):
        """Scan skills/ directory and load all SKILL.md files."""
        SKILLS_DIR.mkdir(parents=True, exist_ok=True)
        self._skills = []
        for skill_file in sorted(SKILLS_DIR.rglob("SKILL.md")):
            skill = self._parse(skill_file)
            if skill:
                self._skills.append(skill)
        self._loaded = True
        print(f"[SkillManager] {len(self._skills)} skill(s) loaded.")

    def reload(self):
        """Force reload from disk."""
        self._loaded = False
        self.load()

    def _parse(self, path: Path) -> Optional[Skill]:
        try:
            text = path.read_text(encoding="utf-8")
            m = _FRONTMATTER_RE.match(text)
            if not m:
                print(f"[SkillManager] No YAML frontmatter in {path} — skipping.")
                return None

            fm_str, body = m.group(1), m.group(2).strip()

            if _HAS_YAML:
                meta = yaml.safe_load(fm_str) or {}
            else:
                # Minimal fallback: parse simple key: value and list items
                meta = _parse_simple_yaml(fm_str)

            triggers = meta.get("triggers", [])
            if isinstance(triggers, str):
                triggers = [triggers]

            return Skill(
                name=meta.get("name", path.parent.name),
                description=meta.get("description", ""),
                triggers=[t.lower() for t in triggers],
                body=body,
                path=path,
                model=meta.get("model"),
            )
        except Exception as e:
            print(f"[SkillManager] Error parsing {path}: {e}")
            return None

    # ── Matching ─────────────────────────────────────────────────────────────

    def match(self, user_text: str) -> Optional[Skill]:
        """Return the first skill whose trigger appears in user_text, or None."""
        if not self._loaded:
            self.load()

        text_lower = user_text.lower()
        for skill in self._skills:
            for trigger in skill.triggers:
                if trigger in text_lower:
                    print(f"[SkillManager] Matched '{skill.name}' (trigger: '{trigger}')")
                    return skill
        return None

    def inject(self, messages: list, user_text: str) -> list:
        """
        Return a new messages list with the matched skill body appended to the
        system message. The original list is never mutated.
        """
        skill = self.match(user_text)
        if not skill:
            return messages

        new_messages = list(messages)
        if new_messages and new_messages[0].get("role") == "system":
            new_messages[0] = {
                "role": "system",
                "content": new_messages[0]["content"] + "\n\n" + skill.body,
            }
        else:
            new_messages.insert(0, {"role": "system", "content": skill.body})

        return new_messages

    # ── Public API ───────────────────────────────────────────────────────────

    @property
    def skills(self) -> List[Skill]:
        if not self._loaded:
            self.load()
        return list(self._skills)

    def get(self, name: str) -> Optional[Skill]:
        return next((s for s in self.skills if s.name == name), None)


# ── Minimal YAML fallback ─────────────────────────────────────────────────────

def _parse_simple_yaml(text: str) -> dict:
    """Very small YAML subset: key: value and key:\n  - item lists."""
    result: dict = {}
    current_key = None
    current_list: Optional[list] = None

    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue

        if line.startswith("  - ") or line.startswith("- "):
            item = stripped.lstrip("- ").strip()
            if current_list is not None:
                current_list.append(item)
            continue

        if ":" in stripped:
            if current_key and current_list is not None:
                result[current_key] = current_list
                current_list = None

            key, _, value = stripped.partition(":")
            key = key.strip()
            value = value.strip()
            if value:
                result[key] = value
                current_key = None
            else:
                current_key = key
                current_list = []

    if current_key and current_list is not None:
        result[current_key] = current_list

    return result


# Global singleton
skill_manager = SkillManager()
