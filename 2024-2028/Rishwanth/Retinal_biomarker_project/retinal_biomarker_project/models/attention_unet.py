"""
models/attention_unet.py — Attention U-Net model for retinal vessel segmentation.

Provides:
    DoubleConv       — two successive Conv2d → BN → ReLU blocks
    AttentionBlock   — soft attention gate (Oktay et al. 2018)
    AttentionUNet    — 4-level Attention U-Net

Modifications vs original:
    • n_channels default changed 1 → 3 to match multi-channel preprocessing
    • AttentionBlock.forward arg order fixed (x=skip first, g=gate second)
    • Spatial misalignment on odd input sizes fixed with F.interpolate
    • Full encoder-decoder implemented
"""
from __future__ import annotations

import torch
import torch.nn as nn
import torch.nn.functional as F

from config import CFG


class DoubleConv(nn.Module):
    """Two successive Conv2d → BN → ReLU blocks — standard U-Net cell."""
    def __init__(self, in_ch: int, out_ch: int):
        super().__init__()
        self.block = nn.Sequential(
            nn.Conv2d(in_ch,  out_ch, kernel_size=3, padding=1, bias=False),
            nn.BatchNorm2d(out_ch),
            nn.ReLU(inplace=True),
            nn.Conv2d(out_ch, out_ch, kernel_size=3, padding=1, bias=False),
            nn.BatchNorm2d(out_ch),
            nn.ReLU(inplace=True),
        )
    def forward(self, x):
        return self.block(x)


class AttentionBlock(nn.Module):
    """
    Soft attention gate as in Oktay et al. (2018) "Attention U-Net".

    Args:
        F_g   : channels of the gating signal   (from decoder)
        F_l   : channels of the skip connection (from encoder)
        F_int : intermediate projection channels (typically F_l // 2)
    """
    def __init__(self, F_g: int, F_l: int, F_int: int):
        super().__init__()
        self.W_g = nn.Sequential(
            nn.Conv2d(F_g, F_int, kernel_size=1, bias=True),
            nn.BatchNorm2d(F_int),
        )
        self.W_x = nn.Sequential(
            nn.Conv2d(F_l, F_int, kernel_size=1, bias=True),
            nn.BatchNorm2d(F_int),
        )
        self.psi = nn.Sequential(
            nn.Conv2d(F_int, 1, kernel_size=1, bias=True),
            nn.BatchNorm2d(1),
            nn.Sigmoid(),
        )
        self.relu = nn.ReLU(inplace=True)

    def forward(self, x: torch.Tensor, g: torch.Tensor) -> torch.Tensor:
        """
        Args:
            x : (B, F_l, H,  W ) — skip connection from encoder  (HIGH res)
            g : (B, F_g, H', W') — gating signal from decoder     (LOW  res)
        Returns:
            (B, F_l, H, W) — attended skip features
        """
        # Align gating signal to skip connection spatial size
        if g.shape[2:] != x.shape[2:]:
            g = F.interpolate(g, size=x.shape[2:], mode="bilinear", align_corners=False)

        g1  = self.W_g(g)                       # (B, F_int, H, W)
        x1  = self.W_x(x)                       # (B, F_int, H, W)
        psi = self.psi(self.relu(g1 + x1))      # (B, 1, H, W)  attention map
        return x * psi                           # gated skip features


class AttentionUNet(nn.Module):
    """
    4-level Attention U-Net for binary vessel segmentation.

    Args:
        n_channels : input channels  (3 for green | CLAHE | Retinex stack)
        n_classes  : output channels (1 for binary segmentation)
    """
    def __init__(self, n_channels: int = 3, n_classes: int = 1):
        super().__init__()

        # ── Encoder ──────────────────────────────────────────────────────────
        self.enc1 = DoubleConv(n_channels, 64)
        self.enc2 = DoubleConv(64,  128)
        self.enc3 = DoubleConv(128, 256)
        self.enc4 = DoubleConv(256, 512)
        self.pool = nn.MaxPool2d(2)

        # ── Bottleneck ────────────────────────────────────────────────────────
        self.bottleneck = DoubleConv(512, 1024)

        # ── Decoder upsampling ────────────────────────────────────────────────
        self.up4 = nn.ConvTranspose2d(1024, 512, kernel_size=2, stride=2)
        self.up3 = nn.ConvTranspose2d(512,  256, kernel_size=2, stride=2)
        self.up2 = nn.ConvTranspose2d(256,  128, kernel_size=2, stride=2)
        self.up1 = nn.ConvTranspose2d(128,   64, kernel_size=2, stride=2)

        # ── Attention gates (F_g=gate, F_l=skip, F_int=projection) ───────────
        self.att4 = AttentionBlock(F_g=512,  F_l=512,  F_int=256)
        self.att3 = AttentionBlock(F_g=256,  F_l=256,  F_int=128)
        self.att2 = AttentionBlock(F_g=128,  F_l=128,  F_int=64)
        self.att1 = AttentionBlock(F_g=64,   F_l=64,   F_int=32)

        # ── Decoder double-conv  (in = upsampled + attended skip) ─────────────
        self.dec4 = DoubleConv(1024, 512)   # 512 up  + 512 skip
        self.dec3 = DoubleConv(512,  256)   # 256 + 256
        self.dec2 = DoubleConv(256,  128)   # 128 + 128
        self.dec1 = DoubleConv(128,   64)   # 64  + 64

        # ── Output head ───────────────────────────────────────────────────────
        self.head = nn.Conv2d(64, n_classes, kernel_size=1)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        # Encode
        e1 = self.enc1(x)                   # (B,   64, H,    W   )
        e2 = self.enc2(self.pool(e1))       # (B,  128, H/2,  W/2 )
        e3 = self.enc3(self.pool(e2))       # (B,  256, H/4,  W/4 )
        e4 = self.enc4(self.pool(e3))       # (B,  512, H/8,  W/8 )

        # Bottleneck
        b  = self.bottleneck(self.pool(e4)) # (B, 1024, H/16, W/16)

        # Decode: upsample → attention → concat → double-conv
        d4 = self.up4(b)
        e4 = self.att4(x=e4, g=d4)         # skip=e4, gate=d4
        d4 = self.dec4(torch.cat([d4, e4], dim=1))

        d3 = self.up3(d4)
        e3 = self.att3(x=e3, g=d3)
        d3 = self.dec3(torch.cat([d3, e3], dim=1))

        d2 = self.up2(d3)
        e2 = self.att2(x=e2, g=d2)
        d2 = self.dec2(torch.cat([d2, e2], dim=1))

        d1 = self.up1(d2)
        e1 = self.att1(x=e1, g=d1)
        d1 = self.dec1(torch.cat([d1, e1], dim=1))

        return self.head(d1)                # (B, n_classes, H, W)  raw logits
