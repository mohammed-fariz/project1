"""
Automatic hyperparameter selection.
No manual tuning needed — parameters are derived from dataset size, class count,
and whether we are doing initial training or incremental fine-tuning.
"""
import math
from typing import Dict, Any


def compute_auto_hyperparams(
    n_train: int,
    n_classes: int,
    is_incremental: bool = False,
) -> Dict[str, Any]:
    """
    Derive optimal hyperparameters automatically.

    Strategy:
      - Batch size scales with dataset size (keeps GPU utilisation reasonable)
      - LR is lower for incremental (avoid catastrophic forgetting)
      - Epochs: enough to converge, capped to avoid over-training small sets
      - Patience: 20% of epoch budget, minimum 5
      - Backbone freeze: freeze when data is too small to fine-tune safely
      - Backbone LR multiplier: 10× smaller than head LR during incremental
    """
    # ── Batch size ──────────────────────────────────────────────────────
    if n_train < 150:
        batch_size = 16
    elif n_train < 500:
        batch_size = 32
    else:
        batch_size = 64

    # ── Learning rate ────────────────────────────────────────────────────
    if is_incremental:
        base_lr = 5e-5          # conservative: preserve old knowledge
    elif n_train < 300:
        base_lr = 3e-4
    else:
        base_lr = 1e-3

    # ── Epoch budget ─────────────────────────────────────────────────────
    if is_incremental:
        # Fewer epochs: model already has good features
        epochs = max(15, min(40, n_train // 15))
    else:
        epochs = max(25, min(80, n_train // 8))

    # ── Early stopping patience ──────────────────────────────────────────
    patience = max(5, epochs // 5)

    # ── Backbone behaviour ───────────────────────────────────────────────
    # Freeze backbone when dataset is tiny; fine-tune otherwise
    freeze_backbone = (not is_incremental) and (n_train < 200)

    # During incremental: backbone gets 10× smaller LR to preserve features
    backbone_lr_multiplier = 0.1

    # ── Weight decay ─────────────────────────────────────────────────────
    weight_decay = 1e-4

    # ── Label smoothing ──────────────────────────────────────────────────
    label_smoothing = 0.1 if n_train > 300 else 0.0

    return {
        "batch_size": batch_size,
        "lr": base_lr,
        "epochs": epochs,
        "patience": patience,
        "weight_decay": weight_decay,
        "freeze_backbone": freeze_backbone,
        "backbone_lr_multiplier": backbone_lr_multiplier,
        "label_smoothing": label_smoothing,
        "n_train": n_train,
        "n_classes": n_classes,
        "is_incremental": is_incremental,
    }
