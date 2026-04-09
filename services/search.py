import os
import json
import concurrent.futures
from datetime import datetime, timezone
from typing import Generator
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
                    "You generate YouTube search query variations for a given topic.\n\n"
                    "Rules:\n"
                    "- Every query MUST contain ALL the words from the original topic, verbatim.\n"
                    "- Only add words to vary the angle — never remove or replace any original words.\n"
                    "- Add angle words that actually appear in real YouTube titles: tutorial, guide, demo, review, tips, tricks, how to, walkthrough, beginners, deep dive, setup, overview, first look, explained.\n"
                    "- Never include years, numbers, or version numbers.\n"
                    "- Keep each query under 8 words.\n"
                    "- Return a JSON array of 5 strings, no explanation.\n\n"
                    "Example — topic: \"gemini notebooklm\"\n"
                    "BAD:  [\"Gemini Explained\", \"Gemini News\", \"NotebookLM review hands on\"]  <- drops words from the original topic\n"
                    "GOOD: [\"gemini notebooklm tutorial\", \"gemini notebooklm deep dive\", "
                    "\"gemini notebooklm insane\", \"gemini notebooklm guide\", "
                    "\"gemini notebooklm tips tricks\"]"
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


def search_enhanced_stream(topic: str, top_n: int = 5) -> Generator[str, None, None]:
    """
    Same as search_enhanced but yields SSE-formatted strings so the caller
    can stream progress back to the client.
    """

    def event(data: dict) -> str:
        return f"data: {json.dumps(data)}\n\n"

    # Step 1 — generate query variations
    yield event({"step": "Generating search query variations with AI..."})
    queries = expand_queries(topic)
    yield event({"queries": queries})

    # Step 2 — parallel YouTube searches
    yield event(
        {"step": f"Searching YouTube with {len(queries)} queries in parallel..."}
    )

    all_entries: list[dict] = []
    completed = 0

    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        futures = {executor.submit(ytdlp.search_topic, q, 8): q for q in queries}
        for future in concurrent.futures.as_completed(futures):
            q = futures[future]
            try:
                results = future.result()
                all_entries.extend(results)
                completed += 1
                yield event(
                    {
                        "query_done": q,
                        "hits": len(results),
                        "completed": completed,
                        "total": len(queries),
                    }
                )
            except Exception as e:
                completed += 1
                yield event(
                    {
                        "query_failed": q,
                        "error": str(e),
                        "completed": completed,
                        "total": len(queries),
                    }
                )

    # Step 3 — deduplicate
    yield event({"step": f"Deduplicating {len(all_entries)} results..."})
    seen: set[str] = set()
    unique: list[dict] = []
    for entry in all_entries:
        vid_id = entry.get("id")
        if vid_id and vid_id not in seen:
            seen.add(vid_id)
            unique.append(entry)

    # Step 4 — score and return
    unique.sort(key=score_video, reverse=True)
    top = unique[:top_n]
    yield event(
        {"step": f"Ranked results. Returning top {len(top)} videos.", "results": top}
    )
