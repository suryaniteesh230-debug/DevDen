"""
av_classification.py — CNN-based Artery/Vein classifier (Modified ResNet18).

Architecture modifications vs standard ResNet18:
    1. Initial 7×7 conv → 3×3 conv        (preserves fine vessel details)
    2. All ReLU → SiLU (Swish)            (smoother gradients)
    3. SE attention after each residual stage (channel-wise AV emphasis)
    4. Head: 512 → 256 → 2  with BN + Dropout(0.3)

Input:
    (B, 7, patch_size, patch_size) float32 patches
    7 channels = RGB (3) + vessel mask (1) + green/CLAHE/Retinex (3)

Provides:
    SEBlock                 — Squeeze-and-Excitation channel attention
    SiLUResBlock            — ReLU-replaced SiLU residual block
    AVResNet18              — modified ResNet18 classifier
    FocalLoss               — multi-class focal loss
    AVCombinedLoss          — 0.5×CrossEntropy + 0.5×FocalLoss
    PatchDataset            — torch Dataset wrapper for patches
    train_av_cnn_epoch()    — one training epoch
    eval_av_cnn()           — one evaluation epoch (returns metrics)
    cross_validate_av_cnn() — Leave-One-Image-Out CV on DRIVE_AV
    train_final_av_cnn()    — train on all data, save checkpoint
    predict_av_labels_cnn() — inference: segment list → label list
    load_av_cnn()           — load saved checkpoint
"""
from __future__ import annotations

import copy

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from sklearn.metrics import (accuracy_score, balanced_accuracy_score,
                              f1_score)
from sklearn.model_selection import LeaveOneGroupOut
from torch.utils.data import DataLoader, Dataset, WeightedRandomSampler

from config import CFG
from av_segments import extract_segment_patch


# ─────────────────────────────────────────────────────────────────────────────
# Building blocks
# ─────────────────────────────────────────────────────────────────────────────

class SEBlock(nn.Module):
    """
    Channel Squeeze-and-Excitation block.
    Global pool → 2-layer MLP → channel reweighting via sigmoid.
    Forces the CNN to emphasise artery/vein-discriminative channels.
    """
    def __init__(self, channels: int, reduction: int = 16):
        super().__init__()
        mid = max(channels // reduction, 4)
        self.pool = nn.AdaptiveAvgPool2d(1)
        self.fc   = nn.Sequential(
            nn.Linear(channels, mid, bias=False),
            nn.SiLU(),
            nn.Linear(mid, channels, bias=False),
            nn.Sigmoid(),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        B, C = x.shape[:2]
        s = self.pool(x).view(B, C)
        w = self.fc(s).view(B, C, 1, 1)
        return x * w


class SiLUResBlock(nn.Module):
    """
    Standard ResNet BasicBlock with ReLU replaced by SiLU.
    No changes to skip connections or stride logic.
    """
    expansion = 1

    def __init__(self, in_ch: int, out_ch: int, stride: int = 1):
        super().__init__()
        self.conv1 = nn.Conv2d(in_ch, out_ch, 3, stride=stride, padding=1, bias=False)
        self.bn1   = nn.BatchNorm2d(out_ch)
        self.act1  = nn.SiLU()
        self.conv2 = nn.Conv2d(out_ch, out_ch, 3, padding=1, bias=False)
        self.bn2   = nn.BatchNorm2d(out_ch)
        self.act2  = nn.SiLU()

        self.downsample = None
        if stride != 1 or in_ch != out_ch:
            self.downsample = nn.Sequential(
                nn.Conv2d(in_ch, out_ch, 1, stride=stride, bias=False),
                nn.BatchNorm2d(out_ch),
            )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        residual = x
        out = self.act1(self.bn1(self.conv1(x)))
        out = self.bn2(self.conv2(out))
        if self.downsample is not None:
            residual = self.downsample(x)
        return self.act2(out + residual)


# ─────────────────────────────────────────────────────────────────────────────
# Modified ResNet18 AV Classifier
# ─────────────────────────────────────────────────────────────────────────────

class AVResNet18(nn.Module):
    """
    Modified ResNet18 for patch-based artery/vein classification.

    Input  : (B, in_channels, patch_size, patch_size)
    Output : (B, 2) raw logits  [vein, artery]

    Modifications vs standard ResNet18:
        • 7×7 stride-2 conv → 3×3 stride-1 conv  (preserves fine vessel details)
        • All ReLU → SiLU (Swish)
        • SE attention block after each of the 4 residual stages
        • Head: 512 → 256 → 2  with BN + Dropout(0.3)
    """

    def __init__(self, in_channels: int = 7, num_classes: int = 2,
                 dropout: float = 0.3):
        super().__init__()

        # ── Stem: 3×3 stride-1 replaces 7×7 stride-2 ────────────────────────
        self.stem = nn.Sequential(
            nn.Conv2d(in_channels, 64, kernel_size=3, stride=1, padding=1, bias=False),
            nn.BatchNorm2d(64),
            nn.SiLU(),
            nn.MaxPool2d(kernel_size=2, stride=2),
        )

        # ── Residual stages + SE attention ────────────────────────────────────
        self.layer1 = self._make_stage(64,  64,  blocks=2, stride=1)
        self.se1    = SEBlock(64)

        self.layer2 = self._make_stage(64,  128, blocks=2, stride=2)
        self.se2    = SEBlock(128)

        self.layer3 = self._make_stage(128, 256, blocks=2, stride=2)
        self.se3    = SEBlock(256)

        self.layer4 = self._make_stage(256, 512, blocks=2, stride=2)
        self.se4    = SEBlock(512)

        # ── Global pooling + bottleneck head ─────────────────────────────────
        self.pool = nn.AdaptiveAvgPool2d(1)
        self.head = nn.Sequential(
            nn.Flatten(),
            nn.Linear(512, 256, bias=False),
            nn.BatchNorm1d(256),
            nn.SiLU(),
            nn.Dropout(p=dropout),
            nn.Linear(256, num_classes),
        )
        self._init_weights()

    def _make_stage(self, in_ch, out_ch, blocks, stride):
        layers = [SiLUResBlock(in_ch, out_ch, stride=stride)]
        for _ in range(1, blocks):
            layers.append(SiLUResBlock(out_ch, out_ch, stride=1))
        return nn.Sequential(*layers)

    def _init_weights(self):
        for m in self.modules():
            if isinstance(m, nn.Conv2d):
                nn.init.kaiming_normal_(m.weight, mode="fan_out",
                                        nonlinearity="relu")
            elif isinstance(m, nn.BatchNorm2d):
                nn.init.ones_(m.weight); nn.init.zeros_(m.bias)
            elif isinstance(m, nn.Linear):
                nn.init.normal_(m.weight, 0, 0.01)
                if m.bias is not None:
                    nn.init.zeros_(m.bias)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        x = self.stem(x)
        x = self.se1(self.layer1(x))
        x = self.se2(self.layer2(x))
        x = self.se3(self.layer3(x))
        x = self.se4(self.layer4(x))
        x = self.pool(x)
        return self.head(x)

    def extract_features(self, x: torch.Tensor) -> torch.Tensor:
        """Returns 512-dim feature vector before classification head."""
        x = self.stem(x)
        x = self.se1(self.layer1(x))
        x = self.se2(self.layer2(x))
        x = self.se3(self.layer3(x))
        x = self.se4(self.layer4(x))
        x = self.pool(x)
        return x.flatten(1)


# ─────────────────────────────────────────────────────────────────────────────
# Loss functions
# ─────────────────────────────────────────────────────────────────────────────

class FocalLoss(nn.Module):
    """
    Multi-class Focal Loss.
    Down-weights easy (well-classified) examples, focuses on hard ones.
    """
    def __init__(self, gamma: float = 2.0, alpha=None, reduction: str = "mean"):
        super().__init__()
        self.gamma     = gamma
        self.alpha     = alpha
        self.reduction = reduction

    def forward(self, logits: torch.Tensor, targets: torch.Tensor) -> torch.Tensor:
        log_probs = F.log_softmax(logits, dim=1)
        probs     = log_probs.exp()
        log_pt    = log_probs.gather(1, targets.view(-1, 1)).squeeze(1)
        pt        = probs.gather(1, targets.view(-1, 1)).squeeze(1)
        focal     = (1 - pt) ** self.gamma * (-log_pt)

        if self.alpha is not None:
            alpha_t = torch.tensor(self.alpha, dtype=torch.float32,
                                   device=logits.device)[targets]
            focal   = alpha_t * focal

        if self.reduction == "mean":
            return focal.mean()
        elif self.reduction == "sum":
            return focal.sum()
        return focal


class AVCombinedLoss(nn.Module):
    """
    Combined loss = 0.5 × CrossEntropy + 0.5 × FocalLoss.

    CrossEntropy: stable gradients throughout training.
    FocalLoss:    drives focus toward hard thin-vessel segments.
    """
    def __init__(self, weight_ce: float = 0.5, weight_focal: float = 0.5,
                 gamma: float = 2.0, class_weights: list = None):
        super().__init__()
        cw          = torch.tensor(class_weights, dtype=torch.float32) \
                      if class_weights else None
        self.ce     = nn.CrossEntropyLoss(weight=cw)
        self.focal  = FocalLoss(gamma=gamma)
        self.w_ce   = weight_ce
        self.w_focal= weight_focal
        self._cw    = cw

    def forward(self, logits: torch.Tensor, targets: torch.Tensor) -> torch.Tensor:
        if self._cw is not None:
            self.ce.weight = self._cw.to(logits.device)
        return (self.w_ce   * self.ce(logits, targets) +
                self.w_focal * self.focal(logits, targets))


# ─────────────────────────────────────────────────────────────────────────────
# Patch Dataset
# ─────────────────────────────────────────────────────────────────────────────

class PatchDataset(Dataset):
    """
    Dataset wrapper for (patch, label) pairs.
    Optionally applies flip and rotation augmentation.
    """
    def __init__(self, patches: np.ndarray, labels: np.ndarray,
                 augment: bool = False):
        self.patches = torch.from_numpy(patches).float()
        self.labels  = torch.from_numpy(labels).long()
        self.augment = augment

    def __len__(self):
        return len(self.labels)

    def __getitem__(self, idx):
        patch = self.patches[idx].clone()
        label = self.labels[idx]
        if self.augment:
            if torch.rand(1) < 0.5:
                patch = torch.flip(patch, dims=[2])
            if torch.rand(1) < 0.5:
                patch = torch.flip(patch, dims=[1])
            if torch.rand(1) < 0.5:
                patch = torch.rot90(patch, k=1, dims=[1, 2])
        return patch, label


def _build_weighted_sampler(labels: np.ndarray) -> WeightedRandomSampler:
    """Balanced sampler — oversamples minority class."""
    class_counts   = np.bincount(labels)
    class_weights  = 1.0 / class_counts
    sample_weights = class_weights[labels]
    return WeightedRandomSampler(
        weights     = torch.from_numpy(sample_weights).float(),
        num_samples = len(labels),
        replacement = True,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Training loop helpers
# ─────────────────────────────────────────────────────────────────────────────

def train_av_cnn_epoch(model, loader, criterion, optimizer, device, scaler):
    """One training epoch. Returns (loss, accuracy)."""
    model.train()
    total_loss = 0.0; correct = 0; total = 0

    for patches, labels in loader:
        patches = patches.to(device)
        labels  = labels.to(device)
        optimizer.zero_grad()
        with torch.amp.autocast("cuda", enabled=(device.type == "cuda")):
            logits = model(patches)
            loss   = criterion(logits, labels)
        scaler.scale(loss).backward()
        scaler.unscale_(optimizer)
        torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=1.0)
        scaler.step(optimizer)
        scaler.update()
        total_loss += loss.item()
        correct    += (logits.argmax(dim=1) == labels).sum().item()
        total      += labels.size(0)

    return total_loss / len(loader), correct / total


@torch.no_grad()
def eval_av_cnn(model, loader, criterion, device):
    """
    One evaluation epoch.
    Returns: (loss, accuracy, balanced_accuracy, artery_f1, vein_f1, predictions)
    """
    model.eval()
    total_loss = 0.0; all_preds = []; all_labels = []

    for patches, labels in loader:
        patches = patches.to(device); labels = labels.to(device)
        with torch.amp.autocast("cuda", enabled=(device.type == "cuda")):
            logits = model(patches)
            loss   = criterion(logits, labels)
        total_loss += loss.item()
        all_preds.extend(logits.argmax(dim=1).cpu().numpy().tolist())
        all_labels.extend(labels.cpu().numpy().tolist())

    all_preds  = np.array(all_preds)
    all_labels = np.array(all_labels)
    acc     = accuracy_score(all_labels, all_preds)
    bal_acc = balanced_accuracy_score(all_labels, all_preds)
    art_f1  = f1_score(all_labels, all_preds, pos_label=1, zero_division=0)
    vein_f1 = f1_score(all_labels, all_preds, pos_label=0, zero_division=0)

    return total_loss / len(loader), acc, bal_acc, art_f1, vein_f1, all_preds


# ─────────────────────────────────────────────────────────────────────────────
# Leave-One-Image-Out cross-validation
# ─────────────────────────────────────────────────────────────────────────────

def cross_validate_av_cnn(patches: np.ndarray, labels: np.ndarray,
                           sample_ids: list, patch_size: int = 32,
                           epochs: int = 30, lr: float = 3e-4,
                           batch_size: int = 64, device=None) -> dict:
    """
    Leave-One-Image-Out CV for the CNN AV classifier.
    Only runs on DRIVE_AV images (stable evaluation).

    Returns:
        dict with mean_acc, mean_bal_acc, mean_art_f1, mean_vein_f1, fold_results
    """
    if device is None:
        device = CFG["device"]

    groups      = np.array(sample_ids)
    drive_mask  = np.array(["DRIVE" in sid for sid in sample_ids])
    if drive_mask.sum() < 10:
        print("[WARNING] Too few DRIVE_AV samples for LOIO-CV. Skipping.")
        return {}

    X_cv = patches[drive_mask]; y_cv = labels[drive_mask]; g_cv = groups[drive_mask]
    unique_drive = np.unique(g_cv)

    if len(unique_drive) < 2:
        print("[WARNING] Need ≥2 DRIVE images for LOIO-CV.")
        return {}

    logo         = LeaveOneGroupOut()
    fold_results = []

    print(f"\n{'='*65}")
    print(f"Leave-One-Image-Out CV  |  CNN AV Classifier  |  {len(unique_drive)} folds")
    print(f"{'='*65}")

    for fold_idx, (train_idx, test_idx) in enumerate(logo.split(X_cv, y_cv, g_cv)):
        X_tr, X_te = X_cv[train_idx], X_cv[test_idx]
        y_tr, y_te = y_cv[train_idx], y_cv[test_idx]
        n0 = (y_tr == 0).sum(); n1 = (y_tr == 1).sum()
        class_w = [n0 / (n0 + n1), n1 / (n0 + n1)]

        train_ds  = PatchDataset(X_tr, y_tr, augment=True)
        test_ds   = PatchDataset(X_te, y_te, augment=False)
        sampler   = _build_weighted_sampler(y_tr)
        tr_loader = DataLoader(train_ds, batch_size=batch_size, sampler=sampler,
                               num_workers=0, pin_memory=True)
        te_loader = DataLoader(test_ds,  batch_size=batch_size, shuffle=False,
                               num_workers=0, pin_memory=True)

        model     = AVResNet18(in_channels=7).to(device)
        criterion = AVCombinedLoss(0.5, 0.5, gamma=2.0, class_weights=class_w)
        optimizer = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=1e-4)
        scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=epochs)
        scaler    = torch.amp.GradScaler("cuda", enabled=(device.type == "cuda"))

        best_bal = 0.0; best_state = None
        for ep in range(1, epochs + 1):
            train_av_cnn_epoch(model, tr_loader, criterion, optimizer, device, scaler)
            _, _, bal_acc, _, _, _ = eval_av_cnn(model, te_loader, criterion, device)
            scheduler.step()
            if bal_acc > best_bal:
                best_bal   = bal_acc
                best_state = copy.deepcopy(model.state_dict())

        model.load_state_dict(best_state)
        _, acc, bal_acc, art_f1, vein_f1, _ = eval_av_cnn(
            model, te_loader, criterion, device)

        test_image = np.unique(g_cv[test_idx])[0]
        fold_results.append({
            "image": test_image, "acc": acc, "bal_acc": bal_acc,
            "art_f1": art_f1, "vein_f1": vein_f1, "n_test": len(y_te),
        })
        print(f"  Fold {fold_idx+1:2d}  [{test_image:25s}]  "
              f"acc={acc:.3f}  bal={bal_acc:.3f}  "
              f"art_F1={art_f1:.3f}  vein_F1={vein_f1:.3f}")

    mean_acc     = np.mean([r["acc"]     for r in fold_results])
    mean_bal     = np.mean([r["bal_acc"] for r in fold_results])
    mean_art_f1  = np.mean([r["art_f1"]  for r in fold_results])
    mean_vein_f1 = np.mean([r["vein_f1"] for r in fold_results])

    print(f"{'─'*65}")
    print(f"  MEAN  acc={mean_acc:.3f}  bal={mean_bal:.3f}  "
          f"art_F1={mean_art_f1:.3f}  vein_F1={mean_vein_f1:.3f}")
    print(f"{'='*65}\n")

    return {
        "mean_acc": mean_acc, "mean_bal_acc": mean_bal,
        "mean_art_f1": mean_art_f1, "mean_vein_f1": mean_vein_f1,
        "fold_results": fold_results,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Train final model on all data
# ─────────────────────────────────────────────────────────────────────────────

def train_final_av_cnn(patches: np.ndarray, labels: np.ndarray,
                        patch_size: int = 32, epochs: int = 50,
                        lr: float = 3e-4, batch_size: int = 64,
                        save_path: str = "av_cnn.pt",
                        device=None) -> AVResNet18:
    """
    Trains the CNN AV classifier on the full dataset and saves checkpoint.
    Returns trained AVResNet18 in eval mode.
    """
    if device is None:
        device = CFG["device"]

    n0 = (labels == 0).sum(); n1 = (labels == 1).sum()
    class_w = [n0 / (n0 + n1), n1 / (n0 + n1)]

    train_ds  = PatchDataset(patches, labels, augment=True)
    sampler   = _build_weighted_sampler(labels)
    tr_loader = DataLoader(train_ds, batch_size=batch_size, sampler=sampler,
                           num_workers=0, pin_memory=True)

    model     = AVResNet18(in_channels=7).to(device)
    criterion = AVCombinedLoss(0.5, 0.5, gamma=2.0, class_weights=class_w)
    optimizer = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=1e-4)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=epochs)
    scaler    = torch.amp.GradScaler("cuda", enabled=(device.type == "cuda"))

    n_params = sum(p.numel() for p in model.parameters() if p.requires_grad)
    print(f"[AV CNN] AVResNet18  params={n_params:,}  "
          f"in_channels=7  patch_size={patch_size}")
    print(f"         Training on {len(labels)} segments  "
          f"(artery={n1}, vein={n0})")
    print(f"         {epochs} epochs  lr={lr}  batch={batch_size}\n")
    print(f"{'Epoch':>6}  {'Loss':>8}  {'Acc':>7}")
    print("─" * 30)

    best_loss = float("inf"); best_state = None

    for ep in range(1, epochs + 1):
        tr_loss, tr_acc = train_av_cnn_epoch(
            model, tr_loader, criterion, optimizer, device, scaler)
        scheduler.step()
        if ep % 5 == 0 or ep == 1:
            print(f"{ep:6d}  {tr_loss:8.4f}  {tr_acc:7.4f}")
        if tr_loss < best_loss:
            best_loss = tr_loss
            best_state = copy.deepcopy(model.state_dict())

    model.load_state_dict(best_state)
    model.eval()
    torch.save({
        "model_state": model.state_dict(), "patch_size": patch_size,
        "in_channels": 7, "epochs": epochs, "n_train": len(labels),
    }, save_path)
    print(f"\n[AV CNN] Saved → {save_path}")
    return model


def load_av_cnn(path: str = "av_cnn.pt", device=None) -> AVResNet18:
    """Load a saved AV CNN checkpoint."""
    if device is None:
        device = CFG["device"]
    ckpt  = torch.load(path, map_location=device)
    model = AVResNet18(in_channels=ckpt.get("in_channels", 7)).to(device)
    model.load_state_dict(ckpt["model_state"])
    model.eval()
    print(f"[AV CNN] Loaded from '{path}'  "
          f"(trained on {ckpt.get('n_train','?')} segments)")
    return model


# ─────────────────────────────────────────────────────────────────────────────
# Prediction
# ─────────────────────────────────────────────────────────────────────────────

@torch.no_grad()
def predict_av_labels_cnn(segments: list, bgr_image: np.ndarray,
                           vessel_mask: np.ndarray, model: AVResNet18,
                           patch_size: int = 32, batch_size: int = 64,
                           device=None) -> list:
    """
    Predicts artery (1) or vein (0) for each segment using the CNN.

    Args:
        segments    : list of segment dicts from merge_segments_by_continuity()
        bgr_image   : (H, W, 3) uint8
        vessel_mask : (H, W) uint8 {0,255}
        model       : trained AVResNet18 in eval mode

    Returns:
        seg_labels : list of int  (same order as segments)  0=vein, 1=artery
    """
    if device is None:
        device = CFG["device"]

    model.eval()
    patches = [
        extract_segment_patch(seg["path"], bgr_image, vessel_mask, patch_size)
        for seg in segments
    ]
    if not patches:
        return []

    patches_t  = torch.from_numpy(np.stack(patches, axis=0)).float()
    seg_labels = []
    for i in range(0, len(patches_t), batch_size):
        batch  = patches_t[i:i + batch_size].to(device)
        logits = model(batch)
        seg_labels.extend(logits.argmax(dim=1).cpu().numpy().tolist())

    n_art  = sum(1 for l in seg_labels if l == 1)
    n_vein = len(seg_labels) - n_art
    print(f"  CNN predicted: {n_art} artery segments, {n_vein} vein segments")
    return seg_labels


print("AV classification utilities defined.")
print("  AVResNet18      — modified ResNet18: 3×3 stem, SiLU, SE blocks")
print("  AVCombinedLoss  — CrossEntropy + FocalLoss")
print("  cross_validate_av_cnn() — LOIO-CV on DRIVE_AV")
print("  train_final_av_cnn()    — train on all data, save checkpoint")
print("  predict_av_labels_cnn() — patch-based inference per segment")
