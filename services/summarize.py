import os
from groq import Groq

# ~4 chars per token, keep chunks well under 6k tokens to leave room for prompt + response
CHUNK_CHARS = 20_000
CHUNK_OVERLAP = 500  # overlap to avoid cutting mid-thought


def _chunk_transcript(transcript: str) -> list[str]:
    """Split transcript into overlapping chunks by character count."""
    if len(transcript) <= CHUNK_CHARS:
        return [transcript]

    chunks = []
    start = 0
    while start < len(transcript):
        end = start + CHUNK_CHARS
        # Try to break at a newline near the end to avoid mid-sentence cuts
        if end < len(transcript):
            newline = transcript.rfind("\n", start + CHUNK_CHARS // 2, end)
            if newline != -1:
                end = newline
        chunks.append(transcript[start:end].strip())
        start = end - CHUNK_OVERLAP
    return chunks


def _summarize_chunk(client: Groq, chunk: str, part: int, total: int) -> str:
    part_note = f" (part {part} of {total})" if total > 1 else ""
    response = client.chat.completions.create(
        model="moonshotai/kimi-k2-instruct",
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a precise summarizer of YouTube video transcripts. "
                    "Summarize the provided transcript segment into clear, concise bullet points. "
                    "Each bullet should capture a distinct key point, insight, or fact. "
                    "Use plain language. Do not include filler or meta-commentary. "
                    "Output only the bullet points, one per line, starting with '• '."
                ),
            },
            {
                "role": "user",
                "content": f"Transcript segment{part_note}:\n\n{chunk}",
            },
        ],
        temperature=0.3,
        max_tokens=2048,
    )
    raw = response.choices[0].message.content.strip()
    if "<think>" in raw:
        raw = raw[raw.rfind("</think>") + len("</think>") :].strip()
    return raw


def _merge_summaries(client: Groq, summaries: list[str]) -> str:
    """Merge multiple chunk summaries into a single coherent bullet list."""
    combined = "\n\n".join(summaries)
    response = client.chat.completions.create(
        model="moonshotai/kimi-k2-instruct",
        messages=[
            {
                "role": "system",
                "content": (
                    "You are given bullet-point summaries from different segments of the same video. "
                    "Merge them into a single, deduplicated, well-organized bullet-point summary. "
                    "Remove redundant points. Keep the most important insights. "
                    "Output only bullet points, one per line, starting with '• '."
                ),
            },
            {
                "role": "user",
                "content": combined,
            },
        ],
        temperature=0.3,
        max_tokens=2048,
    )
    raw = response.choices[0].message.content.strip()
    if "<think>" in raw:
        raw = raw[raw.rfind("</think>") + len("</think>") :].strip()
    return raw


def summarize_transcript(transcript: str) -> str:
    """
    Chunk the transcript, summarize each chunk, then merge into a final
    bullet-pointed summary. Returns the summary string.
    """
    client = Groq(api_key=os.environ["GROQ_API_KEY"])
    chunks = _chunk_transcript(transcript)

    chunk_summaries = []
    for i, chunk in enumerate(chunks, 1):
        summary = _summarize_chunk(client, chunk, i, len(chunks))
        chunk_summaries.append(summary)

    if len(chunk_summaries) == 1:
        return chunk_summaries[0]

    return _merge_summaries(client, chunk_summaries)
