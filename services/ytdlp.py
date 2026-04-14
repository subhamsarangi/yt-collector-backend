import subprocess
import json
import os
import tempfile
import traceback
from datetime import datetime, timezone, timedelta


def fetch_video(youtube_id: str) -> dict:
    """Download metadata and thumbnail only. Returns metadata dict + thumbnail path."""
    url = f"https://www.youtube.com/watch?v={youtube_id}"
    tmpdir = tempfile.mkdtemp()

    cookie_file = os.path.join(os.path.dirname(__file__), "..", "cookies.txt")
    cmd = [
        "yt-dlp",
        "--write-info-json",
        "--write-thumbnail",
        "--convert-thumbnails",
        "jpg",
        "--skip-download",  # metadata + thumbnail only, no audio
        "--js-runtimes",
        "deno",
        "-o",
        f"{tmpdir}/%(id)s.%(ext)s",
        "--no-playlist",
    ]
    if os.path.exists(cookie_file):
        cmd += ["--cookies", os.path.abspath(cookie_file)]
    cmd.append(url)
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as e:
        raise RuntimeError(
            f"yt-dlp metadata failed:\nstdout: {e.stdout}\nstderr: {e.stderr}"
        )

    with open(f"{tmpdir}/{youtube_id}.info.json") as f:
        raw = json.load(f)

    info = {
        k: raw.get(k)
        for k in [
            "id",
            "title",
            "description",
            "upload_date",
            "channel",
            "channel_id",
            "uploader",
            "uploader_url",
            "duration",
            "view_count",
            "like_count",
            "comment_count",
            "tags",
            "categories",
            "chapters",
            "heatmap",
            "webpage_url",
            "thumbnail",
        ]
    }

    return {
        "metadata": info,
        "thumbnail_path": f"{tmpdir}/{youtube_id}.jpg",
    }


def fetch_audio(
    youtube_id: str, duration_seconds: int = 0, cap_seconds: int = 600
) -> dict:
    """Download up to cap_seconds of audio, re-encoded to 16kHz mono mp3."""
    actual_seconds = (
        min(duration_seconds, cap_seconds) if duration_seconds else cap_seconds
    )

    url = f"https://www.youtube.com/watch?v={youtube_id}"
    tmpdir = tempfile.mkdtemp()
    audio_path = f"{tmpdir}/{youtube_id}.mp3"

    cookie_file = os.path.join(os.path.dirname(__file__), "..", "cookies.txt")
    cmd = [
        "yt-dlp",
        "--external-downloader",
        "ffmpeg",
        "--external-downloader-args",
        f"ffmpeg_i:-ss 0 -t {actual_seconds}",
        "-x",
        "--audio-format",
        "mp3",
        "--audio-quality",
        "9",
        "--postprocessor-args",
        "ffmpeg:-ar 16000 -ac 1",
        "--js-runtimes",
        "deno",
        "-o",
        audio_path,
        "--no-playlist",
    ]
    if os.path.exists(cookie_file):
        cmd += ["--cookies", os.path.abspath(cookie_file)]
    cmd.append(url)

    start_time = datetime.now(timezone.utc)
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as e:
        raise RuntimeError(
            f"yt-dlp audio failed:\nstdout: {e.stdout}\nstderr: {e.stderr}"
        )
    elapsed = (datetime.now(timezone.utc) - start_time).total_seconds()

    size_mb = round(os.path.getsize(audio_path) / 1024 / 1024, 2)
    return {
        "audio_path": audio_path,
        "size_mb": size_mb,
        "elapsed_s": round(elapsed, 1),
        "speed_mbps": round(size_mb / elapsed, 2) if elapsed > 0 else 0,
        "downloaded_duration_s": (
            min(duration_seconds, cap_seconds) if duration_seconds else cap_seconds
        ),
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
        "thumbnail_url": (
            data.get("thumbnails", [{}])[-1].get("url", "")
            if data.get("thumbnails")
            else ""
        ),
    }


def scan_channel(channel_url: str) -> list[dict]:
    """Return videos published in the last 24 hours from a channel."""
    since = (datetime.now(timezone.utc) - timedelta(hours=24)).strftime("%Y%m%d")
    print(f"[scan_channel] Scanning {channel_url} for videos since {since}", flush=True)

    # Ensure we hit the /videos tab so yt-dlp gets the uploads playlist
    base_url = channel_url.rstrip("/")
    if not base_url.endswith("/videos"):
        base_url = base_url + "/videos"

    # --flat-playlist ignores --dateafter, so we use --no-download + --dateafter
    # and limit to the 10 most recent uploads to avoid scanning the full history
    cmd = [
        "yt-dlp",
        "--dump-single-json",
        "--no-download",
        "--dateafter",
        since,
        "--playlist-end",
        "10",
        "--no-playlist-reverse",
        base_url,
    ]
    try:
        result = subprocess.run(cmd, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as e:
        print(
            f"[scan_channel] yt-dlp failed for {channel_url}:\nstdout: {e.stdout}\nstderr: {e.stderr}",
            flush=True,
        )
        raise

    data = json.loads(result.stdout)

    # Result may be a single video or a playlist with entries
    if data.get("_type") == "playlist":
        entries = data.get("entries") or []
    elif data.get("id") and len(data.get("id", "")) == 11:
        entries = [data]
    else:
        entries = []

    filtered = [
        e
        for e in entries
        if e
        and e.get("id")
        and len(e["id"]) == 11
        and e.get("ie_key", "").lower() != "youtubetab"
    ]
    print(
        f"[scan_channel] {len(entries)} raw entries → {len(filtered)} valid videos for {channel_url}",
        flush=True,
    )
    return filtered


def search_topic(topic: str, max_results: int = 5, language: str = "en") -> list[dict]:
    """Search YouTube and return top N video results for a topic, filtered by language."""
    cmd = [
        "yt-dlp",
        f"ytsearch{max_results * 3}:{topic}",  # fetch more to account for filtering
        "--dump-single-json",
        "--flat-playlist",
        "--no-download",
    ]
    result = subprocess.run(cmd, check=True, capture_output=True, text=True)
    data = json.loads(result.stdout)
    entries = data.get("entries", [])
    filtered = [
        e
        for e in entries
        if e.get("id")
        and len(e["id"]) == 11
        and e.get("ie_key", "").lower() != "youtubetab"
        and (e.get("language") in (language, None, ""))
    ]
    return filtered[:max_results]
