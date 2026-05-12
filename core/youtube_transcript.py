"""
YouTube ingestion pipeline — transcript retrieval, validation, chunking, metadata.
This module NEVER calls an LLM. It only produces structured data for the caller.
"""

import html
import re
from dataclasses import dataclass, field
from typing import Optional


# ── Constants ──────────────────────────────────────────────────────────────────

MIN_TRANSCRIPT_CHARS = 200     # Reject transcripts shorter than this
MAX_CHUNK_CHARS = 3500         # ~875 tokens — safe for qwen3:1.7b
CHUNK_OVERLAP_CHARS = 150      # Rolling overlap between chunks
NOISE_RATIO_THRESHOLD = 0.4   # Max fraction of noise markers allowed

_NOISE_RE = re.compile(
    r"\[(?:Music|Applause|Laughter|Inaudible|Silence|Música|Musique|Rires|"
    r"Applaudissements|Captions by|CC by)[^\]]*\]"
    r"|♪+|\[__\]|\[BLANK_AUDIO\]",
    re.IGNORECASE,
)

_YT_PATTERNS = [
    r"(?:youtube\.com/watch\?(?:[^&\s]*&)*v=|youtu\.be/)([A-Za-z0-9_-]{11})",
    r"(?:youtube\.com/embed/)([A-Za-z0-9_-]{11})",
    r"(?:youtube\.com/shorts/)([A-Za-z0-9_-]{11})",
]


# ── Data classes ───────────────────────────────────────────────────────────────

@dataclass
class YTPipelineResult:
    """Structured output of the full ingestion pipeline. Never contains LLM output."""
    success: bool
    video_id: str = ""
    transcript_found: bool = False
    language: str = ""
    clean_text: str = ""
    chunks: list = field(default_factory=list)
    chunk_count: int = 0
    total_chars: int = 0
    noise_ratio: float = 0.0
    confidence: float = 0.0
    error: str = ""

    def metadata(self) -> dict:
        return {
            "transcript_found": self.transcript_found,
            "language": self.language,
            "chunks": self.chunk_count,
            "confidence": round(self.confidence, 2),
            "total_chars": self.total_chars,
        }


# ── Public API ─────────────────────────────────────────────────────────────────

def extract_video_id(text: str) -> Optional[str]:
    """Return the 11-char YouTube video ID from any recognised URL format."""
    for pattern in _YT_PATTERNS:
        m = re.search(pattern, text)
        if m:
            return m.group(1)
    return None


def run_pipeline(text: str) -> YTPipelineResult:
    """
    Full ingestion pipeline: extract → retrieve → validate → clean → chunk.
    Returns YTPipelineResult. NEVER calls an LLM.
    """
    video_id = extract_video_id(text)
    if not video_id:
        return YTPipelineResult(
            success=False,
            error="Aucun identifiant YouTube valide trouvé dans le texte.",
        )

    raw_text, language, retrieval_error = _retrieve(video_id)

    if not raw_text:
        return YTPipelineResult(
            success=False,
            video_id=video_id,
            error=(
                "Impossible de récupérer une transcription exploitable pour cette vidéo."
                + (f" ({retrieval_error})" if retrieval_error else "")
            ),
        )

    # Validate
    valid, reason, clean_text, noise_ratio = _validate(raw_text)
    if not valid:
        return YTPipelineResult(
            success=False,
            video_id=video_id,
            transcript_found=True,
            language=language,
            error=f"Impossible de récupérer une transcription exploitable pour cette vidéo. ({reason})",
        )

    # Chunk
    chunks = _chunk(clean_text)
    confidence = _confidence(noise_ratio, len(clean_text), len(chunks))

    return YTPipelineResult(
        success=True,
        video_id=video_id,
        transcript_found=True,
        language=language,
        clean_text=clean_text,
        chunks=chunks,
        chunk_count=len(chunks),
        total_chars=len(clean_text),
        noise_ratio=noise_ratio,
        confidence=confidence,
    )


# ── Retrieval ──────────────────────────────────────────────────────────────────

def _retrieve(video_id: str) -> tuple[str, str, str]:
    """Try youtube-transcript-api first, then yt-dlp. Returns (text, language, error)."""
    text, lang, err = _retrieve_via_api(video_id)
    if text:
        return text, lang, ""
    text, lang, _ = _retrieve_via_ytdlp(video_id)
    if text:
        return text, lang, ""
    return "", "", err


def _retrieve_via_api(video_id: str) -> tuple[str, str, str]:
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
    except ImportError:
        return "", "", "youtube-transcript-api not installed"

    try:
        # 1.x API (instance-based)
        api = YouTubeTranscriptApi()
        transcript_list = api.list(video_id)
    except TypeError:
        # 0.x API (class-method-based)
        try:
            transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
        except Exception as e:
            return "", "", str(e)
    except Exception as e:
        return "", "", str(e)

    transcript = _pick_transcript(transcript_list)
    if not transcript:
        return "", "", "No transcript available"

    try:
        fetched = transcript.fetch()
        lang = transcript.language_code
    except Exception as e:
        return "", "", str(e)

    parts = []
    for entry in fetched:
        t = entry.get("text", "") if isinstance(entry, dict) else getattr(entry, "text", "")
        parts.append(html.unescape(t))

    raw = re.sub(r"\s+", " ", " ".join(parts)).strip()
    return raw, lang, ""


def _pick_transcript(transcript_list):
    """Return the best available transcript (manual > generated, fr > en > any)."""
    preferred = ["fr", "en"]
    for lang in preferred:
        try:
            return transcript_list.find_manually_created_transcript([lang])
        except Exception:
            pass
    for lang in preferred:
        try:
            return transcript_list.find_generated_transcript([lang])
        except Exception:
            pass
    try:
        available = list(transcript_list)
        if available:
            return available[0]
    except Exception:
        pass
    return None


def _retrieve_via_ytdlp(video_id: str) -> tuple[str, str, str]:
    """Fallback: extract subtitles via yt-dlp (if installed)."""
    try:
        import json
        import os
        import tempfile
        import yt_dlp  # noqa: F401

        url = f"https://www.youtube.com/watch?v={video_id}"
        with tempfile.TemporaryDirectory() as tmp:
            opts = {
                "writesubtitles": True,
                "writeautomaticsub": True,
                "subtitleslangs": ["fr", "en"],
                "subtitlesformat": "json3",
                "skip_download": True,
                "outtmpl": os.path.join(tmp, "%(id)s.%(ext)s"),
                "quiet": True,
            }
            import yt_dlp as _ytdlp
            with _ytdlp.YoutubeDL(opts) as ydl:
                ydl.download([url])

            for fname in os.listdir(tmp):
                if not fname.endswith(".json3"):
                    continue
                with open(os.path.join(tmp, fname), encoding="utf-8") as f:
                    data = json.load(f)
                lang = fname.rsplit(".", 2)[-2] if fname.count(".") >= 2 else "unknown"
                parts = [
                    seg.get("utf8", "")
                    for event in data.get("events", [])
                    for seg in event.get("segs", [])
                ]
                text = re.sub(r"\s+", " ", " ".join(parts)).strip()
                if text:
                    return text, lang, ""
    except ImportError:
        pass
    except Exception:
        pass
    return "", "", "yt-dlp fallback failed"


# ── Validation ─────────────────────────────────────────────────────────────────

def _validate(text: str) -> tuple[bool, str, str, float]:
    """Returns (valid, reason, clean_text, noise_ratio)."""
    # 1. Empty
    if not text.strip():
        return False, "Le transcript est vide.", "", 0.0

    # 2. Minimum length
    if len(text) < MIN_TRANSCRIPT_CHARS:
        return False, f"Transcript trop court ({len(text)} caractères).", "", 0.0

    # 3. Noise ratio
    noise_chars = sum(len(m) for m in _NOISE_RE.findall(text))
    noise_ratio = noise_chars / max(len(text), 1)
    if noise_ratio > NOISE_RATIO_THRESHOLD:
        return (
            False,
            f"Transcript dominé par du bruit ({noise_ratio:.0%} de marqueurs non-textuels).",
            "", noise_ratio,
        )

    # 4. Clean and word count
    clean = _NOISE_RE.sub(" ", text)
    clean = re.sub(r"\s+", " ", clean).strip()
    words = clean.split()
    if len(words) < 20:
        return False, f"Transcript insuffisant ({len(words)} mots après nettoyage).", "", noise_ratio

    return True, "ok", clean, noise_ratio


# ── Chunking ───────────────────────────────────────────────────────────────────

def _chunk(text: str) -> list[str]:
    """Split text into overlapping chunks of MAX_CHUNK_CHARS with sentence-boundary cuts."""
    if len(text) <= MAX_CHUNK_CHARS:
        return [text]

    chunks = []
    start = 0

    while start < len(text):
        end = min(start + MAX_CHUNK_CHARS, len(text))

        # Cut at sentence boundary if not at end of text
        if end < len(text):
            for sep in (".", "!", "?", "\n"):
                pos = text.rfind(sep, start + MAX_CHUNK_CHARS // 2, end)
                if pos > start:
                    end = pos + 1
                    break

        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)

        next_start = end - CHUNK_OVERLAP_CHARS
        if next_start <= start:
            next_start = end
        start = next_start

    return chunks


# ── Confidence ─────────────────────────────────────────────────────────────────

def _confidence(noise_ratio: float, total_chars: int, chunk_count: int) -> float:
    score = 1.0
    score -= noise_ratio * 0.5
    if total_chars < 500:
        score *= 0.5
    elif total_chars < 2000:
        score *= 0.75
    elif total_chars > 10000:
        score = min(score + 0.05, 1.0)
    return round(max(0.0, min(1.0, score)), 3)
