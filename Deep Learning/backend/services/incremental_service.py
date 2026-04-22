"""
Incremental learning service — LwF + Hard Sample Mining + CM-based Weak Class Recovery.

Three training modes (resolved automatically):
──────────────────────────────────────────────
  MODE A — new classes only
      n_new_classes > old_num_classes, no weak classes
      → expand FC head, standard CE + KD

  MODE B — weak existing classes only (retrain-only)
      n_new_classes == old_num_classes, weak_existing_classes not empty
      → NO head expansion, CE + KD with reduced weight on weak classes
      → this is the case the old code broke on (guard fired, 404 returned)

  MODE C — mix of new + weak existing
      n_new_classes > old_num_classes, weak_existing_classes not empty
      → expand FC head, CE + KD, reduced weight on weak classes

The guard  `if n_new_classes <= len(old_classes): raise`  has been replaced
with a proper mode check that only raises when there is genuinely nothing to do.
"""

from __future__ import annotations

import json
import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.utils.data import DataLoader, WeightedRandomSampler, Dataset
from torchvision import datasets
from pathlib import Path
from queue import Queue
from typing import Dict, List, Optional

from sklearn.metrics import confusion_matrix

from config import (
    CHECKPOINTS_DIR, CM_DIR, METRICS_DIR,
    LWF_TEMPERATURE, LWF_WEIGHT,
)
from models.resnet_model import build_model, expand_model
from services.training_service import get_transforms, update_registry, DEVICE
from utils.auto_hp import compute_auto_hyperparams
from utils.confusion_matrix_utils import save_confusion_matrix


# ──────────────────────────────────────────────────────────────────────────────
# Constants
# ──────────────────────────────────────────────────────────────────────────────

HARD_MINING_RATIO:   float = 0.70
HARD_MINING_WARMUP:  int   = 2
WEAK_CLASS_KD_SCALE: float = 0.3   # reduced KD for weak/confused classes


# ──────────────────────────────────────────────────────────────────────────────
# IndexedDataset
# ──────────────────────────────────────────────────────────────────────────────

class IndexedDataset(Dataset):
    def __init__(self, dataset: Dataset) -> None:
        self.dataset = dataset

    def __len__(self) -> int:
        return len(self.dataset)  # type: ignore[arg-type]

    def __getitem__(self, idx: int):
        img, label = self.dataset[idx]
        return img, label, idx


# ──────────────────────────────────────────────────────────────────────────────
# HardSampleMiner
# ──────────────────────────────────────────────────────────────────────────────

class HardSampleMiner:
    def __init__(self, dataset_size: int, warmup_epochs: int = HARD_MINING_WARMUP) -> None:
        self.warmup_epochs = warmup_epochs
        self._weights = torch.ones(dataset_size, dtype=torch.float32)

    def record_batch_losses(self, indices: torch.Tensor, losses: torch.Tensor) -> None:
        self._weights[indices.cpu()] = losses.detach().cpu()

    def get_sampler(self, epoch: int) -> Optional[WeightedRandomSampler]:
        if epoch < self.warmup_epochs:
            return None
        w = self._weights.clone()
        w = (w - w.min() + 1e-6) / (w.max() - w.min() + 1e-6)
        uniform = torch.ones_like(w) / len(w)
        mixed = HARD_MINING_RATIO * (w / w.sum()) + (1.0 - HARD_MINING_RATIO) * uniform
        return WeightedRandomSampler(
            weights=mixed.tolist(), num_samples=len(mixed), replacement=True
        )


# ──────────────────────────────────────────────────────────────────────────────
# LwF distillation loss
# ──────────────────────────────────────────────────────────────────────────────

def lwf_distillation_loss(
    student_logits: torch.Tensor,
    teacher_logits: torch.Tensor,
    old_num_classes: int,
    temperature: float = LWF_TEMPERATURE,
    class_kd_weights: Optional[torch.Tensor] = None,
) -> torch.Tensor:
    s = student_logits[:, :old_num_classes] / temperature
    t = teacher_logits[:, :old_num_classes] / temperature

    soft_targets  = F.softmax(t, dim=1)
    log_soft_pred = F.log_softmax(s, dim=1)

    if class_kd_weights is not None:
        per_class_kl = F.kl_div(log_soft_pred, soft_targets, reduction="none").sum(dim=0)
        kd_loss = (per_class_kl * class_kd_weights).mean()
    else:
        kd_loss = F.kl_div(log_soft_pred, soft_targets, reduction="batchmean")

    return kd_loss * (temperature ** 2)


# ──────────────────────────────────────────────────────────────────────────────
# Training entry point
# ──────────────────────────────────────────────────────────────────────────────

def train_incremental(
    dataset_path: Path,
    old_model_path: Path,
    old_classes: List[str],
    session_id: str,
    progress_queue: Queue,
    lwf_weight: float = LWF_WEIGHT,
    weak_existing_classes: Optional[List[str]] = None,
    truly_new_classes: Optional[List[str]] = None,
) -> Dict:
    """
    Parameters
    ----------
    weak_existing_classes : existing class names that scored < threshold on CM
                            → retrained with relaxed KD weight
    truly_new_classes     : brand-new class names not in old model
                            → requires head expansion
    """
    weak_existing_classes = weak_existing_classes or []
    truly_new_classes     = truly_new_classes     or []

    # ── Datasets ──────────────────────────────────────────────────────────
    base_train_ds = datasets.ImageFolder(
        dataset_path / "train", transform=get_transforms(True)
    )
    base_val_ds = datasets.ImageFolder(
        dataset_path / "val", transform=get_transforms(False)
    )

    all_classes   = base_train_ds.classes
    n_new_classes = len(all_classes)
    n_train       = len(base_train_ds)

    # ── Load checkpoint ───────────────────────────────────────────────────
    ckpt            = torch.load(old_model_path, map_location=DEVICE)
    old_num_classes = ckpt["num_classes"]

    # ── Resolve training mode ─────────────────────────────────────────────
    has_new_classes  = n_new_classes > old_num_classes   # head must grow
    has_weak_classes = len(weak_existing_classes) > 0    # retrain only

    if not has_new_classes and not has_weak_classes:
        raise ValueError(
            "Nothing to train: no new classes and no weak existing classes provided."
        )

    if has_new_classes:
        mode = "new+weak" if has_weak_classes else "new_only"
    else:
        mode = "retrain_only"   # MODE B — same class count, no head expansion

    hp = compute_auto_hyperparams(n_train, n_new_classes, is_incremental=True)

    progress_queue.put({
        "type":                  "hp",
        "mode":                  mode,
        "data":                  hp,
        "classes":               all_classes,
        "old_classes":           old_classes,
        "truly_new_classes":     truly_new_classes,
        "weak_existing_classes": weak_existing_classes,
        "device":                str(DEVICE),
        "lwf_weight":            lwf_weight,
        "hard_mining_warmup":    HARD_MINING_WARMUP,
    })

    # ── Build DataLoaders ─────────────────────────────────────────────────
    indexed_train_ds = IndexedDataset(base_train_ds)
    miner = HardSampleMiner(dataset_size=n_train)

    val_loader = DataLoader(
        base_val_ds, batch_size=hp["batch_size"],
        shuffle=False, num_workers=2,
        pin_memory=(DEVICE.type == "cuda"),
    )

    # ── Student model ─────────────────────────────────────────────────────
    student = build_model(old_num_classes, pretrained=False)
    student.load_state_dict(ckpt["model_state_dict"])

    if has_new_classes:
        # MODE A / C: expand the FC head to cover new classes
        student, _ = expand_model(student, n_new_classes)
    # MODE B: head stays the same size — no expand_model call

    student = student.to(DEVICE)

    # ── Teacher model (frozen) ────────────────────────────────────────────
    teacher = build_model(old_num_classes, pretrained=False)
    teacher.load_state_dict(ckpt["model_state_dict"])
    teacher = teacher.to(DEVICE).eval()
    for p in teacher.parameters():
        p.requires_grad = False

    # ── Per-class KD weights ──────────────────────────────────────────────
    # Weak classes get 0.3× KD so student can correct the teacher's mistakes.
    # Strong/new classes get 1.0× KD to preserve knowledge.
    class_kd_weights = torch.ones(old_num_classes, device=DEVICE)
    for cls in weak_existing_classes:
        if cls in old_classes:
            class_kd_weights[old_classes.index(cls)] = WEAK_CLASS_KD_SCALE

    # ── Optimizer ─────────────────────────────────────────────────────────
    backbone_params = [p for n, p in student.named_parameters() if "fc" not in n]
    head_params     = list(student.fc.parameters())

    optimizer = torch.optim.AdamW(
        [
            {"params": backbone_params, "lr": hp["lr"] * hp["backbone_lr_multiplier"]},
            {"params": head_params,     "lr": hp["lr"]},
        ],
        weight_decay=hp["weight_decay"],
    )
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(
        optimizer, T_max=hp["epochs"], eta_min=hp["lr"] * 0.01
    )

    ce_criterion = nn.CrossEntropyLoss(
        label_smoothing=hp["label_smoothing"],
        reduction="none",   # keep per-sample losses for hard mining
    )

    # ── Training loop ─────────────────────────────────────────────────────
    best_val_acc     = 0.0
    best_epoch       = 0
    patience_counter = 0

    history: Dict = {
        "train_loss": [], "train_acc": [],
        "val_loss":   [], "val_acc":   [],
        "lwf_loss":   [], "hard_mining_active": [],
    }

    checkpoint_path = CHECKPOINTS_DIR / f"{session_id}_best.pth"

    for epoch in range(hp["epochs"]):
        mining_active = epoch >= HARD_MINING_WARMUP
        sampler       = miner.get_sampler(epoch)

        train_loader = DataLoader(
            indexed_train_ds,
            batch_size=hp["batch_size"],
            sampler=sampler,
            shuffle=(sampler is None),
            num_workers=2,
            pin_memory=(DEVICE.type == "cuda"),
        )

        # ── Train ─────────────────────────────────────────────────────────
        student.train()
        total_loss_sum = lwf_loss_sum = 0.0
        correct = total = 0
        epoch_indices: List[torch.Tensor] = []
        epoch_losses:  List[torch.Tensor] = []

        for inputs, labels, indices in train_loader:
            inputs, labels = inputs.to(DEVICE), labels.to(DEVICE)
            optimizer.zero_grad()

            student_out   = student(inputs)
            per_sample_ce = ce_criterion(student_out, labels)   # (B,)
            ce_loss       = per_sample_ce.mean()

            with torch.no_grad():
                teacher_out = teacher(inputs)

            kd_loss = lwf_distillation_loss(
                student_out, teacher_out, old_num_classes,
                class_kd_weights=class_kd_weights,
            )

            loss = ce_loss + lwf_weight * kd_loss
            loss.backward()
            torch.nn.utils.clip_grad_norm_(student.parameters(), max_norm=5.0)
            optimizer.step()

            n = inputs.size(0)
            total_loss_sum += loss.item() * n
            lwf_loss_sum   += kd_loss.item() * n
            _, preds = student_out.max(1)
            correct += preds.eq(labels).sum().item()
            total   += n

            epoch_indices.append(indices.cpu())
            epoch_losses.append(per_sample_ce.detach().cpu())

        scheduler.step()
        miner.record_batch_losses(torch.cat(epoch_indices), torch.cat(epoch_losses))

        t_acc  = correct / total
        t_loss = total_loss_sum / total
        t_lwf  = lwf_loss_sum / total

        # ── Validate ──────────────────────────────────────────────────────
        student.eval()
        v_loss_sum = v_correct = v_total = 0

        with torch.no_grad():
            for inputs, labels in val_loader:
                inputs, labels = inputs.to(DEVICE), labels.to(DEVICE)
                out = student(inputs)
                v_loss_sum += F.cross_entropy(out, labels).item() * inputs.size(0)
                _, preds = out.max(1)
                v_correct += preds.eq(labels).sum().item()
                v_total   += inputs.size(0)

        v_acc      = v_correct / v_total
        v_loss_avg = v_loss_sum / v_total

        history["train_loss"].append(round(t_loss, 4))
        history["train_acc"].append(round(t_acc, 4))
        history["val_loss"].append(round(v_loss_avg, 4))
        history["val_acc"].append(round(v_acc, 4))
        history["lwf_loss"].append(round(t_lwf, 4))
        history["hard_mining_active"].append(mining_active)

        is_best = v_acc > best_val_acc
        if is_best:
            best_val_acc     = v_acc
            best_epoch       = epoch + 1
            patience_counter = 0
            torch.save({
                "epoch":                  epoch,
                "model_state_dict":       student.state_dict(),
                "optimizer_state_dict":   optimizer.state_dict(),
                "val_acc":                v_acc,
                "classes":                all_classes,
                "num_classes":            n_new_classes,
                "weak_existing_classes":  weak_existing_classes,
                "truly_new_classes":      truly_new_classes,
                "mode":                   mode,
            }, checkpoint_path)
        else:
            patience_counter += 1

        progress_queue.put({
            "type":               "epoch",
            "epoch":              epoch + 1,
            "total_epochs":       hp["epochs"],
            "train_loss":         round(t_loss, 4),
            "train_acc":          round(t_acc, 4),
            "val_loss":           round(v_loss_avg, 4),
            "val_acc":            round(v_acc, 4),
            "lwf_loss":           round(t_lwf, 4),
            "hard_mining_active": mining_active,
            "is_best":            is_best,
            "best_epoch":         best_epoch,
            "best_val_acc":       round(best_val_acc, 4),
            "lr":                 round(scheduler.get_last_lr()[0], 6),
            "mode":               mode,
        })

        if patience_counter >= hp["patience"]:
            progress_queue.put({"type": "early_stop", "epoch": epoch + 1})
            break

    if not checkpoint_path.exists():
        raise RuntimeError("No checkpoint was saved during training.")

    # ── Final confusion matrix ────────────────────────────────────────────
    final_ckpt = torch.load(checkpoint_path, map_location=DEVICE)
    student.load_state_dict(final_ckpt["model_state_dict"])
    student.eval()

    preds_final, labels_final = [], []
    with torch.no_grad():
        for inputs, labels in val_loader:
            out = student(inputs.to(DEVICE))
            _, preds = out.max(1)
            preds_final.extend(preds.cpu().numpy())
            labels_final.extend(labels.numpy())

    cm = confusion_matrix(
        labels_final, preds_final,
        labels=list(range(n_new_classes)),
    )

    cm_path = CM_DIR / f"{session_id}_cm.png"
    save_confusion_matrix(
        cm, all_classes, cm_path,
        title=(
            f"Incremental [{mode}] — epoch {best_epoch} — val acc {best_val_acc:.2%}"
        ),
    )

    # ── Per-class recall from CM diagonal ────────────────────────────────
    row_sums = cm.sum(axis=1)
    per_class_recall = {
        cls: round(float(cm[i, i] / row_sums[i]) if row_sums[i] > 0 else 0.0, 4)
        for i, cls in enumerate(all_classes)
    }

    # ── Worst pairwise confusion per class ────────────────────────────────
    confusion_pairs = {}
    for i, cls in enumerate(all_classes):
        row = cm[i].copy()
        row[i] = 0
        worst_j     = int(row.argmax())
        worst_count = int(row[worst_j])
        total_i     = int(cm[i].sum())
        if total_i > 0 and worst_count > 0:
            confusion_pairs[cls] = {
                "confused_with":  all_classes[worst_j],
                "confusion_rate": round(worst_count / total_i, 4),
            }

    # ── Save metrics ──────────────────────────────────────────────────────
    metrics = {
        "session_id":              session_id,
        "mode":                    mode,
        "classes":                 all_classes,
        "old_classes":             old_classes,
        "truly_new_classes":       truly_new_classes,
        "weak_existing_classes":   weak_existing_classes,
        "best_epoch":              best_epoch,
        "best_val_acc":            best_val_acc,
        "cm_data":                 cm.tolist(),
        "per_class_recall":        per_class_recall,
        "confusion_pairs":         confusion_pairs,
        "hyperparams":             hp,
        "history":                 history,
        "checkpoint_path":         str(checkpoint_path),
        "cm_path":                 str(cm_path),
        "model_type":              "incremental",
        "lwf_weight":              lwf_weight,
        "hard_mining_warmup":      HARD_MINING_WARMUP,
    }

    with open(METRICS_DIR / f"{session_id}_metrics.json", "w") as f:
        json.dump(metrics, f, indent=2)

    update_registry(session_id, metrics)

    progress_queue.put({
        "type":             "done",
        "metrics":          metrics,
        "cm_url":           f"/results/cm/{session_id}",
        "per_class_recall": per_class_recall,
        "confusion_pairs":  confusion_pairs,
        "mode":             mode,
    })

    return metrics