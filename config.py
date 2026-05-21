"""
Centralized configuration for Pocket AI.
"""

# --- Model Configuration ---
RESPONDER_MODEL = "qwen3:1.7b"
OLLAMA_URL = "http://localhost:11434/api"
LOCAL_ROUTER_PATH = "./merged_model"
HF_ROUTER_REPO = "nlouis/pocket-ai-router"  # Hugging Face repo for auto-download
MAX_HISTORY = 20

# --- TTS Configuration ---
TTS_VOICE_MODEL = "en_GB-northern_english_male-medium"
TTS_MODEL_URL = "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_GB/northern_english_male/medium/en_GB-northern_english_male-medium.onnx"
TTS_CONFIG_URL = "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_GB/northern_english_male/medium/en_GB-northern_english_male-medium.onnx.json"

# --- STT Configuration ---
# Using RealTimeSTT for real-time speech-to-text
STT_MODEL_PATH = None  # Not used with RealTimeSTT (kept for compatibility)
STT_USE_WHISPER = False  # Not used with RealTimeSTT (kept for compatibility)
WHISPER_MODEL_SIZE = "base"  # Not used with RealTimeSTT (kept for compatibility)
WAKE_WORD_DETECTION_METHOD = "transcription"  # RealTimeSTT uses transcription-based detection
REALTIMESTT_MODEL = "base"  # RealTimeSTT model: "tiny", "base", "small", "medium", "large"
USE_PORCUPINE_WAKE_WORD = False  # Use Porcupine for wake word detection (more accurate, requires API key)
PORCUPINE_ACCESS_KEY = None  # Get from https://console.picovoice.ai/ (optional, for better wake word detection)
WAKE_WORD = "jarvis"
WAKE_WORD_SENSITIVITY = 0.4  # For audio pattern matching (0.0-1.0, higher = more sensitive) - Lowered to reduce false positives
WAKE_WORD_CONFIRMATION_COUNT = 1  # Require multiple detections before triggering (reduces false positives)
STT_SAMPLE_RATE = 16000
STT_CHUNK_SIZE = 4096
STT_RECORD_TIMEOUT = 5.0  # Maximum seconds to record after wake word

# --- Voice Assistant Configuration ---
VOICE_ASSISTANT_ENABLED = True
QWEN_TIMEOUT_SECONDS = 300  # 5 minutes of inactivity before sleep
QWEN_KEEP_ALIVE = "5m"  # Keep in memory for 5 minutes after last use

# --- Router Keywords ---
# REMOVED: ROUTER_KEYWORDS - All queries now go through Function Gemma router
# The router handles all routing decisions, so keyword-based bypass is no longer needed

# --- Function Definitions (Official JSON Schema) ---
FUNCTIONS = [
    {
        "type": "function",
        "function": {
            "name": "control_light",
            "description": "Controls smart lights - turn on, off, or dim lights in a room",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {"type": "string", "description": "The action to perform: on, off, or dim"},
                    "room": {"type": "string", "description": "The room name where the light is located"}
                },
                "required": ["action", "room"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "Searches the web for information using Google",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "The search query string"}
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "set_timer",
            "description": "Sets a countdown timer for a specified duration",
            "parameters": {
                "type": "object",
                "properties": {
                    "duration": {"type": "string", "description": "Time duration like 5 minutes or 1 hour"},
                    "label": {"type": "string", "description": "Optional timer name or label"}
                },
                "required": ["duration"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "create_calendar_event",
            "description": "Creates a new calendar event or appointment",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "The event title"},
                    "date": {"type": "string", "description": "The date of the event"},
                    "time": {"type": "string", "description": "The time of the event"},
                    "description": {"type": "string", "description": "Optional event details"}
                },
                "required": ["title", "date"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "read_calendar",
            "description": "Reads and retrieves calendar events for a date or time range",
            "parameters": {
                "type": "object",
                "properties": {
                    "date": {"type": "string", "description": "The date or date range to check"},
                    "filter": {"type": "string", "description": "Optional filter like meetings or appointments"}
                },
                "required": ["date"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "shell_exec",
            "description": "Execute a PowerShell or shell command on the local system. Use for: listing files, checking system info, running scripts, managing processes, checking network, installing packages, or any system operation the user requests explicitly.",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "The PowerShell/shell command to execute"},
                    "timeout": {"type": "integer", "description": "Timeout in seconds (default 30, max 120)"}
                },
                "required": ["command"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "passthrough",
            "description": "DEFAULT FUNCTION - Use this whenever no other function is clearly needed. This is the fallback for: greetings (hello, hi, good morning), chitchat (how are you, what's your name), general knowledge questions, explanations, conversations, and ANY query that does NOT explicitly require controlling lights, setting timers, searching the web, or managing calendar events. When in doubt, use passthrough.",
            "parameters": {
                "type": "object",
                "properties": {
                    "thinking": {"type": "boolean", "description": "Set to true for complex reasoning/math/logic, false for simple greetings and chitchat."}
                },
                "required": ["thinking"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "play_music",
            "description": "Play music by genre or artist on the default media player. Use when the user wants to listen to music.",
            "parameters": {
                "type": "object",
                "properties": {
                    "genre": {
                        "type": "string",
                        "description": "Music genre, e.g. jazz, rock, classical, blues, electro",
                    },
                    "artist": {
                        "type": "string",
                        "description": "Artist name, e.g. Ween, Miles Davis, Pink Floyd",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "control_media",
            "description": "Control media playback: pause, stop, or skip to next track.",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["pause", "stop", "next"],
                        "description": "Playback action to perform",
                    },
                },
                "required": ["action"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "set_volume",
            "description": "Control the volume of the default media player.",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["up", "down", "set"],
                        "description": "up/down for relative change, set for absolute level",
                    },
                    "level": {
                        "type": "number",
                        "description": "Volume level 0-100, required when action is set",
                    },
                },
                "required": ["action"],
            },
        },
    },
]

# --- Console Colors ---
GRAY = "\033[90m"
RESET = "\033[0m"
BOLD = "\033[1m"
CYAN = "\033[36m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
