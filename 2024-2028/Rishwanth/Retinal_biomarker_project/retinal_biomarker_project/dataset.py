"""
dataset.py — Multi-dataset retinal image loaders.

Supports DRIVE, STARE, CHASEDB1 for Stage-1 vessel segmentation.

Provides:
    RetinalDataset    — loads raw (image, mask) pairs from one subset
    AugmentedDataset  — expands a dataset with offline augmentation
    ValDataset        — validation wrapper (no augmentation)
    _IndexedSubset    — index-sliced subset view
    build_loaders()   — constructs combined train/val DataLoaders
"""
from __future__ import annotations

import math
import random
import re
from pathlib import Path

import cv2
import numpy as np
import torch
from torch.utils.data import ConcatDataset, DataLoader, Dataset

from config import CFG, ROOT_DIR, SEG_SUBSETS
from preprocessing import build_multichannel
from augmentation import get_transforms


_IMG_EXT = (".png", ".jpg", ".jpeg", ".tif", ".tiff", ".gif", ".bmp", ".ppm")

# ── Per-dataset configuration ─────────────────────────────────────────────────
# Maps each dataset to: (images subfolder, masks subfolder, annotator preference)
_DATASET_CFG = {
    #  subset       images_folder   masks_folder   prefer_string
    "DRIVE":    ("images",       "masks",       "manual1"),
    "STARE":    ("images",       "masks_1",     ".ah"),
    "CHASEDB1": ("images",       "masks_1",     "_1stHO"),
}


class RetinalDataset(Dataset):
    """
    Loads raw (image, mask) pairs from one subset directory.
    Returns uint8 numpy arrays — augmentation is handled by AugmentedDataset.

    Each __getitem__ returns:
        image : (H, W, 3) uint8  — build_multichannel() output
        mask  : (H, W)   float32 — binary {0.0, 1.0}

    Mask-folder and annotator-preference are driven by _DATASET_CFG:
        DRIVE    → images/ + masks/    prefer "manual1"
        STARE    → images/ + masks_1/  prefer ".ah"
        CHASEDB1 → images/ + masks_1/  prefer "_1stHO"
    """

    _ID_PATTERN = {
        "DRIVE":    r"^(\d+)",
        "STARE":    r"^(im\d+)",
        "CHASEDB1": r"^(Image_\d+[LR])",
    }

    def __init__(self, root_dir: str, subset: str = "DRIVE"):
        self.subset = subset

        if subset not in _DATASET_CFG:
            raise ValueError(
                f"Unknown subset '{subset}'. Known: {list(_DATASET_CFG.keys())}"
            )

        img_folder, mask_folder, self._prefer = _DATASET_CFG[subset]

        self.img_dir  = Path(root_dir) / subset / img_folder
        self.mask_dir = Path(root_dir) / subset / mask_folder

        if not self.img_dir.exists():
            raise FileNotFoundError(
                f"[{subset}] Image dir not found: {self.img_dir}"
            )
        if not self.mask_dir.exists():
            raise FileNotFoundError(
                f"[{subset}] Mask dir '{mask_folder}' not found: {self.mask_dir}\n"
                f"  Expected structure: {Path(root_dir) / subset / mask_folder}"
            )

        self.images = sorted([
            p for p in self.img_dir.iterdir()
            if p.suffix.lower() in _IMG_EXT
        ])
        if not self.images:
            raise RuntimeError(f"[{subset}] No images found in {self.img_dir}")

        print(f"  [{subset}] {len(self.images)} images  "
              f"img_dir='{img_folder}'  mask_dir='{mask_folder}'  "
              f"prefer='{self._prefer}'")

    def _extract_id(self, stem: str) -> str:
        pat = self._ID_PATTERN.get(self.subset, r"^(\w+)")
        m   = re.match(pat, stem, re.IGNORECASE)
        return m.group(1).lower() if m else stem.lower()

    def _resolve_mask(self, img_stem: str) -> Path:
        img_id    = self._extract_id(img_stem)
        all_masks = [p for p in self.mask_dir.iterdir()
                     if p.suffix.lower() in _IMG_EXT]

        candidates = [p for p in all_masks
                      if self._extract_id(p.stem) == img_id]
        if not candidates:
            candidates = [p for p in all_masks if img_id in p.stem.lower()]
        if not candidates:
            raise FileNotFoundError(
                f"[{self.subset}] No mask for '{img_stem}' in {self.mask_dir}.\n"
                f"Available: {[p.name for p in all_masks]}"
            )

        if len(candidates) > 1 and self._prefer:
            preferred = [p for p in candidates if self._prefer in p.stem]
            if preferred:
                candidates = preferred

        return candidates[0]

    def __len__(self):
        return len(self.images)

    def __getitem__(self, idx):
        img_path = self.images[idx]

        bgr = cv2.imread(str(img_path), cv2.IMREAD_COLOR)
        if bgr is None:
            raise IOError(f"cv2.imread failed: {img_path}")
        image = build_multichannel(bgr)            # (H, W, 3) uint8

        mask_path = self._resolve_mask(img_path.stem)
        mask = cv2.imread(str(mask_path), cv2.IMREAD_GRAYSCALE)
        if mask is None:
            raise IOError(f"cv2.imread failed for mask: {mask_path}")
        mask = (mask > 127).astype(np.float32)     # (H, W) binary {0, 1}

        return image, mask   # raw numpy — no transform here


class AugmentedDataset(Dataset):
    """
    Expands a RetinalDataset by applying aug_multiplier random augmentations
    to each image OFFLINE (generated on-the-fly per __getitem__, not pre-saved).

    __len__ = len(raw_dataset) × aug_multiplier

    __getitem__(i):
        raw_idx = i // aug_multiplier  → which original image
        Each call draws a FRESH random augmentation for that image.
        Because the RNG is not fixed per-item, each epoch sees different
        augmented versions → effective diversity is very high.

    In build_loaders() the aug_multiplier is chosen PER DATASET so that every
    dataset contributes the SAME total number of augmented training samples.

    Args:
        raw_dataset    : RetinalDataset or _IndexedSubset
        transform      : albumentations Compose pipeline
        aug_multiplier : augmented copies per raw image (set per-dataset)
    """
    def __init__(self, raw_dataset, transform, aug_multiplier: int):
        self.ds   = raw_dataset
        self.tf   = transform
        self.mult = aug_multiplier

    def __len__(self):
        return len(self.ds) * self.mult

    def __getitem__(self, i):
        raw_idx = i // self.mult
        image_np, mask_np = self.ds[raw_idx]       # (H,W,3) uint8, (H,W) float32

        aug   = self.tf(image=image_np, mask=mask_np)
        img_t = aug["image"]                        # (3, H, W) float32 tensor
        msk_t = aug["mask"]                         # (H, W)    float32 tensor

        if msk_t.dim() == 2:
            msk_t = msk_t.unsqueeze(0)              # → (1, H, W)
        return img_t, msk_t


class ValDataset(Dataset):
    """
    Validation wrapper — applies ONLY resize + normalize (no augmentation).
    Validation images are NEVER augmented to ensure Dice scores are comparable.
    """
    def __init__(self, raw_dataset, transform):
        self.ds = raw_dataset
        self.tf = transform

    def __len__(self):
        return len(self.ds)

    def __getitem__(self, i):
        image_np, mask_np = self.ds[i]
        aug   = self.tf(image=image_np, mask=mask_np)
        img_t = aug["image"]
        msk_t = aug["mask"]
        if msk_t.dim() == 2:
            msk_t = msk_t.unsqueeze(0)
        return img_t, msk_t


class _IndexedSubset(Dataset):
    """Slices a RetinalDataset to a fixed list of indices."""
    def __init__(self, dataset: RetinalDataset, indices: list):
        self.dataset = dataset
        self.indices = indices

    def __len__(self):
        return len(self.indices)

    def __getitem__(self, i):
        return self.dataset[self.indices[i]]


def build_loaders(root_dir: str, subsets: list, val_fraction: float = 0.2):
    """
    For each subset:
        1. Load all raw images via RetinalDataset (exact folders from _DATASET_CFG)
        2. Split indices 80/20 train/val using a seeded Generator
        3. Compute per-dataset aug_multiplier for EQUAL augmented sample counts
        4. Wrap train split in AugmentedDataset (× per-dataset multiplier)
        5. Wrap val split in ValDataset (no augmentation)
    Combine all subsets via ConcatDataset.

    Equal-augmentation logic
    ─────────────────────────
    TARGET = max_train_raw_across_datasets × CFG["aug_multiplier"]

    For each dataset with n_train raw training images:
        per_image_mult = ceil(TARGET / n_train)

    Every dataset therefore produces ≈ TARGET augmented samples per epoch,
    so the model trains on all three datasets with equal class weight.

    Returns:
        train_loader, val_loader
    """
    # ── Pass 1: load datasets and record raw train sizes ─────────────────────
    loaded = {}   # subset → (RetinalDataset, train_idx, val_idx)

    for sub in subsets:
        try:
            ds = RetinalDataset(root_dir, subset=sub)
        except (FileNotFoundError, RuntimeError, ValueError) as e:
            print(f"  [SKIP] {sub}: {e}")
            continue

        n_raw   = len(ds)
        n_val   = max(1, int(n_raw * val_fraction))
        n_train = n_raw - n_val

        rng          = np.random.default_rng(CFG["seed"])
        shuffled_idx = rng.permutation(list(range(n_raw))).tolist()
        train_idx    = shuffled_idx[:n_train]
        val_idx      = shuffled_idx[n_train:]

        loaded[sub] = (ds, train_idx, val_idx)

    if not loaded:
        raise RuntimeError(
            "No datasets loaded. Check ROOT_DIR and subset folder names."
        )

    # ── Compute equal-augmentation target ─────────────────────────────────────
    max_train  = max(len(v[1]) for v in loaded.values())
    target_aug = max_train * CFG["aug_multiplier"]

    per_mult = {
        sub: math.ceil(target_aug / len(v[1]))
        for sub, v in loaded.items()
    }

    # ── Pass 2: build AugmentedDatasets with per-dataset multipliers ──────────
    train_aug_datasets = []
    val_datasets       = []

    print("\n" + "─" * 76)
    print(f"{'Subset':<12} {'Raw':>5} {'Tr_raw':>7} {'Val_raw':>8} "
          f"{'aug×':>6} {'Tr_aug':>8} {'Batches':>8}")
    print("─" * 76)

    total_raw_train = 0
    total_raw_val   = 0
    total_aug_train = 0

    for sub, (ds, train_idx, val_idx) in loaded.items():
        n_raw   = len(ds)
        n_train = len(train_idx)
        n_val   = len(val_idx)
        mult    = per_mult[sub]

        train_raw    = _IndexedSubset(ds, train_idx)
        val_raw      = _IndexedSubset(ds, val_idx)
        train_aug_ds = AugmentedDataset(train_raw, get_transforms("train"), mult)
        val_ds       = ValDataset(val_raw,          get_transforms("val"))

        train_aug_datasets.append(train_aug_ds)
        val_datasets.append(val_ds)

        n_aug   = len(train_aug_ds)
        batches = math.ceil(n_aug / CFG["batch_size"])
        total_raw_train += n_train
        total_raw_val   += n_val
        total_aug_train += n_aug

        print(f"  {sub:<10} {n_raw:>5} {n_train:>7} {n_val:>8} "
              f"{mult:>6}× {n_aug:>8} {batches:>8}")

    combined_train = ConcatDataset(train_aug_datasets)
    combined_val   = ConcatDataset(val_datasets)

    total_batches_train = math.ceil(len(combined_train) / CFG["batch_size"])
    total_batches_val   = math.ceil(len(combined_val)   / CFG["batch_size"])

    print("─" * 76)
    print(f"  {'TOTAL':<10} {total_raw_train + total_raw_val:>5} "
          f"{total_raw_train:>7} {total_raw_val:>8} "
          f"{'':>6}  {total_aug_train:>8} {total_batches_train:>8}")
    print("─" * 76)
    print(f"\n  Equal-aug target : {target_aug} samples per dataset  "
          f"(largest train split = {max_train} × {CFG['aug_multiplier']}×)")
    print(f"  Combined train   : {total_aug_train} samples/epoch  "
          f"({total_batches_train} batches)")
    print(f"  Combined val     : {total_raw_val} images (no augmentation)  "
          f"({total_batches_val} batches)")
    print(f"\n  Folders used per dataset:")
    for sub in loaded:
        img_f, mask_f, pref = _DATASET_CFG[sub]
        print(f"    {sub:<10}  images='{img_f}'   masks='{mask_f}'   prefer='{pref}'")

    # ── DataLoaders ──────────────────────────────────────────────────────────
    def _worker_init(worker_id):
        np.random.seed(CFG["seed"] + worker_id)
        random.seed(CFG["seed"] + worker_id)

    _train_generator = torch.Generator()
    _train_generator.manual_seed(CFG["seed"])

    train_loader = DataLoader(
        combined_train,
        batch_size     = CFG["batch_size"],
        shuffle        = True,
        num_workers    = 2,
        pin_memory     = True,
        worker_init_fn = _worker_init,
        generator      = _train_generator,
    )
    val_loader = DataLoader(
        combined_val,
        batch_size     = CFG["batch_size"],
        shuffle        = False,
        num_workers    = 2,
        pin_memory     = True,
        worker_init_fn = _worker_init,
    )

    return train_loader, val_loader
