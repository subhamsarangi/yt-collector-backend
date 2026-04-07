import os
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from auth import verify_token
from services import ytdlp, r2

router = APIRouter(dependencies=[Depends(verify_token)])


class VideoRequest(BaseModel):
    youtube_id: str


class ChannelScanRequest(BaseModel):
    channel_url: str


class SearchRequest(BaseModel):
    topic: str


@router.post("/video")
def process_video(req: VideoRequest):
    try:
        result = ytdlp.fetch_video(req.youtube_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"yt-dlp failed: {e}")

    # Upload thumbnail
    with open(result["thumbnail_path"], "rb") as f:
        thumbnail_url = r2.upload(
            f"thumbnails/{req.youtube_id}.jpg", f.read(), "image/jpeg"
        )

    # Upload audio
    with open(result["audio_path"], "rb") as f:
        audio_url = r2.upload(f"audio/{req.youtube_id}.mp3", f.read(), "audio/mpeg")

    return {
        "youtube_id": req.youtube_id,
        "thumbnail_url": thumbnail_url,
        "audio_url": audio_url,
        "metadata": result["metadata"],
    }


@router.post("/channel/scan")
def scan_channel(req: ChannelScanRequest):
    try:
        entries = ytdlp.scan_channel(req.channel_url)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Channel scan failed: {e}")
    return {"entries": entries}


@router.post("/search")
def search_topic(req: SearchRequest):
    try:
        results = ytdlp.search_topic(req.topic)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Search failed: {e}")
    return {"results": results}
