"""
models/unetplusplus_scse.py — UNet++ with SCSE attention gates via SMP.

Architecture:
    Encoder                : ResNet34, pre-trained on ImageNet
    Decoder                : UNet++ nested skip-connections
    decoder_attention_type : "scse" (Squeeze-Channel + Spatial Excitation)

This model is a direct smp.UnetPlusPlus instantiation — no subclassing needed.
The SCSE attention modules are handled entirely by SMP internally.

Usage:
    from models.unetplusplus_scse import build_unetplusplus_scse
    model = build_unetplusplus_scse(n_channels=3, n_classes=1)
"""
from __future__ import annotations

import segmentation_models_pytorch as smp
import torch
import torch.nn as nn

from config import CFG


def build_unetplusplus_scse(
    n_channels: int = 3,
    n_classes:  int = 1,
    encoder:    str = "resnet34",
    weights: str | None = "imagenet",
) -> smp.UnetPlusPlus:
    """
    Builds a UNet++ model with SCSE decoder attention.

    Args:
        n_channels : input channels (3 for green|CLAHE|Retinex)
        n_classes  : output channels (1 for binary vessel mask)
        encoder    : encoder backbone (default 'resnet34')
        weights    : encoder weights ('imagenet' or None)

    Returns:
        smp.UnetPlusPlus instance with decoder_attention_type="scse"
    """
    return smp.UnetPlusPlus(
        encoder_name           = encoder,
        encoder_weights        = weights,
        in_channels            = n_channels,
        classes                = n_classes,
        activation             = None,          # raw logits
        decoder_attention_type = "scse",        # Squeeze-Channel-Spatial Excitation
    )
