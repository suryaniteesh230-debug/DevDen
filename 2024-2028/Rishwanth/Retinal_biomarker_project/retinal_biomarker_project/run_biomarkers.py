"""
run_biomarkers.py — Entry point for retinal biomarker extraction.

Loads segmentation models + AV CNN, then runs the full biomarker
pipeline on a folder of fundus images.

Usage:
    python run_biomarkers.py
"""
from __future__ import annotations

import csv
from pathlib import Path

import cv2

from config import CFG
from inference import load_model
from av_classification import load_av_cnn
from biomarkers import (run_biomarker_pipeline, BIOMARKER_LABELS,
                         NORMAL_RANGES, print_biomarker_table)

# ─────────────────────────────────────────────────────────────────────────────
# Configuration — update paths to your saved checkpoints + test images
# ─────────────────────────────────────────────────────────────────────────────

CHECKPOINT_PATHS = {
    "attention_unet":    "best_model_attention_unet.pt",
    "unetplusplus":      "best_model_unetplusplus.pt",
    "unetplusplus_scse": "best_model_unetplusplus_scse.pt",
}

AV_CNN_PATH  = "outputs/checkpoints/av_cnn.pt"
IMAGE_DIR    = "/kaggle/input/datasets/mounishkumar003/drive1-av/DRIVE_AV/test/images"
OUTPUT_DIR   = "outputs/biomarkers"

# ─────────────────────────────────────────────────────────────────────────────
# Load segmentation models
# ─────────────────────────────────────────────────────────────────────────────

print("[§1] Loading segmentation models...")
ALL_SEG_MODELS = {}
for key, cp in CHECKPOINT_PATHS.items():
    if not Path(cp).exists():
        print(f"  ✗ {key} — checkpoint not found: {cp}")
        continue
    try:
        ALL_SEG_MODELS[key] = load_model(cp, device=CFG["device"])
        print(f"  ✓ {key}")
    except Exception as e:
        print(f"  ✗ {key} — {e}")

if not ALL_SEG_MODELS:
    raise RuntimeError(
        "No segmentation models loaded.\n"
        "Update CHECKPOINT_PATHS in run_biomarkers.py."
    )

# ─────────────────────────────────────────────────────────────────────────────
# Load AV CNN
# ─────────────────────────────────────────────────────────────────────────────

print("\n[§2] Loading AV CNN...")
if not Path(AV_CNN_PATH).exists():
    raise FileNotFoundError(
        f"AV CNN checkpoint not found: {AV_CNN_PATH}\n"
        "Run run_av_pipeline.py first to train and save the AV model."
    )
AV_MODEL = load_av_cnn(AV_CNN_PATH, device=CFG["device"])

# ─────────────────────────────────────────────────────────────────────────────
# Build image dict from IMAGE_DIR
# ─────────────────────────────────────────────────────────────────────────────

_IMG_EXT = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".ppm"}
print(f"\n[§3] Scanning images in: {IMAGE_DIR}")

IMAGE_PATHS = {}
_img_dir    = Path(IMAGE_DIR)
if not _img_dir.exists():
    raise FileNotFoundError(f"Image directory not found: {IMAGE_DIR}")

for _p in sorted(_img_dir.iterdir()):
    if _p.suffix.lower() in _IMG_EXT:
        IMAGE_PATHS[_p.stem] = str(_p)

if not IMAGE_PATHS:
    raise RuntimeError(f"No images found in {IMAGE_DIR}")

print(f"  Found {len(IMAGE_PATHS)} images: {list(IMAGE_PATHS.keys())[:5]}...")

# ─────────────────────────────────────────────────────────────────────────────
# Run biomarker pipeline
# ─────────────────────────────────────────────────────────────────────────────

print(f"\n[§4] Running biomarker pipeline...")
RESULTS = run_biomarker_pipeline(
    image_paths    = IMAGE_PATHS,
    all_seg_models = ALL_SEG_MODELS,
    av_model       = AV_MODEL,
    model_keys     = list(ALL_SEG_MODELS.keys()),
    seg_threshold  = 0.5,
    output_dir     = OUTPUT_DIR,
)

# ─────────────────────────────────────────────────────────────────────────────
# Save results CSV
# ─────────────────────────────────────────────────────────────────────────────

_out_dir  = Path(OUTPUT_DIR)
_csv_path = _out_dir / "biomarkers.csv"
_fields   = ["image", "model"] + list(BIOMARKER_LABELS.keys())
_rows     = []

for img_name, model_results in RESULTS.items():
    for model_key, bms in model_results.items():
        _row = {"image": img_name, "model": model_key}
        _row.update(bms)
        _rows.append(_row)

if _rows:
    with open(_csv_path, "w", newline="") as _f:
        _w = csv.DictWriter(_f, fieldnames=_fields, extrasaction="ignore")
        _w.writeheader()
        _w.writerows(_rows)
    print(f"\n[§5] Biomarkers saved → {_csv_path}  ({len(_rows)} rows)")

print_biomarker_table(RESULTS)
print("Done.")
