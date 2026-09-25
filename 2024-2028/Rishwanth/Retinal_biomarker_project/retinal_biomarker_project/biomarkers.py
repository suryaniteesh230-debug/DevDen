"""
biomarkers.py — Retinal vascular biomarker extraction.

All biomarker-related code lives here.

Provides:
    compute_width_map_local()    — distance-transform width map
    biomarker_vessel_density()   — (1) vessel density %
    biomarker_mean_vessel_width()— (2) mean vessel diameter px
    biomarker_vessel_tortuosity()— (3) chord-to-arc tortuosity index
    biomarker_avr()              — (4) artery-to-vein ratio
    biomarker_mean_artery_width()— (5) mean artery diameter px
    biomarker_mean_vein_width()  — (6) mean vein diameter px
    compute_all_biomarkers()     — run all 6 in one call
    run_av_inference_single()    — edge-level AV CNN inference for one image
    render_av_overlay()          — paint arteries red, veins blue
    visualise_results()          — 5-panel figure: fundus/prob/mask/AV/biomarkers
    print_biomarker_table()      — formatted comparison table
    run_biomarker_pipeline()     — full pipeline for a list of images × models

Clinical reference ranges:
    vessel_density      :  7–13 %
    mean_vessel_width   :  2.5–7 px
    vessel_tortuosity   :  1.0–1.15
    avr                 :  0.67–0.75  (gold-standard hypertension biomarker)
    mean_artery_width   :  2–6 px
    mean_vein_width     :  3–9 px
"""
from __future__ import annotations

from pathlib import Path

import cv2
import matplotlib.gridspec as gridspec
import matplotlib.pyplot as plt
import numpy as np
import torch
from scipy.ndimage import distance_transform_edt

try:
    from skimage.morphology import skeletonize as skimage_skeletonize
    from skimage.measure    import label as sk_label, regionprops
    _SKIMAGE_OK = True
except ImportError:
    _SKIMAGE_OK = False
    print("[WARNING] scikit-image not found — tortuosity will use fallback.")

from config import CFG
from preprocessing import build_multichannel
from postprocessing import (postprocess_mask, skeletonize_mask,
                             skeleton_to_graph)
from av_visualisation import labels_to_masks


# ─────────────────────────────────────────────────────────────────────────────
# Width map
# ─────────────────────────────────────────────────────────────────────────────

def compute_width_map_local(vessel_mask: np.ndarray) -> np.ndarray:
    """
    Distance-transform width map.
    diameter = 2 × distance-to-background at each foreground pixel.

    Returns:
        (H, W) float32 — vessel diameter in pixels
    """
    binary = (vessel_mask > 0).astype(np.float32)
    dist   = distance_transform_edt(binary)
    return (dist * 2.0).astype(np.float32)


# ─────────────────────────────────────────────────────────────────────────────
# Biomarker 1 — Vessel Density
# ─────────────────────────────────────────────────────────────────────────────

def biomarker_vessel_density(vessel_mask: np.ndarray) -> float:
    """
    Vessel Density (VD) — fraction of image pixels that are vessel.

    Clinical significance:
        Reduced VD: glaucoma, diabetic retinopathy, vascular occlusion.
        Normal: ~8–12 %.

    Returns: float  0–100  (percentage)
    """
    return round(float((vessel_mask > 0).sum()) / vessel_mask.size * 100.0, 4)


# ─────────────────────────────────────────────────────────────────────────────
# Biomarker 2 — Mean Vessel Width
# ─────────────────────────────────────────────────────────────────────────────

def biomarker_mean_vessel_width(vessel_mask: np.ndarray) -> float:
    """
    Mean Vessel Width (MVW) — average vessel diameter across all vessel pixels.

    Computed via distance-transform: diameter = 2 × distance-to-background.

    Clinical significance:
        Arteriolar narrowing (hypertension) or venous dilation (occlusion).
        Typical: 3–7 px at 512×512.

    Returns: float  (pixels)
    """
    wmap      = compute_width_map_local(vessel_mask)
    vessel_px = wmap[vessel_mask > 0]
    if len(vessel_px) == 0:
        return 0.0
    return round(float(vessel_px.mean()), 4)


# ─────────────────────────────────────────────────────────────────────────────
# Biomarker 3 — Vessel Tortuosity
# ─────────────────────────────────────────────────────────────────────────────

def biomarker_vessel_tortuosity(vessel_mask: np.ndarray,
                                 min_len: int = 5) -> float:
    """
    Vessel Tortuosity (VT) — mean chord-to-arc ratio across skeleton segments.

    Tortuosity = arc_length / chord_length per segment.
    Value of 1.0 = perfectly straight; higher = more tortuous.

    Clinical significance:
        Increased tortuosity: hypertension, diabetic retinopathy,
        retinopathy of prematurity. Typical: 1.02–1.15.

    Algorithm:
        1. Skeletonise the vessel mask.
        2. Label connected skeleton components.
        3. For each component compute:
               chord = Euclidean distance between bounding-box corners
               arc   = number of skeleton pixels
               ratio = arc / max(chord, 1)
        4. Average across all segments with arc ≥ min_len.

    Returns: float  (tortuosity index, ≥ 1.0)
    """
    binary = (vessel_mask > 0).astype(bool)

    if _SKIMAGE_OK:
        skeleton = skimage_skeletonize(binary)
        labeled  = sk_label(skeleton, connectivity=2)
        props    = regionprops(labeled)
    else:
        thin = (binary * 255).astype(np.uint8)
        n_lbl, labeled = cv2.connectedComponents((thin > 0).astype(np.uint8))
        class _Prop:
            def __init__(self, coords):
                self.coords = coords
                self.area   = len(coords)
        props = [_Prop(np.argwhere(labeled == i)) for i in range(1, n_lbl)]

    ratios = []
    for prop in props:
        coords = prop.coords
        arc    = len(coords)
        if arc < min_len:
            continue
        r_min, c_min = coords.min(axis=0)
        r_max, c_max = coords.max(axis=0)
        chord = np.hypot(r_max - r_min, c_max - c_min)
        if chord < 1.0:
            chord = 1.0
        ratios.append(arc / chord)

    if not ratios:
        return 1.0
    return round(float(np.mean(ratios)), 4)


# ─────────────────────────────────────────────────────────────────────────────
# Biomarker 4 — Artery-to-Vein Ratio (AVR)
# ─────────────────────────────────────────────────────────────────────────────

def biomarker_avr(artery_mask: np.ndarray,
                  vein_mask: np.ndarray,
                  vessel_mask: np.ndarray) -> float:
    """
    Artery-to-Vein Ratio (AVR) — mean artery width / mean vein width.

    Gold-standard clinical biomarker for systemic hypertension.

    Clinical significance:
        Normal AVR ~ 0.67–0.75.
        AVR < 0.67 → generalised arteriolar narrowing (hypertension).
        AVR > 0.85 → venous dilation (venous occlusion, diabetes).

    Returns: float  (ratio), 0.0 if no veins
    """
    a_map = compute_width_map_local(artery_mask)
    v_map = compute_width_map_local(vein_mask)

    a_px   = a_map[artery_mask > 0]
    v_px   = v_map[vein_mask   > 0]
    mean_a = float(a_px.mean()) if len(a_px) > 0 else 0.0
    mean_v = float(v_px.mean()) if len(v_px) > 0 else 0.0

    if mean_v < 1e-6:
        return 0.0
    return round(mean_a / mean_v, 4)


# ─────────────────────────────────────────────────────────────────────────────
# Biomarker 5 — Mean Artery Width
# ─────────────────────────────────────────────────────────────────────────────

def biomarker_mean_artery_width(artery_mask: np.ndarray) -> float:
    """
    Mean Artery Width (MAW) — average diameter of classified artery pixels.

    Clinical significance:
        Narrowing (↓MAW) → hypertension, arteriosclerosis.
        Typical: 3–6 px at 512×512.

    Returns: float  (pixels)
    """
    wmap = compute_width_map_local(artery_mask)
    a_px = wmap[artery_mask > 0]
    if len(a_px) == 0:
        return 0.0
    return round(float(a_px.mean()), 4)


# ─────────────────────────────────────────────────────────────────────────────
# Biomarker 6 — Mean Vein Width
# ─────────────────────────────────────────────────────────────────────────────

def biomarker_mean_vein_width(vein_mask: np.ndarray) -> float:
    """
    Mean Vein Width (MVnW) — average diameter of classified vein pixels.

    Clinical significance:
        Dilation (↑MVnW) → venous occlusion, diabetes, papilloedema.
        Typical: 5–9 px at 512×512.

    Returns: float  (pixels)
    """
    wmap = compute_width_map_local(vein_mask)
    v_px = wmap[vein_mask > 0]
    if len(v_px) == 0:
        return 0.0
    return round(float(v_px.mean()), 4)


# ─────────────────────────────────────────────────────────────────────────────
# Convenience wrapper
# ─────────────────────────────────────────────────────────────────────────────

def compute_all_biomarkers(vessel_mask: np.ndarray,
                            artery_mask: np.ndarray,
                            vein_mask:   np.ndarray) -> dict:
    """
    Computes all 6 biomarkers and returns a labelled dict.

    Returns:
        dict with keys:
            vessel_density, mean_vessel_width, vessel_tortuosity,
            avr, mean_artery_width, mean_vein_width
    """
    return {
        "vessel_density":    biomarker_vessel_density(vessel_mask),
        "mean_vessel_width": biomarker_mean_vessel_width(vessel_mask),
        "vessel_tortuosity": biomarker_vessel_tortuosity(vessel_mask),
        "avr":               biomarker_avr(artery_mask, vein_mask, vessel_mask),
        "mean_artery_width": biomarker_mean_artery_width(artery_mask),
        "mean_vein_width":   biomarker_mean_vein_width(vein_mask),
    }


# ─────────────────────────────────────────────────────────────────────────────
# AV inference helper (for one image)
# ─────────────────────────────────────────────────────────────────────────────

@torch.no_grad()
def run_av_inference_single(bgr_image: np.ndarray,
                             vessel_mask: np.ndarray,
                             graph,
                             av_model,
                             patch_size: int = 32,
                             batch_size: int = 64) -> dict:
    """
    Classifies each graph edge (vessel segment) as artery (1) or vein (0)
    using a 7-channel patch extracted around the edge midpoint.

    7 channels: RGB (3) + vessel mask (1) + green/CLAHE/Retinex (3)

    Returns:
        edge_labels : dict {(u, v): int}  0=vein, 1=artery
    """
    if graph is None or graph.number_of_edges() == 0:
        return {}

    device = next(av_model.parameters()).device

    rgb   = cv2.cvtColor(bgr_image, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
    mc    = build_multichannel(bgr_image).astype(np.float32) / 255.0
    vmask = (vessel_mask > 0).astype(np.float32)[:, :, None]
    img7  = np.concatenate([rgb, vmask, mc], axis=-1)  # (H, W, 7)

    H, W  = bgr_image.shape[:2]
    half  = patch_size // 2

    edge_keys = []
    patches   = []

    for u, v, attr in graph.edges(data=True):
        path = attr.get("path", [u, v])
        mid  = path[len(path) // 2]
        r, c = int(mid[0]), int(mid[1])

        r0 = max(0, r - half); r1 = min(H, r + half)
        c0 = max(0, c - half); c1 = min(W, c + half)
        patch = img7[r0:r1, c0:c1]

        pad_r = patch_size - patch.shape[0]
        pad_c = patch_size - patch.shape[1]
        if pad_r > 0 or pad_c > 0:
            patch = np.pad(patch, ((0, pad_r), (0, pad_c), (0, 0)), mode="reflect")

        patch = cv2.resize(patch, (patch_size, patch_size),
                           interpolation=cv2.INTER_LINEAR)
        patches.append(patch.transpose(2, 0, 1).astype(np.float32))
        edge_keys.append((u, v))

    all_labels = []
    for i in range(0, len(patches), batch_size):
        batch  = torch.tensor(np.stack(patches[i:i + batch_size])).to(device)
        logits = av_model(batch)
        all_labels.extend(logits.argmax(dim=1).cpu().numpy().tolist())

    return {k: int(l) for k, l in zip(edge_keys, all_labels)}


# ─────────────────────────────────────────────────────────────────────────────
# Overlay renderer
# ─────────────────────────────────────────────────────────────────────────────

def render_av_overlay(original_rgb: np.ndarray,
                      artery_mask: np.ndarray,
                      vein_mask:   np.ndarray) -> np.ndarray:
    """
    Renders arteries (red) and veins (blue) on the original RGB image.
    Returns (H, W, 3) uint8 RGB blended overlay.
    """
    overlay = original_rgb.copy()
    overlay[artery_mask > 0] = [220, 40, 40]
    overlay[vein_mask   > 0] = [40,  80, 220]
    return cv2.addWeighted(original_rgb, 0.45, overlay, 0.55, 0)


# ─────────────────────────────────────────────────────────────────────────────
# Display metadata
# ─────────────────────────────────────────────────────────────────────────────

BIOMARKER_LABELS = {
    "vessel_density":    ("Vessel Density",    "%"),
    "mean_vessel_width": ("Mean Vessel Width", "px"),
    "vessel_tortuosity": ("Tortuosity Index",  "ratio"),
    "avr":               ("Artery/Vein Ratio", "ratio"),
    "mean_artery_width": ("Mean Artery Width", "px"),
    "mean_vein_width":   ("Mean Vein Width",   "px"),
}

NORMAL_RANGES = {
    "vessel_density":    (7.0,  13.0),
    "mean_vessel_width": (2.5,   7.0),
    "vessel_tortuosity": (1.0,   1.15),
    "avr":               (0.67,  0.75),
    "mean_artery_width": (2.0,   6.0),
    "mean_vein_width":   (3.0,   9.0),
}

_MODEL_DISPLAY = {
    "attention_unet":    "Attention U-Net",
    "unetplusplus":      "UNet++",
    "unetplusplus_scse": "UNet++ + SCSE",
}


def _bm_color(key: str, value: float) -> str:
    lo, hi = NORMAL_RANGES.get(key, (None, None))
    if lo is None:
        return "black"
    return "#2ca02c" if lo <= value <= hi else "#d62728"


# ─────────────────────────────────────────────────────────────────────────────
# Visualisation
# ─────────────────────────────────────────────────────────────────────────────

def visualise_results(image_name:   str,
                      model_key:    str,
                      original_rgb: np.ndarray,
                      prob_map:     np.ndarray,
                      vessel_mask:  np.ndarray,
                      artery_mask:  np.ndarray,
                      vein_mask:    np.ndarray,
                      biomarkers:   dict,
                      save_path:    Path = None):
    """
    5-panel figure:
      [0] Original fundus
      [1] Vessel probability map (heatmap)
      [2] Post-processed vessel mask
      [3] A/V overlay (red=artery, blue=vein)
      [4] Biomarker bar chart (green=normal, red=abnormal)
    """
    model_display = _MODEL_DISPLAY.get(model_key, model_key)
    av_overlay    = render_av_overlay(original_rgb, artery_mask, vein_mask)

    fig = plt.figure(figsize=(26, 6))
    fig.suptitle(f"{image_name}  ·  {model_display}",
                 fontsize=14, fontweight="bold", y=1.02)
    gs = gridspec.GridSpec(1, 5, figure=fig, wspace=0.35)

    ax0 = fig.add_subplot(gs[0])
    ax0.imshow(original_rgb); ax0.set_title("Original Fundus", fontsize=10); ax0.axis("off")

    ax1 = fig.add_subplot(gs[1])
    im  = ax1.imshow(prob_map, cmap="hot", vmin=0, vmax=1)
    ax1.set_title("Vessel Probability Map", fontsize=10); ax1.axis("off")
    plt.colorbar(im, ax=ax1, fraction=0.046, pad=0.04, label="P(vessel)")

    ax2  = fig.add_subplot(gs[2])
    pct  = (vessel_mask > 0).mean() * 100
    ax2.imshow(vessel_mask, cmap="gray")
    ax2.set_title(f"Vessel Mask\n({pct:.1f}% coverage)", fontsize=10); ax2.axis("off")

    ax3 = fig.add_subplot(gs[3])
    ax3.imshow(av_overlay)
    ax3.set_title("A/V Classification\n(red=artery · blue=vein)", fontsize=10); ax3.axis("off")
    ax3.text(0.02, 0.02,
             f"Artery: {int((artery_mask>0).sum()):,}px\nVein: {int((vein_mask>0).sum()):,}px",
             transform=ax3.transAxes, fontsize=7, color="white",
             bbox=dict(boxstyle="round,pad=0.2", facecolor="black", alpha=0.5))

    ax4 = fig.add_subplot(gs[4])
    bm_names  = list(BIOMARKER_LABELS.keys())
    bm_vals   = [biomarkers[k] for k in bm_names]
    bm_labels = [f"{BIOMARKER_LABELS[k][0]}\n({BIOMARKER_LABELS[k][1]})" for k in bm_names]
    bm_colors = [_bm_color(k, v) for k, v in zip(bm_names, bm_vals)]
    bars = ax4.barh(range(len(bm_names)), bm_vals, color=bm_colors,
                    height=0.6, edgecolor="white", linewidth=0.5)
    for i, (val, bar) in enumerate(zip(bm_vals, bars)):
        ax4.text(bar.get_width() + max(bm_vals) * 0.01, i,
                 f"{val:.3f}", va="center", ha="left", fontsize=8)
    ax4.set_yticks(range(len(bm_names))); ax4.set_yticklabels(bm_labels, fontsize=8)
    ax4.set_xlabel("Value", fontsize=9)
    ax4.set_title("Biomarkers\n(green=normal · red=abnormal)", fontsize=10)
    ax4.invert_yaxis(); ax4.spines[["top", "right"]].set_visible(False)

    plt.tight_layout()
    if save_path:
        plt.savefig(save_path, dpi=150, bbox_inches="tight")
        print(f"  Figure saved → {save_path}")
    plt.show(); plt.close()


# ─────────────────────────────────────────────────────────────────────────────
# Table printer
# ─────────────────────────────────────────────────────────────────────────────

def print_biomarker_table(results: dict):
    """
    Prints a formatted comparison table.
    results : {image_name: {model_key: biomarker_dict}}
    """
    _short = {
        "vessel_density":    "VD (%)",
        "mean_vessel_width": "MVW (px)",
        "vessel_tortuosity": "Tort.",
        "avr":               "AVR",
        "mean_artery_width": "MAW (px)",
        "mean_vein_width":   "MVnW (px)",
    }
    header_bms = list(BIOMARKER_LABELS.keys())
    col_w      = 12

    print("\n" + "═" * 80)
    print("  RETINAL VASCULAR BIOMARKER SUMMARY")
    print("═" * 80)
    header = f"{'Image':<20} {'Model':<22}"
    for k in header_bms:
        header += f"{_short[k]:>{col_w}}"
    print(header); print("─" * 80)

    for img_name, model_results in results.items():
        for model_key, bms in model_results.items():
            row = f"{img_name:<20} {_MODEL_DISPLAY.get(model_key, model_key):<22}"
            for k in header_bms:
                row += f"{bms[k]:>{col_w}.4f}"
            print(row)
        print()

    print("─" * 80)
    print("  Clinical reference ranges:")
    for k, (lo, hi) in NORMAL_RANGES.items():
        print(f"    {_short[k]:<12}: {lo:.2f} – {hi:.2f}")
    print("═" * 80 + "\n")


# ─────────────────────────────────────────────────────────────────────────────
# Full pipeline
# ─────────────────────────────────────────────────────────────────────────────

def run_biomarker_pipeline(image_paths:    dict,
                            all_seg_models: dict,
                            av_model,
                            model_keys:     list  = None,
                            seg_threshold:  float = 0.5,
                            output_dir:     str   = "outputs/biomarkers") -> dict:
    """
    Full pipeline: segmentation → postprocessing → AV classification → biomarkers.

    Args:
        image_paths    : {name: path} dict of input images
        all_seg_models : {model_key: nn.Module}
        av_model       : trained AVResNet18 in eval mode
        model_keys     : subset of all_seg_models to run (None = all)
        seg_threshold  : vessel binarisation threshold
        output_dir     : directory for saved visualisation figures

    Returns:
        results : {image_name: {model_key: biomarker_dict}}
    """
    from av_segments import merge_segments_by_continuity, compute_width_map
    from av_segments import refine_av_continuity, segments_to_edge_labels

    if model_keys is None:
        model_keys = list(all_seg_models.keys())

    available_keys = [k for k in model_keys if k in all_seg_models]
    if not available_keys:
        raise RuntimeError(
            f"None of the requested models are loaded.\n"
            f"Requested: {model_keys}\nLoaded: {list(all_seg_models.keys())}"
        )

    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n{'═'*60}")
    print(f"  Biomarker Pipeline — {len(image_paths)} images × {len(available_keys)} models")
    print(f"  Models: {available_keys}")
    print(f"{'═'*60}\n")

    all_results = {}

    for img_name, img_path in image_paths.items():
        print(f"\n{'─'*60}")
        print(f"  Image: {img_name}  Path: {img_path}")
        print(f"{'─'*60}")

        bgr = cv2.imread(img_path, cv2.IMREAD_COLOR)
        if bgr is None:
            print(f"  [SKIP] Cannot read image: {img_path}"); continue

        original_rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
        all_results[img_name] = {}

        for model_key in available_keys:
            model = all_seg_models[model_key]
            print(f"\n  ── Model: {_MODEL_DISPLAY.get(model_key, model_key)} ──")

            # ── Step 1: Segmentation ──────────────────────────────────────────
            print("    [1/5] Vessel segmentation...")
            from inference import predict_single
            prob_map = predict_single(model, bgr)

            # ── Step 2: Post-processing ───────────────────────────────────────
            print("    [2/5] Post-processing...")
            vessel_mask = postprocess_mask(prob_map, threshold=seg_threshold,
                                           min_area=30, gap_px=7)
            n_post = int((vessel_mask > 0).sum())
            print(f"          Vessel pixels: {n_post:,}  "
                  f"({n_post/vessel_mask.size*100:.2f}%)")

            # ── Step 3: Skeleton + graph ──────────────────────────────────────
            print("    [3/5] Skeleton + graph...")
            skeleton = skeletonize_mask(vessel_mask)
            graph    = skeleton_to_graph(skeleton)
            H, W     = bgr.shape[:2]

            if graph is None or graph.number_of_edges() == 0:
                print("          [WARNING] Empty graph — AV skipped.")
                artery_mask = np.zeros((H, W), dtype=np.uint8)
                vein_mask   = np.zeros((H, W), dtype=np.uint8)
                all_results[img_name][model_key] = compute_all_biomarkers(
                    vessel_mask, artery_mask, vein_mask)
                continue

            print(f"          Nodes: {graph.number_of_nodes()}  "
                  f"Edges: {graph.number_of_edges()}")

            # ── Step 4: AV classification ─────────────────────────────────────
            print("    [4/5] A/V classification...")
            edge_labels = run_av_inference_single(
                bgr, vessel_mask, graph, av_model)
            n_art  = sum(1 for v in edge_labels.values() if v == 1)
            n_vein = sum(1 for v in edge_labels.values() if v == 0)
            print(f"          Artery segments: {n_art}  Vein segments: {n_vein}")

            # ── Step 5: Pixel masks ───────────────────────────────────────────
            artery_mask, vein_mask = labels_to_masks(
                graph, edge_labels, (H, W), vessel_mask)
            print(f"          Artery px: {int((artery_mask>0).sum()):,}  "
                  f"Vein px: {int((vein_mask>0).sum()):,}")

            # ── Step 6: Biomarker extraction ──────────────────────────────────
            print("    [5/5] Computing biomarkers...")
            bms = compute_all_biomarkers(vessel_mask, artery_mask, vein_mask)
            all_results[img_name][model_key] = bms

            for k, v in bms.items():
                name, unit = BIOMARKER_LABELS[k]
                lo, hi     = NORMAL_RANGES[k]
                flag       = "✓" if lo <= v <= hi else "✗ (abnormal)"
                print(f"          {name:<22}: {v:8.4f} {unit}  {flag}")

            # ── Visualise ─────────────────────────────────────────────────────
            fig_path = out_dir / f"{img_name.replace(' ', '_')}_{model_key}.png"
            visualise_results(img_name, model_key, original_rgb, prob_map,
                              vessel_mask, artery_mask, vein_mask, bms,
                              save_path=fig_path)

    print_biomarker_table(all_results)
    return all_results


print("Biomarker extraction module defined.")
print("  6 biomarkers: VD, MVW, Tortuosity, AVR, MAW, MVnW")
print("  run_biomarker_pipeline(image_paths, seg_models, av_model)")
