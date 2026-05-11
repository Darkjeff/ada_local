import json
import requests
import datetime
import feedparser
from config import OLLAMA_URL, RESPONDER_MODEL

_RSS_SOURCES = [
    ("https://news.google.com/rss?hl=fr&gl=FR&ceid=FR:fr",                          "Top Stories", 5),
    ("https://news.google.com/rss/search?q=technology&hl=fr&gl=FR&ceid=FR:fr",      "Technology",  5),
    ("https://news.google.com/rss/search?q=science&hl=fr&gl=FR&ceid=FR:fr",         "Science",     3),
]


class NewsManager:
    """Manages fetching and curating news for the Briefing dashboard."""

    def __init__(self):
        # Simple in-memory cache: {category: {"timestamp": dt, "data": []}}
        self.cache = {}
        self.cache_duration = datetime.timedelta(minutes=15)

    def get_briefing(self, status_callback=None, use_ai: bool = True) -> list:
        """
        Get a curated briefing.
        Fetches 'top' and 'technology' news, then asks AI to pick the best ones.
        """
        # 1. Check cache first
        if status_callback: status_callback("Checking local cache...")
        cache_key = "briefing_ai" if use_ai else "briefing_raw"
        cached = self._get_from_cache(cache_key)
        if cached:
            return cached

        # 2. Fetch raw news via RSS
        raw_news = []
        try:
            if status_callback: status_callback("Scanning global headlines...")
            idx = 0
            for url, category, max_items in _RSS_SOURCES:
                if category == "Technology" and status_callback:
                    status_callback("Retrieving technology sector updates...")
                feed = feedparser.parse(url)
                for entry in feed.entries[:max_items]:
                    if hasattr(entry, 'source') and hasattr(entry.source, 'title'):
                        source = entry.source.title
                    else:
                        source = feed.feed.get('title', url.split('/')[2])
                    raw_news.append({
                        "id":       idx,
                        "title":    entry.get('title', ''),
                        "source":   source,
                        "date":     entry.get('published', ''),
                        "url":      entry.get('link', ''),
                        "image":    "",
                        "body":     entry.get('summary', ''),
                        "category": category,
                    })
                    idx += 1

        except Exception as e:
            print(f"Error fetching news from RSS: {e}")
            return []

        # 3. AI Curation
        curated_news = None
        if use_ai:
            if status_callback: status_callback("AI is reading and curating stories...")
            curated_news = self._curate_with_ai(raw_news)
        
        # 4. Fallback if AI fails: just return raw news formatted
        if not curated_news:
            curated_news = self._format_raw_fallback(raw_news)

        # 5. Save to cache
        self.cache[cache_key] = {
            "timestamp": datetime.datetime.now(),
            "data": curated_news
        }
        
        return curated_news

    def _get_from_cache(self, key: str):
        if key in self.cache:
            entry = self.cache[key]
            if datetime.datetime.now() - entry["timestamp"] < self.cache_duration:
                return entry["data"]
        return None

    def _format_raw_fallback(self, raw_news):
        """Fallback formatting if AI fails."""
        formatted = []
        seen_titles = set()
        
        for item in raw_news:
            if item['title'] in seen_titles:
                continue
            seen_titles.add(item['title'])
            
            formatted.append({
                "title": item.get('title'),
                "source": item.get('source'),
                "date": item.get('date'),
                "category": item.get('category', 'General'),
                "url": item.get('url'),
                "image": item.get('image', '')
            })
        return formatted[:8] # Return top 8

    def _curate_with_ai(self, raw_news):
        """Send raw news to LLM to select and strictly format."""
        
        # Minify valid data for prompt
        # We only need title, source, category to make a decision
        news_input = [
            {"id": i, "title": n.get('title'), "source": n.get('source'), "category": n.get('category')} 
            for i, n in enumerate(raw_news)
        ]

        prompt = f"""
You are an expert News Editor.
Here is a list of raw news articles:
{json.dumps(news_input, indent=2)}

Task:
1. Select the 6 most important and diverse stories.
2. Rewrite the titles to be punchy and short (under 10 words).
3. Assign a category: 'Technology', 'Science', 'Markets', 'Culture', or 'Top Stories'.
4. Return ONLY a JSON array of objects.
   Format: [{{"id": <original_id>, "title": "<new_title>", "category": "<category>"}}]

Do NOT add any markdown or text. Just the JSON array.
"""
        
        try:
            response = requests.post(
                f"{OLLAMA_URL}/chat",
                json={
                    "model": RESPONDER_MODEL,
                    "messages": [{"role": "user", "content": prompt}],
                    "stream": False,
                    "options": {"temperature": 0.3}
                },
                timeout=60
            )
            
            if response.status_code == 200:
                content = response.json()['message']['content']
                # Try to clean markdown code blocks if present
                if "```json" in content:
                    content = content.split("```json")[1].split("```")[0].strip()
                elif "```" in content:
                    content = content.split("```")[1].strip()
                
                selected = json.loads(content)
                
                # Merge back with original data (urls, images)
                final_list = []
                for s in selected:
                    original = raw_news[s['id']]
                    final_list.append({
                        "title": s['title'], # AI rewritten title
                        "source": original.get('source'),
                        "date": original.get('date'), # DDGS date is often "2 hours ago"
                        "category": s['category'], # AI Category
                        "url": original.get('url'),
                        "image": original.get('image'),
                        "body": original.get('body') # snippet
                    })
                return final_list
                
        except Exception as e:
            print(f"AI Curation failed: {e}")
            return None
        
        return None

news_manager = NewsManager()
