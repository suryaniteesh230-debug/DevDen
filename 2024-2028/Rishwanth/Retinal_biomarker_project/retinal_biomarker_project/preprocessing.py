"""
preprocessing.py — Fundus image preprocessing utilities.

Provides:
    single_scale_retinex(img, sigma) → uint8 (H, W)
    build_multichannel(bgr_image)    → uint8 (H, W, 3)
        Channel 0 : Raw green channel
        Channel 1 : CLAHE-enhanced green
        Channel 2 : Retinex-corrected green
"""
from __future__ import annotations

import os

import cv2
import numpy as np

from config import CFG, ROOT_DIR


def single_scale_retinex(img: np.ndarray, sigma: float = 50.0) -> np.ndarray:
    """
    Single-Scale Retinex illumination correction.

    Estimates the illumination component via a Gaussian blur and removes it
    in log-space, suppressing uneven lighting common in fundus images.

    Args:
        img   : uint8 (H, W) single-channel image
        sigma : Gaussian blur sigma — controls scale of illumination estimate.
                sigma=50 estimates a broad illumination field, aggressively
                suppressing the low-frequency background gradient.

    Returns:
        uint8 (H, W) normalised to 0–255
    """
    img_f   = img.astype(np.float32) + 1.0          # avoid log(0)
    blur    = cv2.GaussianBlur(img_f, (0, 0), sigma)
    retinex = np.log10(img_f) - np.log10(blur + 1.0)

    # Stretch to 0–255
    retinex -= retinex.min()
    if retinex.max() > 0:
        retinex /= retinex.max()
    return (retinex * 255).astype(np.uint8)


def build_multichannel(bgr_image: np.ndarray) -> np.ndarray:
    """
    Converts a BGR fundus image into a 3-channel preprocessing stack:

        Channel 0 : Raw green channel
                    → highest vessel-to-background contrast
        Channel 1 : CLAHE-enhanced green
                    → boosts thin/low-contrast vessels locally
        Channel 2 : Retinex-corrected green
                    → normalises illumination across datasets

    Args:
        bgr_image : (H, W, 3) uint8 BGR image from cv2.imread

    Returns:
        (H, W, 3) uint8  — ready to pass into albumentations Normalize
    """
    # clipLimit=1.5 still enhances thin vessels but clips artefact peaks.
    # clipLimit=2.0 over-enhances CLAHE tiles causing drusen/optic disc
    # artefacts to be boosted to vessel-like intensities.
    clahe     = cv2.createCLAHE(clipLimit=1.5, tileGridSize=(8, 8))
    green     = bgr_image[:, :, 1]          # (H, W) uint8
    enhanced  = clahe.apply(green)           # CLAHE
    corrected = single_scale_retinex(green)  # Retinex
    return np.stack([green, enhanced, corrected], axis=-1)  # (H, W, 3)


# ── Quick sanity check (runs on import if DRIVE path exists) ─────────────────
_test_dir = os.path.join(ROOT_DIR, "DRIVE", "images")
if os.path.isdir(_test_dir):
    _sample_name = sorted(os.listdir(_test_dir))[0]
    _bgr = cv2.imread(os.path.join(_test_dir, _sample_name))
    if _bgr is not None:
        _mc = build_multichannel(_bgr)
        print(f"Multi-channel shape : {_mc.shape}  dtype={_mc.dtype}")
        print(f"  Ch0 raw green  range : [{_mc[:,:,0].min():3d}, {_mc[:,:,0].max():3d}]")
        print(f"  Ch1 CLAHE      range : [{_mc[:,:,1].min():3d}, {_mc[:,:,1].max():3d}]")
        print(f"  Ch2 Retinex    range : [{_mc[:,:,2].min():3d}, {_mc[:,:,2].max():3d}]")
    else:
        print("[WARNING] Could not read sample image for sanity check.")
else:
    print(f"[INFO] DRIVE path not found at {_test_dir} — skipping sanity check.")
