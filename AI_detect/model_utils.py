from __future__ import annotations

from typing import Any

import torch
from torch import nn


class ConfigurableCNN(nn.Module):
    def __init__(self, *, num_classes: int, spec: dict[str, Any]) -> None:
        super().__init__()
        conv_channels = spec["conv_channels"]
        kernel_size = int(spec.get("kernel_size", 3))
        padding = kernel_size // 2
        batch_norm = bool(spec.get("batch_norm", True))
        pool_size = int(spec.get("pool_size", 4))

        layers: list[nn.Module] = []
        in_channels = 3
        for out_channels in conv_channels:
            out_channels = int(out_channels)
            layers.append(nn.Conv2d(in_channels, out_channels, kernel_size=kernel_size, padding=padding))
            if batch_norm:
                layers.append(nn.BatchNorm2d(out_channels))
            layers.append(nn.ReLU(inplace=True))
            layers.append(nn.MaxPool2d(kernel_size=2))
            in_channels = out_channels
        layers.append(nn.AdaptiveAvgPool2d((pool_size, pool_size)))
        self.features = nn.Sequential(*layers)

        dense_units = spec.get("dense_units", [64])
        if isinstance(dense_units, int):
            dense_units = [dense_units]
        dropout = float(spec.get("dropout", 0.25))

        classifier_layers: list[nn.Module] = []
        current_units = int(conv_channels[-1]) * pool_size * pool_size
        for units in dense_units:
            units = int(units)
            classifier_layers.append(nn.Linear(current_units, units))
            classifier_layers.append(nn.ReLU(inplace=True))
            classifier_layers.append(nn.Dropout(dropout))
            current_units = units
        classifier_layers.append(nn.Linear(current_units, num_classes))
        self.classifier = nn.Sequential(*classifier_layers)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        x = self.features(x)
        x = torch.flatten(x, 1)
        return self.classifier(x)
