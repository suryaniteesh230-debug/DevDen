"""
av_dataset.py — Artery/Vein classification dataset loaders.

Supports DRIVE_AV and LES_AV datasets.

Provides:
    decode_av_label_drive()     — BGR colour label → (artery_bool, vein_bool)
    decode_av_label_les()       — grayscale label → (artery_bool, vein_bool)
    load_drive_av_samples()     — list of DRIVE_AV sample dicts
    load_les_av_samples()       — list of LES_AV sample dicts
    load_sample_arrays()        — unified loader returns (bgr, vessel, artery, vein, fov)
    AV_TRAIN_SAMPLES            — combined DRIVE_AV train + LES_AV
    AV_TEST_SAMPLES             — DRIVE_AV test split only
"""
from __future__ import annotations

import numpy as np
import cv2
from pathlib import Path

# ─────────────────────────────────────────────────────────────────────────────
# Dataset root paths — edit to match your environment
# ─────────────────────────────────────────────────────────────────────────────
DRIVE_AV_ROOT = "/kaggle/input/datasets/mounishkumar003/drive1-av/DRIVE_AV"
LES_AV_ROOT   = (
    "/kaggle/input/datasets/shakibabsar42/"
    "retinal-vessel-fundus-dataset-collection/"
    "retinal-vessel-fundus-dataset-collection/LES-AV"
)


# ─────────────────────────────────────────────────────────────────────────────
# Label decoders
# ─────────────────────────────────────────────────────────────────────────────

def decode_av_label_drive(label_bgr: np.ndarray):
    """
    Decodes DRIVE_AV BGR colour label image.
        BGR(0, 0, 255) = artery
        BGR(255, 0, 0) = vein

    Returns:
        artery_mask : (H, W) bool
        vein_mask   : (H, W) bool
    """
    artery_mask = (
        (label_bgr[:, :, 2] == 255) &
        (label_bgr[:, :, 1] == 0)   &
        (label_bgr[:, :, 0] == 0)
    )
    vein_mask = (
        (label_bgr[:, :, 0] == 255) &
        (label_bgr[:, :, 1] == 0)   &
        (label_bgr[:, :, 2] == 0)
    )
    return artery_mask, vein_mask


def decode_av_label_les(label_gray: np.ndarray):
    """
    Decodes LES_AV grayscale label map.

    Handles two common encodings:
        Integer label map (values 0–10): artery=2, vein=3
        Threshold-based (values > 10) : artery >200, vein 50–200

    Returns:
        artery_mask : (H, W) bool
        vein_mask   : (H, W) bool
    """
    if label_gray.max() <= 10:
        artery_mask = (label_gray == 2)
        vein_mask   = (label_gray == 3)
    else:
        artery_mask = (label_gray > 200)
        vein_mask   = (label_gray > 50) & (label_gray <= 200)
    return artery_mask.astype(bool), vein_mask.astype(bool)


# ─────────────────────────────────────────────────────────────────────────────
# DRIVE_AV sample builders
# ─────────────────────────────────────────────────────────────────────────────

def _build_drive_sample_list(split_dir: Path, has_vessel: bool) -> list:
    img_dir    = split_dir / "images"
    label_dir  = split_dir / "label"
    mask_dir   = split_dir / "mask"
    vessel_dir = split_dir / "vessel" if has_vessel else None

    if not img_dir.exists():
        return []

    img_files = sorted(img_dir.glob("*.png"), key=lambda p: int(p.stem))
    samples   = []

    for img_path in img_files:
        stem        = img_path.stem
        label_path  = label_dir  / f"{stem}.png"
        mask_path   = mask_dir   / f"{stem}.png"
        vessel_path = (vessel_dir / f"{stem}.png") if vessel_dir else None

        if not label_path.exists():
            continue

        samples.append({
            "name":        f"DRIVE_{split_dir.name}_{stem}",
            "stem":        stem,
            "split":       split_dir.name,
            "dataset":     "DRIVE_AV",
            "image_path":  str(img_path),
            "label_path":  str(label_path),
            "mask_path":   str(mask_path)   if mask_path.exists()             else None,
            "vessel_path": str(vessel_path) if (vessel_path and vessel_path.exists()) else None,
            "label_type":  "drive_bgr",
        })

    return samples


def load_drive_av_samples(root: str = DRIVE_AV_ROOT,
                           splits: tuple = ("training", "test")) -> list:
    """
    Loads DRIVE_AV sample dicts for the requested splits.

    Returns:
        list of sample dicts, each with:
            name, stem, split, dataset, image_path, label_path,
            mask_path, vessel_path, label_type
    """
    root        = Path(root)
    all_samples = []

    for split in splits:
        split_dir  = root / split
        has_vessel = (split == "training")

        if not split_dir.exists():
            print(f"[DRIVE-AV] Not found: {split_dir}")
            continue

        samples = _build_drive_sample_list(split_dir, has_vessel)
        print(f"[DRIVE-AV] {split:10s} → {len(samples)} samples  "
              f"(vessel GT: {'yes' if has_vessel else 'no'})")
        all_samples.extend(samples)

    return all_samples


# ─────────────────────────────────────────────────────────────────────────────
# LES_AV sample builders
# ─────────────────────────────────────────────────────────────────────────────

def _build_les_sample_list(root: Path) -> list:
    img_dir    = root / "images"
    label_dir  = root / "masks_multiclass"
    vessel_dir = root / "vessel_masks"
    mask_dir   = root / "masks"

    if not img_dir.exists():
        print(f"[LES-AV] images/ not found at {img_dir}")
        return []

    _ext      = (".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp")
    img_files = sorted([p for p in img_dir.iterdir() if p.suffix.lower() in _ext])
    samples   = []

    for img_path in img_files:
        stem = img_path.stem

        label_path = None
        for candidate in [
            label_dir / f"{stem}.png",
            label_dir / f"{stem}.tif",
            label_dir / f"{stem}_label.png",
            label_dir / f"{stem}_AV.png",
        ]:
            if candidate.exists():
                label_path = candidate
                break

        if label_path is None:
            continue

        vessel_path = vessel_dir / f"{stem}.png" if vessel_dir.exists() else None
        mask_path   = mask_dir   / f"{stem}.png" if mask_dir.exists()   else None

        samples.append({
            "name":        f"LES_{stem}",
            "stem":        stem,
            "split":       "training",
            "dataset":     "LES_AV",
            "image_path":  str(img_path),
            "label_path":  str(label_path),
            "mask_path":   str(mask_path)   if (mask_path   and mask_path.exists())   else None,
            "vessel_path": str(vessel_path) if (vessel_path and vessel_path.exists()) else None,
            "label_type":  "les_gray",
        })

    print(f"[LES-AV]  {len(samples)} samples found.")
    return samples


def load_les_av_samples(root: str = LES_AV_ROOT) -> list:
    """
    Loads LES_AV sample dicts.
    Returns [] if root directory does not exist.
    """
    return _build_les_sample_list(Path(root))


# ─────────────────────────────────────────────────────────────────────────────
# Unified sample loader
# ─────────────────────────────────────────────────────────────────────────────

def load_sample_arrays(sample: dict):
    """
    Loads arrays for one AV sample dict (DRIVE_AV or LES_AV).

    Returns:
        bgr_image   : (H, W, 3) uint8
        vessel_mask : (H, W)    uint8 {0, 255}  or None if not available
        artery_mask : (H, W)    bool
        vein_mask   : (H, W)    bool
        fov_mask    : (H, W)    uint8 {0, 255}  (all-ones if mask not available)
    """
    bgr_image = cv2.imread(sample["image_path"], cv2.IMREAD_COLOR)
    if bgr_image is None:
        raise IOError(f"Cannot read: {sample['image_path']}")

    # ── Vessel mask ───────────────────────────────────────────────────────────
    if sample.get("vessel_path") and Path(sample["vessel_path"]).exists():
        raw         = cv2.imread(sample["vessel_path"], cv2.IMREAD_GRAYSCALE)
        vessel_mask = ((raw > 127) * 255).astype(np.uint8)
    else:
        vessel_mask = None

    # ── AV label → artery/vein bool masks ────────────────────────────────────
    label_type = sample.get("label_type", "drive_bgr")

    if label_type == "drive_bgr":
        label_bgr = cv2.imread(sample["label_path"], cv2.IMREAD_COLOR)
        if label_bgr is None:
            raise IOError(f"Cannot read label: {sample['label_path']}")
        artery_mask, vein_mask = decode_av_label_drive(label_bgr)

    elif label_type == "les_gray":
        label_gray = cv2.imread(sample["label_path"], cv2.IMREAD_GRAYSCALE)
        if label_gray is None:
            raise IOError(f"Cannot read label: {sample['label_path']}")
        artery_mask, vein_mask = decode_av_label_les(label_gray)

    else:
        raise ValueError(f"Unknown label_type: {label_type}")

    # ── FOV mask ──────────────────────────────────────────────────────────────
    if sample.get("mask_path") and Path(sample["mask_path"]).exists():
        raw      = cv2.imread(sample["mask_path"], cv2.IMREAD_GRAYSCALE)
        fov_mask = ((raw > 127) * 255).astype(np.uint8)
    else:
        H, W     = bgr_image.shape[:2]
        fov_mask = np.ones((H, W), dtype=np.uint8) * 255

    return bgr_image, vessel_mask, artery_mask, vein_mask, fov_mask


# ─────────────────────────────────────────────────────────────────────────────
# Build combined sample lists on import
# ─────────────────────────────────────────────────────────────────────────────
print("Loading DRIVE-AV samples...")
DRIVE_AV_ALL     = load_drive_av_samples(DRIVE_AV_ROOT)
DRIVE_TRAIN_SAMP = [s for s in DRIVE_AV_ALL if s["split"] == "training"]
DRIVE_TEST_SAMP  = [s for s in DRIVE_AV_ALL if s["split"] == "test"]

print("\nLoading LES-AV samples...")
LES_AV_ALL = []
_les_root  = Path(LES_AV_ROOT)
if _les_root.exists():
    LES_AV_ALL = load_les_av_samples(LES_AV_ROOT)
else:
    print(f"[LES-AV] Root not found: {LES_AV_ROOT}  (set LES_AV_ROOT to use LES-AV)")

AV_TRAIN_SAMPLES = DRIVE_TRAIN_SAMP + LES_AV_ALL   # both datasets for CNN training
AV_TEST_SAMPLES  = DRIVE_TEST_SAMP                  # DRIVE only for evaluation
AV_SAMPLES       = DRIVE_AV_ALL + LES_AV_ALL        # all samples combined

print(f"\n[AV Dataset] DRIVE_AV train: {len(DRIVE_TRAIN_SAMP)}  "
      f"test: {len(DRIVE_TEST_SAMP)}  LES_AV: {len(LES_AV_ALL)}")
print(f"[AV Dataset] Total training pool : {len(AV_TRAIN_SAMPLES)}")
print(f"[AV Dataset] Evaluation set (DRIVE): {len(DRIVE_TEST_SAMP)}")

# ── Quick verification ────────────────────────────────────────────────────────
if DRIVE_TRAIN_SAMP:
    try:
        _s = DRIVE_TRAIN_SAMP[0]
        _bgr, _ves, _art, _vein, _fov = load_sample_arrays(_s)
        print(f"\nVerification — '{_s['name']}':")
        print(f"  Image  : {_bgr.shape}  dtype={_bgr.dtype}")
        if _ves is not None:
            print(f"  Vessel : {_ves.shape}  unique={np.unique(_ves)}")
        print(f"  Artery : {_art.sum():,} px  |  Vein: {_vein.sum():,} px")
        print(f"  FOV    : {_fov.shape}")
    except Exception as _e:
        print(f"[WARNING] {_e} — check DRIVE_AV_ROOT path")
