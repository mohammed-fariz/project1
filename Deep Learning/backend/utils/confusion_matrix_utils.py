"""
Saves a normalised confusion matrix as a PNG suitable for display in the frontend.
"""
import numpy as np
import matplotlib
matplotlib.use("Agg")           # non-interactive backend — safe in server threads
import matplotlib.pyplot as plt
import seaborn as sns
from pathlib import Path


def save_confusion_matrix(
    cm: np.ndarray,
    classes: list,
    save_path: Path,
    title: str = "Confusion Matrix",
) -> None:
    """
    Args:
        cm        : raw (un-normalised) confusion matrix of shape (n_classes, n_classes)
        classes   : list of class name strings
        save_path : where to write the PNG
        title     : figure title shown above the heatmap
    """
    n = len(classes)
    fig_size = max(7, n + 1)
    fig, ax = plt.subplots(figsize=(fig_size, fig_size - 1))

    # Normalise row-wise so each cell shows recall per class
    row_sums = cm.sum(axis=1, keepdims=True)
    cm_norm = np.where(row_sums == 0, 0.0, cm.astype(float) / row_sums)

    # Annotate with both normalised value and raw count
    annot = np.empty_like(cm, dtype=object)
    for i in range(n):
        for j in range(n):
            annot[i, j] = f"{cm_norm[i, j]:.2f}\n({cm[i, j]})"

    sns.heatmap(
        cm_norm,
        annot=annot,
        fmt="",
        cmap="Blues",
        xticklabels=classes,
        yticklabels=classes,
        ax=ax,
        linewidths=0.4,
        vmin=0.0,
        vmax=1.0,
        cbar_kws={"shrink": 0.8, "label": "Recall"},
    )

    ax.set_xlabel("Predicted label", fontsize=11)
    ax.set_ylabel("True label", fontsize=11)
    ax.set_title(title, fontsize=13, pad=10)
    plt.xticks(rotation=30, ha="right")
    plt.yticks(rotation=0)
    plt.tight_layout()
    plt.savefig(save_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
