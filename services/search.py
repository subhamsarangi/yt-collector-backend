import os
import json
import concurrent.futures
from datetime import datetime, timezone
from groq import Groq
from services import ytdlp


def expand_queries(topic: str) -> list[str]:
    """Use Groq to generate 4-5 search query variations for a topic."""
    client = Groq(api_key=os.environ["GROQ_API_KEY"])
    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {
                "role": "system",
                "content": (
                    "You generate YouTube search query variations. "
                    "Return a JSON array of 5 short search queries (strings only, no explanation). "
                    "Queries should cover different angles: tutorials, explainers, news, deep dives, comparisons. "
                    "Keep each query under 8 words."
                ),
            },
            {"role": "user", "content": f"Topic: {topic}"},
        ],
        temperature=0.7,
        max_tokens=200,
    )
    raw = response.choices[0].message.content.strip()
    # Extract JSON array from response
    start = raw.find("[")
    end = raw.rfind("]") + 1
    queries = json.loads(raw[start:end])
    # Always include the original topic
    if topic not in queries:
        queries.insert(0, topic)
    return queries[:5]


def score_video(entry: dict) -> float:
    """Score a video by views, likes, and recency."""
    views = entry.get("view_count") or 0
    likes = entry.get("like_count") or 0

    # Recency bonus: videos from last 90 days get a boost
    recency_bonus = 0.0
    upload = entry.get("upload_date")
    if upload:
        try:
            uploaded = datetime.strptime(upload, "%Y%m%d").replace(tzinfo=timezone.utc)
            days_old = (datetime.now(timezone.utc) - uploaded).days
            if days_old <= 90:
                recency_bonus = (90 - days_old) * 1000
        except ValueError:
            pass

    return (views * 0.5) + (likes * 2) + recency_bonus


def search_enhanced(topic: str, top_n: int = 5) -> list[dict]:
    """
    Generate query variations, search all in parallel,
    deduplicate, score, and return top N videos.
    """
    queries = expand_queries(topic)

    # Search all queries in parallel
    all_entries: list[dict] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        futures = {executor.submit(ytdlp.search_topic, q, 8): q for q in queries}
        for future in concurrent.futures.as_completed(futures):
            try:
                all_entries.extend(future.result())
            except Exception as e:
                print(f"Search failed for query: {e}")

    # Deduplicate by video ID
    seen: set[str] = set()
    unique: list[dict] = []
    for entry in all_entries:
        vid_id = entry.get("id")
        if vid_id and vid_id not in seen:
            seen.add(vid_id)
            unique.append(entry)

    # Score and sort
    unique.sort(key=score_video, reverse=True)
    return unique[:top_n]
