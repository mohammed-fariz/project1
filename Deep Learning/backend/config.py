from pathlib import Path
import json

BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "data"
MODELS_DIR = BASE_DIR / "models"
RESULTS_DIR = BASE_DIR / "results"

UPLOAD_DIR = DATA_DIR / "uploads"
DATASET_DIR = DATA_DIR / "datasets"
SAMPLES_DIR = DATA_DIR / "samples"

CHECKPOINTS_DIR = MODELS_DIR / "checkpoints"
CM_DIR = RESULTS_DIR / "confusion_matrices"
METRICS_DIR = RESULTS_DIR / "metrics"
MODEL_REGISTRY = MODELS_DIR / "registry.json"

# Auto-create all directories on import
for _d in [UPLOAD_DIR, DATASET_DIR, SAMPLES_DIR, CHECKPOINTS_DIR, CM_DIR, METRICS_DIR]:
    _d.mkdir(parents=True, exist_ok=True)

# Training constants
TRAIN_SPLIT = 0.8
IMG_SIZE = 224
SAMPLES_PER_CLASS = 30          # How many samples to save per class for future incremental
LWF_TEMPERATURE = 2.0           # Distillation temperature for LwF
LWF_WEIGHT = 1.0              # Weight of distillation loss vs CE loss
