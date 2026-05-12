"""
Text-based Web Agent — uses Playwright for navigation and qwen3:1.7b for decisions.
No VLM needed: the agent reads page text/links instead of screenshots.
"""

import json
import re
import time
import urllib.parse

import requests
from PySide6.QtCore import QObject, Signal

from core.settings_store import settings as app_settings
from config import OLLAMA_URL, RESPONDER_MODEL

MAX_STEPS = 12
MAX_PAGE_CHARS = 4000  # keep LLM context manageable


_SYSTEM_PROMPT = """\
You are a web browsing agent. You control a browser to complete tasks.
At each step you receive the current page content and output ONE JSON action.

Available actions:
{"action": "navigate", "url": "https://..."}        - go to a URL
{"action": "click", "link_text": "link text here"}  - click a visible link by its text
{"action": "scroll_down"}                            - scroll down to reveal more content
{"action": "extract", "result": "..."}               - return info found (ends task)
{"action": "done", "result": "..."}                  - task complete, final answer (ends task)

Rules:
- Output ONLY the raw JSON object — no markdown, no explanation.
- Write accented letters directly (é è ê etc.), NEVER \\uXXXX escapes.
- ALWAYS use navigate with a Google search URL for any web search:
    {"action": "navigate", "url": "https://www.google.com/search?q=your+query+here"}
  Never use type/fill/selector — navigate directly.
- After navigating, read the page content and extract the answer.
- Use "extract" or "done" as soon as you have the information.
- If a page has no useful info, navigate to a different URL.
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
        from core.model_persistence import ensure_qwen_loaded, mark_qwen_used
        self._running = True
        self._controller = BrowserController(headless=True)

        try:
            self.step_update.emit("Loading model...")
            ensure_qwen_loaded()
            mark_qwen_used()
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
                    timeout=120,
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

            time.sleep(0.5)  # short settle after action+networkidle

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

    def _dismiss_consent(self, page) -> bool:
        """Dismiss Google/cookie consent dialogs. Returns True if one was found."""
        selectors = [
            # Google consent buttons (FR/EN)
            "button:has-text('Tout accepter')",
            "button:has-text('Accept all')",
            "button:has-text('J\\'accepte')",
            "button:has-text('Accepter')",
            "form[action*='consent'] button[type='submit']",
            "[aria-label*='Avant d\\'accéder'] button",
            "[aria-label*='Before you continue'] button",
        ]
        for sel in selectors:
            try:
                btn = page.locator(sel).first
                if btn.is_visible(timeout=1000):
                    btn.click(timeout=3000)
                    try:
                        page.wait_for_load_state("networkidle", timeout=5000)
                    except Exception:
                        pass
                    return True
            except Exception:
                continue
        return False

    def _execute(self, action: dict):
        name = action.get("action")
        page = self._controller.page

        if name == "navigate":
            url = action.get("url", "")
            if not url.startswith("http"):
                url = "https://" + url
            page.goto(url, timeout=20000)
            try:
                page.wait_for_load_state("networkidle", timeout=8000)
            except Exception:
                pass
            self._dismiss_consent(page)

        elif name == "click":
            # Dismiss any consent overlay before clicking
            self._dismiss_consent(page)
            link_text = action.get("link_text", "")
            try:
                page.get_by_text(link_text, exact=True).first.click(timeout=5000)
            except Exception:
                page.get_by_text(link_text).first.click(timeout=5000)
            try:
                page.wait_for_load_state("networkidle", timeout=6000)
            except Exception:
                pass

        elif name == "search":
            query = action.get("query", "")
            page.goto(f"https://www.google.com/search?q={urllib.parse.quote(query)}", timeout=20000)
            try:
                page.wait_for_load_state("networkidle", timeout=8000)
            except Exception:
                pass
            self._dismiss_consent(page)

        elif name == "fill":
            label_text = action.get("label", "")
            value = action.get("value", "")
            for attr in [f"input[placeholder*='{label_text}']",
                         f"input[aria-label*='{label_text}']",
                         f"textarea[placeholder*='{label_text}']"]:
                try:
                    page.fill(attr, value, timeout=3000)
                    return
                except Exception:
                    continue
            page.get_by_label(label_text).fill(value, timeout=3000)

        elif name == "type":
            # Model may generate type+selector (computer-use style) — support both forms
            selector = action.get("selector", "")
            text = action.get("text", "")
            if selector and text:
                try:
                    page.fill(selector, text, timeout=5000)
                    page.keyboard.press("Enter")
                    try:
                        page.wait_for_load_state("networkidle", timeout=8000)
                    except Exception:
                        pass
                    return
                except Exception:
                    pass
            # Fallback: build a Google search URL from the text
            if text:
                page.goto(f"https://www.google.com/search?q={urllib.parse.quote(text)}", timeout=20000)
                try:
                    page.wait_for_load_state("networkidle", timeout=8000)
                except Exception:
                    pass

        elif name == "key":
            keys = action.get("keys", action.get("key", ""))
            if keys:
                page.keyboard.press(keys)

        elif name == "scroll_down":
            page.mouse.wheel(0, 600)
            time.sleep(0.5)

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
