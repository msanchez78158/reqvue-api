import os
from pathlib import Path
from typing import Any
from uuid import uuid4

import pymupdf4llm
from dotenv import load_dotenv
from fastapi import BackgroundTasks, FastAPI, File, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from extractor import extract_rfq_brief
from trimmer import smart_trim

load_dotenv()

PORT = int(os.getenv("PORT", "8000"))
UPLOAD_DIR = Path("/tmp/reqvue_uploads")
JOB_STORE: dict[str, dict[str, Any]] = {}

app = FastAPI(title="reqvue-api")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _save_upload(upload: UploadFile) -> Path:
    suffix = Path(upload.filename or "").suffix
    upload_path = UPLOAD_DIR / f"{uuid4()}{suffix}"
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

    with upload_path.open("wb") as destination:
        while True:
            chunk = upload.file.read(1024 * 1024)
            if not chunk:
                break
            destination.write(chunk)

    return upload_path


def _extract_markdown_from_file(file_path: Path) -> str:
    return pymupdf4llm.to_markdown(str(file_path))


def process_document(job_id: str, *, file_path: Path | None = None, text: str | None = None) -> None:
    try:
        if file_path is not None:
            markdown = _extract_markdown_from_file(file_path)
        elif text is not None:
            markdown = text
        else:
            raise ValueError("No document content provided")

        trimmed = smart_trim(markdown, max_chars=18000)
        brief = extract_rfq_brief(
            document_name=file_path.name if file_path else "submitted_text",
            document_text=trimmed,
        )

        JOB_STORE[job_id] = {
            "status": "complete",
            "result": brief.model_dump(),
        }
    except Exception as exc:
        JOB_STORE[job_id] = {
            "status": "failed",
            "error": str(exc),
        }
    finally:
        if file_path is not None:
            file_path.unlink(missing_ok=True)


@app.post("/parse")
async def parse_document(
    request: Request,
    background_tasks: BackgroundTasks,
    file: UploadFile | None = File(default=None),
) -> JSONResponse:
    job_id = str(uuid4())
    JOB_STORE[job_id] = {"status": "processing", "result": None}

    if file is not None:
        upload_path = _save_upload(file)
        background_tasks.add_task(process_document, job_id, file_path=upload_path)
        return JSONResponse({"job_id": job_id, "status": "processing"})

    content_type = request.headers.get("content-type", "")
    if "application/json" not in content_type:
        JOB_STORE.pop(job_id, None)
        raise HTTPException(
            status_code=400,
            detail="Provide a multipart file upload or JSON body with {'text': '...'}"
        )

    body = await request.json()
    text = body.get("text") if isinstance(body, dict) else None
    if not text:
        JOB_STORE.pop(job_id, None)
        raise HTTPException(
            status_code=400,
            detail="JSON body must include a non-empty 'text' field"
        )

    background_tasks.add_task(process_document, job_id, text=text)
    return JSONResponse({"job_id": job_id, "status": "processing"})


@app.get("/status/{job_id}")
def get_status(job_id: str) -> JSONResponse:
    job = JOB_STORE.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    payload = {"job_id": job_id, "status": job["status"]}
    if job["status"] == "complete":
        payload["result"] = job["result"]
    elif job["status"] == "failed":
        payload["error"] = job["error"]

    return JSONResponse(payload)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


def process_document_v2(job_id: str, *, file_path: Path | None = None, text: str | None = None) -> None:
    try:
        try:
            from extractor_agent import extract_rfq_brief_v2
        except ModuleNotFoundError as exc:
            raise RuntimeError(
                "parse/v2 is unavailable because optional dependency 'agno' is not installed"
            ) from exc

        if file_path is not None:
            markdown = _extract_markdown_from_file(file_path)
        elif text is not None:
            markdown = text
        else:
            raise ValueError("No document content provided")

        trimmed = smart_trim(markdown, max_chars=18000)
        brief = extract_rfq_brief_v2(
            document_name=file_path.name if file_path else "submitted_text",
            document_text=trimmed,
        )

        JOB_STORE[job_id] = {
            "status": "complete",
            "result": brief.model_dump(),
        }
    except Exception as exc:
        JOB_STORE[job_id] = {
            "status": "failed",
            "error": str(exc),
        }
    finally:
        if file_path is not None:
            file_path.unlink(missing_ok=True)


@app.post("/parse/v2")
async def parse_document_v2(
    request: Request,
    background_tasks: BackgroundTasks,
    file: UploadFile | None = File(default=None),
) -> JSONResponse:
    job_id = str(uuid4())
    JOB_STORE[job_id] = {"status": "processing", "result": None}

    if file is not None:
        upload_path = _save_upload(file)
        background_tasks.add_task(process_document_v2, job_id, file_path=upload_path)
        return JSONResponse({"job_id": job_id, "status": "processing"})

    content_type = request.headers.get("content-type", "")
    if "application/json" not in content_type:
        JOB_STORE.pop(job_id, None)
        raise HTTPException(
            status_code=400,
            detail="Provide a multipart file upload or JSON body with {'text': '...'}"
        )

    body = await request.json()
    text = body.get("text") if isinstance(body, dict) else None
    if not text:
        JOB_STORE.pop(job_id, None)
        raise HTTPException(
            status_code=400,
            detail="JSON body must include a non-empty 'text' field"
        )

    background_tasks.add_task(process_document_v2, job_id, text=text)
    return JSONResponse({"job_id": job_id, "status": "processing"})
