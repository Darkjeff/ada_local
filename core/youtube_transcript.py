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
    Compatible with youtube-transcript-api 0.x and 1.x.
    """
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
    except ImportError:
        return {
            "success": False, "text": "", "language": "",
            "error": "youtube-transcript-api not installed. Run: pip install youtube-transcript-api",
        }

    # Detect API version: 1.x uses instances, 0.x uses class methods
    try:
        api = YouTubeTranscriptApi()
        transcript_list = api.list(video_id)
        _new_api = True
    except TypeError:
        # 0.x: class-based static methods
        try:
            transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
        except Exception as e:
            return {"success": False, "text": "", "language": "", "error": str(e)}
        _new_api = False
    except Exception as e:
        return {"success": False, "text": "", "language": "", "error": str(e)}

    # Priority: manual FR > manual EN > generated FR > generated EN > any → translate FR
    preferred = ["fr", "en"]
    transcript = None

    for lang in preferred:
        try:
            transcript = transcript_list.find_manually_created_transcript([lang])
            break
        except Exception:
            pass

    if not transcript:
        for lang in preferred:
            try:
                transcript = transcript_list.find_generated_transcript([lang])
                break
            except Exception:
                pass

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
        fetched = transcript.fetch()
        language = transcript.language_code
    except Exception as e:
        return {"success": False, "text": "", "language": "", "error": str(e)}

    # Handle both dict entries (0.x) and object entries (1.x)
    parts = []
    for entry in fetched:
        if isinstance(entry, dict):
            parts.append(entry.get("text", ""))
        else:
            parts.append(getattr(entry, "text", str(entry)))

    full_text = re.sub(r"\s+", " ", " ".join(parts)).strip()

    if len(full_text) > MAX_TRANSCRIPT_CHARS:
        full_text = full_text[:MAX_TRANSCRIPT_CHARS]
        last_period = max(full_text.rfind("."), full_text.rfind("!"), full_text.rfind("?"))
        if last_period > MAX_TRANSCRIPT_CHARS // 2:
            full_text = full_text[:last_period + 1]
        full_text += "\n[… transcript tronqué]"

    return {"success": True, "text": full_text, "language": language, "error": ""}
