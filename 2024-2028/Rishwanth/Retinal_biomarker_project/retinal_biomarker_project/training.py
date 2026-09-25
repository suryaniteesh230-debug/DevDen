"""
training.py — Loss functions, optimizer setup, training and validation loops.

Shared by all three segmentation models. Model-specific loss differences
(e.g. clDice for UNet++DS) are handled via the criterion argument.

Provides:
    TverskyLoss              — Tversky index loss
    FocalTverskyLoss         — focal variant of Tversky loss
    SoftSkeletonize          — differentiable soft skeletonisation
    clDiceLoss               — centreline Dice loss
    CombinedLoss             — BCE+FocalTversky (used by AttentionUNet and UNet++SCSE)
    CombinedLossWithClDice   — FocalTversky+clDice (used by UNet++DS)
    compute_loss_with_deep_supervision  — weighted loss for UNet++DS aux heads
    train_one_epoch()        — one training epoch
    validate()               — one validation epoch returning 5 metrics
    run_training_loop()      — full training loop with early stopping
"""
from __future__ import annotations

import torch
import torch.nn as nn
import torch.nn.functional as F

from config import CFG


# ─────────────────────────────────────────────────────────────────────────────
# Loss functions
# ─────────────────────────────────────────────────────────────────────────────

class TverskyLoss(nn.Module):
    """
    Tversky loss for class-imbalanced segmentation.

    Tversky index = TP / (TP + alpha·FP + beta·FN)

    alpha=0.3, beta=0.7: penalises missed vessels (FN) 2.3× more than FP.
    Operates on raw logits (applies sigmoid internally).
    Per-sample computation then averaged across the batch.
    """
    def __init__(self, alpha: float = 0.3, beta: float = 0.7, smooth: float = 1.0):
        super().__init__()
        self.alpha  = alpha
        self.beta   = beta
        self.smooth = smooth

    def forward(self, inputs: torch.Tensor, targets: torch.Tensor) -> torch.Tensor:
        probs = torch.sigmoid(inputs)
        B     = probs.size(0)
        p     = probs.view(B, -1)
        t     = targets.view(B, -1)

        tp = (p * t).sum(dim=1)
        fp = (p * (1 - t)).sum(dim=1)
        fn = ((1 - p) * t).sum(dim=1)

        tversky = (tp + self.smooth) / (tp + self.alpha * fp + self.beta * fn + self.smooth)
        return (1.0 - tversky).mean()


class FocalTverskyLoss(nn.Module):
    """
    Focal variant of Tversky loss.

    Raises Tversky loss to power gamma, which down-weights easy (well-segmented)
    regions and forces the network to focus on hard-to-detect thin vessels.

    gamma < 1 : softens the loss for hard examples (default 0.75)
    """
    def __init__(self, alpha: float = 0.3, beta: float = 0.7, gamma: float = 0.75):
        super().__init__()
        self.tversky = TverskyLoss(alpha=alpha, beta=beta)
        self.gamma   = gamma

    def forward(self, inputs: torch.Tensor, targets: torch.Tensor) -> torch.Tensor:
        t_loss = self.tversky(inputs, targets)
        return t_loss ** self.gamma


class CombinedLoss(nn.Module):
    """
    Combined loss = w_bce × BCE(pos_weight) + w_ftv × FocalTversky

    Used by: AttentionUNet, UNet++SCSE.

    BCE with pos_weight=9 handles early-epoch gradient imbalance (bg:fg ≈ 9:1).
    FocalTversky drives high-sensitivity vessel detection in later epochs.

    Weights: 0.3 × BCE + 0.7 × FocalTversky
    """
    def __init__(self,
                 pos_weight:  float = 9.0,
                 weight_bce:  float = 0.3,
                 weight_ftv:  float = 0.7,
                 alpha: float = 0.3,
                 beta:  float = 0.7,
                 gamma: float = 0.75):
        super().__init__()
        pw          = torch.tensor([pos_weight])
        self.bce    = nn.BCEWithLogitsLoss(pos_weight=pw)
        self.ftv    = FocalTverskyLoss(alpha=alpha, beta=beta, gamma=gamma)
        self.w_bce  = weight_bce
        self.w_ftv  = weight_ftv

    def forward(self, inputs: torch.Tensor, targets: torch.Tensor) -> torch.Tensor:
        self.bce.pos_weight = self.bce.pos_weight.to(inputs.device)
        return self.w_bce * self.bce(inputs, targets) + self.w_ftv * self.ftv(inputs, targets)


class SoftSkeletonize(nn.Module):
    """
    Differentiable soft-skeletonisation via iterative min-pooling.

    Approximates the morphological skeleton of a binary probability map using
    repeated 3×3 min-pooling, following Shit et al. (2021) "clDice".

    Args:
        num_iter : number of erosion iterations (≈ half the max vessel width in px)
                   Default 10 is appropriate for 1–3 px capillaries at 512px.
    """
    def __init__(self, num_iter: int = 10):
        super().__init__()
        self.num_iter = num_iter

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """
        Args:
            x : (B, 1, H, W) probabilities in [0, 1]  (post-sigmoid)
        Returns:
            skeleton approximation (B, 1, H, W) in [0, 1]
        """
        skel = x
        for _ in range(self.num_iter):
            # -max(-x) == min(x); max-pool on negated = min-pool
            eroded = -F.max_pool2d(-skel, kernel_size=3, stride=1, padding=1)
            skel   = skel * eroded      # soft AND: preserve only interior points
        return skel


class clDiceLoss(nn.Module):
    """
    Centreline Dice loss for topology-preserving vessel segmentation.

    clDice = 2 × Tprec × Tsens / (Tprec + Tsens)

    where:
        Tprec  = soft_skeleton(prediction) · target       / sum(soft_skeleton(pred))
        Tsens  = soft_skeleton(target)     · prediction   / sum(soft_skeleton(tgt))

    Reference: Shit et al. (2021) https://arxiv.org/abs/2003.07311

    Args:
        num_iter : soft-skeleton erosion iterations (default 10)
        smooth   : numerical stability (default 1.0)
        alpha    : weight of clDice vs standard Dice (default 0.5)
                   Final loss = alpha·clDice + (1-alpha)·Dice
    """
    def __init__(self, num_iter: int = 10, smooth: float = 1.0, alpha: float = 0.5):
        super().__init__()
        self.soft_skel = SoftSkeletonize(num_iter=num_iter)
        self.smooth    = smooth
        self.alpha     = alpha

    def forward(self, inputs: torch.Tensor, targets: torch.Tensor) -> torch.Tensor:
        """
        Args:
            inputs  : (B, 1, H, W) raw logits
            targets : (B, 1, H, W) binary masks {0, 1}
        Returns:
            scalar loss
        """
        if targets.dim() == 3:
            targets = targets.unsqueeze(1)

        probs     = torch.sigmoid(inputs)                  # (B,1,H,W)
        skel_pred = self.soft_skel(probs)                  # skeleton of prediction
        skel_tgt  = self.soft_skel(targets.float())        # skeleton of ground truth

        B  = probs.size(0)
        sp = skel_pred.view(B, -1)
        st = skel_tgt.view(B, -1)
        pr = probs.view(B, -1)
        tg = targets.float().view(B, -1)

        t_prec = ((sp * tg).sum(dim=1) + self.smooth) / (sp.sum(dim=1) + self.smooth)
        t_sens = ((st * pr).sum(dim=1) + self.smooth) / (st.sum(dim=1) + self.smooth)
        cl_dice = 1.0 - (2.0 * t_prec * t_sens / (t_prec + t_sens + 1e-8)).mean()

        # Standard Dice term (ensures pixel-level recall alongside topology).
        tp = (pr * tg).sum(dim=1)
        fp = (pr * (1.0 - tg)).sum(dim=1)
        fn = ((1.0 - pr) * tg).sum(dim=1)
        dice = 1.0 - ((2.0 * tp + self.smooth) /
                      (2.0 * tp + fp + fn + self.smooth)).mean()

        return self.alpha * cl_dice + (1.0 - self.alpha) * dice


class CombinedLossWithClDice(nn.Module):
    """
    Combined loss: 0.5 × FocalTversky + 0.5 × clDice

    Used by: UnetPlusPlusDS (UNet++ with deep supervision).

    FocalTversky  → pixel-level vessel recall, tolerates FP, penalises FN.
    clDice        → topology preservation, penalises centreline breaks.
    """
    def __init__(
        self,
        weight_ftv: float = 0.5,
        weight_cld: float = 0.5,
        alpha_tv:   float = 0.3,
        beta_tv:    float = 0.7,
        gamma_tv:   float = 0.75,
        iter_skel:  int   = 10,
    ):
        super().__init__()
        self.ftv   = FocalTverskyLoss(alpha=alpha_tv, beta=beta_tv, gamma=gamma_tv)
        self.cld   = clDiceLoss(num_iter=iter_skel)
        self.w_ftv = weight_ftv
        self.w_cld = weight_cld

    def forward(self, inputs: torch.Tensor, targets: torch.Tensor) -> torch.Tensor:
        """
        Args:
            inputs  : (B, 1, H, W) raw logits
            targets : (B, 1, H, W) or (B, H, W) binary masks
        Returns:
            scalar combined loss
        """
        if targets.dim() == 3:
            targets = targets.unsqueeze(1)
        return self.w_ftv * self.ftv(inputs, targets) + \
               self.w_cld * self.cld(inputs, targets)


# ─────────────────────────────────────────────────────────────────────────────
# Deep supervision loss helper (for UnetPlusPlusDS)
# ─────────────────────────────────────────────────────────────────────────────
# Aux head weights: block 0 (deepest, H/16) → 0.4 | H/8 → 0.2 | H/4 → 0.1
_AUX_WEIGHTS = [0.4, 0.2, 0.1]


def compute_loss_with_deep_supervision(
    criterion: nn.Module,
    model_output,          # tuple(main, [aux0, aux1, aux2]) or tensor
    targets: torch.Tensor,
) -> torch.Tensor:
    """
    Compute weighted combined loss over main + auxiliary heads.

    total = 1.0 × L(main) + 0.4 × L(aux0) + 0.2 × L(aux1) + 0.1 × L(aux2)

    Args:
        criterion    : CombinedLossWithClDice instance
        model_output : tuple (main, [aux…]) or raw tensor (eval/compat)
        targets      : (B, 1, H, W) or (B, H, W) binary masks
    Returns:
        scalar total loss
    """
    if isinstance(model_output, torch.Tensor):
        return criterion(model_output, targets)

    main_logit, aux_logits = model_output
    loss = criterion(main_logit, targets)           # main head weight = 1.0

    for aux_w, aux_logit in zip(_AUX_WEIGHTS, aux_logits):
        loss = loss + aux_w * criterion(aux_logit, targets)

    return loss


# ─────────────────────────────────────────────────────────────────────────────
# Training epoch
# ─────────────────────────────────────────────────────────────────────────────

def train_one_epoch(model, loader, criterion, optimizer, device, scaler,
                    deep_supervision: bool = False):
    """
    One training epoch.

    Args:
        deep_supervision : if True, passes (main, aux) output to
                           compute_loss_with_deep_supervision().
                           Set True for UnetPlusPlusDS.
    """
    model.train()
    total_loss = 0.0

    for images, masks in loader:
        images = images.float().to(device)
        masks  = masks.float().to(device)

        optimizer.zero_grad()
        with torch.amp.autocast("cuda", enabled=(device.type == "cuda")):
            output = model(images)
            if deep_supervision:
                loss = compute_loss_with_deep_supervision(criterion, output, masks)
            else:
                loss = criterion(output, masks)

        scaler.scale(loss).backward()
        scaler.unscale_(optimizer)
        torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=1.0)
        scaler.step(optimizer)
        scaler.update()
        total_loss += loss.item()

    return total_loss / len(loader)


# ─────────────────────────────────────────────────────────────────────────────
# Validation epoch  — returns loss + 4 segmentation metrics
# ─────────────────────────────────────────────────────────────────────────────

@torch.no_grad()
def validate(model, loader, criterion, device):
    """
    Returns:
        val_loss, val_dice, val_iou, val_sensitivity, val_specificity

    Uses the main (full-resolution) output head only.
    model.eval() → single tensor output (no auxiliary heads).
    """
    model.eval()
    total_loss = total_dice = total_iou = total_sens = total_spec = 0.0

    for images, masks in loader:
        images = images.float().to(device)
        masks  = masks.float().to(device)

        with torch.amp.autocast("cuda", enabled=(device.type == "cuda")):
            logits = model(images)
            # In eval mode UnetPlusPlusDS returns a tensor; ensure we handle both
            if isinstance(logits, tuple):
                logits = logits[0]
            loss = criterion(logits, masks)

        preds = (torch.sigmoid(logits) > 0.5).float()
        B = preds.size(0)
        p = preds.view(B, -1)
        t = masks.view(B, -1)

        tp = (p * t).sum(dim=1)
        fp = (p * (1 - t)).sum(dim=1)
        fn = ((1 - p) * t).sum(dim=1)
        tn = ((1 - p) * (1 - t)).sum(dim=1)

        dice = ((2 * tp + 1) / (2 * tp + fp + fn + 1)).mean()
        iou  = ((tp + 1) / (tp + fp + fn + 1)).mean()
        sens = ((tp + 1) / (tp + fn + 1)).mean()    # recall / sensitivity
        spec = ((tn + 1) / (tn + fp + 1)).mean()    # specificity

        total_loss += loss.item()
        total_dice += dice.item()
        total_iou  += iou.item()
        total_sens += sens.item()
        total_spec += spec.item()

    n = len(loader)
    return total_loss/n, total_dice/n, total_iou/n, total_sens/n, total_spec/n


# ─────────────────────────────────────────────────────────────────────────────
# Full training loop
# ─────────────────────────────────────────────────────────────────────────────

def run_training_loop(model, train_loader, val_loader, criterion,
                      save_path: str = "best_model.pt",
                      arch: str = "AttentionUNet",
                      encoder: str = "",
                      deep_supervision: bool = False):
    """
    Full training loop with early stopping, cosine LR schedule, and AMP.

    Args:
        model            : nn.Module to train
        train_loader     : DataLoader
        val_loader       : DataLoader
        criterion        : loss function
        save_path        : where to save the best checkpoint
        arch             : architecture name string saved in checkpoint
        encoder          : encoder name string saved in checkpoint
        deep_supervision : if True, uses compute_loss_with_deep_supervision

    Returns:
        best_dice : best validation Dice achieved
    """
    optimizer = torch.optim.Adam(
        model.parameters(), lr=CFG["lr"], weight_decay=1e-4
    )
    scheduler = torch.optim.lr_scheduler.CosineAnnealingWarmRestarts(
        optimizer,
        T_0     = 15,
        T_mult  = 1,
        eta_min = 1e-6,
    )
    scaler = torch.amp.GradScaler("cuda", enabled=(CFG["device"].type == "cuda"))

    best_dice = 0.0
    patience  = 0

    print(f"\n{'Epoch':>6}  {'TrainLoss':>10}  {'ValLoss':>8}  "
          f"{'Dice':>6}  {'IoU':>6}  {'Sens':>6}  {'Spec':>6}  {'LR':>9}")
    print("─" * 78)

    for epoch in range(1, CFG["epochs"] + 1):

        train_loss = train_one_epoch(
            model, train_loader, criterion, optimizer, CFG["device"], scaler,
            deep_supervision=deep_supervision
        )
        val_loss, val_dice, val_iou, val_sens, val_spec = validate(
            model, val_loader, criterion, CFG["device"]
        )
        scheduler.step(epoch)

        current_lr = optimizer.param_groups[0]["lr"]
        print(f"{epoch:6d}  {train_loss:10.4f}  {val_loss:8.4f}  "
              f"{val_dice:6.4f}  {val_iou:6.4f}  {val_sens:6.4f}  {val_spec:6.4f}  "
              f"{current_lr:9.2e}")

        if val_dice > best_dice:
            best_dice = val_dice
            ckpt = {
                "epoch":       epoch,
                "model_state": model.state_dict(),
                "optim_state": optimizer.state_dict(),
                "best_dice":   best_dice,
                "cfg":         CFG,
                "seed":        CFG["seed"],
                "arch":        arch,
            }
            if encoder:
                ckpt["encoder"] = encoder
            torch.save(ckpt, save_path)
            print(f"  ✓ Checkpoint saved  (dice={best_dice:.4f}  sens={val_sens:.4f})")
            patience = 0
        else:
            patience += 1
            if patience >= CFG["patience"]:
                print(f"\nEarly stopping at epoch {epoch}  "
                      f"(no improvement for {CFG['patience']} epochs)")
                break

    print(f"\nTraining complete.  Best Val Dice: {best_dice:.4f}")
    return best_dice
