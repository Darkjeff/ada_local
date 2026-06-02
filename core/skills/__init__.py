"""
core/skills — Module Skills SQLite ADA
Système de mémoire procédurale basé sur FTS5.
"""
from .skills_db import init_db, seed_from_files, get_connection
from .skills_manager import (
    search_skills, search_archive,
    get_skill, save_skill, delete_skill, archive_skill, restore_skill,
    promote_skill, set_priority, record_success,
    run_maintenance, list_skills,
)
from .skills_injector import build_system_prompt

__all__ = [
    "init_db", "seed_from_files", "get_connection",
    "search_skills", "search_archive",
    "get_skill", "save_skill", "delete_skill", "archive_skill",
    "restore_skill", "promote_skill", "set_priority",
    "record_success", "run_maintenance", "list_skills",
    "build_system_prompt",
]
