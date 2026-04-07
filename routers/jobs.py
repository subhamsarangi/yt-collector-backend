import os
from fastapi import APIRouter, Depends, HTTPException
from supabase import create_client
from auth import verify_token

router = APIRouter(dependencies=[Depends(verify_token)])


def get_supabase():
    return create_client(
        os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_ROLE_KEY"]
    )


@router.get("/job/{job_id}")
def get_job_status(job_id: str):
    sb = get_supabase()
    result = (
        sb.table("queue")
        .select("id, status, retries, whisper_retries, last_error")
        .eq("id", job_id)
        .single()
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="Job not found")
    return result.data


@router.get("/job/{job_id}/metadata")
def get_job_metadata(job_id: str):
    sb = get_supabase()
    # job_id maps to queue.id; get the associated video metadata
    queue = sb.table("queue").select("youtube_id").eq("id", job_id).single().execute()
    if not queue.data:
        raise HTTPException(status_code=404, detail="Job not found")

    video = (
        sb.table("videos")
        .select("metadata")
        .eq("youtube_id", queue.data["youtube_id"])
        .single()
        .execute()
    )
    if not video.data:
        raise HTTPException(status_code=404, detail="Video metadata not found")
    return video.data["metadata"]
