"""
/incremental  routes — CM-based weak class detection + retrain-only mode
─────────────────────────────────────────────────────────────────────────
GET  /incremental/model-info
POST /incremental/upload-new-class
POST /incremental/start/{id}
GET  /incremental/progress/{id}
GET  /incremental/class-health/{id}

Decision logic on upload
─────────────────────────
For every folder in the uploaded ZIP:

  folder name NOT in model
  └─ truly_new → always train (incremental, head expands)

  folder name already IN model → check last CM:
  ├─ recall < 0.90  OR  confusion_rate >= 0.25
  │   └─ weak_existing → retrain with relaxed KD (no head expansion if no new classes)
  └─ recall >= 0.90  AND  confusion_rate < 0.25
      └─ skip → class is healthy, ignore

Training modes (resolved in service):
  new_only      → has new classes, no weak   → head expands
  retrain_only  → no new classes, has weak   → head stays same size
  new+weak      → has both                   → head expands, weak get relaxed KD
"""

from __future__ import annotations

import asyncio
import json
import uuid
import zipfile
from pathlib import Path
from queue import Empty, Queue
from threading import Thread
from typing import Dict, List, Optional, Tuple

from fastapi import APIRouter, File, Form, UploadFile, HTTPException
from fastapi.responses import StreamingResponse

from config import UPLOAD_DIR, SAMPLES_DIR, DATASET_DIR, METRICS_DIR
from services.dataset_service import (
    extract_upload, prepare_dataset, save_samples, merge_old_samples_with_new,
)
from services.training_service import get_latest_model_info
from services.incremental_service import train_incremental

router = APIRouter(prefix="/incremental", tags=["Incremental learning"])

# Classes with recall >= this AND confusion < CONFUSION_THRESHOLD → skip
RECALL_THRESHOLD:    float = 0.90
CONFUSION_THRESHOLD: float = 0.25

_jobs: Dict[str, Queue] = {}


# ──────────────────────────────────────────────────────────────────────────────
# CM quality check  (reads saved JSON — no model loading)
# ──────────────────────────────────────────────────────────────────────────────

def _load_cm_metrics(model_info: Dict) -> Optional[Dict]:
    """Read per_class_recall and confusion_pairs from the latest metrics JSON."""
    path = METRICS_DIR / f"{model_info['session_id']}_metrics.json"
    if not path.exists():
        return None
    with open(path) as f:
        data = json.load(f)
    return data if "per_class_recall" in data else None


def _classify_existing_classes(
    candidate_names: List[str],
    model_info: Dict,
    recall_threshold: float,
    confusion_threshold: float,
) -> Tuple[List[str], List[str], Dict]:
    """
    For each class name that already exists in the model, decide:
      weak    → recall < threshold  OR  confusion_rate >= confusion_threshold
      skipped → recall >= threshold AND confusion_rate < confusion_threshold

    Returns (weak_names, skipped_names, quality_report)
    """
    metrics = _load_cm_metrics(model_info)

    # No CM saved yet → conservative: retrain everything
    if metrics is None:
        return (
            candidate_names, [],
            {cls: {"reason": "no_cm_available", "decision": "retrain"}
             for cls in candidate_names},
        )

    per_class_recall = metrics.get("per_class_recall", {})
    confusion_pairs  = metrics.get("confusion_pairs",  {})

    weak, skipped, report = [], [], {}

    for cls in candidate_names:
        recall         = per_class_recall.get(cls)
        conf_info      = confusion_pairs.get(cls, {})
        confusion_rate = conf_info.get("confusion_rate", 0.0)
        confused_with  = conf_info.get("confused_with")
        reasons        = []

        if recall is None:
            # Class not found in last CM → conservative: retrain
            reasons.append("not_in_cm")
        else:
            if recall < recall_threshold:
                reasons.append(f"low_recall={recall:.2f} < {recall_threshold:.2f}")
            if confusion_rate >= confusion_threshold:
                reasons.append(
                    f"confused_with={confused_with} @ {confusion_rate:.2f}"
                    f" >= {confusion_threshold:.2f}"
                )

        if reasons:
            weak.append(cls)
            decision = "retrain"
        else:
            skipped.append(cls)
            decision = "skip"

        report[cls] = {
            "recall":         recall,
            "confused_with":  confused_with,
            "confusion_rate": confusion_rate,
            "decision":       decision,
            "reasons":        reasons,
        }

    return weak, skipped, report


# ──────────────────────────────────────────────────────────────────────────────
# Routes
# ──────────────────────────────────────────────────────────────────────────────

@router.get("/model-info")
async def model_info():
    info = get_latest_model_info()
    if not info:
        raise HTTPException(404, "No trained model found. Run initial training first.")
    return info


@router.get("/class-health/{session_id}")
async def class_health(session_id: str):
    path = METRICS_DIR / f"{session_id}_metrics.json"
    if not path.exists():
        raise HTTPException(404, f"No metrics found for session '{session_id}'.")

    with open(path) as f:
        m = json.load(f)

    recall     = m.get("per_class_recall", {})
    conf_pairs = m.get("confusion_pairs",  {})

    weak = [
        cls for cls, r in recall.items()
        if r < RECALL_THRESHOLD
        or conf_pairs.get(cls, {}).get("confusion_rate", 0.0) >= CONFUSION_THRESHOLD
    ]

    return {
        "session_id":          session_id,
        "mode":                m.get("mode"),
        "classes":             m.get("classes", []),
        "per_class_recall":    recall,
        "confusion_pairs":     conf_pairs,
        "best_val_acc":        m.get("best_val_acc"),
        "recall_threshold":    RECALL_THRESHOLD,
        "confusion_threshold": CONFUSION_THRESHOLD,
        "weak_classes":        weak,
    }


@router.post("/upload-new-class")
async def upload_new_class(
    new_class_file: UploadFile = File(...),
    old_samples_file: Optional[UploadFile] = File(None),
    use_saved_samples: bool = Form(True),
    recall_threshold: float = Form(
        RECALL_THRESHOLD,
        description="Recall below this → retrain. Default 0.90.",
    ),
    confusion_threshold: float = Form(
        CONFUSION_THRESHOLD,
        description="Confusion rate above this → retrain. Default 0.25.",
    ),
):
    """
    Decision table
    ──────────────
    Upload contains only NEW class folders
        → train normally, expand head

    Upload contains only EXISTING class folders
        → each folder checked against last CM:
            recall < 0.90 or confusion >= 0.25  → retrain (retrain_only mode)
            recall >= 0.90 and confusion < 0.25 → skip, return 400 with details

    Upload contains MIXED (new + existing)
        → new folders always trained
        → existing folders CM-checked, weak ones included
    """
    info = get_latest_model_info()
    if not info:
        raise HTTPException(400, "Train an initial model before adding new classes.")

    session_id   = f"inc_{str(uuid.uuid4())[:8]}"
    existing_set = set(info["classes"])

    # ── Extract ZIP ───────────────────────────────────────────────────────
    zip_path = UPLOAD_DIR / f"{session_id}_new.zip"
    zip_path.write_bytes(await new_class_file.read())

    if not zipfile.is_zipfile(zip_path):
        raise HTTPException(400, "new_class_file must be a ZIP archive.")

    new_root       = extract_upload(zip_path, f"{session_id}_new")
    candidate_dirs = sorted([d for d in new_root.iterdir() if d.is_dir()])

    if not candidate_dirs:
        raise HTTPException(400, "ZIP must contain at least one class sub-folder.")

    # ── Split: truly new vs existing ─────────────────────────────────────
    truly_new_dirs = [d for d in candidate_dirs if d.name not in existing_set]
    existing_dirs  = [d for d in candidate_dirs if d.name in existing_set]

    # ── CM quality check for existing class folders ───────────────────────
    weak_names, skipped_names, quality_report = _classify_existing_classes(
        [d.name for d in existing_dirs],
        info, recall_threshold, confusion_threshold,
    )

    weak_dirs  = [d for d in existing_dirs if d.name in weak_names]
    train_dirs = truly_new_dirs + weak_dirs  # everything that needs training

    truly_new_names = [d.name for d in truly_new_dirs]

    # ── Nothing to train ─────────────────────────────────────────────────
    if not train_dirs:
        detail_lines = [
            f"  {cls}: recall={quality_report[cls]['recall']:.2f}, "
            f"confusion={quality_report[cls]['confusion_rate']:.2f} → skipped (healthy)"
            for cls in skipped_names
        ]
        raise HTTPException(
            400,
            "Nothing to train.\n"
            "All uploaded classes already exist in the model and are healthy "
            f"(recall >= {recall_threshold:.0%}, confusion < {confusion_threshold:.0%}):\n"
            + "\n".join(detail_lines),
        )

    # ── Resolve old samples ───────────────────────────────────────────────
    old_samples_path: Optional[Path] = None

    if use_saved_samples:
        saved = SAMPLES_DIR / info["session_id"]
        if saved.exists():
            old_samples_path = saved

    if old_samples_path is None and old_samples_file is not None:
        old_zip = UPLOAD_DIR / f"{session_id}_old.zip"
        old_zip.write_bytes(await old_samples_file.read())
        if not zipfile.is_zipfile(old_zip):
            raise HTTPException(400, "old_samples_file must be a ZIP archive.")
        old_samples_path = extract_upload(old_zip, f"{session_id}_old_samples")

    if old_samples_path is None:
        raise HTTPException(
            400,
            "No old samples available. "
            "Enable use_saved_samples or upload old_samples_file.",
        )

    # ── Merge + prepare dataset ───────────────────────────────────────────
    merged_dir   = merge_old_samples_with_new(train_dirs, old_samples_path, session_id)
    dataset_info = prepare_dataset(merged_dir, session_id)
    save_samples(merged_dir, session_id)

    # ── Persist session metadata ──────────────────────────────────────────
    meta = {
        "old_model_path":          info["checkpoint_path"],
        "old_classes":             sorted(existing_set),
        "truly_new_classes":       truly_new_names,
        "weak_existing_classes":   weak_names,
        "skipped_classes":         skipped_names,
        "quality_report":          quality_report,
        "recall_threshold":        recall_threshold,
        "confusion_threshold":     confusion_threshold,
    }
    (UPLOAD_DIR / f"{session_id}_meta.json").write_text(json.dumps(meta, indent=2))

    # Determine the mode the service will use (for UI clarity)
    if truly_new_names and weak_names:
        mode = "new+weak"
    elif truly_new_names:
        mode = "new_only"
    else:
        mode = "retrain_only"

    return {
        "session_id":            session_id,
        "mode":                  mode,
        # ── Per bucket ────────────────────────────────────────────────────
        "new_classes":           truly_new_names,   # brand new
        "weak_existing_classes": weak_names,        # existing but poorly learned
        "skipped_classes":       skipped_names,     # existing and healthy
        # ── Full picture ──────────────────────────────────────────────────
        "old_classes":           sorted(existing_set),
        "all_classes":           dataset_info["classes"],
        "quality_report":        quality_report,
        "recall_threshold":      recall_threshold,
        "confusion_threshold":   confusion_threshold,
        "dataset_info":          dataset_info,
        "start_url":             f"/incremental/start/{session_id}",
        "progress_url":          f"/incremental/progress/{session_id}",
        "summary": (
            f"Mode: {mode} | "
            f"{len(truly_new_names)} new, "
            f"{len(weak_names)} weak→retrain, "
            f"{len(skipped_names)} healthy→skip"
        ),
    }


@router.post("/start/{session_id}")
async def start_incremental(session_id: str):
    info = get_latest_model_info()
    if not info:
        raise HTTPException(400, "No base model found.")

    dataset_path = DATASET_DIR / session_id
    if not dataset_path.exists():
        raise HTTPException(
            404,
            f"Dataset for session '{session_id}' not found. "
            "Call /incremental/upload-new-class first.",
        )

    if session_id in _jobs:
        raise HTTPException(409, "Training already in progress for this session.")

    meta_path = UPLOAD_DIR / f"{session_id}_meta.json"
    if meta_path.exists():
        with open(meta_path) as f:
            meta = json.load(f)
    else:
        # Backward-compat fallback
        meta = {
            "old_model_path":        info["checkpoint_path"],
            "old_classes":           info["classes"],
            "truly_new_classes":     [],
            "weak_existing_classes": [],
        }

    q: Queue = Queue()
    _jobs[session_id] = q

    def _run() -> None:
        try:
            train_incremental(
                dataset_path          = dataset_path,
                old_model_path        = Path(meta["old_model_path"]),
                old_classes           = meta["old_classes"],
                session_id            = session_id,
                progress_queue        = q,
                weak_existing_classes = meta.get("weak_existing_classes", []),
                truly_new_classes     = meta.get("truly_new_classes",     []),
            )
        except Exception as exc:
            q.put({"type": "error", "message": str(exc)})
        finally:
            _jobs.pop(session_id, None)

    Thread(target=_run, daemon=True).start()

    return {
        "session_id":             session_id,
        "status":                 "started",
        "mode":                   meta.get("mode", "unknown"),
        "truly_new_classes":      meta.get("truly_new_classes",     []),
        "weak_existing_classes":  meta.get("weak_existing_classes", []),
        "progress_url":           f"/incremental/progress/{session_id}",
    }


@router.get("/progress/{session_id}")
async def incremental_progress(session_id: str):
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
                yield 'data: {"type": "heartbeat"}\n\n'

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )