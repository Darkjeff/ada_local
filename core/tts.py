"""
TTS (Text-to-Speech) module using Piper TTS executable.
Provides streaming sentence-based synthesis with interrupt support.
Supports Windows (piper.exe) and Linux (piper) via platform detection.
"""

import io
import os
import re
import queue
import shutil
import subprocess
import tarfile
import threading
import zipfile
import platform
import requests
from pathlib import Path

import numpy as np
import sounddevice as sd

# ANSI colors for console output
GRAY = "\033[90m"
CYAN = "\033[36m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
RESET = "\033[0m"

# HTTP session for downloads
http_session = requests.Session()


class SentenceBuffer:
    """Buffers streaming text and extracts complete sentences."""
    
    SENTENCE_ENDINGS = re.compile(r'([.!?])\s+|([.!?])$')
    
    def __init__(self):
        self.buffer = ""
    
    def add(self, text):
        """Add text chunk and return any complete sentences."""
        self.buffer += text
        sentences = []
        
        while True:
            match = self.SENTENCE_ENDINGS.search(self.buffer)
            if match:
                end_pos = match.end()
                sentence = self.buffer[:end_pos].strip()
                if sentence:
                    sentences.append(sentence)
                self.buffer = self.buffer[end_pos:]
            else:
                break
        
        return sentences
    
    def flush(self):
        """Return any remaining text as a final sentence."""
        remaining = self.buffer.strip()
        self.buffer = ""
        return remaining if remaining else None


class PiperTTS:
    """Piper TTS wrapper using pre-built executable for Windows compatibility."""
    
    VOICE_MODEL = "en_GB-northern_english_male-medium"
    MODEL_URL = "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_GB/northern_english_male/medium/en_GB-northern_english_male-medium.onnx"
    CONFIG_URL = "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_GB/northern_english_male/medium/en_GB-northern_english_male-medium.onnx.json"
    
    PIPER_VERSION = "2023.11.14-2"
    
    def __init__(self):
        self.enabled = False
        self.piper_exe = None
        self.model_path = None
        self.speech_queue = queue.Queue()
        self.worker_thread = None
        self.running = False
        self.interrupt_event = threading.Event()
        self.piper_dir = Path.home() / ".local" / "share" / "piper"
        self.models_dir = self.piper_dir / "voices"
        self.current_process = None
        self.available = True  # We'll check during initialize
    
    def _get_piper_release_info(self):
        """Return (download_url, subdir, exe_name, archive_type) for the current OS/arch."""
        system = platform.system()
        machine = platform.machine().lower()
        base = f"https://github.com/rhasspy/piper/releases/download/{self.PIPER_VERSION}"

        if system == "Windows":
            return (f"{base}/piper_windows_amd64.zip", "piper_windows", "piper.exe", "zip")
        elif system == "Linux":
            arch = "aarch64" if ("aarch64" in machine or "arm64" in machine) else "x86_64"
            return (f"{base}/piper_linux_{arch}.tar.gz", "piper_linux", "piper", "tar")
        else:
            raise RuntimeError(f"[TTS] Unsupported OS: {system}")

    def _download_piper_executable(self):
        """Download and extract Piper executable for the current OS."""
        release_url, exe_subdir, exe_name, archive_type = self._get_piper_release_info()

        piper_exe_dir = self.piper_dir / exe_subdir
        piper_exe = piper_exe_dir / exe_name

        if piper_exe.exists():
            print(f"{GREEN}[TTS] ✓ Piper executable found{RESET}")
            return str(piper_exe)

        print(f"{CYAN}[TTS] Downloading Piper executable ({platform.system()})...{RESET}")
        self.piper_dir.mkdir(parents=True, exist_ok=True)

        try:
            r = http_session.get(release_url, stream=True)
            r.raise_for_status()

            archive_data = io.BytesIO()
            total_size = int(r.headers.get('content-length', 0))
            downloaded = 0

            for chunk in r.iter_content(chunk_size=8192):
                archive_data.write(chunk)
                downloaded += len(chunk)
                if total_size > 0:
                    pct = (downloaded / total_size) * 100
                    print(f"\r{CYAN}[TTS] Downloading... {pct:.1f}%{RESET}", end="", flush=True)

            print()
            archive_data.seek(0)
            piper_exe_dir.mkdir(parents=True, exist_ok=True)

            if archive_type == "zip":
                with zipfile.ZipFile(archive_data, 'r') as zf:
                    for member in zf.namelist():
                        if member.startswith("piper/"):
                            target_path = piper_exe_dir / member[6:]
                            if member.endswith('/'):
                                target_path.mkdir(parents=True, exist_ok=True)
                            else:
                                target_path.parent.mkdir(parents=True, exist_ok=True)
                                with zf.open(member) as src, open(target_path, 'wb') as dst:
                                    dst.write(src.read())
            elif archive_type == "tar":
                with tarfile.open(fileobj=archive_data, mode='r:gz') as tf:
                    for member in tf.getmembers():
                        if member.name.startswith("piper/"):
                            member.name = member.name[6:]  # strip "piper/" prefix
                            if member.name:
                                tf.extract(member, path=str(piper_exe_dir))

            # Ensure the Linux binary is executable
            if platform.system() == "Linux" and piper_exe.exists():
                piper_exe.chmod(piper_exe.stat().st_mode | 0o111)

            print(f"{GREEN}[TTS] ✓ Piper executable extracted!{RESET}")
            return str(piper_exe)

        except Exception as e:
            print(f"{YELLOW}[TTS] Failed to download Piper executable: {e}{RESET}")
            return None
    
    def _download_model(self):
        """Download voice model if not present."""
        self.models_dir.mkdir(parents=True, exist_ok=True)
        model_path = self.models_dir / f"{self.VOICE_MODEL}.onnx"
        config_path = self.models_dir / f"{self.VOICE_MODEL}.onnx.json"
        
        if not model_path.exists():
            print(f"{CYAN}[TTS] Downloading voice model ({self.VOICE_MODEL})...{RESET}")
            r = http_session.get(self.MODEL_URL, stream=True)
            r.raise_for_status()
            with open(model_path, 'wb') as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)
            r = http_session.get(self.CONFIG_URL)
            r.raise_for_status()
            with open(config_path, 'wb') as f:
                f.write(r.content)
            print(f"{GREEN}[TTS] ✓ Model downloaded!{RESET}")
        
        return str(model_path)
    
    def initialize(self):
        """Set up Piper executable and voice model."""
        try:
            print(f"{CYAN}[TTS] Initializing Piper TTS (executable mode)...{RESET}")
            
            # Download/find piper executable
            self.piper_exe = self._download_piper_executable()
            if not self.piper_exe:
                print(f"{YELLOW}[TTS] Could not set up Piper executable{RESET}")
                self.available = False
                return False
            
            # Download/find voice model
            self.model_path = self._download_model()
            
            # Test the executable
            try:
                result = subprocess.run(
                    [self.piper_exe, "--version"],
                    capture_output=True,
                    text=True,
                    timeout=10
                )
                print(f"{CYAN}[TTS] Piper version: {result.stdout.strip()}{RESET}")
            except Exception as e:
                print(f"{YELLOW}[TTS] Warning: Could not get Piper version: {e}{RESET}")
            
            # Start the worker thread
            self.running = True
            self.worker_thread = threading.Thread(target=self._speech_worker, daemon=True)
            self.worker_thread.start()
            
            print(f"{GREEN}[TTS] ✓ Piper TTS ready ({self.VOICE_MODEL}){RESET}")
            return True
            
        except Exception as e:
            print(f"{YELLOW}[TTS] Failed to initialize: {e}{RESET}")
            import traceback
            traceback.print_exc()
            return False
    
    def _speech_worker(self):
        """Background thread that plays queued sentences."""
        while self.running:
            try:
                if self.interrupt_event.is_set():
                    self.interrupt_event.clear()
                
                text = self.speech_queue.get(timeout=0.5)
                if text is None:
                    break
                
                if self.interrupt_event.is_set():
                    self.speech_queue.task_done()
                    continue

                self._speak_text(text)
                self.speech_queue.task_done()
            except queue.Empty:
                continue
    
    def _speak_text(self, text):
        """Synthesize and play text using Piper executable."""
        if not self.piper_exe or not self.model_path or not text.strip():
            return
        
        try:
            # Run piper and capture raw audio output
            cmd = [
                self.piper_exe,
                "--model", self.model_path,
                "--output-raw"
            ]
            
            self.current_process = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            )
            
            # Send text to piper
            stdout, stderr = self.current_process.communicate(
                input=text.encode('utf-8'),
                timeout=30
            )
            
            if self.interrupt_event.is_set():
                self.current_process = None
                return
            
            if self.current_process.returncode != 0:
                print(f"{YELLOW}[TTS] Piper error: {stderr.decode('utf-8', errors='ignore')}{RESET}")
                self.current_process = None
                return
            
            self.current_process = None
            
            # Play the audio (Piper outputs 16-bit PCM at 22050 Hz)
            if stdout and not self.interrupt_event.is_set():
                audio_data = np.frombuffer(stdout, dtype=np.int16)
                sd.play(audio_data, samplerate=22050, blocking=True)
                
        except subprocess.TimeoutExpired:
            print(f"{YELLOW}[TTS] Synthesis timeout{RESET}")
            if self.current_process:
                self.current_process.kill()
                self.current_process = None
        except Exception as e:
            print(f"{YELLOW}[TTS Error]: {e}{RESET}")
            import traceback
            traceback.print_exc()
    
    def queue_sentence(self, sentence):
        """Add a sentence to the speech queue."""
        if self.enabled and self.piper_exe and sentence.strip():
            self.speech_queue.put(sentence)
    
    def stop(self):
        """Interrupt current speech and clear queue."""
        self.interrupt_event.set()
        with self.speech_queue.mutex:
            self.speech_queue.queue.clear()
        
        # Stop current playback
        try:
            sd.stop()
        except:
            pass
        
        # Kill current piper process if running
        if self.current_process:
            try:
                self.current_process.kill()
            except:
                pass
            
    def wait_for_completion(self):
        """Wait for all queued speech to finish."""
        if self.enabled:
            self.speech_queue.join()
    
    def toggle(self, enable):
        """Enable/disable TTS."""
        if enable and not self.piper_exe:
            if self.initialize():
                self.enabled = True
                return True
            return False
        self.enabled = enable
        return True
    
    def shutdown(self):
        """Clean up resources."""
        self.running = False
        self.stop()
        self.speech_queue.put(None)


# Global TTS instance
tts = PiperTTS()
