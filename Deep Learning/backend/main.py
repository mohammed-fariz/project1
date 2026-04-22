"""
FastAPI application entry point.

Run with:
    uvicorn main:app --reload --host 0.0.0.0 --port 8000

Swagger UI:  http://localhost:8000/docs
Frontend:    http://localhost:8000/app/
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pathlib import Path

from routers.training import router as train_router
from routers.incremental import router as incremental_router
from routers.results_and_inference import predict_router, results_router

app = FastAPI(
    title="ResNet18 Incremental Learning API",
    description=(
        "Train ResNet18 on custom image classes, then incrementally add new classes "
        "using Learning without Forgetting (LwF) — no scratch retraining needed."
    ),
    version="1.0.0",
)

# ── CORS ─────────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ───────────────────────────────────────────────────────────────────
app.include_router(train_router)
app.include_router(incremental_router)
app.include_router(predict_router)
app.include_router(results_router)

# ── Static frontend ───────────────────────────────────────────────────────────
frontend_dir = Path(__file__).parent.parent / "frontend"
if frontend_dir.exists():
    app.mount("/app", StaticFiles(directory=str(frontend_dir), html=True), name="frontend")


@app.get("/", tags=["Health"])
async def root():
    return {
        "status": "ok",
        "docs": "/docs",
        "frontend": "/app/",
        "endpoints": {
            "initial_training": "POST /train/upload-and-train",
            "training_progress": "GET  /train/progress/{session_id}  (SSE)",
            "model_info": "GET  /incremental/model-info",
            "add_new_class": "POST /incremental/upload-new-class",
            "start_incremental": "POST /incremental/start/{session_id}",
            "incremental_progress": "GET  /incremental/progress/{session_id}  (SSE)",
            "predict": "POST /predict/image",
            "confusion_matrix": "GET  /results/cm/{session_id}",
            "metrics": "GET  /results/metrics/{session_id}",
            "registry": "GET  /results/registry",
        },
    }


@app.get("/health", tags=["Health"])
async def health():
    return {"status": "ok"}
