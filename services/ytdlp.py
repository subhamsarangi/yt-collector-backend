import subprocess
import json
import os
import tempfile
import traceback
from datetime import datetime, timezone, timedelta


def fetch_video(youtube_id: str) -> dict:
    """Download metadata, thumbnail, and audio for a single video. Returns metadata dict + file paths."""
    url = f"https://www.youtube.com/watch?v={youtube_id}"
    tmpdir = tempfile.mkdtemp()

    # Download metadata + thumbnail + audio
    cmd = [
        "yt-dlp",
        "--write-info-json",
        "--write-thumbnail",
        "--convert-thumbnails",
        "jpg",
        "-x",
        "--audio-format",
        "mp3",
        "--audio-quality",
        "5",  # ~128kbps, good enough for Whisper
        "--postprocessor-args",
        "ffmpeg:-ar 16000 -ac 1",  # 16kHz mono
        "-o",
        f"{tmpdir}/%(id)s.%(ext)s",
        "--no-playlist",
        url,
    ]
    subprocess.run(cmd, check=True, capture_output=True)

    with open(f"{tmpdir}/{youtube_id}.info.json") as f:
        info = json.load(f)

    return {
        "metadata": info,
        "audio_path": f"{tmpdir}/{youtube_id}.mp3",
        "thumbnail_path": f"{tmpdir}/{youtube_id}.jpg",
    }


def fetch_channel_info(channel_url: str) -> dict:
    """Return channel name and category/topic from its URL."""
    cmd = [
        "yt-dlp",
        "--flat-playlist",
        "--dump-single-json",
        "--playlist-items",
        "0",  # fetch playlist metadata only, no entries
        "--no-download",
        channel_url,
    ]
    result = subprocess.run(cmd, check=True, capture_output=True, text=True)
    data = json.loads(result.stdout)
    return {
        "name": data.get("channel") or data.get("uploader") or data.get("title", ""),
        "domain": (data.get("tags") or [None])[0] or "",
    }


def scan_channel(channel_url: str) -> list[dict]:
    """Return videos published in the last 24 hours from a channel."""
    since = (datetime.now(timezone.utc) - timedelta(hours=24)).strftime("%Y%m%d")

    cmd = [
        "yt-dlp",
        "--flat-playlist",
        "--dump-single-json",
        "--dateafter",
        since,
        "--no-download",
        channel_url,
    ]
    result = subprocess.run(cmd, check=True, capture_output=True, text=True)
    data = json.loads(result.stdout)
    return data.get("entries", [])


def search_topic(topic: str, max_results: int = 5) -> list[dict]:
    """Search YouTube and return top N results for a topic."""
    cmd = [
        "yt-dlp",
        f"ytsearch{max_results}:{topic}",
        "--dump-single-json",
        "--flat-playlist",
        "--no-download",
    ]
    result = subprocess.run(cmd, check=True, capture_output=True, text=True)
    data = json.loads(result.stdout)
    return data.get("entries", [])
