"""
Speech-to-Text with Wake Word Detection for Voice Assistant.

RealtimeSTT tourne dans un sous-processus isolé pour éviter tout conflit
entre PyAudio/PortAudio, les mp.Queue, et la boucle événementielle Qt.
Le processus parent (Qt) communique avec le sous-processus via une Queue.
"""

import queue
import threading
import multiprocessing
import time
from typing import Callable

from config import (
    WAKE_WORD, REALTIMESTT_MODEL, WAKE_WORD_SENSITIVITY,
    USE_PORCUPINE_WAKE_WORD, PORCUPINE_ACCESS_KEY,
    GRAY, RESET, CYAN, YELLOW, GREEN
)


# ─────────────────────────────────────────────────────────────────────────────
# Fonction de travail du sous-processus
# Doit être au niveau module (non imbriquée) pour être picklable avec "spawn".
# ─────────────────────────────────────────────────────────────────────────────

def _stt_subprocess_worker(result_queue, shutdown_event,
                            wake_word, model_name, device,
                            use_porcupine, porcupine_key,
                            wake_sensitivity):
    """
    Tourne dans un processus fils isolé.
    Envoie des dicts {'type': ...} dans result_queue.
    Types : 'ready', 'wake_word', 'speech', 'error'
    """
    import os
    os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
    os.environ.setdefault("OMP_NUM_THREADS", "1")

    recorder = None
    try:
        from RealtimeSTT import AudioToTextRecorder

        recorder_kwargs = dict(
            model=model_name,
            language="en",
            device=device,
            spinner=False,
        )

        if use_porcupine and porcupine_key:
            recorder_kwargs.update(dict(
                wakeword_backend="pvporcupine",
                wake_words=wake_word,
                wake_words_sensitivity=wake_sensitivity,
                porcupine_access_key=porcupine_key,
            ))

        recorder = AudioToTextRecorder(**recorder_kwargs)
        result_queue.put({'type': 'ready'})

        while not shutdown_event.is_set():
            text = recorder.text()
            if not (text and text.strip()):
                continue

            # Détection par transcription si Porcupine n'est pas activé
            if not (use_porcupine and porcupine_key):
                if wake_word.lower() not in text.lower():
                    continue
                result_queue.put({'type': 'wake_word'})

            clean = (text
                     .replace(wake_word, '')
                     .replace(wake_word.capitalize(), '')
                     .strip())
            if clean:
                result_queue.put({'type': 'speech', 'text': clean})

    except Exception as exc:
        result_queue.put({'type': 'error', 'message': str(exc)})
    finally:
        if recorder is not None:
            try:
                recorder.shutdown()
            except Exception:
                pass


# ─────────────────────────────────────────────────────────────────────────────
# Classe principale — utilisée par le processus Qt
# ─────────────────────────────────────────────────────────────────────────────

class STTListener:
    """
    Lance RealtimeSTT dans un sous-processus spawn isolé.
    Reçoit les résultats via un thread de polling léger.
    """

    def __init__(self, wake_word_callback: Callable, speech_callback: Callable):
        self.wake_word_callback = wake_word_callback
        self.speech_callback = speech_callback
        self.running = False
        self.initialized = False

        self._process = None
        self._result_queue = None
        self._shutdown_event = None
        self._poll_thread = None

        print(f"{CYAN}[STT] STT initialisé (sous-processus isolé){RESET}")
        print(f"{CYAN}[STT] Wake word : '{WAKE_WORD}'{RESET}")

    def initialize(self) -> bool:
        """Démarre le sous-processus STT et attend qu'il soit prêt."""
        try:
            import torch
            cuda_available = torch.cuda.is_available()
            device = "cuda" if cuda_available else "cpu"
            mode = "Porcupine" if (USE_PORCUPINE_WAKE_WORD and PORCUPINE_ACCESS_KEY) else "transcription"
            print(f"{CYAN}[STT] Démarrage sous-processus (device={device}, mode={mode})...{RESET}")

            ctx = multiprocessing.get_context("spawn")
            self._result_queue = ctx.Queue()
            self._shutdown_event = ctx.Event()

            self._process = ctx.Process(
                target=_stt_subprocess_worker,
                args=(
                    self._result_queue,
                    self._shutdown_event,
                    WAKE_WORD,
                    REALTIMESTT_MODEL,
                    device,
                    USE_PORCUPINE_WAKE_WORD,
                    PORCUPINE_ACCESS_KEY,
                    WAKE_WORD_SENSITIVITY,
                ),
                daemon=True,
                name="STTWorker",
            )
            self._process.start()

            print(f"{CYAN}[STT] Chargement du modèle Whisper (peut prendre quelques minutes au premier démarrage)...{RESET}")

            # Attendre 'ready' — peut inclure le téléchargement du modèle
            try:
                msg = self._result_queue.get(timeout=300)
            except queue.Empty:
                print(f"{GRAY}[STT] ✗ Délai dépassé (5 min) en attendant le sous-processus STT{RESET}")
                self._terminate_process()
                return False

            if msg.get('type') == 'error':
                print(f"{GRAY}[STT] ✗ Erreur dans le sous-processus : {msg.get('message')}{RESET}")
                self._terminate_process()
                return False

            if msg.get('type') != 'ready':
                print(f"{GRAY}[STT] ✗ Message inattendu : {msg}{RESET}")
                self._terminate_process()
                return False

            self.initialized = True
            print(f"{GREEN}[STT] ✓ Sous-processus STT prêt (modèle : {REALTIMESTT_MODEL}){RESET}")
            return True

        except ImportError:
            print(f"{GRAY}[STT] ✗ RealtimeSTT non installé. Installer avec : pip install realtimestt{RESET}")
            return False
        except Exception as e:
            print(f"{GRAY}[STT] ✗ Échec du démarrage du sous-processus : {e}{RESET}")
            import traceback
            traceback.print_exc()
            return False

    def _on_wakeword_detected(self):
        print(f"\n{CYAN}[STT] 👂 Wake word '{WAKE_WORD}' détecté ! Écoute...{RESET}")
        if self.wake_word_callback:
            self.wake_word_callback()

    def start(self) -> bool:
        """Démarre le thread de polling des résultats."""
        if not self.initialized:
            print(f"{YELLOW}[STT] Non initialisé. Appeler initialize() d'abord.{RESET}")
            return False
        if self.running:
            return True

        self.running = True
        self._poll_thread = threading.Thread(
            target=self._poll_results,
            daemon=True,
            name="STTPoll",
        )
        self._poll_thread.start()
        print(f"{CYAN}[STT] ✓ Écoute démarrée{RESET}")
        return True

    def _poll_results(self):
        """Lit la queue et dispatch les callbacks vers le processus Qt."""
        while self.running:
            try:
                msg = self._result_queue.get(timeout=0.2)
                mtype = msg.get('type')

                if mtype == 'wake_word':
                    self._on_wakeword_detected()
                elif mtype == 'speech':
                    text = msg.get('text', '').strip()
                    if text:
                        print(f"{CYAN}[STT] 🔊 Reconnu : '{text}'{RESET}")
                        self.speech_callback(text)
                elif mtype == 'error':
                    print(f"{GRAY}[STT] ✗ Erreur sous-processus : {msg.get('message')}{RESET}")
                    self.running = False

            except queue.Empty:
                # Vérifier si le sous-processus est mort de manière inattendue
                if self._process and not self._process.is_alive():
                    print(f"{GRAY}[STT] ✗ Le sous-processus STT s'est arrêté de façon inattendue{RESET}")
                    self.running = False
            except Exception as e:
                print(f"{GRAY}[STT] Erreur de polling : {e}{RESET}")

    def stop(self):
        """Arrête proprement le polling et le sous-processus."""
        self.running = False
        self._terminate_process()
        if self._poll_thread and self._poll_thread.is_alive():
            self._poll_thread.join(timeout=2.0)
        print(f"{CYAN}[STT] Arrêté{RESET}")

    def _terminate_process(self):
        if self._shutdown_event:
            try:
                self._shutdown_event.set()
            except Exception:
                pass
        if self._process and self._process.is_alive():
            self._process.terminate()
            self._process.join(timeout=5.0)



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

            # Pre-trust silero-vad so RealTimeSTT's VAD engine doesn't fail
            # with "Untrusted repository" on newer PyTorch versions.
            try:
                torch.hub.load(
                    "snakers4/silero-vad", "silero_vad",
                    trust_repo=True, verbose=False
                )
                print(f"{CYAN}[STT] silero-vad pre-loaded (trusted){RESET}")
            except Exception as _e:
                print(f"{GRAY}[STT] silero-vad pre-load skipped: {_e}{RESET}")

            # Check CUDA availability
            cuda_available = torch.cuda.is_available()
            if cuda_available:
                cuda_device = torch.cuda.current_device()
                cuda_name = torch.cuda.get_device_name(cuda_device)
                print(f"{GREEN}[STT] ✓ CUDA is available (Device: {cuda_name}){RESET}")
            else:
                print(f"{YELLOW}[STT] ⚠ CUDA is not available, will use CPU{RESET}")
            
            device = "cuda" if cuda_available else "cpu"
            print(f"{CYAN}[STT] Initializing AudioToTextRecorder with device='{device}'...{RESET}")

            recorder_kwargs = dict(
                model=REALTIMESTT_MODEL,
                language="en",
                device=device,
                spinner=False,
            )

            if USE_PORCUPINE_WAKE_WORD and PORCUPINE_ACCESS_KEY:
                print(f"{CYAN}[STT] Wake word mode: Porcupine hardware detection{RESET}")
                recorder_kwargs.update(dict(
                    wakeword_backend="pvporcupine",
                    wake_words=WAKE_WORD,
                    wake_words_sensitivity=WAKE_WORD_SENSITIVITY,
                    on_wakeword_detected=self._on_wakeword_detected,
                    porcupine_access_key=PORCUPINE_ACCESS_KEY,
                ))
            else:
                print(f"{CYAN}[STT] Wake word mode: transcription-based detection{RESET}")

            self.recorder = AudioToTextRecorder(**recorder_kwargs)
            
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

                # recorder.text() blocks until speech is detected
                transcription_start = time.time()
                text = self.recorder.text()
                transcription_time = time.time() - transcription_start

                print(f"{CYAN}[STT] ✓ Transcription completed in {transcription_time:.2f}s{RESET}")
                print(f"{CYAN}[STT] 📝 Raw transcribed text: '{text}'{RESET}")

                if text and text.strip():
                    # In transcription-based mode, check that the text contains the wake word
                    if not (USE_PORCUPINE_WAKE_WORD and PORCUPINE_ACCESS_KEY):
                        if WAKE_WORD.lower() not in text.lower():
                            print(f"{GRAY}[STT] ⚠ Wake word not found, ignoring: '{text}'{RESET}")
                            continue
                        self._on_wakeword_detected()

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
        recorder = self.recorder
        self.recorder = None  # detach early so _run_listener exits
        if recorder:
            # recorder.shutdown() can block indefinitely on audio hardware;
            # run it in a daemon thread and abandon it after 8 seconds.
            def _shutdown():
                try:
                    recorder.shutdown()
                except Exception:
                    pass
            t = threading.Thread(target=_shutdown, daemon=True)
            t.start()
            t.join(timeout=8.0)
            if t.is_alive():
                print(f"{GRAY}[STT] recorder.shutdown() did not return in 8s — abandoning{RESET}")
        if self.listening_thread and self.listening_thread.is_alive():
            self.listening_thread.join(timeout=5.0)
            if self.listening_thread.is_alive():
                print(f"{GRAY}[STT] Thread still alive after 5s — forcing exit{RESET}")
        print(f"{CYAN}[STT] Listener stopped{RESET}")
