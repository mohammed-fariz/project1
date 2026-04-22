"""
Initial training service.

train_initial_model()
  ├── auto-selects hyperparameters
  ├── trains ResNet18 (frozen or full fine-tune based on dataset size)
  ├── streams progress via a Queue (consumed by SSE route)
  ├── saves best checkpoint, confusion matrix, metrics JSON
  └── updates models/registry.json
"""
import json
import torch
import torch.nn as nn
from torch.utils.data import DataLoader
from torchvision import datasets, transforms
from pathlib import Path
from queue import Queue
from typing import Dict, Any
from sklearn.metrics import confusion_matrix
import numpy as np

from config import (
    CHECKPOINTS_DIR, CM_DIR, METRICS_DIR, MODEL_REGISTRY, IMG_SIZE
)
from models.resnet_model import build_model
from utils.auto_hp import compute_auto_hyperparams
from utils.confusion_matrix_utils import save_confusion_matrix

DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")


# ──────────────────────────────────────────────────────────────────────────────
# Shared transforms
# ──────────────────────────────────────────────────────────────────────────────

def get_transforms(train: bool) -> transforms.Compose:
    if train:
        return transforms.Compose([
            transforms.RandomResizedCrop(IMG_SIZE, scale=(0.7, 1.0)),
            transforms.RandomHorizontalFlip(),
            transforms.RandomRotation(15),
            transforms.ColorJitter(brightness=0.3, contrast=0.3, saturation=0.2),
            transforms.ToTensor(),
            transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
        ])
    return transforms.Compose([
        transforms.Resize(256),
        transforms.CenterCrop(IMG_SIZE),
        transforms.ToTensor(),
        transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
    ])


# ──────────────────────────────────────────────────────────────────────────────
# Model registry helpers
# ──────────────────────────────────────────────────────────────────────────────

def update_registry(session_id: str, metrics: Dict) -> None:
    """Append session to registry.json and mark it as the latest."""
    if MODEL_REGISTRY.exists():
        with open(MODEL_REGISTRY) as f:
            registry = json.load(f)
    else:
        registry = {"sessions": [], "latest": None}

    # Remove any stale entry with same session_id
    registry["sessions"] = [
        s for s in registry["sessions"] if s["session_id"] != session_id
    ]

    registry["sessions"].append({
        "session_id": session_id,
        "classes": metrics["classes"],
        "best_val_acc": metrics["best_val_acc"],
        "checkpoint_path": metrics["checkpoint_path"],
        "model_type": metrics["model_type"],
        "num_classes": len(metrics["classes"]),
    })
    registry["latest"] = session_id

    with open(MODEL_REGISTRY, "w") as f:
        json.dump(registry, f, indent=2)


def get_latest_model_info() -> Dict | None:
    """Return registry entry for the latest trained model, or None."""
    if not MODEL_REGISTRY.exists():
        return None
    with open(MODEL_REGISTRY) as f:
        registry = json.load(f)
    latest_id = registry.get("latest")
    if not latest_id:
        return None
    for s in registry["sessions"]:
        if s["session_id"] == latest_id:
            return s
    return None


# ──────────────────────────────────────────────────────────────────────────────
# Training helpers
# ──────────────────────────────────────────────────────────────────────────────

def _run_epoch(model, loader, criterion, optimizer, device, train: bool):
    model.train() if train else model.eval()
    total_loss, correct, total = 0.0, 0, 0
    all_preds, all_labels = [], []

    ctx = torch.enable_grad() if train else torch.no_grad()
    with ctx:
        for inputs, labels in loader:
            inputs, labels = inputs.to(device), labels.to(device)
            if train:
                optimizer.zero_grad()
            outputs = model(inputs)
            loss = criterion(outputs, labels)
            if train:
                loss.backward()
                optimizer.step()

            total_loss += loss.item() * inputs.size(0)
            _, preds = outputs.max(1)
            correct += preds.eq(labels).sum().item()
            total += inputs.size(0)
            all_preds.extend(preds.cpu().numpy())
            all_labels.extend(labels.cpu().numpy())

    return total_loss / total, correct / total, all_preds, all_labels


# ──────────────────────────────────────────────────────────────────────────────
# Main training entry point
# ──────────────────────────────────────────────────────────────────────────────

def train_initial_model(
    dataset_path: Path,
    session_id: str,
    progress_queue: Queue,
) -> Dict:
    """
    Train ResNet18 on the prepared dataset.
    All hyperparameters are computed automatically.
    Progress is pushed to `progress_queue` as dicts for SSE consumption.
    """
    train_ds = datasets.ImageFolder(dataset_path / "train", transform=get_transforms(True))
    val_ds = datasets.ImageFolder(dataset_path / "val", transform=get_transforms(False))

    classes = train_ds.classes
    n_classes = len(classes)
    n_train = len(train_ds)

    hp = compute_auto_hyperparams(n_train, n_classes, is_incremental=False)
    progress_queue.put({"type": "hp", "data": hp, "classes": classes, "device": str(DEVICE)})

    train_loader = DataLoader(
        train_ds, batch_size=hp["batch_size"], shuffle=True,
        num_workers=2, pin_memory=(DEVICE.type == "cuda")
    )
    val_loader = DataLoader(
        val_ds, batch_size=hp["batch_size"], shuffle=False, num_workers=2
    )

    # ── Build model ──────────────────────────────────────────────────────
    model = build_model(n_classes, pretrained=True).to(DEVICE)

    if hp["freeze_backbone"]:
        for name, param in model.named_parameters():
            if "fc" not in name:
                param.requires_grad = False

    # ── Optimizer & scheduler ────────────────────────────────────────────
    trainable = filter(lambda p: p.requires_grad, model.parameters())
    optimizer = torch.optim.AdamW(
        trainable, lr=hp["lr"], weight_decay=hp["weight_decay"]
    )
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(
        optimizer, T_max=hp["epochs"], eta_min=hp["lr"] * 0.01
    )
    criterion = nn.CrossEntropyLoss(label_smoothing=hp["label_smoothing"])

    # ── Training loop ────────────────────────────────────────────────────
    best_val_loss = float("inf")
    best_val_acc = 0.0   # keep this for logging only
    best_epoch = 0
    patience_counter = 0
    history: Dict[str, list] = {
        "train_loss": [], "train_acc": [], "val_loss": [], "val_acc": []
    }
    checkpoint_path = CHECKPOINTS_DIR / f"{session_id}_best.pth"

    for epoch in range(hp["epochs"]):
        t_loss, t_acc, _, _ = _run_epoch(
            model, train_loader, criterion, optimizer, DEVICE, train=True
        )
        v_loss, v_acc, val_preds, val_labels = _run_epoch(
            model, val_loader, criterion, optimizer, DEVICE, train=False
        )
        scheduler.step()

        history["train_loss"].append(round(t_loss, 4))
        history["train_acc"].append(round(t_acc, 4))
        history["val_loss"].append(round(v_loss, 4))
        history["val_acc"].append(round(v_acc, 4))

        is_best = v_loss < best_val_loss
        if is_best:
            best_val_loss = v_loss
            best_val_acc = v_acc   # optional (for reporting)
            best_epoch = epoch + 1
            patience_counter = 0
            torch.save(
                {
                    "epoch": epoch,
                    "model_state_dict": model.state_dict(),
                    "optimizer_state_dict": optimizer.state_dict(),
                    "val_acc": v_acc,
                    "val_loss": v_loss,
                    "classes": classes,
                    "num_classes": n_classes,
                },
                checkpoint_path,
            )
        else:
            patience_counter += 1

        progress_queue.put({
            "type": "epoch",
            "epoch": epoch + 1,
            "total_epochs": hp["epochs"],
            "train_loss": round(t_loss, 4),
            "train_acc": round(t_acc, 4),
            "val_loss": round(v_loss, 4),
            "val_acc": round(v_acc, 4),
            "is_best": is_best,
            "best_epoch": best_epoch,
            "best_val_acc": round(best_val_acc, 4),
            "best_val_loss": round(best_val_loss, 4),
            "lr": round(scheduler.get_last_lr()[0], 6),
        })

        if patience_counter >= hp["patience"]:
            progress_queue.put({"type": "early_stop", "epoch": epoch + 1, "patience": hp["patience"]})
            break

    # ── Confusion matrix from best checkpoint ───────────────────────────
    ckpt = torch.load(checkpoint_path, map_location=DEVICE)
    model.load_state_dict(ckpt["model_state_dict"])
    _, _, final_preds, final_labels = _run_epoch(
        model, val_loader, criterion, optimizer, DEVICE, train=False
    )

    cm = confusion_matrix(final_labels, final_preds, labels=list(range(n_classes)))
    cm_path = CM_DIR / f"{session_id}_cm.png"
    save_confusion_matrix(
        cm, classes, cm_path,
        title=f"Initial model — epoch {best_epoch} — val loss {best_val_loss:.4f}"
    )

    # ── Persist metrics ──────────────────────────────────────────────────
    metrics = {
        "session_id": session_id,
        "classes": classes,
        "best_epoch": best_epoch,
        "best_val_acc": best_val_acc,
        "hyperparams": hp,
        "history": history,
        "checkpoint_path": str(checkpoint_path),
        "cm_path": str(cm_path),
        "model_type": "initial",
    }
    with open(METRICS_DIR / f"{session_id}_metrics.json", "w") as f:
        json.dump(metrics, f, indent=2)

    update_registry(session_id, metrics)

    progress_queue.put({"type": "done", "metrics": metrics, "cm_url": f"/results/cm/{session_id}"})
    return metrics
