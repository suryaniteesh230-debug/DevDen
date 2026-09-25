"""
train_unetplusplus.py — Train the UNet++ with deep supervision (ResNet34 encoder).

Uses CombinedLossWithClDice (0.5×FocalTversky + 0.5×clDice) and deep supervision.

Usage:
    python train_unetplusplus.py
"""
from __future__ import annotations

import torch

from config import CFG, ROOT_DIR, SEG_SUBSETS
from dataset import build_loaders
from models.unetplusplus import UnetPlusPlusDS
from training import CombinedLossWithClDice, run_training_loop

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
model = UnetPlusPlusDS(
    n_channels = CFG["n_channels"],   # 3  (green | CLAHE | Retinex)
    n_classes  = CFG["n_classes"],    # 1  (binary vessel mask)
    encoder    = "resnet34",
    weights    = "imagenet",
).to(CFG["device"])

n_params = sum(p.numel() for p in model.parameters() if p.requires_grad)
print(f"UnetPlusPlusDS (ResNet34-imagenet)  |  "
      f"input channels: {CFG['n_channels']}  |  "
      f"trainable params: {n_params:,}")

# Forward-pass shape check
model.train()
with torch.no_grad():
    _dummy = torch.zeros(
        2, CFG["n_channels"], CFG["img_size"], CFG["img_size"],
        device=CFG["device"]
    )
    _out = model(_dummy)
    assert isinstance(_out, tuple), "Expected (main, [aux0,aux1,aux2]) in train mode"
    _main, _aux = _out
    print(f"[train mode]  main  : {list(_main.shape)}  ← raw logits")
    for j, a in enumerate(_aux):
        print(f"              aux{j}   : {list(a.shape)}")

model.eval()
with torch.no_grad():
    _out_eval = model(_dummy)
    assert isinstance(_out_eval, torch.Tensor), \
        "Expected single tensor in eval mode"
    print(f"[eval  mode]  output: {list(_out_eval.shape)}  ← raw logits")

model.train()

# ── Loss ──────────────────────────────────────────────────────────────────────
criterion = CombinedLossWithClDice(
    weight_ftv = 0.5,
    weight_cld = 0.5,
    alpha_tv   = 0.3,
    beta_tv    = 0.7,
    gamma_tv   = 0.75,
    iter_skel  = 10,
)

print("Loss      : CombinedLossWithClDice = 0.5 × FocalTversky + 0.5 × clDice")
print(f"            FocalTversky(alpha=0.3, beta=0.7, gamma=0.75)")
print(f"            clDice(num_iter=10, alpha=0.5)")
print(f"            Deep-sup weights: main×1.0, aux0×0.4, aux1×0.2, aux2×0.1")
print(f"Optimizer : Adam  lr={CFG['lr']}  wd=1e-4")
print(f"Scheduler : CosineAnnealingWarmRestarts  T_0=15  eta_min=1e-6")

# ── Train ─────────────────────────────────────────────────────────────────────
run_training_loop(
    model        = model,
    train_loader = train_loader,
    val_loader   = val_loader,
    criterion    = criterion,
    save_path    = "best_model_unetplusplus.pt",
    arch         = "UnetPlusPlusDS",
    encoder      = "resnet34",
    deep_supervision = True,
)
