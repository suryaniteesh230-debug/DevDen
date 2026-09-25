"""
av_visualisation.py — AV mask generation and visualisation (9 pipeline outputs).

Provides:
    labels_to_masks()              — edge labels → pixel artery/vein masks
    plot_all_seg_outputs()         — output 1: all 3 models + ensemble prob maps
    plot_refined_masks()           — output 2: post-processed masks
    plot_skeleton()                — output 3: skeleton overlay
    plot_graph()                   — output 4: graph coloured by AV label
    plot_vessel_segments()         — output 5: merged segment colours
    plot_av_masks()                — output 6+7: binary artery/vein masks
    plot_av_overlay()              — output 8: final A/V overlay
    plot_continuity_refinement()   — output 9: before/after continuity pass
    evaluate_av_masks()            — pixel-level AV metrics vs GT
    generate_all_outputs()         — all 9 outputs in one call
"""
from __future__ import annotations

from pathlib import Path

import cv2
import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import numpy as np


# ─────────────────────────────────────────────────────────────────────────────
# Segment labels → pixel masks
# ─────────────────────────────────────────────────────────────────────────────

def labels_to_masks(graph, edge_labels: dict,
                    image_shape: tuple,
                    vessel_mask: np.ndarray):
    """
    Converts per-edge artery/vein labels into pixel-space binary masks.

    Args:
        graph        : nx.Graph
        edge_labels  : dict {(u,v): label}  0=vein, 1=artery, -1=unknown
        image_shape  : (H, W)
        vessel_mask  : (H, W) uint8 {0, 255}

    Returns:
        artery_mask : (H, W) uint8 {0, 255}
        vein_mask   : (H, W) uint8 {0, 255}
    """
    H, W        = image_shape
    artery_mask = np.zeros((H, W), dtype=np.uint8)
    vein_mask   = np.zeros((H, W), dtype=np.uint8)

    for u, v, attr in graph.edges(data=True):
        key   = (u, v) if (u, v) in edge_labels else (v, u)
        label = edge_labels.get(key, -1)
        if label not in (0, 1):
            continue
        path = attr.get("path", [u, v])
        for (r, c) in path:
            r = int(r); c = int(c)
            if 0 <= r < H and 0 <= c < W:
                if label == 1:
                    artery_mask[r, c] = 255
                else:
                    vein_mask[r, c]   = 255

    kernel      = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    artery_mask = cv2.dilate(artery_mask, kernel, iterations=1)
    vein_mask   = cv2.dilate(vein_mask,   kernel, iterations=1)
    artery_mask = cv2.bitwise_and(artery_mask, vessel_mask)
    vein_mask   = cv2.bitwise_and(vein_mask,   vessel_mask)

    return artery_mask, vein_mask


# ─────────────────────────────────────────────────────────────────────────────
# Output 1 — All three models + ensemble
# ─────────────────────────────────────────────────────────────────────────────

def plot_all_seg_outputs(original_rgb: np.ndarray, seg_results: dict,
                          save_path: str = "output_1_all_seg_models.png"):
    """
    Probability maps and binary masks from all 3 models + ensemble.

    seg_results: {model_key: (prob_map, binary_mask)}
    """
    model_keys  = ["attention_unet", "unetplusplus", "unetplusplus_scse", "ensemble"]
    model_names = {
        "attention_unet":    "Attention U-Net",
        "unetplusplus":      "UNet++",
        "unetplusplus_scse": "UNet++ + SCSE",
        "ensemble":          "Ensemble (avg)",
    }
    available = [k for k in model_keys if k in seg_results]
    n_cols    = len(available) + 1

    fig, axes = plt.subplots(2, n_cols, figsize=(4.5 * n_cols, 9))
    axes[0, 0].imshow(original_rgb)
    axes[0, 0].set_title("Original Fundus", fontsize=11, fontweight="bold")
    axes[0, 0].axis("off"); axes[1, 0].axis("off")

    for col, key in enumerate(available, start=1):
        prob_map, binary_mask = seg_results[key]
        label = model_names.get(key, key)
        im = axes[0, col].imshow(prob_map, cmap="hot", vmin=0, vmax=1)
        axes[0, col].set_title(f"{label}\nProb Map", fontsize=10); axes[0, col].axis("off")
        plt.colorbar(im, ax=axes[0, col], fraction=0.046, pad=0.04)
        pct = (binary_mask > 0).mean() * 100
        axes[1, col].imshow(binary_mask, cmap="gray")
        axes[1, col].set_title(f"{label}\nBinary ({pct:.1f}% vessel)", fontsize=10)
        axes[1, col].axis("off")

    plt.suptitle("Output 1 — Segmentation: All 3 Models + Ensemble",
                 fontsize=13, fontweight="bold", y=1.01)
    plt.tight_layout()
    plt.savefig(save_path, dpi=150, bbox_inches="tight"); plt.show()
    print(f"Saved → {save_path}")


# ─────────────────────────────────────────────────────────────────────────────
# Output 2 — Refined masks
# ─────────────────────────────────────────────────────────────────────────────

def plot_refined_masks(original_rgb: np.ndarray, refined_results: dict,
                        save_path: str = "output_2_refined_masks.png"):
    """Post-processed binary vessel masks from each model."""
    available = list(refined_results.keys()); n_cols = len(available) + 1
    fig, axes = plt.subplots(1, n_cols, figsize=(4.5 * n_cols, 5))
    axes[0].imshow(original_rgb); axes[0].set_title("Original", fontsize=11); axes[0].axis("off")
    model_names = {"attention_unet": "Attention U-Net", "unetplusplus": "UNet++",
                   "unetplusplus_scse": "UNet++ + SCSE", "ensemble": "Ensemble"}
    for col, key in enumerate(available, start=1):
        mask = refined_results[key]; pct = (mask > 0).mean() * 100
        axes[col].imshow(mask, cmap="gray")
        axes[col].set_title(f"{model_names.get(key, key)}\nRefined ({pct:.1f}%)", fontsize=10)
        axes[col].axis("off")
    plt.suptitle("Output 2 — Refined Vessel Masks (Post-Processed)",
                 fontsize=13, fontweight="bold", y=1.02)
    plt.tight_layout(); plt.savefig(save_path, dpi=150, bbox_inches="tight"); plt.show()
    print(f"Saved → {save_path}")


# ─────────────────────────────────────────────────────────────────────────────
# Output 3 — Skeleton
# ─────────────────────────────────────────────────────────────────────────────

def plot_skeleton(original_rgb: np.ndarray, skeleton: np.ndarray,
                  save_path: str = "output_3_skeleton.png"):
    """1-pixel-wide vessel centreline skeleton."""
    fig, axes = plt.subplots(1, 2, figsize=(14, 6))
    axes[0].imshow(original_rgb); axes[0].set_title("Original"); axes[0].axis("off")
    axes[1].imshow(original_rgb, alpha=0.35)
    axes[1].imshow(skeleton, cmap="Greens", alpha=0.8)
    axes[1].set_title(f"Output 3 — Skeleton\n{int(skeleton.sum()):,} skeleton pixels",
                      fontweight="bold"); axes[1].axis("off")
    plt.tight_layout()
    plt.savefig(save_path, dpi=150, bbox_inches="tight"); plt.show()
    print(f"Saved → {save_path}")


# ─────────────────────────────────────────────────────────────────────────────
# Output 4 — Graph
# ─────────────────────────────────────────────────────────────────────────────

def plot_graph(original_rgb: np.ndarray, skeleton: np.ndarray, graph,
               edge_labels: dict = None, max_edges: int = 3000,
               save_path: str = "output_4_graph.png"):
    """Vessel graph overlay (red=artery, blue=vein, gray=unknown)."""
    fig, ax = plt.subplots(1, 1, figsize=(10, 10))
    ax.imshow(original_rgb, alpha=0.4); ax.imshow(skeleton, cmap="gray", alpha=0.3)

    for i, (u, v, attr) in enumerate(graph.edges(data=True)):
        if i > max_edges: break
        path = attr.get("path", [u, v])
        if edge_labels is not None:
            key   = (u, v) if (u, v) in edge_labels else (v, u)
            label = edge_labels.get(key, -1)
            color = "#FF4444" if label == 1 else "#4488FF" if label == 0 else "#888888"
        else:
            color = "cyan"
        ax.plot([p[1] for p in path], [p[0] for p in path],
                "-", color=color, linewidth=0.8, alpha=0.8)

    for (r, c), attr in list(graph.nodes(data=True))[:2000]:
        ntype = attr.get("node_type", "endpoint")
        color = "yellow" if ntype == "junction" else "lime"
        size  = 4 if ntype == "junction" else 2
        ax.plot(c, r, "o", color=color, markersize=size, zorder=5)

    j = sum(1 for _, a in graph.nodes(data=True) if a.get("node_type") == "junction")
    e = graph.number_of_nodes() - j
    handles = [
        mpatches.Patch(color="#FF4444", label="Artery"),
        mpatches.Patch(color="#4488FF", label="Vein"),
        mpatches.Patch(color="#888888", label="Unknown"),
        mpatches.Patch(color="yellow",  label=f"Junctions ({j})"),
        mpatches.Patch(color="lime",    label=f"Endpoints ({e})"),
    ]
    ax.legend(handles=handles, loc="lower right", fontsize=9,
              facecolor="black", labelcolor="white")
    ax.set_title(f"Output 4 — Graph  N={graph.number_of_nodes()}  "
                 f"E={graph.number_of_edges()}", fontweight="bold"); ax.axis("off")
    plt.tight_layout()
    plt.savefig(save_path, dpi=150, bbox_inches="tight"); plt.show()
    print(f"Saved → {save_path}")


# ─────────────────────────────────────────────────────────────────────────────
# Output 5 — Vessel segments
# ─────────────────────────────────────────────────────────────────────────────

def plot_vessel_segments(original_rgb: np.ndarray, segments: list,
                          seg_labels: list,
                          save_path: str = "output_5_segments.png"):
    """Each merged vessel segment coloured by AV label."""
    vis = original_rgb.copy().astype(np.float32)
    H, W = vis.shape[:2]
    for seg, lbl in zip(segments, seg_labels):
        path  = seg.get("path", [])
        color = (255, 80, 80) if lbl == 1 else (80, 80, 255)
        for (r, c) in path:
            r, c = int(r), int(c)
            if 0 <= r < H and 0 <= c < W:
                vis[r, c] = color
    vis = vis.astype(np.uint8)
    n_art  = sum(1 for l in seg_labels if l == 1)
    n_vein = len(seg_labels) - n_art

    fig, axes = plt.subplots(1, 2, figsize=(16, 7))
    axes[0].imshow(original_rgb); axes[0].set_title("Original"); axes[0].axis("off")
    axes[1].imshow(vis)
    axes[1].set_title(f"Output 5 — Merged Vessel Segments\n"
                      f"Artery={n_art}  Vein={n_vein}", fontweight="bold"); axes[1].axis("off")
    handles = [mpatches.Patch(color=(1,0.3,0.3), label="Artery segments"),
               mpatches.Patch(color=(0.3,0.3,1), label="Vein segments")]
    axes[1].legend(handles=handles, loc="lower right")
    plt.tight_layout()
    plt.savefig(save_path, dpi=150, bbox_inches="tight"); plt.show()
    print(f"Saved → {save_path}")


# ─────────────────────────────────────────────────────────────────────────────
# Output 6+7 — Artery/vein masks
# ─────────────────────────────────────────────────────────────────────────────

def plot_av_masks(artery_mask: np.ndarray, vein_mask: np.ndarray,
                  save_path: str = "output_6_7_av_masks.png"):
    """Binary artery mask (output 6) and vein mask (output 7)."""
    fig, axes = plt.subplots(1, 2, figsize=(14, 6))
    axes[0].imshow(artery_mask, cmap="gray")
    axes[0].set_title(f"Output 6 — Artery Mask\n{int((artery_mask>0).sum()):,} px",
                      fontweight="bold"); axes[0].axis("off")
    axes[1].imshow(vein_mask, cmap="gray")
    axes[1].set_title(f"Output 7 — Vein Mask\n{int((vein_mask>0).sum()):,} px",
                      fontweight="bold"); axes[1].axis("off")
    plt.tight_layout()
    plt.savefig(save_path, dpi=150, bbox_inches="tight"); plt.show()
    print(f"Saved → {save_path}")


# ─────────────────────────────────────────────────────────────────────────────
# Output 8 — A/V overlay
# ─────────────────────────────────────────────────────────────────────────────

def plot_av_overlay(original_rgb: np.ndarray,
                    artery_mask: np.ndarray, vein_mask: np.ndarray,
                    model_label: str = "",
                    save_path: str = "output_8_av_overlay.png"):
    """Arteries in red, veins in blue, overlaid on original fundus."""
    overlay   = original_rgb.copy().astype(np.float32)
    art_bool  = artery_mask > 0; vein_bool = vein_mask > 0
    overlay[art_bool,  0] = np.clip(overlay[art_bool,  0] * 0.3 + 255 * 0.7, 0, 255)
    overlay[art_bool,  1] = np.clip(overlay[art_bool,  1] * 0.3,             0, 255)
    overlay[art_bool,  2] = np.clip(overlay[art_bool,  2] * 0.3,             0, 255)
    overlay[vein_bool, 0] = np.clip(overlay[vein_bool, 0] * 0.3,             0, 255)
    overlay[vein_bool, 1] = np.clip(overlay[vein_bool, 1] * 0.3,             0, 255)
    overlay[vein_bool, 2] = np.clip(overlay[vein_bool, 2] * 0.3 + 255 * 0.7, 0, 255)
    overlay = overlay.astype(np.uint8)

    fig, axes = plt.subplots(1, 2, figsize=(16, 7))
    axes[0].imshow(original_rgb); axes[0].set_title("Original"); axes[0].axis("off")
    axes[1].imshow(overlay)
    axes[1].legend(handles=[mpatches.Patch(color=(1,.2,.2), label="Arteries"),
                             mpatches.Patch(color=(.2,.2,1), label="Veins")],
                   loc="lower right", fontsize=11)
    title_suffix = f" [{model_label}]" if model_label else ""
    axes[1].set_title(f"Output 8 — A/V Overlay{title_suffix}\n"
                      f"Artery: {art_bool.sum():,} px   Vein: {vein_bool.sum():,} px",
                      fontweight="bold"); axes[1].axis("off")
    plt.suptitle("Retinal Artery-Vein Classification  |  CNN Pipeline",
                 fontsize=14, fontweight="bold", y=1.01)
    plt.tight_layout()
    plt.savefig(save_path, dpi=150, bbox_inches="tight"); plt.show()
    print(f"Saved → {save_path}")


# ─────────────────────────────────────────────────────────────────────────────
# Output 9 — Continuity refinement before/after
# ─────────────────────────────────────────────────────────────────────────────

def plot_continuity_refinement(original_rgb: np.ndarray, graph,
                                vessel_mask: np.ndarray,
                                labels_before: dict, labels_after: dict,
                                image_shape: tuple,
                                save_path: str = "output_9_continuity_refinement.png"):
    """Before/after comparison of A/V labelling after continuity propagation."""
    artery_before, vein_before = labels_to_masks(graph, labels_before, image_shape, vessel_mask)
    artery_after,  vein_after  = labels_to_masks(graph, labels_after,  image_shape, vessel_mask)

    def _overlay(rgb, artery, vein):
        ov = rgb.copy().astype(np.float32)
        ab = artery > 0; vb = vein > 0
        ov[ab, 0] = np.clip(ov[ab, 0] * 0.3 + 255 * 0.7, 0, 255)
        ov[ab, 1] = np.clip(ov[ab, 1] * 0.3, 0, 255)
        ov[ab, 2] = np.clip(ov[ab, 2] * 0.3, 0, 255)
        ov[vb, 0] = np.clip(ov[vb, 0] * 0.3, 0, 255)
        ov[vb, 1] = np.clip(ov[vb, 1] * 0.3, 0, 255)
        ov[vb, 2] = np.clip(ov[vb, 2] * 0.3 + 255 * 0.7, 0, 255)
        return ov.astype(np.uint8)

    ov_before = _overlay(original_rgb, artery_before, vein_before)
    ov_after  = _overlay(original_rgb, artery_after,  vein_after)
    n_changed = sum(1 for k in labels_after
                    if labels_after[k] != labels_before.get(k, labels_after[k]))

    fig, axes = plt.subplots(1, 3, figsize=(21, 7))
    axes[0].imshow(original_rgb); axes[0].set_title("Original"); axes[0].axis("off")
    axes[1].imshow(ov_before)
    axes[1].set_title("CNN Output\n(before refinement)", fontweight="bold"); axes[1].axis("off")
    axes[2].imshow(ov_after)
    axes[2].set_title(f"After Continuity Refinement\n({n_changed} labels changed)",
                      fontweight="bold"); axes[2].axis("off")
    handles = [mpatches.Patch(color=(1,.2,.2), label="Arteries"),
               mpatches.Patch(color=(.2,.2,1), label="Veins")]
    for ax in axes[1:]:
        ax.legend(handles=handles, loc="lower right", fontsize=9)
    plt.suptitle("Output 9 — Continuity Propagation Refinement", fontsize=14,
                 fontweight="bold", y=1.01)
    plt.tight_layout()
    plt.savefig(save_path, dpi=150, bbox_inches="tight"); plt.show()
    print(f"Saved → {save_path}")


# ─────────────────────────────────────────────────────────────────────────────
# Quantitative evaluation
# ─────────────────────────────────────────────────────────────────────────────

def evaluate_av_masks(pred_artery: np.ndarray, pred_vein: np.ndarray,
                      gt_artery: np.ndarray,   gt_vein: np.ndarray) -> dict:
    """Pixel-level AV classification metrics vs ground truth."""
    def dice(p, g):
        inter = (p & g).sum(); union = p.sum() + g.sum()
        return float(2 * inter / union) if union > 0 else 0.0

    pa = pred_artery > 0; pv = pred_vein > 0
    metrics = {
        "artery_dice":  dice(pa, gt_artery),
        "vein_dice":    dice(pv, gt_vein),
        "artery_pxacc": float((pa == gt_artery).mean()),
        "vein_pxacc":   float((pv == gt_vein).mean()),
        "mean_dice":   (dice(pa, gt_artery) + dice(pv, gt_vein)) / 2,
    }
    print("=== AV Evaluation (pixel-level) ===")
    for k, v in metrics.items():
        print(f"  {k:20s}: {v:.4f}")
    return metrics


# ─────────────────────────────────────────────────────────────────────────────
# Generate all 9 outputs in one call
# ─────────────────────────────────────────────────────────────────────────────

def generate_all_outputs(original_rgb, seg_results, refined_results,
                          skeleton, graph, segments, seg_labels_cnn,
                          edge_labels_before, edge_labels_after,
                          artery_mask, vein_mask, vessel_mask,
                          model_label: str = "Ensemble",
                          output_dir:  str = "av_pipeline_outputs"):
    """
    Generate and save all 9 required pipeline outputs.

    Args:
        seg_results        : {model_key: (prob_map, binary)}
        refined_results    : {model_key: refined_mask}
        segments           : list of segment dicts
        seg_labels_cnn     : list of int (CNN raw predictions)
        edge_labels_before : {(u,v): int}  CNN output
        edge_labels_after  : {(u,v): int}  after continuity refinement
        artery_mask        : (H,W) uint8  final artery mask
        vein_mask          : (H,W) uint8  final vein mask
        vessel_mask        : (H,W) uint8  refined vessel mask
    """
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    H, W = original_rgb.shape[:2]
    print("\nGenerating all 9 pipeline outputs...")

    plot_all_seg_outputs(original_rgb, seg_results,
                         str(out / "output_1_all_seg_models.png"))
    plot_refined_masks(original_rgb, refined_results,
                       str(out / "output_2_refined_masks.png"))
    plot_skeleton(original_rgb, skeleton, str(out / "output_3_skeleton.png"))
    plot_graph(original_rgb, skeleton, graph, edge_labels_after,
               save_path=str(out / "output_4_graph.png"))
    plot_vessel_segments(original_rgb, segments, seg_labels_cnn,
                         str(out / "output_5_segments.png"))
    plot_av_masks(artery_mask, vein_mask, str(out / "output_6_7_av_masks.png"))
    plot_av_overlay(original_rgb, artery_mask, vein_mask, model_label=model_label,
                    save_path=str(out / "output_8_av_overlay.png"))
    plot_continuity_refinement(original_rgb, graph, vessel_mask,
                               edge_labels_before, edge_labels_after, (H, W),
                               save_path=str(out / "output_9_continuity_refinement.png"))

    print(f"\nAll 9 outputs saved to: {out.resolve()}")
    for i, desc in enumerate([
        "output_1_all_seg_models.png       — all 3 models + ensemble prob maps",
        "output_2_refined_masks.png         — post-processed binary masks",
        "output_3_skeleton.png              — vessel skeleton",
        "output_4_graph.png                 — vessel graph (A/V colored)",
        "output_5_segments.png              — merged vessel segments",
        "output_6_7_av_masks.png            — binary artery + vein masks",
        "output_8_av_overlay.png            — final A/V overlay on fundus",
        "output_9_continuity_refinement.png — before/after refinement",
    ], start=1):
        print(f"  {desc}")


print("AV visualisation utilities defined (9 pipeline outputs).")
