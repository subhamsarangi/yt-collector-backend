import os
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from supabase import create_client
from auth import verify_token
from services import pdf as pdf_service

router = APIRouter(dependencies=[Depends(verify_token)])


def get_supabase():
    return create_client(
        os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_ROLE_KEY"]
    )


@router.post("/pdf/video/{video_id}")
def pdf_video(video_id: str):
    sb = get_supabase()
    result = sb.table("videos").select("*").eq("id", video_id).single().execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Video not found")

    pdf_bytes = pdf_service.render_video_pdf(result.data)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=video-{video_id}.pdf"},
    )


@router.post("/pdf/topic/{topic_id}")
def pdf_topic(topic_id: str):
    sb = get_supabase()

    topic = sb.table("topics").select("*").eq("id", topic_id).single().execute()
    if not topic.data:
        raise HTTPException(status_code=404, detail="Topic not found")

    videos = sb.table("videos").select("*").eq("topic_id", topic_id).execute()

    pdf_bytes = pdf_service.render_topic_pdf(topic.data, videos.data or [])
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=topic-{topic_id}.pdf"},
    )
