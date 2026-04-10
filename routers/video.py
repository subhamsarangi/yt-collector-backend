import os
import traceback
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from auth import verify_token
from services import ytdlp, r2, search as search_service, summarize as summarize_service

router = APIRouter(dependencies=[Depends(verify_token)])


class VideoRequest(BaseModel):
    youtube_id: str


class ChannelScanRequest(BaseModel):
    channel_url: str


class ChannelInfoRequest(BaseModel):
    channel_url: str


class SearchRequest(BaseModel):
    topic: str


class SummarizeRequest(BaseModel):
    transcript: str


@router.post("/video")
def process_video(req: VideoRequest):
    try:
        result = ytdlp.fetch_video(req.youtube_id)
    except Exception as e:
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail="yt-dlp metadata failed")

    # Upload thumbnail
    with open(result["thumbnail_path"], "rb") as f:
        thumbnail_url = r2.upload(
            f"thumbnails/{req.youtube_id}.jpg", f.read(), "image/jpeg"
        )

    return {
        "youtube_id": req.youtube_id,
        "thumbnail_url": thumbnail_url,
        "metadata": result["metadata"],
    }


class VideoAudioRequest(BaseModel):
    youtube_id: str
    duration: int = 0  # seconds — used to decide chunking


@router.post("/video/audio")
def process_video_audio(req: VideoAudioRequest):
    try:
        result = ytdlp.fetch_audio(req.youtube_id, req.duration)
    except Exception as e:
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"yt-dlp audio failed: {e}")

    chunk_urls = []
    for chunk in result["chunks"]:
        with open(chunk["path"], "rb") as f:
            key = (
                f"audio/{req.youtube_id}_chunk{len(chunk_urls):03d}.mp3"
                if result["chunked"]
                else f"audio/{req.youtube_id}.mp3"
            )
            url = r2.upload(key, f.read(), "audio/mpeg")
        chunk_urls.append({"url": url, "offset": chunk["offset"]})
        os.remove(chunk["path"])  # free disk immediately after upload

    return {
        "youtube_id": req.youtube_id,
        "chunked": result["chunked"],
        "chunks": chunk_urls,
        # convenience for single-chunk case
        "audio_url": chunk_urls[0]["url"] if not result["chunked"] else None,
    }


@router.post("/channel/scan")
def scan_channel(req: ChannelScanRequest):
    try:
        entries = ytdlp.scan_channel(req.channel_url)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Channel scan failed: {e}")
    return {"entries": entries}


@router.post("/channel/info")
def channel_info(req: ChannelInfoRequest):
    try:
        info = ytdlp.fetch_channel_info(req.channel_url)
    except Exception as e:
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail="Channel info failed")
    return info


@router.post("/search")
def search_topic(req: SearchRequest):
    try:
        results = ytdlp.search_topic(req.topic)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Search failed: {e}")
    return {"results": results}


@router.post("/search/enhanced")
def search_enhanced(req: SearchRequest):
    try:
        results = search_service.search_enhanced(req.topic)
    except Exception as e:
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Enhanced search failed: {e}")
    return {"results": results}


@router.post("/search/enhanced/stream")
def search_enhanced_stream(req: SearchRequest):
    return StreamingResponse(
        search_service.search_enhanced_stream(req.topic),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/summarize")
def summarize_transcript(req: SummarizeRequest):
    try:
        summary = summarize_service.summarize_transcript(req.transcript)
    except Exception as e:
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Summarization failed: {e}")
    return {"summary": summary}
