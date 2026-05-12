"""
YouTube Transcript — fetches subtitles via youtube-transcript-api.
No audio download, no yt-dlp needed.
"""

import re
from typing import Optional


_YT_PATTERNS = [
    r"(?:youtube\.com/watch\?(?:.*&)?v=|youtu\.be/)([A-Za-z0-9_-]{11})",
]

MAX_TRANSCRIPT_CHARS = 6000  # ~1500 tokens, safe for qwen3:1.7b


def extract_video_id(text: str) -> Optional[str]:
    """Return the 11-char YouTube video ID found in text, or None."""
    for pattern in _YT_PATTERNS:
        m = re.search(pattern, text)
        if m:
            return m.group(1)
    return None


def fetch_transcript(video_id: str) -> dict:
    """
    Fetch the best available transcript for a YouTube video.
    Returns {"success": bool, "text": str, "language": str, "error": str}.
    Prefers French, then English, then whatever is available.
    """
    try:
        from youtube_transcript_api import YouTubeTranscriptApi, NoTranscriptFound, TranscriptsDisabled
    except ImportError:
        return {
            "success": False,
            "text": "",
            "language": "",
            "error": "youtube-transcript-api not installed. Run: pip install youtube-transcript-api",
        }

    try:
        transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
    except Exception as e:
        return {"success": False, "text": "", "language": "", "error": str(e)}

    # Priority: manual French > manual English > auto French > auto English > any
    preferred = ["fr", "en"]
    transcript = None

    # Try manual first
    for lang in preferred:
        try:
            transcript = transcript_list.find_manually_created_transcript([lang])
            break
        except Exception:
            pass

    # Try generated
    if not transcript:
        for lang in preferred:
            try:
                transcript = transcript_list.find_generated_transcript([lang])
                break
            except Exception:
                pass

    # Fallback: first available, translated to French
    if not transcript:
        try:
            available = list(transcript_list)
            if available:
                transcript = available[0].translate("fr")
        except Exception:
            pass

    if not transcript:
        return {"success": False, "text": "", "language": "", "error": "No transcript available for this video."}

    try:
        entries = transcript.fetch()
        language = transcript.language_code
    except Exception as e:
        return {"success": False, "text": "", "language": "", "error": str(e)}

    # Concatenate and truncate
    full_text = " ".join(e["text"] for e in entries)
    full_text = re.sub(r"\s+", " ", full_text).strip()

    truncated = False
    if len(full_text) > MAX_TRANSCRIPT_CHARS:
        full_text = full_text[:MAX_TRANSCRIPT_CHARS]
        # Cut at last sentence boundary
        last_period = max(full_text.rfind("."), full_text.rfind("!"), full_text.rfind("?"))
        if last_period > MAX_TRANSCRIPT_CHARS // 2:
            full_text = full_text[: last_period + 1]
        truncated = True

    if truncated:
        full_text += "\n[… transcript tronqué]"

    return {"success": True, "text": full_text, "language": language, "error": ""}
