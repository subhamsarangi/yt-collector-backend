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
    since_dt = datetime.now(timezone.utc) - timedelta(hours=24)
    since_ts = since_dt.timestamp()
    since_str = since_dt.strftime("%Y%m%d")
    print(
        f"[scan_channel] Scanning {channel_url} for videos since {since_str}",
        flush=True,
    )

    # Ensure we hit the /videos tab
    base_url = channel_url.rstrip("/")
    if not base_url.endswith("/videos"):
        base_url = base_url + "/videos"

    cookie_file = os.path.join(os.path.dirname(__file__), "..", "cookies.txt")

    # --flat-playlist avoids bot checks and returns lightweight stubs with timestamps.
    # We grab the last 15 uploads and filter by date ourselves.
    cmd = [
        "yt-dlp",
        "--flat-playlist",
        "--dump-single-json",
        "--playlist-end",
        "15",
        "--no-download",
        base_url,
    ]
    if os.path.exists(cookie_file):
        cmd += ["--cookies", os.path.abspath(cookie_file)]

    try:
        result = subprocess.run(cmd, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as e:
        print(
            f"[scan_channel] yt-dlp failed for {channel_url}:\nstdout: {e.stdout}\nstderr: {e.stderr}",
            flush=True,
        )
        raise

    data = json.loads(result.stdout)
    entries = data.get("entries") or []

    filtered = []
    for e in entries:
        if not e:
            continue
        vid_id = e.get("id", "")
        if not vid_id or len(vid_id) != 11:
            continue
        if e.get("ie_key", "").lower() == "youtubetab":
            continue

        # Filter by date: prefer unix timestamp, fall back to upload_date string (YYYYMMDD)
        ts = e.get("timestamp")
        upload_date = e.get("upload_date")  # "20260415"
        print(
            f"[scan_channel] {vid_id} — timestamp={ts} upload_date={upload_date} release_timestamp={e.get('release_timestamp')}",
            flush=True,
        )
        if ts is not None:
            if ts < since_ts:
                print(
                    f"[scan_channel] Skipping {vid_id} — too old (timestamp)",
                    flush=True,
                )
                continue
        elif upload_date:
            if upload_date < since_str:
                print(
                    f"[scan_channel] Skipping {vid_id} — too old ({upload_date})",
                    flush=True,
                )
                continue
        else:
            # No date info at all — skip to avoid false positives
            print(f"[scan_channel] Skipping {vid_id} — no date available", flush=True)
            continue

        filtered.append(e)

    print(
        f"[scan_channel] {len(entries)} raw entries → {len(filtered)} within 24h for {channel_url}",
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
