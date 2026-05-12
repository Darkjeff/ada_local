"""
Speech-to-Text with Wake Word Detection for Voice Assistant.
Uses RealTimeSTT for real-time transcription with built-in wake word detection.
"""

import threading
import time
from typing import Optional, Callable
from config import (
    WAKE_WORD, REALTIMESTT_MODEL, WAKE_WORD_SENSITIVITY,
    GRAY, RESET, CYAN, YELLOW, GREEN
)


class STTListener:
    """
    Real-time STT listener with wake word detection using RealTimeSTT.
    Uses RealTimeSTT's built-in wake word detection and text() method.
    """
    
    def __init__(self, wake_word_callback: Callable, speech_callback: Callable):
        self.wake_word_callback = wake_word_callback
        self.speech_callback = speech_callback
        self.running = False
        self.listening_thread = None
        
        # RealTimeSTT recorder
        self.recorder = None
        self.initialized = False
        
        print(f"{CYAN}[STT] Initializing RealTimeSTT listener...{RESET}")
        print(f"{CYAN}[STT] Wake word: '{WAKE_WORD}'{RESET}")
        print(f"{CYAN}[STT] Detection method: RealTimeSTT built-in wake word detection{RESET}")
    
    def initialize(self) -> bool:
        """Initialize RealTimeSTT with wake word detection."""
        try:
            from RealtimeSTT import AudioToTextRecorder
            import torch
            
            print(f"{CYAN}[STT] Loading RealTimeSTT...{RESET}")
            
            # Check CUDA availability
            cuda_available = torch.cuda.is_available()
            if cuda_available:
                cuda_device = torch.cuda.current_device()
                cuda_name = torch.cuda.get_device_name(cuda_device)
                print(f"{GREEN}[STT] ✓ CUDA is available (Device: {cuda_name}){RESET}")
            else:
                print(f"{YELLOW}[STT] ⚠ CUDA is not available, will use CPU{RESET}")
            
            print(f"{CYAN}[STT] Initializing AudioToTextRecorder with device='cuda'...{RESET}")
            
            # Initialize RealTimeSTT with built-in wake word detection
            # Using pvporcupine backend since "jarvis" is a predefined Porcupine wake word
            self.recorder = AudioToTextRecorder(
                model=REALTIMESTT_MODEL,  # Use configured model (base, small, etc.)
                language="en",
                device="cuda",  # Use GPU for faster processing
                spinner=False,  # Disable spinner for cleaner output
                wakeword_backend="pvporcupine",  # Use Porcupine for wake word detection
                wake_words=WAKE_WORD,  # Built-in wake word detection
                wake_words_sensitivity=WAKE_WORD_SENSITIVITY,  # Sensitivity (0.0-1.0)
                on_wakeword_detected=self._on_wakeword_detected,
            )
            
            # Verify device after initialization
            if hasattr(self.recorder, 'model') and hasattr(self.recorder.model, 'device'):
                actual_device = str(self.recorder.model.device)
                print(f"{GREEN}[STT] ✓ Model device: {actual_device}{RESET}")
            elif hasattr(self.recorder, '_device'):
                print(f"{GREEN}[STT] ✓ Recorder device: {self.recorder._device}{RESET}")
            
            self.initialized = True
            print(f"{CYAN}[STT] ✓ RealTimeSTT initialized successfully (model: {REALTIMESTT_MODEL}, wake word: '{WAKE_WORD}'){RESET}")
            return True
        except ImportError:
            print(f"{GRAY}[STT] ✗ RealTimeSTT not installed. Install with: pip install realtimestt{RESET}")
            return False
        except Exception as e:
            print(f"{GRAY}[STT] ✗ RealTimeSTT initialization error: {e}{RESET}")
            import traceback
            traceback.print_exc()
            return False
    
    def _on_wakeword_detected(self):
        """Callback when wake word is detected."""
        print(f"\n{CYAN}[STT] 👂 Wake word '{WAKE_WORD}' detected! Listening...{RESET}")
        # Notify callback if set
        if self.wake_word_callback:
            self.wake_word_callback()

    def start(self):
        """Start listening."""
        if not self.initialized:
            print(f"{YELLOW}[STT] Not initialized. Call initialize() first.{RESET}")
            return False
        
        if self.running:
            print(f"{YELLOW}[STT] Already running.{RESET}")
            return True
        
        self.running = True
        print(f"{CYAN}[STT] Starting RealTimeSTT listener...{RESET}")
        
        # Start RealTimeSTT in a background thread
        try:
            self.listening_thread = threading.Thread(
                target=self._run_listener,
                daemon=True
            )
            self.listening_thread.start()
            print(f"{CYAN}[STT] ✓ Listener started{RESET}")
            return True
        except Exception as e:
            print(f"{GRAY}[STT] Failed to start listener: {e}{RESET}")
            self.running = False
            return False
    
    def _run_listener(self):
        """Main listening loop using RealTimeSTT's text() method."""
        try:
            print(f"{GRAY}[STT] 🔄 Starting transcription loop...{RESET}")
            while self.running:
                if not self.recorder:
                    break
                
                print(f"{GRAY}[STT] ⏳ Waiting for wake word '{WAKE_WORD}'...{RESET}")
                
                # recorder.text() blocks until wake word is detected, then returns transcribed text
                transcription_start = time.time()
                text = self.recorder.text()
                transcription_time = time.time() - transcription_start
                
                print(f"{CYAN}[STT] ✓ Transcription completed in {transcription_time:.2f}s{RESET}")
                print(f"{CYAN}[STT] 📝 Raw transcribed text: '{text}'{RESET}")
                
                if text and text.strip():
                    # Remove wake word from the text if present
                    text_clean = text.replace(WAKE_WORD, "").replace(WAKE_WORD.capitalize(), "").strip()
                    
                    print(f"{CYAN}[STT] 🧹 Cleaned text (after removing wake word): '{text_clean}'{RESET}")
                    
                    if text_clean:
                        print(f"{CYAN}[STT] 🔊 Speech recognized: '{text_clean}'{RESET}")
                        
                        # Pass transcribed speech to callback
                        self.speech_callback(text_clean)
                    else:
                        print(f"{GRAY}[STT] ⚠ Text is empty after cleaning, skipping...{RESET}")
                else:
                    print(f"{GRAY}[STT] ⚠ No text received or text is empty{RESET}")
                
        except Exception as e:
            print(f"{GRAY}[STT] Listener error: {e}{RESET}")
            import traceback
            traceback.print_exc()
            self.running = False
    
    def stop(self):
        """Stop listening and wait for the thread to fully terminate."""
        self.running = False
        if self.recorder:
            try:
                print(f"{CYAN}[STT] Shutting down recorder...{RESET}")
                self.recorder.shutdown()
            except Exception as e:
                print(f"{GRAY}[STT] Error stopping recorder: {e}{RESET}")
            finally:
                self.recorder = None  # release ctranslate2 model + thread pool
        if self.listening_thread and self.listening_thread.is_alive():
            self.listening_thread.join(timeout=10.0)
            if self.listening_thread.is_alive():
                print(f"{GRAY}[STT] Thread still alive after 10s — forcing exit{RESET}")
        print(f"{CYAN}[STT] Listener stopped{RESET}")
