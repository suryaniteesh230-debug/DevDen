"""
train_unetplusplus_scse.py — Train the UNet++ with SCSE attention (ResNet34 encoder).

Uses CombinedLoss (0.3×BCE + 0.7×FocalTversky). No deep supervision.

Usage:
    python train_unetplusplus_scse.py
"""
from __future__ import annotations

import torch

import segmentation_models_pytorch as smp

from config import CFG, ROOT_DIR, SEG_SUBSETS
from dataset import build_loaders
from models.unetplusplus_scse import build_unetplusplus_scse
from training import CombinedLoss, run_training_loop

# ── Build data loaders ────────────────────────────────────────────────────────
print("Loading datasets...")
train_loader, val_loader = build_loaders(ROOT_DIR, SEG_SUBSETS)

# ── Sanity check ──────────────────────────────────────────────────────────────
imgs, msks = next(iter(train_loader))
print(f"\nBatch check:")
print(f"  Image : {list(imgs.shape)}  dtype={imgs.dtype}  "
      f"range=[{imgs.min():.3f}, {imgs.max():.3f}]")
print(f"  Mask  : {list(msks.shape)}  dtype={msks.dtype}  "
      f"unique={msks.unique().tolist()}")

# ── Model ─────────────────────────────────────────────────────────────────────
model = build_unetplusplus_scse(
    n_channels = CFG["n_channels"],
    n_classes  = CFG["n_classes"],
    encoder    = "resnet34",
    weights    = "imagenet",
).to(CFG["device"])

n_params = sum(p.numel() for p in model.parameters() if p.requires_grad)
print(f"UnetPlusPlus (ResNet34 + SCSE)  |  "
      f"input channels: {CFG['n_channels']}  |  "
      f"trainable params: {n_params:,}")

# Forward-pass shape check
with torch.no_grad():
    _dummy = torch.zeros(
        1, CFG["n_channels"], CFG["img_size"], CFG["img_size"],
        device=CFG["device"]
    )
    _out = model(_dummy)
    print(f"Input  shape : {list(_dummy.shape)}")
    print(f"Output shape : {list(_out.shape)}  ← raw logits")

# ── Loss ──────────────────────────────────────────────────────────────────────
criterion = CombinedLoss(
    pos_weight = 9.0,
    weight_bce = 0.3,
    weight_ftv = 0.7,
    alpha      = 0.3,
    beta       = 0.7,
    gamma      = 0.75,
)

print(f"Loss      : CombinedLoss(BCE×0.3 + FocalTversky×0.7)")
print(f"           FocalTversky(alpha=0.3, beta=0.7, gamma=0.75)")
print(f"Optimizer : Adam  lr={CFG['lr']}  wd=1e-4")
print(f"Scheduler : CosineAnnealingWarmRestarts  T_0=15  eta_min=1e-6")

# ── Train ─────────────────────────────────────────────────────────────────────
run_training_loop(
    model        = model,
    train_loader = train_loader,
    val_loader   = val_loader,
    criterion    = criterion,
    save_path    = "best_model_unetplusplus_scse.pt",
    arch         = "unetplusplus_scse",
    encoder      = "resnet34",
    deep_supervision = False,
)
