"""
/train  routes
──────────────
POST /train/upload-and-train   Upload a ZIP of class folders → prepare dataset → return session_id
GET  /train/progress/{id}      SSE stream of epoch-by-epoch training progress
"""
import asyncio
import uuid
import zipfile
from pathlib import Path
from queue import Queue, Empty
from threading import Thread

from fastapi import APIRouter, File, UploadFile, HTTPException
from fastapi.responses import StreamingResponse
import json

from config import UPLOAD_DIR
from services.dataset_service import extract_upload, prepare_dataset, save_samples
from services.training_service import train_initial_model

router = APIRouter(prefix="/train", tags=["Initial training"])

# In-process job store { session_id: Queue }
# In production, replace with Redis Streams or Celery.
_jobs: dict[str, Queue] = {}


@router.post("/upload-and-train", summary="Upload class ZIP and start training")
async def upload_and_train(file: UploadFile = File(...)):
    """
    Expected ZIP layout:
        dataset.zip
        ├── dog/
        │   ├── 001.jpg
        │   └── …
        ├── cat/
        └── bird/

    Response:
        { session_id, classes, dataset_info }

    Then poll  GET /train/progress/{session_id}  via SSE.
    """
    session_id = str(uuid.uuid4())[:8]

    # 1. Save upload
    zip_path = UPLOAD_DIR / f"{session_id}.zip"
    content = await file.read()
    zip_path.write_bytes(content)

    if not zipfile.is_zipfile(zip_path):
        zip_path.unlink(missing_ok=True)
        raise HTTPException(400, "Uploaded file must be a ZIP archive.")

    # 2. Extract
    source_dir = extract_upload(zip_path, session_id)

    # 3. Validate class count
    classes = sorted([d.name for d in source_dir.iterdir() if d.is_dir()])
    if len(classes) < 2:
        raise HTTPException(400, f"Need ≥ 2 class folders inside the ZIP; found: {classes}")

    # 4. Train/val split
    dataset_info = prepare_dataset(source_dir, session_id)

    # 5. Save samples for future incremental sessions
    save_samples(source_dir, session_id)

    # 6. Kick off training in a background thread
    progress_queue: Queue = Queue()
    _jobs[session_id] = progress_queue

    def _run():
        try:
            train_initial_model(Path(dataset_info["dataset_path"]), session_id, progress_queue)
        except Exception as exc:
            progress_queue.put({"type": "error", "message": str(exc)})

    Thread(target=_run, daemon=True).start()

    return {
        "session_id": session_id,
        "classes": classes,
        "dataset_info": dataset_info,
        "progress_url": f"/train/progress/{session_id}",
    }


@router.get("/progress/{session_id}", summary="SSE stream of training progress")
async def training_progress(session_id: str):
    """
    Server-Sent Events stream.  Each message is a JSON object:
      { type: 'hp' | 'epoch' | 'early_stop' | 'done' | 'error' | 'heartbeat' }

    The stream closes automatically when type=='done' or type=='error'.
    """
    if session_id not in _jobs:
        raise HTTPException(404, f"Session '{session_id}' not found.")

    q = _jobs[session_id]

    async def event_generator():
        loop = asyncio.get_event_loop()
        while True:
            try:
                msg = await loop.run_in_executor(None, lambda: q.get(timeout=30))
                yield f"data: {json.dumps(msg)}\n\n"
                if msg.get("type") in ("done", "error"):
                    break
            except Empty:
                yield "data: {\"type\": \"heartbeat\"}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",   # Disable nginx buffering
        },
    )
