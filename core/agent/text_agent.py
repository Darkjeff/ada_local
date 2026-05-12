"""
Text-based Web Agent — uses Playwright for navigation and qwen3:1.7b for decisions.
No VLM needed: the agent reads page text/links instead of screenshots.
"""

import json
import re
import requests
import time
from PySide6.QtCore import QObject, Signal

from core.settings_store import settings as app_settings
from config import OLLAMA_URL, RESPONDER_MODEL

MAX_STEPS = 12
MAX_PAGE_CHARS = 4000  # keep LLM context manageable


_SYSTEM_PROMPT = """\
You are a web browsing agent. You control a browser to complete tasks.
At each step you receive the current page content and output ONE JSON action.

Available actions:
{"action": "navigate", "url": "https://..."}          - go to a URL
{"action": "click", "link_text": "exact link text"}   - click a link by its text
{"action": "search", "query": "..."}                  - type in the main search/input box and submit
{"action": "fill", "label": "...", "value": "..."}    - fill a form field by its label or placeholder
{"action": "scroll_down"}                              - scroll down to see more content
{"action": "extract", "result": "..."}                 - return information found on the page (ends task)
{"action": "done", "result": "..."}                    - task complete, provide final answer (ends task)

Rules:
- Output ONLY the JSON object, nothing else.
- Always start by navigating to a relevant URL.
- Use "extract" or "done" once you have the answer.
- If stuck after 3 steps, try a different approach (different URL or search query).
"""


class TextBrowserAgent(QObject):
    """Lightweight text-based browser agent using qwen3:1.7b + Playwright."""

    step_update = Signal(str)   # log line
    result_ready = Signal(str)  # final answer
    finished = Signal()
    error_occurred = Signal(str)

    def __init__(self):
        super().__init__()
        self._running = False
        self._controller = None

    def start_task(self, instruction: str):
        from core.agent.browser_controller import BrowserController
        self._running = True
        self._controller = BrowserController(headless=True)

        try:
            self._controller.start()
            self.step_update.emit(f"Starting: {instruction}")
            self._run_loop(instruction)
        except Exception as e:
            self.error_occurred.emit(str(e))
        finally:
            self._running = False
            try:
                self._controller.stop()
            except Exception:
                pass
            self.finished.emit()

    def stop(self):
        self._running = False

    # ── Main loop ─────────────────────────────────────────────────────────────

    def _run_loop(self, goal: str):
        history = []
        ollama_url = app_settings.get("ollama_url", OLLAMA_URL)
        # Strip trailing /api if present so we can append /api/chat cleanly
        base = ollama_url.rstrip("/")
        if base.endswith("/api"):
            base = base[:-4]
        chat_url = f"{base}/api/chat"

        model = app_settings.get("models.chat", RESPONDER_MODEL)

        for step in range(1, MAX_STEPS + 1):
            if not self._running:
                self.step_update.emit("Stopped by user.")
                return

            page_content = self._get_page_summary()

            user_msg = (
                f"Goal: {goal}\n\n"
                f"Step {step}/{MAX_STEPS}\n\n"
                f"Current page:\n{page_content}\n\n"
                "Output the next JSON action:"
            )

            messages = [
                {"role": "system", "content": _SYSTEM_PROMPT},
                *history,
                {"role": "user", "content": user_msg},
            ]

            self.step_update.emit(f"[Step {step}] Thinking...")

            try:
                resp = requests.post(
                    chat_url,
                    json={"model": model, "messages": messages,
                          "stream": False, "think": False},
                    timeout=60,
                )
                resp.raise_for_status()
                reply = resp.json().get("message", {}).get("content", "").strip()
            except Exception as e:
                self.error_occurred.emit(f"LLM error: {e}")
                return

            action = self._parse_action(reply)
            if not action:
                self.step_update.emit(f"[Step {step}] Could not parse action: {reply[:120]}")
                history.append({"role": "assistant", "content": reply})
                history.append({"role": "user", "content": "Output a valid JSON action."})
                continue

            history.append({"role": "assistant", "content": json.dumps(action)})

            action_name = action.get("action", "")
            self.step_update.emit(f"[Step {step}] {action_name}: {json.dumps(action)}")

            # Terminal actions
            if action_name in ("done", "extract"):
                result = action.get("result", reply)
                self.result_ready.emit(result)
                return

            # Execute browser action
            try:
                self._execute(action)
            except Exception as e:
                self.step_update.emit(f"  ✗ Execution error: {e}")

            time.sleep(1.5)  # let page settle

        self.step_update.emit("Max steps reached.")
        self.result_ready.emit("I reached the step limit without completing the task.")

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _get_page_summary(self) -> str:
        if not self._controller or not self._controller.page:
            return "(no page loaded)"
        try:
            page = self._controller.page
            title = page.title() or "(no title)"
            url = page.url or ""

            # Headings
            headings = page.eval_on_selector_all(
                "h1, h2, h3",
                "els => els.slice(0,8).map(e => e.innerText.trim()).filter(Boolean)"
            )

            # Links (text + href)
            links = page.eval_on_selector_all(
                "a[href]",
                "els => els.slice(0,30).map(e => ({t: e.innerText.trim(), h: e.href})).filter(l => l.t)"
            )
            links_str = "\n".join(f"  [{l['t'][:60]}] {l['h'][:80]}" for l in links[:20])

            # Visible body text
            body = page.eval_on_selector(
                "body",
                "el => el.innerText"
            ) or ""
            body = re.sub(r"\s{3,}", "\n", body)[:MAX_PAGE_CHARS]

            summary = (
                f"URL: {url}\nTitle: {title}\n"
                f"Headings: {headings}\n"
                f"Links:\n{links_str}\n"
                f"Body:\n{body}"
            )
            return summary[:MAX_PAGE_CHARS + 500]
        except Exception as e:
            return f"(error reading page: {e})"

    def _execute(self, action: dict):
        name = action.get("action")
        page = self._controller.page

        if name == "navigate":
            url = action.get("url", "")
            if not url.startswith("http"):
                url = "https://" + url
            page.goto(url, timeout=15000)

        elif name == "click":
            link_text = action.get("link_text", "")
            # Try exact text, then partial
            try:
                page.get_by_text(link_text, exact=True).first.click(timeout=5000)
            except Exception:
                page.get_by_text(link_text).first.click(timeout=5000)

        elif name == "search":
            query = action.get("query", "")
            # Try common search input selectors
            for sel in ["input[type='search']", "input[name='q']", "input[type='text']", "textarea"]:
                try:
                    page.fill(sel, query, timeout=3000)
                    page.press(sel, "Enter")
                    return
                except Exception:
                    continue
            raise RuntimeError("No search input found")

        elif name == "fill":
            label_text = action.get("label", "")
            value = action.get("value", "")
            # Try placeholder or aria-label
            for attr in [f"input[placeholder*='{label_text}']",
                         f"input[aria-label*='{label_text}']",
                         f"textarea[placeholder*='{label_text}']"]:
                try:
                    page.fill(attr, value, timeout=3000)
                    return
                except Exception:
                    continue
            # Fallback: find by label element
            page.get_by_label(label_text).fill(value, timeout=3000)

        elif name == "scroll_down":
            page.mouse.wheel(0, 600)

    def _parse_action(self, text: str) -> dict | None:
        # Strip markdown code blocks
        text = re.sub(r"```(?:json)?\s*|\s*```", "", text).strip()
        # Find first { ... }
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(0))
            except Exception:
                pass
        return None
