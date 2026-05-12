"""
Model Persistence Manager - Manages which models stay loaded and which can sleep.
"""

import threading
import time
import requests
from typing import Optional
from config import (
    RESPONDER_MODEL, OLLAMA_URL, QWEN_TIMEOUT_SECONDS, 
    QWEN_KEEP_ALIVE, GRAY, RESET, CYAN
)
from core.model_manager import get_running_models, sync_unload_model


class QwenModelManager:
    """Manages Qwen model lifecycle - load, keep alive, and sleep."""
    
    def __init__(self):
        self.model_name = RESPONDER_MODEL
        self.last_used_time: Optional[float] = None
        self.is_loaded = False
        self.lock = threading.RLock()  # Re-entrant: timeout loop holds lock then calls unload()
        self.timeout_thread: Optional[threading.Thread] = None
        self.monitoring = False
        self.http_session = requests.Session()
    
    def ensure_loaded(self) -> bool:
        """Ensure Qwen model is loaded. Load if not already loaded."""
        with self.lock:
            if self.is_loaded:
                # Update last used time
                self.last_used_time = time.time()
                return True
            
            # Check if already running in Ollama (persistence restart case)
            running_models = get_running_models()
            if self.model_name in running_models or any(self.model_name in m for m in running_models):
                print(f"{CYAN}[QwenManager] {self.model_name} already running in Ollama.{RESET}")
                self.is_loaded = True
                self.last_used_time = time.time()
                self._start_timeout_monitor()
                return True
            
            # Load the model
            try:
                print(f"{CYAN}[QwenManager] Loading {self.model_name}...{RESET}")
                response = self.http_session.post(
                    f"{OLLAMA_URL}/generate",
                    json={
                        "model": self.model_name,
                        "prompt": "hi",
                        "stream": False,
                        "keep_alive": QWEN_KEEP_ALIVE,
                        "options": {"num_predict": 1}
                    },
                    timeout=120
                )
                
                if response.status_code == 200:
                    self.is_loaded = True
                    self.last_used_time = time.time()
                    print(f"{CYAN}[QwenManager] {self.model_name} loaded.{RESET}")
                    
                    # Start timeout monitoring
                    self._start_timeout_monitor()
                    return True
                else:
                    print(f"{GRAY}[QwenManager] Failed to load {self.model_name}: {response.status_code}{RESET}")
                    return False
            except Exception as e:
                print(f"{GRAY}[QwenManager] Error loading {self.model_name}: {e}{RESET}")
                return False
    
    def mark_used(self):
        """Mark model as used (update timestamp)."""
        with self.lock:
            self.last_used_time = time.time()
            if not self.is_loaded:
                self.ensure_loaded()
            elif self.monitoring:
                # Restart timeout monitoring
                self._start_timeout_monitor()
    
    def unload(self, reason: str = "manual"):
        """Unload Qwen model to free VRAM."""
        with self.lock:
            if not self.is_loaded:
                return
            
            try:
                print(f"{GRAY}[QwenManager] Unloading {self.model_name} ({reason})...{RESET}")
                sync_unload_model(self.model_name)
                self.is_loaded = False
                self.last_used_time = None
                self.monitoring = False
                print(f"{GRAY}[QwenManager] {self.model_name} unloaded.{RESET}")
            except Exception as e:
                print(f"{GRAY}[QwenManager] Error unloading {self.model_name}: {e}{RESET}")
    
    def _start_timeout_monitor(self):
        """Start or restart timeout monitoring thread."""
        self.monitoring = True
        
        # Stop existing thread if any
        if self.timeout_thread and self.timeout_thread.is_alive():
            # Thread will check self.monitoring and exit
            pass
        
        # Start new monitoring thread
        self.timeout_thread = threading.Thread(
            target=self._timeout_monitor_loop,
            daemon=True
        )
        self.timeout_thread.start()
    
    def _timeout_monitor_loop(self):
        """Monitor for timeout and unload model if inactive."""
        while self.monitoring:
            time.sleep(10)  # Check every 10 seconds
            
            with self.lock:
                if not self.monitoring or not self.is_loaded:
                    break
                
                if self.last_used_time is None:
                    continue
                
                elapsed = time.time() - self.last_used_time
                
                if elapsed >= QWEN_TIMEOUT_SECONDS:
                    print(f"{GRAY}[QwenManager] Timeout reached ({elapsed:.0f}s), unloading {self.model_name}...{RESET}")
                    self.unload("timeout")
                    break
    
    def check_status(self) -> dict:
        """Get current status of Qwen model."""
        with self.lock:
            running_models = get_running_models()
            is_running = self.model_name in running_models or any(
                self.model_name in m for m in running_models
            )
            
            return {
                "is_loaded": self.is_loaded,
                "is_running": is_running,
                "last_used": self.last_used_time,
                "time_since_use": time.time() - self.last_used_time if self.last_used_time else None
            }


# Global Qwen model manager instance
qwen_manager = QwenModelManager()


def ensure_qwen_loaded() -> bool:
    """Ensure Qwen model is loaded. Public interface."""
    return qwen_manager.ensure_loaded()


def mark_qwen_used():
    """Mark Qwen model as used. Public interface."""
    qwen_manager.mark_used()


def unload_qwen(reason: str = "manual"):
    """Unload Qwen model. Public interface."""
    qwen_manager.unload(reason)


def get_qwen_status() -> dict:
    """Get Qwen model status. Public interface."""
    return qwen_manager.check_status()
