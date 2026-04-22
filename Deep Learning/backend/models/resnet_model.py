"""
ResNet18 model builder.
- build_model()   : fresh model (pretrained or random)
- expand_model()  : add new output neurons while preserving old weights (for incremental)
"""
import torch
import torch.nn as nn
from torchvision import models
from typing import Tuple


def build_model(num_classes: int, pretrained: bool = True) -> nn.Module:
    """Build ResNet18 with a custom classification head."""
    weights = models.ResNet18_Weights.IMAGENET1K_V1 if pretrained else None
    model = models.resnet18(weights=weights)
    in_features = model.fc.in_features
    model.fc = nn.Linear(in_features, num_classes)
    return model


def expand_model(model: nn.Module, new_num_classes: int) -> Tuple[nn.Module, int]:
    """
    Expand the final FC layer to accommodate additional classes.
    Old neuron weights are preserved exactly — only new neurons are randomly initialised.

    Returns:
        model            : the same model with expanded head
        old_num_classes  : number of classes before expansion
    """
    old_fc: nn.Linear = model.fc
    old_num_classes = old_fc.out_features

    if new_num_classes <= old_num_classes:
        raise ValueError(
            f"new_num_classes ({new_num_classes}) must be > old_num_classes ({old_num_classes})"
        )

    new_fc = nn.Linear(old_fc.in_features, new_num_classes)

    with torch.no_grad():
        # Copy old weights & biases into the first `old_num_classes` rows
        new_fc.weight[:old_num_classes] = old_fc.weight.clone()
        new_fc.bias[:old_num_classes] = old_fc.bias.clone()
        # New neurons already initialised by kaiming_uniform_ (PyTorch default)

    model.fc = new_fc
    return model, old_num_classes
