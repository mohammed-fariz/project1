"""
/predict  and  /results  routes
─────────────────────────────────
POST /predict/image           Classify image — returns unknown if confidence < threshold
GET  /results/cm/{session_id} Serve confusion matrix PNG
GET  /results/metrics/{id}    Training metrics JSON
GET  /results/registry        Full model registry
GET  /results/history/{id}    Epoch history for charting
GET  /results/latest          Latest model info
"""
import io
from pathlib import Path

from fastapi import APIRouter, File, Form, UploadFile, HTTPException
from fastapi.responses import FileResponse
from PIL import Image
import torch
import torch.nn.functional as F
from torchvision import transforms
import json

from config import CM_DIR, METRICS_DIR, MODEL_REGISTRY, IMG_SIZE
from models.resnet_model import build_model
from services.training_service import get_latest_model_info, DEVICE

# ─────────────────────────────────────────────────────────────────────────────
# Inference router
# ─────────────────────────────────────────────────────────────────────────────
predict_router = APIRouter(prefix="/predict", tags=["Inference"])

_model_cache: dict = {}   # { checkpoint_path: (model, classes) }

_val_transform = transforms.Compose([
    transforms.Resize(256),
    transforms.CenterCrop(IMG_SIZE),
    transforms.ToTensor(),
    transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
])

# Default threshold — predictions below this → "unknown"
DEFAULT_THRESHOLD = 0.60


def _load_latest_model():
    """Load and cache the latest registered model."""
    info = get_latest_model_info()
    if not info:
        return None, None

    ckpt_path = info["checkpoint_path"]
    if ckpt_path in _model_cache:
        return _model_cache[ckpt_path]

    ckpt = torch.load(ckpt_path, map_location=DEVICE)
    classes = ckpt["classes"]
    n_classes = ckpt["num_classes"]

    model = build_model(n_classes, pretrained=False)
    model.load_state_dict(ckpt["model_state_dict"])
    model = model.to(DEVICE).eval()

    _model_cache.clear()             # keep only the latest model in cache
    _model_cache[ckpt_path] = (model, classes)
    return model, classes


@predict_router.post("/image", summary="Classify image with confidence threshold")
async def predict_image(
    file: UploadFile = File(..., description="Image file to classify (JPEG / PNG)"),
    threshold: float = Form(
        DEFAULT_THRESHOLD,
        description=(
            "Confidence threshold (0-1). If the top-1 softmax score is below this "
            "value the response returns prediction='unknown' and below_threshold=true. "
            "Increase to be stricter; decrease to allow lower-confidence predictions. "
            "Default: 0.60"
        ),
    ),
):
    """
    Classifies a single image.

    **Why threshold matters:**
    A softmax classifier always outputs a probability distribution that sums to 1.
    Even for a completely unrelated image (screenshot, random photo) the model
    is forced to pick the most-likely class — it can never say "I don't know".
    The threshold adds that guard: if no class reaches the minimum confidence the
    result is labelled "unknown" instead.

    **Sent as a multipart form field** (same request as the file) so it is always
    received correctly regardless of browser / fetch configuration.

    Response:
    ```json
    {
      "prediction":       "dog",           // class name, or "unknown"
      "confidence":       0.87,            // top-1 softmax probability
      "below_threshold":  false,           // true → image is likely out-of-distribution
      "threshold_used":   0.60,            // threshold that was applied
      "all_probs": [
        {"class": "dog",  "probability": 0.87},
        {"class": "cat",  "probability": 0.09},
        {"class": "bird", "probability": 0.04}
      ],
      "model_classes":    ["bird","cat","dog"]
    }
    ```
    """
    # ── Validate threshold range ─────────────────────────────────────────
    if not (0.0 <= threshold <= 1.0):
        raise HTTPException(
            422,
            f"threshold must be between 0.0 and 1.0, got {threshold}"
        )

    # ── Load model ────────────────────────────────────────────────────────
    model, classes = _load_latest_model()
    if model is None:
        raise HTTPException(
            400, "No trained model found. Complete initial training first."
        )

    # ── Decode image ──────────────────────────────────────────────────────
    img_bytes = await file.read()
    if not img_bytes:
        raise HTTPException(400, "Empty file received.")

    try:
        img = Image.open(io.BytesIO(img_bytes)).convert("RGB")
    except Exception:
        raise HTTPException(
            400,
            "Could not decode the image. Upload a valid JPEG or PNG file."
        )

    # ── Run inference ─────────────────────────────────────────────────────
    tensor = _val_transform(img).unsqueeze(0).to(DEVICE)

    with torch.no_grad():
        logits = model(tensor)
        probs  = F.softmax(logits, dim=1)[0]   # shape: (n_classes,)

    # Sort all class probabilities highest → lowest
    all_probs = sorted(
        [
            {"class": cls, "probability": round(p.item(), 4)}
            for cls, p in zip(classes, probs)
        ],
        key=lambda x: -x["probability"],
    )

    top_conf       = all_probs[0]["probability"]
    below_threshold = top_conf < threshold

    return {
        "prediction":      "unknown" if below_threshold else all_probs[0]["class"],
        "confidence":      top_conf,
        "below_threshold": below_threshold,
        "threshold_used":  threshold,
        "all_probs":       all_probs,
        "model_classes":   classes,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Results router
# ─────────────────────────────────────────────────────────────────────────────
results_router = APIRouter(prefix="/results", tags=["Results & metrics"])


@results_router.get("/cm/{session_id}", summary="Get confusion matrix PNG")
async def get_cm(session_id: str):
    path = CM_DIR / f"{session_id}_cm.png"
    if not path.exists():
        raise HTTPException(404, f"Confusion matrix for '{session_id}' not found.")
    return FileResponse(path, media_type="image/png")


@results_router.get("/metrics/{session_id}", summary="Get full training metrics JSON")
async def get_metrics(session_id: str):
    path = METRICS_DIR / f"{session_id}_metrics.json"
    if not path.exists():
        raise HTTPException(404, f"Metrics for '{session_id}' not found.")
    with open(path) as f:
        return json.load(f)


@results_router.get("/history/{session_id}", summary="Get epoch history for chart rendering")
async def get_history(session_id: str):
    path = METRICS_DIR / f"{session_id}_metrics.json"
    if not path.exists():
        raise HTTPException(404, "Metrics not found.")
    with open(path) as f:
        data = json.load(f)
    return {
        "session_id":   session_id,
        "classes":      data["classes"],
        "best_epoch":   data["best_epoch"],
        "best_val_acc": data["best_val_acc"],
        "history":      data["history"],
        "model_type":   data.get("model_type", "unknown"),
    }


@results_router.get("/registry", summary="Get full model registry")
async def get_registry():
    if not MODEL_REGISTRY.exists():
        return {"sessions": [], "latest": None}
    with open(MODEL_REGISTRY) as f:
        return json.load(f)


@results_router.get("/latest", summary="Get latest model info")
async def get_latest():
    info = get_latest_model_info()
    if not info:
        raise HTTPException(404, "No models trained yet.")
    return info
