import json
import re
import requests
from typing import List, Dict, Any, Generator

from core.settings_store import settings as app_settings

class VLMClient:
    """
    Client for interacting with Qwen3-VL (or similar) models via Ollama.
    Handles the specific prompt engineering for 'computer use'.
    """
    def __init__(self, model_name: str = None, base_url: str = None, model_params: Dict[str, Any] = None):
        # Read from settings store, with fallbacks
        self.model_name = model_name or app_settings.get("models.web_agent", "qwen3-vl:4b")
        self.base_url = base_url or app_settings.get("ollama_url", "http://localhost:11434")
        self.model_params = model_params or app_settings.get("web_agent_params", {})

    def construct_system_prompt(self) -> str:
        """
        Constructs the system prompt based on the Qwen cookbook for computer use.
        """
        return """You are a helpful assistant.

            # Tools

            You may call one or more functions to assist with the user query.

            You are provided with function signatures within <tools></tools> XML tags:
            <tools>
            {
                "type": "function", 
                "function": {
                    "name": "computer_use", 
                    "description": "Interact with a browser by navigating, clicking, typing, or scrolling.", 
                    "parameters": {
                        "properties": {
                            "action": {
                                "description": "The action to perform.",
                                "enum": ["navigate", "left_click", "type", "key", "scroll", "terminate"],
                                "type": "string"
                            },
                            "url": {
                                "description": "The URL to navigate to. Required for `action=navigate`.",
                                "type": "string"
                            },
                            "coordinate": {
                                "description": "The (x, y) coordinate to click. Required for `action=left_click`. IMPORTANT: Use the 1000x1000 coordinate system.",
                                "type": "array",
                                "items": {"type": "integer"}
                            },
                            "text": {
                                "description": "The text to type. Required for `action=type`. You may also include a `selector` (CSS selector) to target a specific input.",
                                "type": "string"
                            },
                            "keys": {
                                "description": "Key to press. Required for `action=key`. Examples: 'Enter', 'Tab', 'Escape', 'Control+a'.",
                                "type": "string"
                            },
                            "pixels": {
                                "description": "Amount to scroll. Positive scrolls down (content up). Required for `action=scroll`.",
                                "type": "integer"
                            },
                            "status": {
                                "description": "The completion status. Required for `action=terminate`.",
                                "enum": ["success", "failure"],
                                "type": "string"
                            }
                        }, 
                        "required": ["action"], 
                        "type": "object"
                    }
                }
            }
            </tools>

            For each function call, return a json object with function name and arguments within <tool_call></tool_call> XML tags.
            
            CRITICAL RULES:
            - You MUST ALWAYS output exactly ONE <tool_call> block per turn. NEVER a text-only response.
            - To search on Google: use `navigate` with url="https://www.google.com/search?q=YOUR+QUERY" — this is faster than typing.
            - If you use `type` to fill a search box, ALWAYS follow it with `key` action with keys="Enter" on the next turn.
            - If you see the same screen twice in a row, your previous action had no effect — try a different action.
            - When the task is done and you have the information, use `terminate` with status="success".

            <tool_call>
            {"name": <function-name>, "arguments": <args-json-object>}
            </tool_call>

            # Examples
            User: Search Google for "hantavirus news"
            Assistant: <tool_call>
            {"name": "computer_use", "arguments": {"action": "navigate", "url": "https://www.google.com/search?q=hantavirus+news"}}
            </tool_call>

            User: Press Enter to submit the form
            Assistant: <tool_call>
            {"name": "computer_use", "arguments": {"action": "key", "keys": "Enter"}}
            </tool_call>
            """

    def generate_action(self, messages: List[Dict[str, Any]]) -> Generator[Dict[str, Any], None, None]:
        """
        Sends the messages to the model and yields chunks/result.
        Yields:
            Dict: {"type": "thinking", "content": str} for streaming thought
            Dict: {"type": "text", "content": str} for streaming text response
            Dict: {"type": "action", "content": dict} for final parsed action
        """
        try:
            response = requests.post(
                f"{self.base_url}/api/chat",
                json={
                    "model": self.model_name,
                    "messages": messages,
                    "stream": True,
                    "think": True,
                    "options": self.model_params
                },
                stream=True
            )
            
            full_response = ""
            full_thinking = ""
            
            for line in response.iter_lines():
                if line:
                    data = json.loads(line.decode('utf-8'))
                    msg = data.get("message", {})
                    
                    # 1. Handle "thinking" field (Qwen/DeepSeek reasoning models)
                    if "thinking" in msg and msg["thinking"]:
                        yield {"type": "thinking", "content": msg["thinking"]}
                        full_thinking += msg["thinking"]
                    
                    # 2. Handle "content" field
                    chunk = msg.get("content", "")
                    if chunk:
                        full_response += chunk
                        yield {"type": "text", "content": chunk}
                        
                    if data.get("done"):
                        break
            
            print(f"\n[DEBUG] Full Thinking:\n{full_thinking}\n")
            print(f"[DEBUG] Full Model Response (No Thinking):\n{full_response}\n[DEBUG] End Response\n")

            # Parse the final complete response
            action = self._parse_action(full_response)
            if not action and full_thinking:
                print("[DEBUG] Content empty or no action, trying to parse from Thinking...")
                # Fallback: sometimes models put the tool call inside the thought process or mixed
                action = self._parse_action(full_thinking + "\n" + full_response)
            
            if action:
                yield {"type": "action", "content": action}
            else:
                # Debugging: Inform user/logs that no tool call was found
                debug_msg = f"[DEBUG] NO TOOL CALL FOUND.\nFull Text: {full_response}\nFull Thinking: {full_thinking}"
                yield {"type": "text", "content": debug_msg}

        except Exception as e:
            print(f"VLM Error: {e}")
            yield {"type": "error", "content": str(e)}

    def _extract_json_candidates(self, text: str) -> List[str]:
        """
        Extracts all top-level text blocks wrapped in {} that might be JSON.
        Handles nested braces and strings to avoid false positives.
        """
        candidates = []
        brace_level = 0
        start_index = -1
        in_string = False
        escape = False
        
        for i, char in enumerate(text):
            if in_string:
                if escape:
                    escape = False
                elif char == '\\':
                    escape = True
                elif char == '"':
                    in_string = False
                continue
            
            if char == '"':
                in_string = True
                continue
                
            if char == '{':
                if brace_level == 0:
                    start_index = i
                brace_level += 1
            elif char == '}':
                if brace_level > 0:
                    brace_level -= 1
                    if brace_level == 0:
                        candidates.append(text[start_index:i+1])
                        
        return candidates

    def _parse_action(self, response_text: str) -> Dict[str, Any]:
        """
        Robustly extracts the JSON action from <tool_call> tags or raw text.
        """
        # 1. Try to find <tool_call> tags
        pattern = r"<tool_call>\s*(.*?)\s*</tool_call>"
        match = re.search(pattern, response_text, re.DOTALL)
        
        candidates = []
        if match:
            candidates.append(match.group(1))
        
        # 2. Extract all top-level JSON-like objects from the full text
        candidates.extend(self._extract_json_candidates(response_text))
        
        for json_str in candidates:
            json_str = json_str.replace("“", '"').replace("”", '"')
            
            try:
                data = json.loads(json_str)
                if isinstance(data, dict):
                    if "name" in data and "arguments" in data:
                        return data["arguments"]
                    if "action" in data:
                        return data
            except json.JSONDecodeError:
                continue
                
        return None
