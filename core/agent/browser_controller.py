import base64
import time
from playwright.sync_api import sync_playwright, Page, BrowserContext, Browser

class BrowserController:
    """
    Controls the browser using Playwright, handling actions from the VLM
    and capturing screenshots. Operates in a 1000x1000 coordinate space
    as expected by Qwen2.5/3-VL.
    """
    def __init__(self, headless: bool = False, viewport_width: int = 1280, viewport_height: int = 720):
        self.headless = headless
        self.viewport_width = viewport_width
        self.viewport_height = viewport_height
        self.playwright = None
        self.browser: Browser = None
        self.context: BrowserContext = None
        self.page: Page = None
        
        # Qwen uses a 1000x1000 coordinate system
        self.model_width = 1000
        self.model_height = 1000

    def start(self):
        """Starts the Playwright browser session."""
        if self.playwright:
            return

        self.playwright = sync_playwright().start()
        self.browser = self.playwright.chromium.launch(
            headless=self.headless,
            args=["--disable-blink-features=AutomationControlled"] # Attempt to reduce detection
        )
        self.context = self.browser.new_context(
            viewport={"width": self.viewport_width, "height": self.viewport_height},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        self.page = self.context.new_page()
        try:
            self.page.goto("https://www.google.com")
        except:
            pass

    def stop(self):
        """Stops the browser session."""
        if self.context:
            self.context.close()
        if self.browser:
            self.browser.close()
        if self.playwright:
            self.playwright.stop()
        
        self.page = None
        self.context = None
        self.browser = None
        self.playwright = None

    def get_screenshot(self) -> str:
        """Returns the current page screenshot as a base64 string."""
        if not self.page:
            return ""
        
        screenshot_bytes = self.page.screenshot(type="jpeg", quality=70)
        return base64.b64encode(screenshot_bytes).decode("utf-8")

    def _scale_coordinates(self, x: int, y: int):
        """Scales 1000x1000 coordinates to the actual viewport size."""
        scaled_x = (x / self.model_width) * self.viewport_width
        scaled_y = (y / self.model_height) * self.viewport_height
        return scaled_x, scaled_y

    def execute_action(self, action_name: str, params: dict):
        """
        Executes a browser action.
        
        Args:
            action_name: The name of the action (e.g., 'left_click', 'type').
            params: Dictionary of arguments for the action.
        """
        if not self.page:
            raise RuntimeError("Browser not started")

        # Bring browser to front if possible (OS dependent, but good for local debugging)
        # self.page.bring_to_front()

        if action_name == "mouse_move":
            coords = params.get("coordinate")
            if coords:
                x, y = self._scale_coordinates(coords[0], coords[1])
                self.page.mouse.move(x, y)

        elif action_name == "left_click":
            coords = params.get("coordinate")
            if coords:
                x, y = self._scale_coordinates(coords[0], coords[1])
                self.page.mouse.click(x, y)

        elif action_name == "left_click_drag":
            # "Click and drag the cursor to a specified (x, y) pixel coordinate"
            # We assume this means dragging FROM current position TO the new position.
            coords = params.get("coordinate")
            if coords:
                x, y = self._scale_coordinates(coords[0], coords[1])
                # 1. Mouse down at current location
                self.page.mouse.down()
                # 2. Move to new (x,y)
                self.page.mouse.move(x, y, steps=10) # steps makes it smoother/more human-like
                # 3. Mouse up
                self.page.mouse.up()

        elif action_name == "right_click":
            coords = params.get("coordinate")
            if coords:
                x, y = self._scale_coordinates(coords[0], coords[1])
                self.page.mouse.click(x, y, button="right")

        elif action_name == "middle_click":
            coords = params.get("coordinate")
            if coords:
                x, y = self._scale_coordinates(coords[0], coords[1])
                self.page.mouse.click(x, y, button="middle")

        elif action_name == "double_click":
            coords = params.get("coordinate")
            if coords:
                x, y = self._scale_coordinates(coords[0], coords[1])
                self.page.mouse.dblclick(x, y)

        elif action_name == "triple_click":
            coords = params.get("coordinate")
            if coords:
                x, y = self._scale_coordinates(coords[0], coords[1])
                self.page.mouse.click(x, y, click_count=3)

        elif action_name == "type":
            text = params.get("text")
            selector = params.get("selector")
            if text:
                if selector:
                    try:
                        self.page.fill(selector, text)
                    except Exception:
                        self.page.keyboard.type(text)
                else:
                    self.page.keyboard.type(text)

        elif action_name == "key":
            keys = params.get("keys") # Expecting formatted keys like 'Enter', 'Control+C'
            if keys:
                # Playwright expects single string for 'press', e.g. 'Enter'
                # If Qwen sends a list, we iterate
                if isinstance(keys, list):
                    for k in keys:
                        # Map some common keys if necessary, Playwright is usually good
                        # Qwen might send 'Return', Playwright wants 'Enter'
                        if k.lower() == "return": k = "Enter"
                        self.page.keyboard.press(k)
                else:
                    self.page.keyboard.press(keys)

        elif action_name == "scroll":
            pixels = params.get("pixels", 0)
            if pixels:
                # Qwen: Positive = scroll up (content moves down).
                # Playwright: Negative delta_y = scroll up.
                self.page.mouse.wheel(0, -pixels)

        elif action_name == "hscroll":
            pixels = params.get("pixels", 0)
            if pixels:
                # Qwen: Positive = scroll? Usage not fully defined but likely consistent.
                # Assuming positive = scroll right? Or same "up/down" logic applied to horizontal?
                # Cookbook: "Positive values scroll up, negative values scroll down... Required only by `action=scroll` and `action=hscroll`"
                # "Scroll up" for horizontal usually means "Scroll Left" (content moves right).
                # Playwright: delta_x > 0 is scroll right, < 0 is scroll left.
                # If "Up" ~ "Left", then Positive -> Negative delta_x.
                self.page.mouse.wheel(-pixels, 0)
        
        elif action_name == "navigate":
            url = params.get("url")
            if url:
                self.goto(url)

        elif action_name == "wait":
            duration = params.get("time", 1.0)
            time.sleep(duration)

        elif action_name == "terminate":
            # handled by agent loop
            pass

    def goto(self, url: str):
        if self.page:
            if not url.startswith("http"):
                url = "https://" + url
            self.page.goto(url)
