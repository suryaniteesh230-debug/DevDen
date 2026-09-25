"""
run_av_pipeline.py — End-to-end artery/vein classification pipeline.

Connects all modules into one runnable script.

Pipeline:
    1. Load all 3 segmentation models
    2. Build AV patch dataset (DRIVE_AV + LES_AV)
    3. Leave-One-Image-Out cross-validation (DRIVE_AV only)
    4. Train final AV CNN on all data
    5. Per-model inference loop (all test images)
    6. Save metrics CSV and output images

Usage:
    python run_av_pipeline.py
"""
from __future__ import annotations

import csv
import time
import traceback
from pathlib import Path

import cv2
import numpy as np

from config import CFG
from av_dataset import AV_TRAIN_SAMPLES, AV_TEST_SAMPLES, load_sample_arrays
from av_segments import (build_av_patch_dataset, compute_width_map,
                          merge_segments_by_continuity,
                          refine_av_continuity, segments_to_edge_labels)
from av_classification import (cross_validate_av_cnn, train_final_av_cnn,
                                predict_av_labels_cnn, load_av_cnn)
from av_visualisation import (labels_to_masks, evaluate_av_masks,
                               generate_all_outputs, plot_av_overlay)
from inference import load_model
from postprocessing import full_postprocess_pipeline

# ─────────────────────────────────────────────────────────────────────────────
# Configuration — update checkpoint paths to your saved .pt files
# ─────────────────────────────────────────────────────────────────────────────

CHECKPOINT_PATHS = {
    "attention_unet":    "best_model_attention_unet.pt",
    "unetplusplus":      "best_model_unetplusplus.pt",
    "unetplusplus_scse": "best_model_unetplusplus_scse.pt",
}

AV_CNN_SAVE_PATH = "av_cnn.pt"
OUTPUTS_ROOT     = Path("outputs")

_MODEL_KEYS = ["attention_unet", "unetplusplus", "unetplusplus_scse"]


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _safe_and(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """cv2.bitwise_and with automatic dtype + shape alignment."""
    H, W = a.shape[:2]
    a = np.asarray(a, dtype=np.uint8)
    b = np.asarray(b, dtype=np.uint8)
    if b.shape[:2] != (H, W):
        b = cv2.resize(b, (W, H), interpolation=cv2.INTER_NEAREST)
    return cv2.bitwise_and(a, b)


def _av_overlay_image(rgb: np.ndarray,
                       artery_mask: np.ndarray,
                       vein_mask: np.ndarray) -> np.ndarray:
    """RGB overlay — arteries=red, veins=blue."""
    ov = rgb.copy().astype(np.float32)
    a  = artery_mask > 0; v = vein_mask > 0
    ov[a, 0] = np.clip(ov[a, 0] * 0.3 + 179, 0, 255)
    ov[a, 1] = np.clip(ov[a, 1] * 0.3,       0, 255)
    ov[a, 2] = np.clip(ov[a, 2] * 0.3,       0, 255)
    ov[v, 0] = np.clip(ov[v, 0] * 0.3,       0, 255)
    ov[v, 1] = np.clip(ov[v, 1] * 0.3,       0, 255)
    ov[v, 2] = np.clip(ov[v, 2] * 0.3 + 179, 0, 255)
    return ov.astype(np.uint8)


# ─────────────────────────────────────────────────────────────────────────────
# §1 — Output directory structure
# ─────────────────────────────────────────────────────────────────────────────

for _d in ([OUTPUTS_ROOT / "overlays",
             OUTPUTS_ROOT / "artery_masks",
             OUTPUTS_ROOT / "vein_masks",
             OUTPUTS_ROOT / "checkpoints",
             OUTPUTS_ROOT / "metrics"] +
            [OUTPUTS_ROOT / k for k in _MODEL_KEYS]):
    _d.mkdir(parents=True, exist_ok=True)

print(f"[§1] Output tree created under: {OUTPUTS_ROOT.resolve()}")


# ─────────────────────────────────────────────────────────────────────────────
# §2 — Load all 3 segmentation models
# ─────────────────────────────────────────────────────────────────────────────

print("\n[§2] Loading segmentation models...")

ALL_SEG_MODELS = {}
for _key in _MODEL_KEYS:
    cp = CHECKPOINT_PATHS.get(_key, "")
    if not Path(cp).exists():
        print(f"  ✗  {_key} — checkpoint not found: {cp}")
        print(f"     Update CHECKPOINT_PATHS['{_key}'] in run_av_pipeline.py")
        continue
    try:
        ALL_SEG_MODELS[_key] = load_model(cp, device=CFG["device"])
        print(f"  ✓  {_key}")
    except Exception as _e:
        print(f"  ✗  {_key} — failed: {_e}")

if not ALL_SEG_MODELS:
    raise RuntimeError(
        "[§2] No segmentation models loaded.\n"
        "Update CHECKPOINT_PATHS in run_av_pipeline.py and re-run."
    )
print(f"\n  Loaded: {list(ALL_SEG_MODELS.keys())}")


# ─────────────────────────────────────────────────────────────────────────────
# §3 — Optional LES-AV augmentation of training set
# ─────────────────────────────────────────────────────────────────────────────

LES_AV_ROOT = (
    "/kaggle/input/datasets/shakibabsar42/"
    "retinal-vessel-fundus-dataset-collection/"
    "retinal-vessel-fundus-dataset-collection/LES-AV"
)

print("\n[§3] Checking LES-AV dataset...")
_les_dir = Path(LES_AV_ROOT)

if _les_dir.exists():
    from av_dataset import load_les_av_samples
    _les_samples = load_les_av_samples(LES_AV_ROOT)
    COMBINED_TRAIN = AV_TRAIN_SAMPLES + _les_samples
    print(f"  ✓ LES-AV found — {len(_les_samples)} samples added")
else:
    COMBINED_TRAIN = AV_TRAIN_SAMPLES
    print(f"  ✗ LES-AV not found — training on DRIVE_AV only")

print(f"  Total training samples : {len(COMBINED_TRAIN)}")


# ─────────────────────────────────────────────────────────────────────────────
# §4 — Build AV patch dataset
# ─────────────────────────────────────────────────────────────────────────────

print("\n" + "=" * 65)
print("  §4  Building AV Patch Dataset")
print("=" * 65)

_t = time.time()
X_all, y_all, sample_ids_all, meta_all = build_av_patch_dataset(
    COMBINED_TRAIN,
    seg_model     = None,
    threshold     = 0.5,
    use_gt_vessel = True,
)

if len(y_all) == 0:
    raise RuntimeError(
        "[§4] No patches extracted.\n"
        "  • Check DRIVE_AV_ROOT in av_dataset.py\n"
        "  • Ensure label/ and vessel/ folders exist"
    )

print(f"\n  Time            : {time.time()-_t:.1f}s")
print(f"  Total segments  : {len(y_all)}")
print(f"  Arteries        : {(y_all==1).sum()}  ({100*(y_all==1).mean():.1f}%)")
print(f"  Veins           : {(y_all==0).sum()}  ({100*(y_all==0).mean():.1f}%)")
print(f"  Patch shape     : {X_all.shape}")


# ─────────────────────────────────────────────────────────────────────────────
# §5 — Leave-One-Image-Out cross-validation
# ─────────────────────────────────────────────────────────────────────────────

print("\n" + "=" * 65)
print("  §5  Leave-One-Image-Out Cross-Validation (DRIVE_AV only)")
print("=" * 65)

_drive_names = {s["name"] for s in AV_TRAIN_SAMPLES}
_cv_mask     = np.array([sid in _drive_names for sid in sample_ids_all])

_t         = time.time()
cv_results = {}

if _cv_mask.sum() > 0:
    cv_results = cross_validate_av_cnn(
        X_all[_cv_mask],
        y_all[_cv_mask],
        [s for s, m in zip(sample_ids_all, _cv_mask) if m],
    )
else:
    print("  [WARNING] No DRIVE_AV samples — skipping CV.")

print(f"  CV time: {time.time()-_t:.1f}s")

_cv_path = OUTPUTS_ROOT / "metrics" / "cv_results.csv"
if cv_results.get("fold_results"):
    with open(_cv_path, "w", newline="") as _f:
        _w = csv.DictWriter(
            _f, fieldnames=["image", "acc", "bal_acc", "art_f1", "vein_f1", "n_test"])
        _w.writeheader(); _w.writerows(cv_results["fold_results"])
    print(f"  CV results saved → {_cv_path}")


# ─────────────────────────────────────────────────────────────────────────────
# §6 — Train final AV CNN
# ─────────────────────────────────────────────────────────────────────────────

print("\n" + "=" * 65)
print(f"  §6  Training Final AV Classifier")
print(f"  {len(y_all)} segments  |  {len(COMBINED_TRAIN)} images")
print("=" * 65)

_clf_path = str(OUTPUTS_ROOT / "checkpoints" / "av_cnn.pt")
_t        = time.time()

AV_MODEL = train_final_av_cnn(X_all, y_all, save_path=_clf_path)
AV_MODEL.eval()

print(f"  Training time : {time.time()-_t:.1f}s")
print(f"  Saved → {_clf_path}")


# ─────────────────────────────────────────────────────────────────────────────
# §7 — Per-model inference loop
# ─────────────────────────────────────────────────────────────────────────────

print("\n" + "=" * 65)
print("  §7  Per-Model Inference  (all 3 segmentation models)")
print("=" * 65)

INFERENCE_SAMPLES = AV_TEST_SAMPLES if AV_TEST_SAMPLES else AV_TRAIN_SAMPLES[:3]
print(f"  Inference images : {len(INFERENCE_SAMPLES)}")

ALL_RESULTS = {}

for _model_key, _seg_model in ALL_SEG_MODELS.items():
    print(f"\n{'─'*65}")
    print(f"  Model : {_model_key}")
    print(f"{'─'*65}")
    _t_model     = time.time()
    _model_results = {}

    for _sample in INFERENCE_SAMPLES:
        print(f"\n  Image : {_sample['name']}")

        # Load arrays
        try:
            _bgr, _vessel_gt, _artery_gt, _vein_gt, _fov = \
                load_sample_arrays(_sample)
        except Exception as _e:
            print(f"  [SKIP] Load error: {_e}"); continue

        _rgb = cv2.cvtColor(_bgr, cv2.COLOR_BGR2RGB)

        # Segmentation
        try:
            from inference import predict_single
            _prob_map = predict_single(_seg_model, _bgr)
        except Exception as _e:
            print(f"    [SKIP] Seg error: {_e}"); continue

        # Postprocessing
        try:
            _refined, _skeleton, _graph = full_postprocess_pipeline(
                _prob_map, threshold=0.5, gap_px=7)
        except Exception as _e:
            print(f"    [SKIP] Postprocess error: {_e}"); continue

        _fov_u8  = np.asarray(_fov, dtype=np.uint8)
        _refined = _safe_and(_refined, _fov_u8)

        if _graph is None or _graph.number_of_edges() == 0:
            print(f"    [SKIP] Empty graph."); continue

        print(f"    [Graph] {_graph.number_of_nodes()} nodes  {_graph.number_of_edges()} edges")

        # Build segments for CNN
        _width_map      = compute_width_map(_refined)
        _segments       = merge_segments_by_continuity(
            _graph, _width_map, angle_thresh_deg=30.0,
            width_ratio_thresh=2.0, min_length=5.0)
        _seg_label_list = predict_av_labels_cnn(
            segments    = _segments,
            bgr_image   = _bgr,
            vessel_mask = _refined,
            model       = AV_MODEL,
        )

        # Map back to edge keys
        _edge_keys   = [(_u, _v) for _u, _v in _graph.edges()]
        _labels_raw  = segments_to_edge_labels(_graph, _segments, _seg_label_list)
        _n_art_raw   = sum(1 for l in _labels_raw.values() if l == 1)
        _n_vein_raw  = sum(1 for l in _labels_raw.values() if l == 0)
        print(f"    [CNN raw] Artery={_n_art_raw}  Vein={_n_vein_raw}")

        # Continuity refinement
        _labels_refined = refine_av_continuity(_graph, _labels_raw)

        # Pixel masks
        _artery_mask, _vein_mask = labels_to_masks(
            _graph, _labels_refined,
            image_shape = _bgr.shape[:2],
            vessel_mask = _refined,
        )

        # Save masks + overlay
        _stem = f"{_model_key}_{_sample['name']}"
        cv2.imwrite(str(OUTPUTS_ROOT / "artery_masks" / f"{_stem}.png"), _artery_mask)
        cv2.imwrite(str(OUTPUTS_ROOT / "vein_masks"   / f"{_stem}.png"), _vein_mask)
        _ov = _av_overlay_image(_rgb, _artery_mask, _vein_mask)
        cv2.imwrite(str(OUTPUTS_ROOT / "overlays" / f"{_stem}.png"),
                    cv2.cvtColor(_ov, cv2.COLOR_RGB2BGR))

        # All 9 pipeline output images
        _img_out = OUTPUTS_ROOT / _model_key / _sample["name"]
        _img_out.mkdir(parents=True, exist_ok=True)
        try:
            generate_all_outputs(
                original_rgb       = _rgb,
                seg_results        = {_model_key: (_prob_map, _refined)},
                refined_results    = {_model_key: _refined},
                skeleton           = _skeleton,
                graph              = _graph,
                segments           = _segments,
                seg_labels_cnn     = _seg_label_list,
                edge_labels_before = _labels_raw,
                edge_labels_after  = _labels_refined,
                artery_mask        = _artery_mask,
                vein_mask          = _vein_mask,
                vessel_mask        = _refined,
                model_label        = _model_key,
                output_dir         = str(_img_out),
            )
        except Exception as _e:
            print(f"    [WARNING] generate_all_outputs error: {_e}")

        # Metrics
        _metrics = {
            "model": _model_key, "image": _sample["name"],
            "n_nodes": _graph.number_of_nodes(), "n_edges": _graph.number_of_edges(),
            "n_art_seg": _n_art_raw, "n_vein_seg": _n_vein_raw,
            "artery_dice": 0.0, "vein_dice": 0.0, "mean_dice": 0.0,
            "artery_pxacc": 0.0, "vein_pxacc": 0.0,
        }
        if _artery_gt is not None and _vein_gt is not None:
            try:
                _ev = evaluate_av_masks(_artery_mask, _vein_mask, _artery_gt, _vein_gt)
                _metrics.update({
                    "artery_dice":  round(_ev.get("artery_dice",  0), 4),
                    "vein_dice":    round(_ev.get("vein_dice",    0), 4),
                    "mean_dice":    round(_ev.get("mean_dice",    0), 4),
                    "artery_pxacc": round(_ev.get("artery_pxacc", 0), 4),
                    "vein_pxacc":   round(_ev.get("vein_pxacc",   0), 4),
                })
            except Exception as _e:
                print(f"    [WARNING] eval error: {_e}")

        _model_results[_sample["name"]] = _metrics
        print(f"    Art-Dice={_metrics['artery_dice']:.4f}  "
              f"Vein-Dice={_metrics['vein_dice']:.4f}  "
              f"Mean-Dice={_metrics['mean_dice']:.4f}")

    ALL_RESULTS[_model_key] = _model_results
    print(f"\n  '{_model_key}' done in {time.time()-_t_model:.1f}s")


# ─────────────────────────────────────────────────────────────────────────────
# §8 — Save metrics CSV
# ─────────────────────────────────────────────────────────────────────────────

_metrics_path = OUTPUTS_ROOT / "metrics" / "metrics.csv"
_fields = ["model", "image", "n_nodes", "n_edges", "n_art_seg", "n_vein_seg",
           "artery_dice", "vein_dice", "mean_dice", "artery_pxacc", "vein_pxacc"]
_rows   = [m for res in ALL_RESULTS.values() for m in res.values()]

if _rows:
    with open(_metrics_path, "w", newline="") as _f:
        _w = csv.DictWriter(_f, fieldnames=_fields, extrasaction="ignore")
        _w.writeheader(); _w.writerows(_rows)
    print(f"\n[§8] Metrics saved → {_metrics_path}  ({len(_rows)} rows)")


# ─────────────────────────────────────────────────────────────────────────────
# §9 — Final summary
# ─────────────────────────────────────────────────────────────────────────────

print("\n\n" + "=" * 70)
print("  FINAL SUMMARY — Retinal Artery-Vein Classification")
print("  All 3 Segmentation Models")
print("=" * 70)

if cv_results:
    print(f"\n  LOIO Cross-Validation (CNN on DRIVE_AV):")
    print(f"    Mean Accuracy     : {cv_results.get('mean_acc',    0):.4f}")
    print(f"    Mean Balanced Acc : {cv_results.get('mean_bal_acc',0):.4f}")
    print(f"    Mean Artery F1    : {cv_results.get('mean_art_f1', 0):.4f}")
    print(f"    Mean Vein   F1    : {cv_results.get('mean_vein_f1',0):.4f}")

print(f"\n  {'Model':<25} {'Imgs':>5} {'ArtDice':>9} {'VeinDice':>9} {'MeanDice':>9}")
print("  " + "─" * 60)

for _mk in _MODEL_KEYS:
    _res = ALL_RESULTS.get(_mk, {})
    if not _res:
        print(f"  {_mk:<25}  (no results)"); continue
    _n  = len(_res)
    _ad = np.mean([v["artery_dice"] for v in _res.values()])
    _vd = np.mean([v["vein_dice"]   for v in _res.values()])
    _md = np.mean([v["mean_dice"]   for v in _res.values()])
    print(f"  {_mk:<25} {_n:>5} {_ad:>9.4f} {_vd:>9.4f} {_md:>9.4f}")

print(f"\n  Saved outputs:")
print(f"    {OUTPUTS_ROOT}/metrics/metrics.csv       — per-model pixel metrics")
print(f"    {OUTPUTS_ROOT}/metrics/cv_results.csv    — LOIO CV fold results")
print(f"    {OUTPUTS_ROOT}/checkpoints/av_cnn.pt     — trained AV CNN")
print(f"    {OUTPUTS_ROOT}/<model>/<image>/           — 9 PNGs per image per model")
print(f"    {OUTPUTS_ROOT}/overlays/                  — quick-access overlay PNGs")
print(f"    {OUTPUTS_ROOT}/artery_masks/              — binary artery masks")
print(f"    {OUTPUTS_ROOT}/vein_masks/                — binary vein masks")
print("\n" + "=" * 70)
print("  Pipeline complete.")
print("=" * 70)
