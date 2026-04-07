from fastapi import FastAPI
from dotenv import load_dotenv

load_dotenv()

from routers import video, jobs, pdf

app = FastAPI(title="YT Collector API")

app.include_router(video.router)
app.include_router(jobs.router)
app.include_router(pdf.router)


@app.get("/health")
def health():
    return {"status": "ok"}
