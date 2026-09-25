"""
av_segments.py — Vessel segment extraction, merging, patch extraction, and
                 topology-aware continuity propagation refinement.

Provides:
    compute_width_map()              — distance-transform width map
    _segment_orientation()           — dominant angle of a path
    _segment_mean_width()            — mean width along a path
    _angle_diff()                    — smallest angle between two orientations
    merge_segments_by_continuity()   — orientation + width continuity merging
    assign_segment_label()           — majority-vote AV label from GT masks
    extract_segment_patch()          — 7-channel CNN input patch
    build_av_patch_dataset()         — full patch dataset builder
    segments_to_edge_labels()        — segment label list → edge label dict
    refine_av_continuity()           — 3-pass continuity propagation refinement
"""
from __future__ import annotations

import numpy as np
import cv2

from preprocessing import build_multichannel
from postprocessing import (skeletonize_mask, skeleton_to_graph,
                             full_postprocess_pipeline)


# ─────────────────────────────────────────────────────────────────────────────
# Width map
# ─────────────────────────────────────────────────────────────────────────────

def compute_width_map(vessel_mask: np.ndarray) -> np.ndarray:
    """
    Computes vessel width at each pixel via distance transform.

    Distance transform gives the distance from each foreground pixel to the
    nearest background pixel. For a vessel, the value at the centreline equals
    half the vessel diameter.

    Args:
        vessel_mask : (H, W) uint8 {0,255}

    Returns:
        width_map : (H, W) float32 — estimated width in pixels
    """
    binary    = (vessel_mask > 0).astype(np.uint8)
    dist      = cv2.distanceTransform(binary, cv2.DIST_L2, 5)
    width_map = dist * 2.0   # diameter = 2 × radius
    return width_map.astype(np.float32)


# ─────────────────────────────────────────────────────────────────────────────
# Segment geometry helpers
# ─────────────────────────────────────────────────────────────────────────────

def _segment_orientation(path: list) -> float:
    """Dominant orientation (radians, 0 to π) of a segment path (start→end)."""
    if len(path) < 2:
        return 0.0
    p0 = np.array(path[0],  dtype=np.float32)
    p1 = np.array(path[-1], dtype=np.float32)
    d  = p1 - p0
    return float(np.arctan2(abs(d[0]), abs(d[1])))


def _segment_mean_width(path: list, width_map: np.ndarray) -> float:
    """Mean vessel width along segment path pixels."""
    if not path:
        return 0.0
    H, W = width_map.shape
    rows = np.array([p[0] for p in path], dtype=int).clip(0, H - 1)
    cols = np.array([p[1] for p in path], dtype=int).clip(0, W - 1)
    return float(width_map[rows, cols].mean())


def _angle_diff(a1: float, a2: float) -> float:
    """Smallest angle difference between two orientations in [0, π]."""
    diff = abs(a1 - a2)
    return min(diff, np.pi - diff)


# ─────────────────────────────────────────────────────────────────────────────
# Segment merging
# ─────────────────────────────────────────────────────────────────────────────

def merge_segments_by_continuity(graph, width_map: np.ndarray,
                                  angle_thresh_deg: float = 30.0,
                                  width_ratio_thresh: float = 2.0,
                                  min_length: float = 5.0) -> list:
    """
    Merges graph edges that exhibit strong orientation + width continuity.

    At each junction node (degree ≥ 3), pairs of incident edges are evaluated.
    If two edges are nearly collinear (angle < angle_thresh_deg) AND have
    similar widths (ratio < width_ratio_thresh), they are merged into a single
    combined segment.

    This reduces artery→vein identity switching at junctions because the CNN
    classifies a longer, coherent segment instead of two short fragments.

    Args:
        graph              : nx.Graph from skeleton_to_graph()
        width_map          : (H, W) float32 width map
        angle_thresh_deg   : max angle difference to allow merging
        width_ratio_thresh : max width ratio to allow merging
        min_length         : minimum edge length to keep (pixels)

    Returns:
        segments : list of dicts, each with:
            path, length, nodes, mean_width, orientation
    """
    angle_thresh = np.radians(angle_thresh_deg)

    edge_info = {}
    for u, v, attr in graph.edges(data=True):
        path   = attr.get("path", [u, v])
        length = attr.get("length", 1.0)
        if length < min_length:
            continue
        edge_info[(u, v)] = {
            "path":        path,
            "length":      length,
            "orientation": _segment_orientation(path),
            "mean_width":  _segment_mean_width(path, width_map),
        }

    merged_set = set()
    segments   = []

    for node in graph.nodes():
        if graph.degree(node) < 2:
            continue

        incident = []
        for nbr in graph.neighbors(node):
            key = (node, nbr) if (node, nbr) in edge_info else (nbr, node)
            if key in edge_info and key not in merged_set:
                path = edge_info[key]["path"]
                if path[0] != node:
                    path = list(reversed(path))
                incident.append((key, edge_info[key], path))

        for i in range(len(incident)):
            key_i, info_i, path_i = incident[i]
            if key_i in merged_set:
                continue
            for j in range(i + 1, len(incident)):
                key_j, info_j, path_j = incident[j]
                if key_j in merged_set:
                    continue

                if _angle_diff(info_i["orientation"],
                               info_j["orientation"]) > angle_thresh:
                    continue

                w1 = max(info_i["mean_width"], 0.5)
                w2 = max(info_j["mean_width"], 0.5)
                if max(w1, w2) / min(w1, w2) > width_ratio_thresh:
                    continue

                merged_path   = list(reversed(path_i[1:])) + [node] + path_j[1:]
                merged_length = info_i["length"] + info_j["length"]
                start_node    = path_i[-1]
                end_node      = path_j[-1]

                segments.append({
                    "path":        merged_path,
                    "length":      merged_length,
                    "nodes":       (start_node, end_node),
                    "mean_width":  _segment_mean_width(merged_path, width_map),
                    "orientation": _segment_orientation(merged_path),
                })
                merged_set.add(key_i)
                merged_set.add(key_j)
                break

    for key, info in edge_info.items():
        if key not in merged_set:
            segments.append({
                "path":        info["path"],
                "length":      info["length"],
                "nodes":       key,
                "mean_width":  info["mean_width"],
                "orientation": info["orientation"],
            })

    return segments


# ─────────────────────────────────────────────────────────────────────────────
# Label assignment
# ─────────────────────────────────────────────────────────────────────────────

def assign_segment_label(path_pixels: list, artery_mask: np.ndarray,
                          vein_mask: np.ndarray,
                          min_purity: float = 0.6):
    """
    Assigns artery (1) or vein (0) label by majority vote along path pixels.
    Returns None if uncertain (< min_purity majority).
    """
    if not path_pixels:
        return None
    pts  = np.array(path_pixels, dtype=int)
    rows = pts[:, 0].clip(0, artery_mask.shape[0] - 1)
    cols = pts[:, 1].clip(0, artery_mask.shape[1] - 1)

    n_art  = int(artery_mask[rows, cols].sum())
    n_vein = int(vein_mask[rows, cols].sum())
    total  = n_art + n_vein

    if total == 0:
        return None
    if n_art  / total >= min_purity:
        return 1
    elif n_vein / total >= min_purity:
        return 0
    return None


# ─────────────────────────────────────────────────────────────────────────────
# Patch extraction
# ─────────────────────────────────────────────────────────────────────────────

def extract_segment_patch(path_pixels: list, bgr_image: np.ndarray,
                           vessel_mask: np.ndarray, patch_size: int = 32,
                           n_samples: int = 3) -> np.ndarray:
    """
    Extracts a 7-channel CNN input patch for a vessel segment.

    Channels:
        0-2 : RGB
        3   : vessel mask (binary float)
        4   : raw green channel
        5   : CLAHE-enhanced green
        6   : Retinex-corrected green

    Samples n_samples points along the path (at 0%, 50%, 100% etc.) and
    averages to produce one representative patch per segment.

    Args:
        path_pixels : list of (row, col)
        bgr_image   : (H, W, 3) uint8
        vessel_mask : (H, W) uint8 {0,255}
        patch_size  : square patch dimension (default 32)
        n_samples   : number of points along path to sample and average

    Returns:
        (7, patch_size, patch_size) float32, normalised [0, 1]
    """
    if len(path_pixels) < 2:
        return np.zeros((7, patch_size, patch_size), dtype=np.float32)

    H, W  = bgr_image.shape[:2]
    half  = patch_size // 2

    mc        = build_multichannel(bgr_image)
    rgb_image = cv2.cvtColor(bgr_image, cv2.COLOR_BGR2RGB)

    path_arr = np.array(path_pixels)
    indices  = np.linspace(0, len(path_arr) - 1, n_samples, dtype=int)
    patch_sum = np.zeros((7, patch_size, patch_size), dtype=np.float32)

    for idx in indices:
        r, c = int(path_arr[idx, 0]), int(path_arr[idx, 1])

        r1 = max(0, r - half); r2 = r1 + patch_size
        c1 = max(0, c - half); c2 = c1 + patch_size
        if r2 > H: r1 = H - patch_size; r2 = H
        if c2 > W: c1 = W - patch_size; c2 = W
        r1 = max(0, r1); c1 = max(0, c1)

        rgb_crop  = rgb_image[r1:r2, c1:c2]
        mc_crop   = mc[r1:r2, c1:c2]
        mask_crop = vessel_mask[r1:r2, c1:c2]

        if rgb_crop.shape[:2] != (patch_size, patch_size):
            rgb_crop  = cv2.resize(rgb_crop,  (patch_size, patch_size))
            mc_crop   = cv2.resize(mc_crop,   (patch_size, patch_size))
            mask_crop = cv2.resize(mask_crop, (patch_size, patch_size),
                                   interpolation=cv2.INTER_NEAREST)

        patch = np.zeros((7, patch_size, patch_size), dtype=np.float32)
        patch[0] = rgb_crop[:, :, 0] / 255.0
        patch[1] = rgb_crop[:, :, 1] / 255.0
        patch[2] = rgb_crop[:, :, 2] / 255.0
        patch[3] = (mask_crop > 0).astype(np.float32)
        patch[4] = mc_crop[:, :, 0] / 255.0
        patch[5] = mc_crop[:, :, 1] / 255.0
        patch[6] = mc_crop[:, :, 2] / 255.0
        patch_sum += patch

    return patch_sum / len(indices)


# ─────────────────────────────────────────────────────────────────────────────
# Full patch dataset builder
# ─────────────────────────────────────────────────────────────────────────────

def build_av_patch_dataset(av_samples: list, seg_model=None,
                            threshold: float = 0.5,
                            use_gt_vessel: bool = True,
                            patch_size: int = 32,
                            min_purity: float = 0.6,
                            min_length: float = 8.0,
                            angle_thresh_deg: float = 30.0,
                            width_ratio_thresh: float = 2.0):
    """
    Builds a patch-based dataset for CNN AV classifier training.

    For each sample:
      1. Get vessel mask (GT or model inference)
      2. Postprocess → skeleton → graph
      3. Merge segments by continuity
      4. Assign labels from GT artery/vein masks
      5. Extract 7-channel patches

    Returns:
        patches    : (N, 7, patch_size, patch_size) float32
        labels     : (N,) int  0=vein, 1=artery
        sample_ids : list of sample name strings
        meta       : list of segment metadata dicts
    """
    from av_dataset import load_sample_arrays

    all_patches = []; all_labels = []; sample_ids = []; meta_list = []

    for sample in av_samples:
        print(f"\nProcessing: {sample['name']}")
        try:
            bgr, vessel_mask_gt, artery_mask, vein_mask, fov_mask = \
                load_sample_arrays(sample)
        except Exception as e:
            print(f"  [SKIP] Load error: {e}"); continue

        if use_gt_vessel and vessel_mask_gt is not None:
            bin_mask = vessel_mask_gt
        elif seg_model is not None:
            from inference import predict_single
            prob_map = predict_single(seg_model, bgr)
            bin_mask, _, _ = full_postprocess_pipeline(prob_map, threshold=threshold)
        elif vessel_mask_gt is not None:
            bin_mask = vessel_mask_gt
        else:
            print("  [SKIP] No vessel mask available."); continue

        bin_mask = cv2.bitwise_and(bin_mask, fov_mask)

        try:
            skeleton = skeletonize_mask(bin_mask)
            graph    = skeleton_to_graph(skeleton)
        except Exception as e:
            print(f"  [SKIP] Skeleton/graph error: {e}"); continue

        if graph.number_of_edges() == 0:
            print("  [SKIP] Empty graph."); continue

        width_map = compute_width_map(bin_mask)
        segments  = merge_segments_by_continuity(
            graph, width_map,
            angle_thresh_deg   = angle_thresh_deg,
            width_ratio_thresh = width_ratio_thresh,
            min_length         = min_length,
        )

        H, W = bgr.shape[:2]
        if artery_mask.shape != (H, W):
            artery_mask = cv2.resize(artery_mask.astype(np.uint8), (W, H),
                                     interpolation=cv2.INTER_NEAREST).astype(bool)
        if vein_mask.shape != (H, W):
            vein_mask = cv2.resize(vein_mask.astype(np.uint8), (W, H),
                                   interpolation=cv2.INTER_NEAREST).astype(bool)

        n_kept = 0
        for seg in segments:
            path = seg["path"]
            if seg["length"] < min_length:
                continue
            label = assign_segment_label(path, artery_mask, vein_mask, min_purity)
            if label is None:
                continue
            patch = extract_segment_patch(path, bgr, bin_mask, patch_size)
            all_patches.append(patch)
            all_labels.append(label)
            sample_ids.append(sample["name"])
            meta_list.append({
                "name":        sample["name"], "label":       label,
                "length":      seg["length"],  "mean_width":  seg["mean_width"],
                "orientation": seg["orientation"],
                "path_start":  path[0],        "path_end":    path[-1],
            })
            n_kept += 1

        n_art  = sum(1 for m in meta_list[-n_kept:] if m["label"] == 1)
        n_vein = n_kept - n_art
        print(f"  Segments: {n_kept} kept  (artery={n_art}, vein={n_vein})")

    if not all_patches:
        print("[WARNING] No patches extracted. Check dataset paths.")
        return (np.zeros((0, 7, patch_size, patch_size), dtype=np.float32),
                np.zeros(0, dtype=int), [], [])

    patches = np.stack(all_patches, axis=0)
    labels  = np.array(all_labels, dtype=int)
    n_art   = (labels == 1).sum(); n_vein = (labels == 0).sum()
    print(f"\n=== Patch Dataset Summary ===")
    print(f"  Total segments : {len(labels)}")
    print(f"  Arteries       : {n_art}  ({100*n_art/len(labels):.1f}%)")
    print(f"  Veins          : {n_vein}  ({100*n_vein/len(labels):.1f}%)")
    print(f"  Patch shape    : {patches.shape}")

    return patches, labels, sample_ids, meta_list


# ─────────────────────────────────────────────────────────────────────────────
# segments_to_edge_labels
# ─────────────────────────────────────────────────────────────────────────────

def segments_to_edge_labels(graph, segments: list, seg_labels: list) -> dict:
    """
    Maps segment-level labels back to graph edge keys.

    For merged segments that span multiple edges, the label is applied to the
    closest matching graph edge via path endpoint lookup.

    Returns:
        edge_labels : dict {(u, v): int}  0=vein, 1=artery, -1=unknown
    """
    edge_labels = {}

    for seg, lbl in zip(segments, seg_labels):
        nodes = seg.get("nodes", ())
        path  = seg.get("path", [])

        if len(nodes) == 2:
            u, v = nodes
            if graph.has_edge(u, v):
                edge_labels[(u, v)] = lbl; continue
            if graph.has_edge(v, u):
                edge_labels[(v, u)] = lbl; continue

        if len(path) >= 2:
            p_start = tuple(path[0]); p_end = tuple(path[-1])
            for u, v, attr in graph.edges(data=True):
                ep = attr.get("path", [])
                if len(ep) >= 2:
                    if ((tuple(ep[0]) == p_start and tuple(ep[-1]) == p_end) or
                        (tuple(ep[0]) == p_end   and tuple(ep[-1]) == p_start)):
                        edge_labels[(u, v)] = lbl; break

    for u, v in graph.edges():
        if (u, v) not in edge_labels and (v, u) not in edge_labels:
            edge_labels[(u, v)] = -1

    n_art     = sum(1 for l in edge_labels.values() if l == 1)
    n_vein    = sum(1 for l in edge_labels.values() if l == 0)
    n_unknown = sum(1 for l in edge_labels.values() if l == -1)
    print(f"  Edge label coverage: artery={n_art}  vein={n_vein}  "
          f"unknown={n_unknown}  total={len(edge_labels)}")
    return edge_labels


# ─────────────────────────────────────────────────────────────────────────────
# Three-pass continuity propagation refinement
# ─────────────────────────────────────────────────────────────────────────────

def _pass1_neighbour_consistency(graph, edge_labels: dict,
                                  min_agreement: float = 0.75,
                                  max_iters: int = 5) -> dict:
    labels = dict(edge_labels)
    for _ in range(max_iters):
        n_changed = 0
        for node in graph.nodes():
            if graph.degree(node) < 3:
                continue
            incident = []
            for nbr in graph.neighbors(node):
                key = (node, nbr) if (node, nbr) in labels else (nbr, node)
                if key in labels:
                    incident.append(key)
            if len(incident) < 2:
                continue
            lbl_vals = [labels[k] for k in incident]
            n_art    = sum(1 for l in lbl_vals if l == 1)
            n_total  = len(lbl_vals)
            n_vein   = n_total - n_art
            if n_art  / n_total >= min_agreement:
                for k in incident:
                    if labels[k] == 0: labels[k] = 1; n_changed += 1
            elif n_vein / n_total >= min_agreement:
                for k in incident:
                    if labels[k] == 1: labels[k] = 0; n_changed += 1
        if n_changed == 0:
            break
    return labels


def _pass2_path_majority_voting(graph, edge_labels: dict,
                                 min_path_agreement: float = 0.70) -> dict:
    labels    = dict(edge_labels)
    endpoints = [n for n in graph.nodes() if graph.degree(n) == 1]
    MAX_DEPTH = 50

    def trace_path(start):
        path_edges = []; visited = {start}; current = start
        for _ in range(MAX_DEPTH):
            nbrs = [n for n in graph.neighbors(current) if n not in visited]
            if not nbrs: break
            if len(nbrs) > 1 and graph.degree(current) > 2: break
            nxt = nbrs[0]
            key = (current, nxt) if (current, nxt) in labels else (nxt, current)
            if key in labels: path_edges.append(key)
            visited.add(nxt); current = nxt
            if graph.degree(current) != 2: break
        return path_edges

    for ep in endpoints:
        path_edges = trace_path(ep)
        if len(path_edges) < 3: continue
        lbl_vals = [labels[k] for k in path_edges]
        n_art    = sum(1 for l in lbl_vals if l == 1)
        n_total  = len(lbl_vals)
        if n_art  / n_total >= min_path_agreement:
            for k in path_edges: labels[k] = 1
        elif (n_total - n_art) / n_total >= min_path_agreement:
            for k in path_edges: labels[k] = 0

    return labels


def _pass3_isolated_correction(graph, edge_labels: dict,
                                 min_isolation_agreement: float = 0.80) -> dict:
    labels = dict(edge_labels)

    def neighbourhood_labels(node, exclude_key):
        nbr_lbls = []
        for nbr in graph.neighbors(node):
            key = (node, nbr) if (node, nbr) in labels else (nbr, node)
            if key in labels and key != exclude_key:
                nbr_lbls.append(labels[key])
        return nbr_lbls

    changed = True
    while changed:
        changed = False
        for key in list(labels.keys()):
            u, v = key; lbl = labels[key]
            all_nbr = neighbourhood_labels(u, key) + neighbourhood_labels(v, key)
            if len(all_nbr) < 2: continue
            n_opposite = sum(1 for l in all_nbr if l != lbl)
            if n_opposite / len(all_nbr) >= min_isolation_agreement:
                labels[key] = 1 - lbl; changed = True

    return labels


def refine_av_continuity(graph, edge_labels: dict,
                          pass1_agreement: float = 0.75,
                          pass2_agreement: float = 0.70,
                          pass3_agreement: float = 0.80,
                          verbose: bool = True) -> dict:
    """
    Full three-pass continuity propagation refinement.

    Pass 1 — Junction-level neighbour consistency (iterative until convergence)
    Pass 2 — Path-level majority voting (endpoint-to-endpoint tracing)
    Pass 3 — Isolated conflicting segment correction

    Args:
        graph            : nx.Graph from skeleton_to_graph()
        edge_labels      : dict {(u,v): int}  0=vein, 1=artery  (CNN output)
        pass1_agreement  : threshold for Pass 1 (default 0.75)
        pass2_agreement  : threshold for Pass 2 (default 0.70)
        pass3_agreement  : threshold for Pass 3 (default 0.80)
        verbose          : print statistics

    Returns:
        refined_labels : dict {(u,v): int}
    """
    original = dict(edge_labels)
    n_total  = len(edge_labels)

    labels = _pass1_neighbour_consistency(graph, edge_labels, pass1_agreement)
    n_p1   = sum(1 for k in labels if labels[k] != original.get(k, labels[k]))

    labels = _pass2_path_majority_voting(graph, labels, pass2_agreement)
    n_p2   = sum(1 for k in labels if labels[k] != original.get(k, labels[k]))

    labels = _pass3_isolated_correction(graph, labels, pass3_agreement)
    n_p3   = sum(1 for k in labels if labels[k] != original.get(k, labels[k]))

    if verbose:
        print(f"[Continuity Refinement]")
        print(f"  Pass 1 (junction consistency) : {n_p1} labels changed")
        print(f"  Pass 2 (path majority voting) : {n_p2 - n_p1} additional changes")
        print(f"  Pass 3 (isolated correction)  : {n_p3 - n_p2} additional changes")
        print(f"  Total changed : {n_p3} / {n_total} "
              f"({100*n_p3/max(n_total,1):.1f}%)")
        n_art  = sum(1 for l in labels.values() if l == 1)
        n_vein = len(labels) - n_art
        print(f"  Final: {n_art} artery, {n_vein} vein segments")

    return labels


print("Segment extraction + continuity refinement utilities defined.")
print("  merge_segments_by_continuity() — orientation + width merging")
print("  extract_segment_patch()        — 7-channel CNN patches")
print("  build_av_patch_dataset()       — full dataset builder")
print("  refine_av_continuity()         — 3-pass topology refinement")
