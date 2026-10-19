"""API FastAPI: encola jobs NMR y expone su estado/resultado."""

import os
import uuid
from typing import Optional

import redis
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from rq import Queue

from . import config

app = FastAPI(title="SpinQit NMR Quantum Service")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


def get_queue() -> Queue:
    conn = redis.Redis.from_url(config.REDIS_URL)
    return Queue(config.QUEUE_NAME, connection=conn)


class ExecuteRequest(BaseModel):
    code: str
    resume_url: Optional[str] = None


@app.get("/", include_in_schema=False)
def index():
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/execute")
def execute(req: ExecuteRequest):
    if not req.code or not req.code.strip():
        raise HTTPException(status_code=400, detail="El código no puede estar vacío.")

    job_id = str(uuid.uuid4())
    queue = get_queue()
    queue.enqueue(
        "app.jobs.execute_circuit",
        req.code,
        job_id,
        req.resume_url,
        job_id=job_id,
        job_timeout=config.JOB_TIMEOUT,
        result_ttl=config.RESULT_TTL,
    )
    return {"job_id": job_id, "status": "queued"}


def _job_status(job) -> str:
    """Normaliza el estado a cadena (RQ 2.x devuelve un enum JobStatus)."""
    status = job.get_status()
    return getattr(status, "value", status)


def _job_error(job) -> str:
    try:
        latest = job.latest_result()
        if latest is not None and getattr(latest, "exc_string", None):
            return str(latest.exc_string)
    except Exception:
        pass
    try:
        if job.exc_info:
            return str(job.exc_info)
    except Exception:
        pass
    return "Job falló sin información de error."


@app.get("/jobs/{job_id}")
def get_job(job_id: str):
    queue = get_queue()
    job = queue.fetch_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job no encontrado.")

    status = _job_status(job)
    payload = {"job_id": job_id, "status": status}

    if status == "finished":
        try:
            payload["result"] = job.return_value()
        except Exception:
            payload["result"] = None
    elif status == "failed":
        payload["error"] = _job_error(job)

    return payload
