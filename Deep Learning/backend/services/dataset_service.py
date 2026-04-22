"""
Dataset service — all file-system operations for building datasets.

Key functions
─────────────
extract_upload()              : unzip an uploaded file into a session folder
prepare_dataset()             : split class folders into train/ and val/
save_samples()                : stash N images per class for future incremental sessions
merge_old_samples_with_new()  : combine new class + old samples into one source tree
"""
import os
import shutil
import random
import zipfile
from pathlib import Path
from typing import Dict, List, Optional

from config import (
    UPLOAD_DIR, DATASET_DIR, SAMPLES_DIR, TRAIN_SPLIT, SAMPLES_PER_CLASS
)

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tiff"}


def _gather_images(folder: Path) -> List[Path]:
    return [
        p for p in folder.iterdir()
        if p.is_file() and p.suffix.lower() in IMAGE_EXTS
    ]


# ──────────────────────────────────────────────────────────────────────────────
# Extraction
# ──────────────────────────────────────────────────────────────────────────────

def extract_upload(zip_path: Path, session_id: str) -> Path:
    """
    Extract a ZIP archive into  data/uploads/<session_id>/.
    Returns the extraction root path.
    """
    extract_root = UPLOAD_DIR / session_id
    if extract_root.exists():
        shutil.rmtree(extract_root)
    extract_root.mkdir(parents=True)

    with zipfile.ZipFile(zip_path, "r") as zf:
        zf.extractall(extract_root)

    # If the ZIP has a single top-level folder, unwrap it so we get class folders directly
    children = [p for p in extract_root.iterdir() if not p.name.startswith("__")]
    if len(children) == 1 and children[0].is_dir():
        inner = children[0]
        for item in inner.iterdir():
            shutil.move(str(item), extract_root / item.name)
        inner.rmdir()

    return extract_root


# ──────────────────────────────────────────────────────────────────────────────
# Train / val split
# ──────────────────────────────────────────────────────────────────────────────

def prepare_dataset(source_dir: Path, session_id: str) -> Dict:
    """
    Build  data/datasets/<session_id>/train/<cls>/  and  …/val/<cls>/
    from a flat class-folder structure under source_dir.

    Returns a dict with class names and per-class image counts.
    """
    dataset_path = DATASET_DIR / session_id
    train_root = dataset_path / "train"
    val_root = dataset_path / "val"

    # Clean slate
    if dataset_path.exists():
        shutil.rmtree(dataset_path)

    class_dirs = sorted([d for d in source_dir.iterdir() if d.is_dir()])
    classes = [d.name for d in class_dirs]
    counts: Dict[str, Dict] = {}

    for cls_dir in class_dirs:
        images = _gather_images(cls_dir)
        random.shuffle(images)

        n_train = max(1, int(len(images) * TRAIN_SPLIT))
        train_imgs = images[:n_train]
        val_imgs = images[n_train:] if len(images) > 1 else images[:1]  # at least 1 val

        (train_root / cls_dir.name).mkdir(parents=True, exist_ok=True)
        (val_root / cls_dir.name).mkdir(parents=True, exist_ok=True)

        for img in train_imgs:
            shutil.copy2(img, train_root / cls_dir.name / img.name)
        for img in val_imgs:
            shutil.copy2(img, val_root / cls_dir.name / img.name)

        counts[cls_dir.name] = {"train": len(train_imgs), "val": len(val_imgs)}

    return {
        "classes": classes,
        "counts": counts,
        "dataset_path": str(dataset_path),
        "n_total_train": sum(v["train"] for v in counts.values()),
        "n_total_val": sum(v["val"] for v in counts.values()),
    }


# ──────────────────────────────────────────────────────────────────────────────
# Sample management
# ──────────────────────────────────────────────────────────────────────────────

def save_samples(source_dir: Path, session_id: str, n: int = SAMPLES_PER_CLASS) -> Path:
    """
    Copy up to `n` images per class into  data/samples/<session_id>/.
    These are re-used in future incremental learning sessions to prevent
    catastrophic forgetting alongside LwF.
    """
    samples_path = SAMPLES_DIR / session_id
    if samples_path.exists():
        shutil.rmtree(samples_path)

    for cls_dir in [d for d in source_dir.iterdir() if d.is_dir()]:
        images = _gather_images(cls_dir)
        random.shuffle(images)
        chosen = images[:n]

        out_dir = samples_path / cls_dir.name
        out_dir.mkdir(parents=True)
        for img in chosen:
            shutil.copy2(img, out_dir / img.name)

    return samples_path


def merge_old_samples_with_new(
    new_class_dirs: list,          # List[Path] — one or more NEW class folders
    old_samples_path: Path,
    session_id: str,
) -> Path:
    """
    Build a merged source tree for incremental training:
      merged/
        <new_class_1>/  ← new images (1 or more new classes)
        <new_class_2>/  …
        <old_class_1>/  ← saved samples
        <old_class_2>/  …

    Args:
        new_class_dirs   : list of Path objects, each being a folder of new-class images
        old_samples_path : root folder containing one sub-folder per old class
        session_id       : used to name the merged folder uniquely

    Returns the root of the merged tree.
    """
    merged = UPLOAD_DIR / f"{session_id}_merged"
    if merged.exists():
        shutil.rmtree(merged)
    merged.mkdir(parents=True)

    # New classes (can be more than one)
    for cls_dir in new_class_dirs:
        dst = merged / cls_dir.name
        dst.mkdir(exist_ok=True)
        for img in _gather_images(cls_dir):
            shutil.copy2(img, dst / img.name)

    # Old class samples
    for cls_dir in [d for d in old_samples_path.iterdir() if d.is_dir()]:
        dst_old = merged / cls_dir.name
        dst_old.mkdir(exist_ok=True)
        for img in _gather_images(cls_dir):
            shutil.copy2(img, dst_old / img.name)

    return merged
