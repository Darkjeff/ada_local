"""
CAD Agent — generates build123d Python code via Ollama and executes it locally.
Produces STL files from natural language descriptions with up to 3 auto-retries.
"""

import base64
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Callable, Optional

from PySide6.QtCore import QObject, Signal

from config import OLLAMA_URL, RESPONDER_MODEL
from core.llm import http_session
from core.settings_store import settings as app_settings

MAX_RETRIES = 3
OUTPUT_DIR = Path.home() / "ADA_CAD"

_SYSTEM_PROMPT = """\
You are a parametric CAD code generator using the build123d Python library.

STRICT OUTPUT FORMAT:
- Output ONLY a single ```python code block — nothing before, nothing after.
- First line: from build123d import *
- Assign the final shape to: result_part
- Last line: export_stl(result_part, 'output.stl')

CORRECT builder API:
```python
from build123d import *

with BuildPart() as p:
    Box(30, 20, 10)
    fillet(p.edges(), radius=1)

result_part = p.part
export_stl(result_part, 'output.stl')
```

RULES:
- All dimensions in millimeters, range 5mm–500mm.
- Fillets: max 2mm radius. Chamfers: max 1mm.
- Use builder context managers (with BuildPart() as p:) — do NOT call Extrude(), Fillet() as class constructors.
- For holes: use Hole() inside BuildPart context.
- For extrusions: use extrude() method on a sketch face.
"""

_ITERATION_SYSTEM = """\
You are updating an existing build123d CAD script. Apply ONLY the requested change.
Output the COMPLETE updated script as a single ```python code block.
Keep all unchanged geometry intact.
"""


class CadAgent(QObject):
    """Generates and executes build123d code via Ollama with auto-retry."""

    log = Signal(str)        # progress log line
    thinking = Signal(str)   # LLM thinking text
    finished = Signal(dict)  # {"success": bool, "stl_path": str, "code": str, "error": str}

    def __init__(self, parent=None):
        super().__init__(parent)
        self._running = False

    def stop(self):
        self._running = False

    # ── Public entry points ───────────────────────────────────────────────────

    def generate(self, prompt: str):
        """Generate a new CAD model from a natural language prompt."""
        self._running = True
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        stl_path = OUTPUT_DIR / f"model_{timestamp}.stl"
        script_path = OUTPUT_DIR / f"model_{timestamp}.py"
        self._run(prompt, stl_path, script_path, existing_code=None)

    def iterate(self, prompt: str, current_code: str):
        """Iterate on an existing build123d script."""
        self._running = True
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        stl_path = OUTPUT_DIR / f"model_{timestamp}.stl"
        script_path = OUTPUT_DIR / f"model_{timestamp}.py"
        self._run(prompt, stl_path, script_path, existing_code=current_code)

    # ── Core generation loop ──────────────────────────────────────────────────

    def _run(self, prompt: str, stl_path: Path, script_path: Path, existing_code: Optional[str]):
        ollama_url = app_settings.get("ollama_url", OLLAMA_URL)
        base = ollama_url.rstrip("/")
        if base.endswith("/api"):
            base = base[:-4]
        generate_url = f"{base}/api/generate"
        model = app_settings.get("models.chat", RESPONDER_MODEL)

        if existing_code:
            user_prompt = (
                f"Current build123d script:\n```python\n{existing_code}\n```\n\n"
                f"User request: {prompt}\n\n"
                "Output the complete updated script."
            )
            system = _ITERATION_SYSTEM
        else:
            user_prompt = f"Create a 3D model: {prompt}"
            system = _SYSTEM_PROMPT

        error_context = ""
        last_code = ""

        for attempt in range(1, MAX_RETRIES + 1):
            if not self._running:
                self.finished.emit({"success": False, "error": "Stopped", "stl_path": "", "code": ""})
                return

            full_prompt = user_prompt + error_context

            self.log.emit(f"[Attempt {attempt}/{MAX_RETRIES}] Generating code...")

            # Stream the LLM response
            raw = self._call_ollama(generate_url, model, system, full_prompt)
            if raw is None:
                self.finished.emit({"success": False, "error": "LLM call failed", "stl_path": "", "code": last_code})
                return

            code = self._extract_code(raw)
            if not code:
                self.log.emit(f"  ✗ No code block found in response.")
                error_context = "\n\nERROR: Your response did not contain a ```python code block. Output ONLY the code block."
                continue

            last_code = code
            code_with_path = self._inject_path(code, stl_path)

            # Save script
            script_path.write_text(code_with_path, encoding="utf-8")
            self.log.emit(f"  Script saved: {script_path.name}")

            # Execute
            self.log.emit(f"  Executing build123d...")
            ok, stdout, stderr = self._execute(script_path)

            if ok and stl_path.exists():
                self.log.emit(f"  ✓ STL generated: {stl_path}")
                self.finished.emit({
                    "success": True,
                    "stl_path": str(stl_path),
                    "code": code,
                    "error": ""
                })
                return

            # Execution failed — send error back to LLM
            err_msg = (stderr or stdout or "Unknown error")[:600]
            self.log.emit(f"  ✗ Execution error:\n{err_msg}")
            error_context = (
                f"\n\nPREVIOUS CODE FAILED with this error:\n{err_msg}\n"
                "Fix the error and output the corrected complete script."
            )

        self.finished.emit({
            "success": False,
            "error": f"Failed after {MAX_RETRIES} attempts",
            "stl_path": "",
            "code": last_code
        })

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _call_ollama(self, url: str, model: str, system: str, prompt: str) -> Optional[str]:
        """Stream Ollama response, emit thinking chunks, return full text."""
        try:
            resp = http_session.post(
                url,
                json={
                    "model": model,
                    "system": system,
                    "prompt": prompt,
                    "stream": True,
                    "think": True,
                    "options": {"temperature": 0.3, "num_predict": 2048},
                },
                stream=True,
                timeout=180,
            )
            resp.raise_for_status()
        except Exception as e:
            self.log.emit(f"  ✗ Ollama error: {e}")
            return None

        import json
        full_response = []
        in_think = False

        for line in resp.iter_lines():
            if not self._running:
                return None
            if not line:
                continue
            try:
                chunk = json.loads(line)
            except Exception:
                continue

            # Thinking tokens
            think_chunk = chunk.get("thinking", "")
            if think_chunk:
                self.thinking.emit(think_chunk)

            # Response tokens
            token = chunk.get("response", "")
            if token:
                full_response.append(token)

        return "".join(full_response)

    @staticmethod
    def _extract_code(text: str) -> Optional[str]:
        m = re.search(r"```python\s*(.*?)```", text, re.DOTALL)
        if m:
            return m.group(1).strip()
        # Fallback: plain ``` block
        m = re.search(r"```\s*(from build123d.*?)```", text, re.DOTALL)
        if m:
            return m.group(1).strip()
        return None

    @staticmethod
    def _inject_path(code: str, stl_path: Path) -> str:
        safe = str(stl_path).replace("\\", "\\\\")
        code = re.sub(r"export_stl\s*\(\s*result_part\s*,\s*['\"]output\.stl['\"]\s*\)",
                      f"export_stl(result_part, '{safe}')", code)
        return code

    @staticmethod
    def _execute(script_path: Path):
        try:
            result = subprocess.run(
                [sys.executable, str(script_path)],
                capture_output=True,
                text=True,
                timeout=120,
            )
            ok = result.returncode == 0
            return ok, result.stdout, result.stderr
        except subprocess.TimeoutExpired:
            return False, "", "Execution timed out after 120s"
        except Exception as e:
            return False, "", str(e)

    @staticmethod
    def read_stl_b64(stl_path: str) -> str:
        with open(stl_path, "rb") as f:
            return base64.b64encode(f.read()).decode("utf-8")
