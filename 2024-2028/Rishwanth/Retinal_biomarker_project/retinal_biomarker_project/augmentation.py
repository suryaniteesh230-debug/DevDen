"""
augmentation.py — Albumentations training and validation pipelines.

Provides:
    get_transforms(phase)  → A.Compose   phase = 'train' | 'val'
"""
from __future__ import annotations

import cv2
import albumentations as A
from albumentations.pytorch import ToTensorV2

from config import CFG


def get_transforms(phase: str) -> A.Compose:
    """
    Returns albumentations pipeline for vessel segmentation.

    Input  : (H, W, 3) uint8  — output of build_multichannel()
    Output : (3, H, W) float32 tensor in range [-1, 1]

    Args:
        phase : 'train' | 'val'
    """
    # All 3 channels are green-derived → same neutral prior works for all
    _mean = (0.5, 0.5, 0.5)
    _std  = (0.5, 0.5, 0.5)

    if phase == "train":
        return A.Compose([
            A.Resize(CFG["img_size"], CFG["img_size"]),

            # ── Geometric (orientation + scale invariance) ────────────────────
            A.HorizontalFlip(p=0.5),
            A.VerticalFlip(p=0.5),
            A.RandomRotate90(p=0.5),

            # Use Affine instead of ShiftScaleRotate to silence FutureWarning.
            # NOTE: 'mode' argument was removed in newer albumentations — use
            # 'border_mode' (OpenCV constant) instead.
            A.Affine(
                translate_percent = {"x": (-0.05, 0.05), "y": (-0.05, 0.05)},
                scale             = (0.95, 1.05),
                rotate            = (-15, 15),
                border_mode       = cv2.BORDER_REFLECT_101,
                p                 = 0.5,
            ),

            # ── Photometric (contrast & illumination robustness) ──────────────
            # INCREASED brightness/contrast range: capillaries only 10-20 grey
            # levels above background — model must learn at ALL contrast levels.
            A.RandomBrightnessContrast(
                brightness_limit = 0.20,   # ±20%
                contrast_limit   = 0.20,   # ±20%
                p                = 0.6,
            ),
            A.RandomGamma(
                gamma_limit = (80, 120),   # wider: 0.8–1.2
                p           = 0.4,
            ),
            # Random CLAHE re-application during augmentation: forces model to
            # handle both enhanced and non-enhanced vessel contrast.
            A.CLAHE(
                clip_limit     = (1.0, 3.0),  # random clip between 1–3
                tile_grid_size = (8, 8),
                p              = 0.4,
            ),

            # ── Spatial distortion (vessel shape diversity) ───────────────────
            # GridDistortion: locally warps the grid independently per cell —
            # stretches bifurcations and junctions in varied ways.
            A.GridDistortion(
                num_steps     = 5,
                distort_limit = 0.15,
                p             = 0.3,
            ),
            # ElasticTransform: smooth continuous vessel curvature deformation.
            A.ElasticTransform(
                alpha = 40,    # deformation magnitude (pixels at 512px)
                sigma = 6,     # smoothness — higher = more globally smooth
                p     = 0.4,
            ),

            # ── Occlusion robustness (vessel continuity) ─────────────────────
            # CoarseDropout randomly blacks out small rectangular patches.
            # This forces the model to predict vessel continuity THROUGH missing
            # regions, which directly improves connectivity in the output mask.
            A.CoarseDropout(
                num_holes_range   = (1, 8),
                hole_height_range = (16, 32),
                hole_width_range  = (16, 32),
                fill              = 0,
                p                 = 0.2,
            ),

            # ── Noise ────────────────────────────────────────────────────────
            # ISONoise: stable sensor noise simulation (GaussNoise broken on Kaggle)
            A.ISONoise(
                color_shift = (0.01, 0.05),
                intensity   = (0.1, 0.4),
                p           = 0.3,
            ),

            # ── Normalize → [-1, 1] ──────────────────────────────────────────
            A.Normalize(mean=_mean, std=_std, max_pixel_value=255.0),
            ToTensorV2(),
        ])

    else:   # 'val' / 'test' — deterministic: only resize + normalise
        return A.Compose([
            A.Resize(CFG["img_size"], CFG["img_size"]),
            A.Normalize(mean=_mean, std=_std, max_pixel_value=255.0),
            ToTensorV2(),
        ])


# ── Sanity check ─────────────────────────────────────────────────────────────
_t = get_transforms("train")
_v = get_transforms("val")
print(f"Train pipeline : {len(_t.transforms)} transforms")
print(f"Val   pipeline : {len(_v.transforms)} transforms")
print("Augmentation transforms OK.")
print(f"Offline aug multiplier : {CFG['aug_multiplier']}× — each image becomes "
      f"{CFG['aug_multiplier']} unique augmented training samples.")
