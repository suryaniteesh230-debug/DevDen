"""
config.py — Shared configuration and reproducibility seed.
All other modules import CFG, ROOT_DIR, SEG_SUBSETS, and seed_everything from here.
"""
from __future__ import annotations

import os
import random
import subprocess
import sys

import numpy as np
import torch


# ─────────────────────────────────────────────────────────────────────────────
# segmentation_models_pytorch — install if missing
# ─────────────────────────────────────────────────────────────────────────────
_SMP_PACKAGE = "segmentation-models-pytorch"
_SMP_VERSION = "0.3.4"
_SMP_IMPORT  = "segmentation_models_pytorch"

try:
    import importlib
    importlib.import_module(_SMP_IMPORT)
    import segmentation_models_pytorch as _smp_probe
    print(f"[config] segmentation_models_pytorch already installed "
          f"(version {_smp_probe.__version__}).")
except ModuleNotFoundError:
    print(f"[config] Installing {_SMP_PACKAGE}=={_SMP_VERSION} …")
    _result = subprocess.run(
        [sys.executable, "-m", "pip", "install", "--quiet",
         f"{_SMP_PACKAGE}=={_SMP_VERSION}"],
        capture_output=True, text=True
    )
    if _result.returncode != 0:
        raise RuntimeError(
            f"pip install {_SMP_PACKAGE}=={_SMP_VERSION} failed.\n"
            f"pip stdout: {_result.stdout}\n"
            f"pip stderr: {_result.stderr}\n\n"
            "Possible fixes:\n"
            "  1. Enable internet access in Kaggle: Settings → Internet → On\n"
            "  2. Add the package via Kaggle's Add-ons → pip packages panel\n"
            f"  3. Install manually: !pip install {_SMP_PACKAGE}=={_SMP_VERSION}"
        ) from None
    import importlib
    import segmentation_models_pytorch as _smp_probe
    print(f"[config] Installed segmentation_models_pytorch "
          f"{_smp_probe.__version__} successfully.")


# ─────────────────────────────────────────────────────────────────────────────
# Seed
# ─────────────────────────────────────────────────────────────────────────────

def seed_everything(seed: int = 42):
    """
    Set all random seeds for full reproducibility.

    Covers:
        Python random   — used by albumentations internally
        NumPy           — used by OpenCV-based augmentations
        PyTorch CPU     — all CPU tensor ops
        PyTorch CUDA    — GPU kernels (via manual_seed_all)
        cuDNN           — deterministic convolution algorithms

    Note: deterministic=True slightly slows training but ensures identical
    results across runs with the same seed and data.
    """
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)
    torch.backends.cudnn.deterministic = True
    torch.backends.cudnn.benchmark     = False   # must be False for determinism
    os.environ["PYTHONHASHSEED"] = str(seed)
    print(f"[Seed] All RNGs fixed to {seed} — training is fully reproducible.")


# ─────────────────────────────────────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────────────────────────────────────

CFG = {
    "seed":            42,
    "img_size":        512,    # 512×512 — thin vessels vanish at 256
    "batch_size":      4,
    "lr":              1e-4,
    "epochs":          100,    # raised from 50: cosine schedule needs more cycles
    "n_channels":      3,      # green | CLAHE-green | Retinex-green
    "n_classes":       1,
    "patience":        30,     # raised from 20: gives more room past LR restarts
    # Offline augmentation multiplier — each raw image → N augmented copies
    # stored as a pre-built list before training starts.
    # Effect on dataset size:
    #   DRIVE only (16 train images)  : 16  × 20 =  320 training samples
    #   +STARE     (~18 train images) : 34  × 20 =  680 training samples
    #   +CHASEDB1  (~22 train images) : 56  × 20 = 1120 training samples
    # Raising this number costs no extra storage (augmentations are generated
    # on-the-fly and not saved to disk) and directly combats over-fitting.
    "aug_multiplier":  20,
    "device":          torch.device("cuda" if torch.cuda.is_available() else "cpu"),
}

# Run seed immediately — before any random_split or dataset creation
seed_everything(CFG["seed"])

ROOT_DIR = (
    "/kaggle/input/datasets/shakibabsar42/"
    "retinal-vessel-fundus-dataset-collection/"
    "retinal-vessel-fundus-dataset-collection"
)

# Datasets used for Stage-1 vessel segmentation
SEG_SUBSETS = ["DRIVE", "STARE", "CHASEDB1"]

print(f"Device          : {CFG['device']}")
print(f"Image size      : {CFG['img_size']}×{CFG['img_size']}  (512 preserves thin vessels)")
print(f"Channels        : {CFG['n_channels']}  (green | CLAHE | Retinex)")
print(f"Subsets         : {SEG_SUBSETS}")
print(f"Aug multiplier  : {CFG['aug_multiplier']}× per image")
print(f"Max epochs      : {CFG['epochs']}  |  Patience: {CFG['patience']}")
